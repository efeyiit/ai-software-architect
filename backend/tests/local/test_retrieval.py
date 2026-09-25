import pytest

from app.local.importer import UploadedSource, import_files
from app.local.retrieval import LocalRetrieval
from app.local.store import LocalStore


class Vectors:
    model_id = "test-only"
    dimension = 2
    execution_location = "local"
    def embed_documents(self, texts):
        return [[1., 0.] for _ in texts]
    def embed_query(self, text):
        return [1., 0.]


def test_persistent_search_is_scoped_by_repository_and_snapshot(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    old = import_files("one", [UploadedSource(path="main.py", content="old source")])
    new = import_files("one", [UploadedSource(path="main.py", content="new source")], repository_id=old.repository_id)
    other = import_files("two", [UploadedSource(path="secret.py", content="other repository")])
    for source in (old, new, other):
        store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / "vectors", store, Vectors())
    for source in (old, new, other):
        index.index_snapshot(source.repository_id, source.snapshot_id)
    index.close()
    reopened = LocalRetrieval(tmp_path / "vectors", store, Vectors())
    try:
        hits = reopened.search(new.repository_id, new.snapshot_id, "source")
        assert [hit["text"] for hit in hits] == ["new source"]
        assert reopened.search(old.repository_id, old.snapshot_id, "source")[0]["text"] == "old source"
        with pytest.raises(KeyError):
            reopened.search("missing", new.snapshot_id, "source")
        with pytest.raises(Exception):
            LocalRetrieval(tmp_path / "vectors", store, Vectors())
    finally:
        reopened.close()


def test_model_absence_never_fabricates_answer(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    source = import_files("one", [UploadedSource(path="main.py", content="print('hello')")])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / "vectors", store, Vectors())
    try:
        assert index.ask(source.repository_id, source.snapshot_id, "Explain this file")["status"] == "unavailable"
    finally:
        index.close()


@pytest.mark.parametrize("quote,expected", [("return 'hello'", "answered"), ("invented quote", "rejected")])
def test_citations_must_match_exact_source(tmp_path, quote, expected):
    class Answers:
        execution_location = "local"
        def answer(self, prompt):
            return {"claims": [{"text": "The function returns hello.", "citations": [{"evidence_id": prompt.evidence[0].id,
                "start_line": 2, "end_line": 2, "quote": quote}]}]}
    store = LocalStore(tmp_path / "data.sqlite3")
    source = import_files("one", [UploadedSource(path="main.py", content="def greet():\n    return 'hello'")])
    store.save_snapshot(source)
    index = LocalRetrieval(tmp_path / "vectors", store, Vectors(), Answers())
    try:
        assert index.ask(source.repository_id, source.snapshot_id, "What does greet return?")["status"] == expected
    finally:
        index.close()
