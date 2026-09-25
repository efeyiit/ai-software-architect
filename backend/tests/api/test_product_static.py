from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.static import ProductStaticFiles


def test_product_site_deep_links_preserve_api_boundaries(tmp_path):
    (tmp_path / "index.html").write_text("<html>product shell</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("app();", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/health")
    def api_health():
        return {"status": "ok"}

    app.mount("/", ProductStaticFiles(directory=tmp_path, html=True))
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/dashboard").text == "<html>product shell</html>"
    assert client.get("/repository/123/files").text == "<html>product shell</html>"
    assert client.get("/assets/app.js").text == "app();"
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/missing").status_code == 404
    assert client.get("/auth/missing").status_code == 404
