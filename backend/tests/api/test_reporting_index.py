from types import SimpleNamespace

from app.api.router import ChatInput
from app.rag.indexing import AuthorizedScope
from app.services.github_public.service import RepositoryFile, RepositorySnapshot
from app.services.github_private.service import PrivateRepositorySnapshot
from app.services.reporting import ApiRuntime
from app.services.reporting.service import ReportingMaterial
from app.services.reporting import service as reporting


SHA = "a" * 40


def test_worker_index_handoff_preserves_source_id_and_separate_documents(monkeypatch):
    snapshot = RepositorySnapshot(
        "local-repository-id", "https://github.com/a/r", "r", "main", SHA,
        "b" * 40, (
            RepositoryFile("src/a.py", "c" * 40, 1, "Python", True, None),
            RepositoryFile("README.md", "d" * 40, 1, None, False, "unsupported_type"),
        ), (("Python", 1),), ())
    index_calls = []

    class Index:
        def index_snapshot(self, *args, **kwargs):
            index_calls.append((args, kwargs))
            return 2

    runtime = ApiRuntime("unused", SimpleNamespace(oauth=None), rag_index=Index())
    monkeypatch.setattr(runtime, "load_material", lambda *args: ReportingMaterial(
        snapshot, {"src/a.py": "x"}, {"README.md": "y"}, {}))
    monkeypatch.setattr(runtime, "_scope", lambda owner, repo: AuthorizedScope(
        owner, repo, "github-source-id", SHA, False))
    monkeypatch.setattr(runtime, "_authorized_snapshot", lambda owner, repo: (snapshot, None))

    assert runtime._index_material("owner", "local-repository-id", SHA) == 2
    args, kwargs = index_calls[0]
    assert args[0:2] == ("owner", "local-repository-id")
    assert args[2].repository_id == "github-source-id"
    assert args[3] == {"src/a.py": "x"}
    assert kwargs == {"document_texts": {"README.md": "y"},
                      "private_document_snapshot": None}


def test_chat_request_limit_matches_local_answer_contract():
    from pydantic import ValidationError
    for question in ("   ", "x" * 1001):
        try:
            ChatInput(question=question)
        except ValidationError:
            pass
        else:
            raise AssertionError("invalid chat question accepted")


def test_private_document_reader_and_index_keep_owner_bound_wrapper(monkeypatch):
    files = (
        RepositoryFile("src/a.py", "c" * 40, 1, "Python", True, None),
        RepositoryFile("README.md", "d" * 40, 1, None, False, "unsupported_type"),
    )
    local = RepositorySnapshot("local-id", "https://github.com/a/r", "r", "main",
                               SHA, "b" * 40, files, (("Python", 1),), ())
    source = RepositorySnapshot("github-id", local.github_url, local.name,
                                local.default_branch, SHA, local.tree_sha, files,
                                local.languages, local.frameworks)
    wrapper = PrivateRepositorySnapshot("owner", source)
    calls = []

    class PrivateReader:
        def fetch_file(self, owner, selected, file):
            assert owner == "owner" and selected is wrapper and file.path == "src/a.py"
            return "x"

        def document_files(self, owner, selected):
            assert owner == "owner" and selected is wrapper
            return (files[1],)

        def fetch_document_file(self, owner, selected, file):
            assert owner == "owner" and selected is wrapper and file.path == "README.md"
            return "y"

    class Index:
        def index_snapshot(self, *args, **kwargs):
            calls.append((args, kwargs))
            return 2

    runtime = ApiRuntime("unused", SimpleNamespace(oauth=None), private=PrivateReader(),
                         rag_index=Index())
    monkeypatch.setattr(runtime, "_authorized_snapshot", lambda *args: (local, wrapper))
    monkeypatch.setattr(runtime, "_scope", lambda owner, repo: AuthorizedScope(
        owner, repo, "github-id", SHA, True))
    material = runtime.load_material("owner", "local-id", SHA)
    assert material.document_sources == {"README.md": "y"}
    assert material.private_document_snapshot is wrapper
    assert runtime._index_material("owner", "local-id", SHA) == 2
    args, kwargs = calls[0]
    assert args[2].repository_id == "github-id"
    assert kwargs["document_texts"] == {"README.md": "y"}
    assert kwargs["private_document_snapshot"].local_user_id == "owner"
    assert kwargs["private_document_snapshot"].repository == args[2]


def test_redacted_env_template_is_not_sent_to_blob_verified_index(monkeypatch):
    files = (
        RepositoryFile("src/a.py", "c" * 40, 1, "Python", True, None),
        RepositoryFile("README.md", "d" * 40, 1, None, False, "unsupported_type"),
        RepositoryFile(".env.example", "e" * 40, 9, None, False, "unsupported_type"),
    )
    snapshot = RepositorySnapshot("local-id", "https://github.com/a/r", "r", "main",
                                  SHA, "b" * 40, files, (("Python", 1),), ())
    read_paths = []

    class PublicReader:
        def fetch_file(self, selected, file):
            return "x"

        def document_files(self, selected):
            return (files[1], files[2])

        def fetch_document_file(self, selected, file):
            read_paths.append(file.path)
            return "y"

    runtime = ApiRuntime("unused", SimpleNamespace(oauth=None), public=PublicReader())
    monkeypatch.setattr(runtime, "_authorized_snapshot", lambda *args: (snapshot, None))
    material = runtime.load_material("owner", "local-id", SHA)
    assert material.document_sources == {"README.md": "y"}
    assert read_paths == ["README.md"]


def test_production_rag_requires_qdrant_key_and_passes_it_to_client(monkeypatch):
    class Database:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, *args):
            return self

        def fetchone(self):
            return ("repositories", "analysis_jobs", "analysis_cache")

    calls = []
    monkeypatch.setattr(reporting.psycopg, "connect", lambda *args, **kwargs: Database())
    monkeypatch.setattr(reporting, "QdrantClient", lambda *args, **kwargs:
                        calls.append(kwargs) or object())
    monkeypatch.setenv("ARIADNE_DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("ARIADNE_QDRANT_URL", "http://127.0.0.1:6333")
    monkeypatch.setenv("ARIADNE_LOCAL_RUNTIME_TOKEN", "model-secret")
    monkeypatch.delenv("ARIADNE_QDRANT_API_KEY", raising=False)
    from pytest import raises
    with raises(ValueError, match="Qdrant key"):
        ApiRuntime.from_env(SimpleNamespace(oauth=None))
    monkeypatch.setenv("ARIADNE_QDRANT_API_KEY", "qdrant-secret")
    runtime = ApiRuntime.from_env(SimpleNamespace(oauth=None))
    assert calls == [{"url": "http://127.0.0.1:6333", "api_key": "qdrant-secret",
                      "timeout": 30}]
    assert runtime.chat_service is not None
