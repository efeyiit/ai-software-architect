"""HTTP flow against a disposable PostgreSQL schema and inert GitHub fixtures."""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.api.router import create_api_router
from app.main import app as production_app
from app.cache import apply_cache_schema
from app.database import Store, apply_schema
from app.jobs import apply_jobs_schema
from app.rag.indexing import AuthorizedScope
from app.rag.indexing import QdrantIndex
from app.rag.chat import ChatProviderAnswer, ProviderCitation, ProviderClaim, RepositoryChat
from app.security.identity import PostgresIdentityStore, apply_identity_schema
from app.security.identity.http import IdentityHTTP, SESSION_COOKIE, require_session_user
from app.services.github_public.service import RepositoryFile, RepositorySnapshot
from app.services.reporting import ApiRuntime


SHA = "a" * 40
SOURCE = "def hello():\n    return 1\n"
BLOB = hashlib.sha1(b"blob " + str(len(SOURCE.encode())).encode() + b"\0" + SOURCE.encode()).hexdigest()


class PublicFixture:
    def __init__(self):
        self.commit_sha = SHA

    def fetch_repository(self, url):
        return RepositorySnapshot("42", url, "r", "main", self.commit_sha, "b" * 40,
                                  (RepositoryFile("src/a.py", BLOB, len(SOURCE), "Python", True, None),),
                                  (("Python", 1),), ())

    def fetch_file(self, snapshot, file):
        return SOURCE

    def document_files(self, snapshot):
        return ()


class LocalVectors:
    model_id = "t25-test-vectors-only"
    dimension = 3
    execution_location = "local"

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [1.0, 1.0, 1.0]


class ControlledAnswer:
    execution_location = "local"

    def answer(self, prompt):
        return ChatProviderAnswer(claims=[ProviderClaim(text="hello returns 1", citations=[
            ProviderCitation(evidence_id="E1", start_line=1, end_line=1, quote="def hello():")])])


