from fastapi.testclient import TestClient

from app.local.main import create_local_app


def test_local_session_import_source_and_restart(tmp_path):
    with TestClient(create_local_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/local/repositories").status_code == 401
        session = client.get("/api/local/session")
        assert session.status_code == 200
        headers = {"X-CSRF-Token": session.json()["csrf_token"]}
        payload = {"name": "Example", "files": [{"path": "main.py", "content": "print('hello')"}]}
        assert client.post("/api/local/import", json=payload).status_code == 403
        imported = client.post("/api/local/import", json=payload, headers=headers)
        assert imported.status_code == 200, imported.text
        source = imported.json()
        params = {"repository_id": source["repository_id"], "snapshot_id": source["snapshot_id"], "path": "main.py"}
        assert client.get("/api/local/source", params=params).json()["content"] == "print('hello')"
        assert client.get("/api/local/source", params=params | {"path": "../secret"}).status_code == 404
    with TestClient(create_local_app(tmp_path), base_url="http://127.0.0.1") as client:
        client.get("/api/local/session")
        assert len(client.get("/api/local/repositories").json()) == 1


def test_host_origin_and_fetch_metadata_are_enforced(tmp_path):
    with TestClient(create_local_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/local/session", headers={"Host": "evil.example"}).status_code == 403
        assert client.get("/api/local/session", headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.get("/api/local/session", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.get("/api/local/session", headers={"Origin": "http://127.0.0.1"}).status_code == 200


def test_body_limit_before_parsing(tmp_path):
    with TestClient(create_local_app(tmp_path, max_body_bytes=64), base_url="http://127.0.0.1") as client:
        token = client.get("/api/local/session").json()["csrf_token"]
        result = client.post("/api/local/import", content=b"x" * 65, headers={"X-CSRF-Token": token})
        assert result.status_code == 413


def test_second_instance_cannot_interrupt_first(tmp_path):
    import pytest
    with TestClient(create_local_app(tmp_path), base_url="http://127.0.0.1") as first:
        with pytest.raises(OSError):
            with TestClient(create_local_app(tmp_path), base_url="http://127.0.0.1"):
                pass
        assert first.get("/health").status_code == 200
