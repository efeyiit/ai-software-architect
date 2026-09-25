"""Private document reads stay owner bound and match pinned Git blobs."""

import base64
from hashlib import sha1

import pytest
from qdrant_client import QdrantClient

from app.rag.indexing import AuthorizedScope, IndexingError, QdrantIndex
from app.services.github_private import GitHubPrivateService
from app.services.github_public import GitHubPublicError


COMMIT = "a" * 40
TREE = "b" * 40


def blob_sha(content: str) -> str:
    data = content.encode()
    return sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class Identity:
    def __init__(self):
        self.denied = False
        self.calls = []

    def valid_token(self, user_id, purpose):
        self.calls.append((user_id, purpose))
        if self.denied:
            raise GitHubPublicError("ACCESS_DENIED", "Permission revoked")
        return "fixture-token"


class API:
    def __init__(self):
        self.commit = COMMIT
        self.repo_id = 123
        self.denied = False
        self.tampered = False
        self.calls = []
        self.documents = {
            "README.md": "Private project overview\n",
            "docs/setup.md": "Setup steps\n",
            ".env.example": "API_KEY=secret-value\nPORT=8080\n",
            ".env": "REAL_SECRET=never-fetch\n",
            "secret/notes.md": "never-fetch\n",
        }
        self.sources = {"src/main.py": "print('ok')\n"}
        self.blobs = {blob_sha(content): content.encode()
                      for content in (list(self.documents.values()) + list(self.sources.values()))}

    def get_json(self, path, max_bytes):
        self.calls.append(path)
        if self.denied:
            raise GitHubPublicError("ACCESS_DENIED", "Permission revoked")
        if path == "/repos/owner/private-repo":
            return {"id": self.repo_id, "full_name": "owner/private-repo",
                    "name": "private-repo", "private": True, "default_branch": "main"}
        if path == "/repos/owner/private-repo/commits/main":
            return {"sha": self.commit, "commit": {"tree": {"sha": TREE}}}
        if path == f"/repos/owner/private-repo/git/trees/{TREE}?recursive=1":
            return {"truncated": False, "tree": [
                {"type": "blob", "path": path, "sha": blob_sha(content), "size": len(content.encode())}
                for path, content in (self.sources | self.documents).items()]}
        prefix = "/repos/owner/private-repo/git/blobs/"
        if path.startswith(prefix):
            sha = path.removeprefix(prefix)
            content = self.blobs[sha]
            if self.tampered:
                content = b"x" * len(content)
            return {"sha": sha, "encoding": "base64", "content": base64.b64encode(content).decode()}
        raise AssertionError(path)


@pytest.fixture
def reader():
    identity = Identity()
    api = API()
    service = GitHubPrivateService(identity, lambda token: api)
    snapshot = service.fetch_repository("alice", "https://github.com/owner/private-repo")
    return service, identity, api, snapshot


def test_private_document_allowlist_and_redacted_env(reader):
    service, identity, api, snapshot = reader
    files = service.document_files("alice", snapshot)
    assert [file.path for file in files] == ["README.md", "docs/setup.md", ".env.example"]
    texts = {file.path: service.fetch_document_file("alice", snapshot, file) for file in files}
    assert texts == {"README.md": "Private project overview\n",
                     "docs/setup.md": "Setup steps\n", ".env.example": "API_KEY=\nPORT="}
    assert identity.calls[-1] == ("alice", "private")
    assert api.calls[-1].startswith("/repos/owner/private-repo/git/blobs/")


def test_private_document_owner_and_disallowed_path_fail_before_blob_request(reader):
    service, identity, api, snapshot = reader
    before = len(api.calls)
    with pytest.raises(GitHubPublicError, match="authorized"):
        service.document_files("bob", snapshot)
    assert len(api.calls) == before
    denied = next(file for file in snapshot.repository.files if file.path == ".env")
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file("alice", snapshot, denied)
    assert error.value.code == "INVALID_REQUEST"
    assert not any("/git/blobs/" in path for path in api.calls)


@pytest.mark.parametrize("change", ["denied", "moved", "replaced"])
def test_private_document_live_permission_source_and_sha_checks(reader, change):
    service, identity, api, snapshot = reader
    file = service.document_files("alice", snapshot)[0]
    if change == "denied":
        api.denied = True
    elif change == "moved":
        api.commit = "c" * 40
    else:
        api.repo_id = 999
    before = len(api.calls)
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file("alice", snapshot, file)
    assert error.value.code == "ACCESS_DENIED"
    assert not any("/git/blobs/" in path for path in api.calls[before:])


def test_private_document_rejects_false_blob_content_hash(reader):
    service, _, api, snapshot = reader
    file = service.document_files("alice", snapshot)[0]
    api.tampered = True
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file("alice", snapshot, file)
    assert error.value.code == "INVALID_GITHUB_RESPONSE"


def test_private_reader_documents_reach_index_only_with_live_scope_and_wrapper(reader):
    service, identity, api, wrapper = reader
    sources = {file.path: service.fetch_file("alice", wrapper, file)
               for file in wrapper.repository.included_files}
    documents = {file.path: service.fetch_document_file("alice", wrapper, file)
                 for file in service.document_files("alice", wrapper)
                 if not file.path.lower().rsplit("/", 1)[-1].startswith(".env.")}

    def resolve(owner, repository_id):
        if (owner != "alice" or repository_id != "local-repository" or identity.denied
                or api.denied or api.repo_id != 123):
            return None
        return AuthorizedScope(owner, repository_id, "123", api.commit, True)

    class Vectors:
        model_id = "private-doc-fixture"
        dimension = 3
        execution_location = "local"

        def embed_documents(self, texts):
            return [[1.0, 0.0, 0.0] for _ in texts]

        def embed_query(self, text):
            return [1.0, 0.0, 0.0]

    index = QdrantIndex(QdrantClient(":memory:"), resolve, Vectors())
    with pytest.raises(IndexingError, match="authorized snapshot"):
        index.index_snapshot("alice", "local-repository", wrapper.repository, sources,
                             document_texts=documents)
    assert index.index_snapshot("alice", "local-repository", wrapper.repository, sources,
                                document_texts=documents,
                                private_document_snapshot=wrapper) == 3
    assert {hit.chunk.kind for hit in index.search("alice", "local-repository", "project")} == {
        "code", "document"}
    identity.denied = True
    with pytest.raises(IndexingError, match="denied"):
        index.search("alice", "local-repository", "project")
