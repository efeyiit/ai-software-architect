"""T04 live scope adapter against the T20 Qdrant consumer contract."""

from hashlib import sha1
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.rag.indexing import IndexingError, QdrantIndex
from app.security.identity import IdentityError
from app.services.github_private.scope import LiveRepositoryScopeResolver, ScopeResolutionError
from app.services.github_public import GitHubPublicError
from app.services.github_public.service import RepositoryFile, RepositorySnapshot


ALICE = str(uuid4())
BOB = str(uuid4())
LOCAL_REPO = str(uuid4())
SHA = "a" * 40
NEXT_SHA = "b" * 40


class FakeStore:
    def __init__(self):
        self.rows = {(ALICE, LOCAL_REPO): {
            "id": LOCAL_REPO, "user_id": ALICE,
            "github_url": "https://github.com/owner/secret"}}
        self.calls = []

    def get_repository(self, caller, repo):
        self.calls.append((caller, repo))
        return self.rows.get((caller, repo))


class FakeIdentity:
    def __init__(self):
        self.denied = False
        self.calls = []

    def valid_token(self, caller, purpose):
        self.calls.append((caller, purpose))
        if self.denied:
            raise IdentityError("GITHUB_ACCESS_DENIED", "GitHub denied the credential")
        return "fixture-token"


class FakeAPI:
    def __init__(self, private):
        self.private = private
        self.sha = SHA
        self.denied = False
        self.unavailable = False
        self.calls = []

    def get_json(self, path, max_bytes):
        self.calls.append(path)
        if self.unavailable:
            raise GitHubPublicError("GITHUB_UNAVAILABLE", "GitHub could not be reached", retryable=True)
        if self.denied:
            raise GitHubPublicError("ACCESS_DENIED", "GitHub denied access")
        if not self.private:
            raise GitHubPublicError("REPOSITORY_NOT_FOUND", "Not public")
        if path == "/repos/owner/secret":
            return {"id": 42, "full_name": "owner/secret", "private": True,
                    "default_branch": "main"}
        if path == "/repos/owner/secret/commits/main":
            return {"sha": self.sha}
        raise AssertionError(path)


class Vectors:
    model_id = "fixture-only"
    dimension = 3
    execution_location = "local"

    def embed_documents(self, texts):
        return [[1.0, 1.0, 1.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 1.0, 1.0]


@pytest.fixture
def setup():
    store = FakeStore()
    identity = FakeIdentity()
    public = FakeAPI(False)
    private = FakeAPI(True)
    resolver = LiveRepositoryScopeResolver(store, identity, public, lambda token: private)
    return resolver, store, identity, public, private


def snapshot(sha=SHA, github_id="42"):
    source = "private alpha\n"
    content = source.encode()
    blob_sha = sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    file = RepositoryFile("main.py", blob_sha, len(content), "Python", True, None)
    return RepositorySnapshot(github_id, "https://github.com/owner/secret", "secret",
                              "main", sha, "c" * 40, (file,), (), ()), {"main.py": source}


def test_owner_gate_precedes_network_and_scope_uses_remote_sha(setup):
    resolver, store, identity, public, private = setup
    assert resolver(BOB, LOCAL_REPO) is None
    assert resolver(ALICE, str(uuid4())) is None
    assert resolver("not-a-session-uuid", LOCAL_REPO) is None
    assert not public.calls and not private.calls and not identity.calls
    scope = resolver(ALICE, LOCAL_REPO)
    assert (scope.owner_id, scope.repository_id, scope.source_repository_id,
            scope.commit_sha, scope.private) == (ALICE, LOCAL_REPO, "42", SHA, True)
    assert private.calls == ["/repos/owner/secret", "/repos/owner/secret/commits/main"]
    assert identity.calls == [(ALICE, "private")]


def test_revoked_permission_remote_errors_and_stale_sha_fail_closed(setup):
    resolver, _, identity, public, private = setup
    client = QdrantClient(":memory:")
    index = QdrantIndex(client, resolver, Vectors())
    repo, texts = snapshot()
    assert index.index_snapshot(ALICE, LOCAL_REPO, repo, texts) == 1
    assert len(index.search(ALICE, LOCAL_REPO, "alpha")) == 1
    private.sha = NEXT_SHA
    assert index.search(ALICE, LOCAL_REPO, "alpha") == ()
    with pytest.raises(IndexingError, match="current"):
        index.index_snapshot(ALICE, LOCAL_REPO, repo, texts)
    private.sha = SHA
    identity.denied = True
    with pytest.raises(IndexingError, match="denied"):
        index.search(ALICE, LOCAL_REPO, "alpha")
    identity.denied = False
    private.denied = True
    with pytest.raises(IndexingError, match="denied"):
        index.search(ALICE, LOCAL_REPO, "alpha")
    private.denied = False
    public.unavailable = True
    with pytest.raises(ScopeResolutionError) as error:
        index.search(ALICE, LOCAL_REPO, "alpha")
    assert error.value.code == "GITHUB_UNAVAILABLE"
    assert error.value.retryable


def test_source_repository_id_is_live_not_claimed_by_snapshot(setup):
    resolver, _, _, _, _ = setup
    index = QdrantIndex(QdrantClient(":memory:"), resolver, Vectors())
    wrong_source, texts = snapshot(github_id="99")
    with pytest.raises(IndexingError, match="snapshot"):
        index.index_snapshot(ALICE, LOCAL_REPO, wrong_source, texts)


def test_public_repo_path_does_not_require_private_token(setup):
    resolver, store, identity, public, private = setup
    store.rows[ALICE, LOCAL_REPO]["github_url"] = "https://github.com/owner/secret"
    def public_json(path, max_bytes):
        public.calls.append(path)
        if path == "/repos/owner/secret":
            return {"id": 42, "full_name": "owner/secret", "private": False,
                    "default_branch": "main"}
        if path == "/repos/owner/secret/commits/main":
            return {"sha": SHA}
        raise AssertionError(path)
    public.get_json = public_json
    scope = resolver(ALICE, LOCAL_REPO)
    assert scope.private is False
    assert identity.calls == []
    assert private.calls == []


def test_stale_database_transaction_is_rejected(setup):
    _, store, identity, public, private = setup
    store.connection = SimpleNamespace(autocommit=False)
    with pytest.raises(ScopeResolutionError) as error:
        LiveRepositoryScopeResolver(store, identity, public, lambda token: private)
    assert error.value.code == "CONFIGURATION_ERROR"


def test_database_failure_never_reuses_cached_scope(setup):
    resolver, store, _, _, _ = setup
    def broken(caller, repo):
        raise RuntimeError("database internals")
    store.get_repository = broken
    with pytest.raises(ScopeResolutionError) as error:
        resolver(ALICE, LOCAL_REPO)
    assert error.value.code == "STORE_UNAVAILABLE"
    assert "database internals" not in str(error.value)