@pytest.fixture
def http_db():
    dsn = os.getenv("ARIADNE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set ARIADNE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "t25_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            connection = psycopg.connect(dsn, autocommit=True)
            connection.execute("SELECT set_config('search_path', %s, false)", (schema,))
            apply_schema(connection)
            apply_identity_schema(connection)
            apply_jobs_schema(connection)
            apply_cache_schema(connection)
            alice = Store(connection).create_user("alice@fixture", "x")
            bob = Store(connection).create_user("bob@fixture", "x")
            raw = "fixture-cookie-" + uuid4().hex
            identity_store = PostgresIdentityStore(connection)
            identity_store.replace_session(alice, hashlib.sha256(raw.encode()).digest(),
                                           datetime.now(timezone.utc) + timedelta(hours=1))
            bob_raw = "fixture-cookie-" + uuid4().hex
            identity_store.replace_session(bob, hashlib.sha256(bob_raw.encode()).digest(),
                                           datetime.now(timezone.utc) + timedelta(hours=1))
            identity = IdentityHTTP(SimpleNamespace(config=SimpleNamespace(
                redirect_uri="https://app.example/auth/github/callback")), identity_store,
                connection=connection)
            public = PublicFixture()
            permission = {"allowed": True}

            def scope(owner, repository_id):
                with psycopg.connect(dsn, autocommit=True) as check:
                    check.execute("SELECT set_config('search_path', %s, false)", (schema,))
                    row = Store(check).get_repository(owner, repository_id)
                if row is None or not permission["allowed"]:
                    return None
                return AuthorizedScope(owner, repository_id, "42", public.commit_sha, False)

            runtime = ApiRuntime(dsn, identity, public=public, search_path=schema,
                                 scope_resolver=scope)
            app = FastAPI()
            app.state.identity_http = identity
            app.include_router(create_api_router(require_session_user, runtime))
            client = TestClient(app, base_url="https://app.example")
            client.cookies.set(SESSION_COOKIE, raw)
            bob_client = TestClient(app, base_url="https://app.example")
            bob_client.cookies.set(SESSION_COOKIE, bob_raw)
            csrf = hashlib.sha256(("ariadne-csrf:" + raw).encode()).hexdigest()
            yield client, bob_client, runtime, permission, public, csrf
            connection.close()
        finally:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_http_enqueue_worker_result_owner_revocation_and_sha(http_db):
    client, bob_client, runtime, permission, public, csrf = http_db
    headers = {"X-Ariadne-CSRF": csrf}
    assert client.post("/api/repositories", json={"github_url": "https://github.com/a/r"}).status_code == 403
    created = client.post("/api/repositories", json={"github_url": "https://github.com/a/r"},
                          headers=headers)
    assert created.status_code == 201
    repo = created.json()["id"]
    assert client.get("/api/repositories").json() == [{
        "id": repo, "github_url": "https://github.com/a/r", "name": "r", "commit_sha": SHA}]
    assert bob_client.get("/api/repositories").json() == []
    assert client.get(f"/api/repositories/{repo}").status_code == 200
    listed = client.get(f"/api/repositories/{repo}/files")
    assert listed.status_code == 200
    assert listed.json() == {"snapshot": {"repository_id": repo, "commit_sha": SHA},
                             "files": [{"path": "src/a.py", "language": "Python", "included": True,
                                        "size": len(SOURCE), "exclusion_reason": None}]}
    summary = client.get(f"/api/repositories/{repo}/files/summary", params={"path": "src/a.py"})
    assert summary.status_code == 200
    assert summary.json()["snapshot"] == {"repository_id": repo, "commit_sha": SHA}
    assert summary.json()["ai_status"] == "unavailable"
    assert summary.json()["path"] == "src/a.py"
    assert any("hello" in fact["text"] for fact in summary.json()["structural_facts"])
    assert SOURCE not in str(summary.json())
    assert client.get(f"/api/repositories/{repo}/files/summary", params={"path": "../secret.py"}).status_code == 422
    queued = client.post(f"/api/repositories/{repo}/analyze", headers=headers)
    assert queued.status_code == 202
    job_id = queued.json()["job_id"]
    assert client.get(f"/api/repositories/{repo}/jobs/{job_id}").json()["status"] == "queued"
    runtime.worker().process_one()
    job = client.get(f"/api/repositories/{repo}/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    result = client.get(f"/api/repositories/{repo}/analyses/{job_id}")
    assert result.status_code == 200
    assert result.json()["schema_version"] == 2
    assert len(result.json()["roles"]) == 5
    assert result.json()["dependencies"] is not None
    assert client.get(f"/api/repositories/{repo}/issues").status_code == 200
    assert client.get(f"/api/repositories/{repo}/dependencies").json()["graph"] is not None
    diagrams = client.get(f"/api/repositories/{repo}/diagrams")
    assert diagrams.status_code == 200
    assert diagrams.json()["snapshot"] == {"repository_id": repo, "commit_sha": SHA}
    assert set(diagrams.json()["diagrams"]) == {"mermaid", "plantuml"}
    assert "classDiagram" in diagrams.json()["diagrams"]["mermaid"]["class_diagram"]
    reused = client.post(f"/api/repositories/{repo}/analyze", headers=headers).json()
    assert reused == {"status": "cached", "analysis_id": job_id, "commit_sha": SHA}
    assert client.post(f"/api/repositories/{repo}/chat", json={"question": "Hello?"},
                       headers=headers).json()["status"] == "unavailable"
    assert bob_client.get(f"/api/repositories/{repo}").status_code == 404
    assert bob_client.get(f"/api/repositories/{repo}/files").status_code == 404
    assert bob_client.get(f"/api/repositories/{repo}/files/summary",
                          params={"path": "src/a.py"}).status_code == 404
    assert bob_client.get(f"/api/repositories/{repo}/jobs/{job_id}").status_code == 404
    assert bob_client.get(f"/api/repositories/{repo}/analyses/{job_id}").status_code == 404
    assert bob_client.get(f"/api/repositories/{repo}/diagrams").status_code == 404
    permission["allowed"] = False
    assert client.get("/api/repositories").json() == []
    assert client.get(f"/api/repositories/{repo}/analyses/{job_id}").status_code == 404
    assert client.get(f"/api/repositories/{repo}/files").status_code == 404
    assert client.get(f"/api/repositories/{repo}/diagrams").status_code == 404
    permission["allowed"] = True
    public.commit_sha = "c" * 40
    assert client.get(f"/api/repositories/{repo}/analyses/{job_id}").status_code == 409


def test_file_summary_rejects_tampered_blob(http_db):
    client, _, runtime, _, public, csrf = http_db
    repo = client.post("/api/repositories", json={"github_url": "https://github.com/a/r"},
                       headers={"X-Ariadne-CSRF": csrf}).json()["id"]
    public.fetch_file = lambda *args: "different source"
    response = client.get(f"/api/repositories/{repo}/files/summary", params={"path": "src/a.py"})
    assert response.status_code == 409
    assert response.json()["detail"] == "snapshot_changed"


def test_diagram_route_rejects_tampered_blob(http_db):
    client, _, runtime, _, public, csrf = http_db
    headers = {"X-Ariadne-CSRF": csrf}
    repo = client.post("/api/repositories", json={"github_url": "https://github.com/a/r"},
                       headers=headers).json()["id"]
    client.post(f"/api/repositories/{repo}/analyze", headers=headers)
    runtime.worker().process_one()
    public.fetch_file = lambda *args: "different source"
    response = client.get(f"/api/repositories/{repo}/diagrams")
    assert response.status_code == 409
    assert response.json()["detail"] == "snapshot_changed"


def test_http_partial_report_is_terminal_and_keeps_typed_data(http_db, monkeypatch):
    client, _, runtime, _, _, csrf = http_db
    from app.ai.orchestration import coordinator as coordination

    def failed_documentation(*args):
        raise RuntimeError("fixture role failure")

    monkeypatch.setattr(coordination, "generate_documentation", failed_documentation)
    headers = {"X-Ariadne-CSRF": csrf}
    repo = client.post("/api/repositories", json={"github_url": "https://github.com/a/r"},
                       headers=headers).json()["id"]
    job_id = client.post(f"/api/repositories/{repo}/analyze", headers=headers).json()["job_id"]
    runtime.worker().process_one()
    job = client.get(f"/api/repositories/{repo}/jobs/{job_id}").json()
    assert job["status"] == "partial"
    result = client.get(f"/api/repositories/{repo}/analyses/{job_id}").json()
    assert result["status"] == "partial" and result["partial"] is True
    assert result["dependencies"] is not None
    assert result["documentation"] is None
    assert client.get(f"/api/repositories/{repo}/diagrams").json()["status"] == "partial"
    assert any(role["role"] == "documentation" and role["status"] == "failed"
               for role in result["roles"])
    assert client.post(f"/api/repositories/{repo}/analyze", headers=headers).json()["status"] == "queued"


def test_http_cancel_and_worker_error_do_not_claim_success(http_db):
    client, _, runtime, _, public, csrf = http_db
    headers = {"X-Ariadne-CSRF": csrf}
    repo = client.post("/api/repositories", json={"github_url": "https://github.com/a/r"},
                       headers=headers).json()["id"]
    first = client.post(f"/api/repositories/{repo}/analyze", headers=headers).json()["job_id"]
    cancelled = client.post(f"/api/repositories/{repo}/jobs/{first}/cancel", headers=headers)
    assert cancelled.json()["status"] == "cancelled"
    assert client.get(f"/api/repositories/{repo}/analyses/{first}").status_code == 404

    second = client.post(f"/api/repositories/{repo}/analyze", headers=headers).json()["job_id"]
    public.fetch_file = lambda *args: "tampered bytes"
    runtime.worker().process_one()
    state = client.get(f"/api/repositories/{repo}/jobs/{second}").json()
    assert state["status"] == "failed"
    assert state["error_code"] == "INVALID_SNAPSHOT"
    assert client.get(f"/api/repositories/{repo}/analyses/{second}").status_code == 404


def test_http_chat_uses_local_qdrant_and_rechecks_revocation(http_db):
    client, _, runtime, permission, public, csrf = http_db
    headers = {"X-Ariadne-CSRF": csrf}
    repo = client.post("/api/repositories", json={"github_url": "https://github.com/a/r"},
                       headers=headers).json()["id"]
    index = QdrantIndex(QdrantClient(":memory:"), runtime.scope_resolver, LocalVectors())
    owner = client.app.state.identity_http.store.load_session(
        hashlib.sha256(client.cookies.get(SESSION_COOKIE).encode()).digest())
    index.index_snapshot(owner, repo, public.fetch_repository("https://github.com/a/r"),
                         {"src/a.py": SOURCE})
    runtime.chat_service = RepositoryChat(index, ControlledAnswer())
    response = client.post(f"/api/repositories/{repo}/chat", json={"question": "What does hello do?"},
                           headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["claims"][0]["citations"][0]["commit_sha"] == SHA
    permission["allowed"] = False
    assert client.post(f"/api/repositories/{repo}/chat", json={"question": "hello?"},
                       headers=headers).status_code == 404


def test_production_main_mounts_real_session_and_api_with_pg(http_db, monkeypatch):
    _, _, runtime, _, _, _ = http_db
    monkeypatch.setenv("ARIADNE_DATABASE_URL",
                       runtime.dsn + "?options=-csearch_path%3D" + runtime.search_path)
    monkeypatch.setenv("ARIADNE_GITHUB_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("ARIADNE_GITHUB_CLIENT_SECRET", "fixture-secret")
    monkeypatch.setenv("ARIADNE_GITHUB_REDIRECT_URI", "https://app.example/auth/github/callback")
    monkeypatch.setenv("ARIADNE_OAUTH_FERNET_KEYS", Fernet.generate_key().decode())
    with TestClient(production_app, base_url="https://app.example") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/auth/me").status_code == 401
        assert client.get("/api/repositories/" + str(uuid4())).status_code == 401
