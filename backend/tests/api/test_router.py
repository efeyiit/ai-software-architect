from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.router import create_api_router
from app.main import app as production_app


class RecordingRuntime:
    def __init__(self):
        self.calls = []

    def repository(self, owner, repository_id):
        self.calls.append((owner, repository_id))
        return {"id": repository_id, "owner": owner}


def test_repository_route_uses_trusted_session_dependency() -> None:
    runtime = RecordingRuntime()
    app = FastAPI()

    def verified_session():
        return "trusted-owner"

    app.include_router(create_api_router(verified_session, runtime))
    response = TestClient(app).get("/api/repositories/repo-1")
    assert response.status_code == 200
    assert runtime.calls == [("trusted-owner", "repo-1")]


def test_missing_session_denies_before_any_runtime_access() -> None:
    runtime = RecordingRuntime()
    app = FastAPI()

    def no_session():
        raise HTTPException(status_code=401, detail="authentication_required")

    app.include_router(create_api_router(no_session, runtime))
    response = TestClient(app).get("/api/repositories/repo-1")
    assert response.status_code == 401
    assert runtime.calls == []


def test_production_routes_fail_closed_without_identity_config(monkeypatch) -> None:
    monkeypatch.delenv("ARIADNE_DATABASE_URL", raising=False)
    with TestClient(production_app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/repositories/repo-1", headers={"X-User-ID": "forged"}).status_code == 503
        assert client.get("/auth/me").status_code == 503
