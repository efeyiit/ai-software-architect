from fastapi.testclient import TestClient

from app.demo.main import create_demo_app
from app.rag.chat import ChatProviderAnswer, ProviderCitation, ProviderClaim


class LocalVectors:
    model_id = "demo-test-vectors-only"
    dimension = 3
    execution_location = "local"

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [1.0, 1.0, 1.0]


class ControlledLocalAnswer:
    execution_location = "local"

    def answer(self, prompt):
        return ChatProviderAnswer(claims=[ProviderClaim(
            text="createOrder returns an order identifier.", citations=[ProviderCitation(
                evidence_id="E1", start_line=1, end_line=1,
                quote="export function createOrder")])])


class InvalidCitationAnswer:
    execution_location = "local"

    def answer(self, prompt):
        return ChatProviderAnswer(claims=[ProviderClaim(
            text="Unverified claim", citations=[ProviderCitation(
                evidence_id="E1", start_line=1, end_line=1, quote="not in fixture")])])


def test_demo_unavailable_is_explicit_and_production_routes_absent():
    app = create_demo_app(readiness=lambda: "unavailable")
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    meta = client.get("/demo/meta").json()
    assert meta["mode"] == "local_demo"
    assert meta["label"] == "Yerel demo"
    assert meta["model_status"] == "unavailable"
    assert meta["data_origin"] == "bundled_synthetic"
    assert client.post("/demo/chat", json={"question": "What does createOrder do?"}).json()["status"] == "unavailable"
    assert client.get("/auth/me").status_code == 404
    assert client.get("/api/repositories/demo-commerce-api").status_code == 404
    assert client.post("/demo/chat", json={"question": "hi"},
                       headers={"Origin": "https://evil.example"}).status_code == 403
    assert TestClient(app, base_url="http://evil.example").get("/demo/meta").status_code == 400


def test_demo_chat_uses_local_qdrant_and_validated_source_citation():
    app = create_demo_app(embedding=LocalVectors(), answer_provider=ControlledLocalAnswer(),
                          readiness=lambda: "ready")
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    assert client.get("/demo/meta").json()["model_status"] == "ready"
    response = client.post("/demo/chat", json={"question": "What does createOrder do?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered" and body["origin"] == "ai"
    assert body["claims"][0]["citations"][0]["path"] == "src/api/orders.ts"
    assert body["claims"][0]["citations"][0]["quote"] == "export function createOrder"
    assert "@" + body["commit_sha"] in body["answer"]


def test_demo_loading_and_bad_citation_are_not_answers():
    app = create_demo_app(embedding=LocalVectors(), answer_provider=InvalidCitationAnswer(),
                          readiness=lambda: "loading")
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    assert client.get("/demo/meta").json()["model_status"] == "loading"
    assert client.post("/demo/chat", json={"question": "What does it do?"}).json()["status"] == "unavailable"
    assert client.post("/demo/chat", json={"question": " " * 1001}).status_code == 422
    ready = create_demo_app(embedding=LocalVectors(), answer_provider=InvalidCitationAnswer(),
                            readiness=lambda: "ready")
    result = TestClient(ready, base_url="http://127.0.0.1:8765").post(
        "/demo/chat", json={"question": "What does createOrder do?"}).json()
    assert result["status"] == "rejected" and result["origin"] == "none"


def test_demo_serves_built_site_on_deep_links(tmp_path):
    (tmp_path / "index.html").write_text("<html>Local demo shell</html>", encoding="utf-8")
    app = create_demo_app(frontend_dir=tmp_path)
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    assert client.get("/", follow_redirects=False).headers["location"] == "/demo"
    assert "Local demo shell" in client.get("/demo").text
    assert "Local demo shell" in client.get("/repository/demo-commerce-api/files").text
    assert client.get("/missing.js").status_code == 404
