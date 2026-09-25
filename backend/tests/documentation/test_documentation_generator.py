import base64
from hashlib import sha1
import json
from dataclasses import replace

import pytest

from app.ai.documentation import DocumentationError, generate_documentation
from app.services.github_public import GitHubPublicError, GitHubPublicService, RepositoryFile, RepositorySnapshot


SHA = "a" * 40
SECRET = "sk_test_NEVER_PRINT_THIS_123456"


def fixture(sources):
    files = tuple(RepositoryFile(path, "b" * 40, len(body.encode()),
                                 "Python" if path.endswith(".py") else None,
                                 path.endswith(".py"),
                                 None if path.endswith(".py") else "unsupported_type")
                  for path, body in sources.items())
    return RepositorySnapshot("42", "https://github.com/example/demo", "demo", "main",
                              SHA, "c" * 40, files, (), ())


def test_source_backed_readme_and_openapi_route():
    sources = {
        "pyproject.toml": '[project]\nname = "demo"\nrequires-python = ">=3.12"\n',
        ".env.example": "API_TOKEN=placeholder\nPORT=8080\n",
        "Dockerfile": "FROM python:3.12\n",
        "openapi.json": json.dumps({"openapi": "3.1.0", "paths": {"/items": {
            "post": {"requestBody": {"content": {"application/json": {"schema": {
                "type": "object", "properties": {"name": {"type": "string"}}}}}},
                "responses": {"200": {"description": "ok", "content": {
                    "application/json": {"schema": {"type": "object", "properties": {
                        "id": {"type": "integer"}}}}}}}}}}}),
        "app.py": '@app.get("/health")\ndef health():\n    return {"status": "ok"}\n',
    }
    result = generate_documentation(fixture(sources), sources)
    assert result.snapshot.commit_sha == SHA
    assert result.snapshot.repository_id == "42"
    assert result.ai_status == "unavailable"
    assert "Requirements" in result.readme and "Installation" in result.readme
    assert "Environment Variables" in result.readme and "Docker Setup" in result.readme
    assert "Testing" in result.readme
    assert "API_TOKEN" in result.readme and "placeholder" not in result.readme
    assert any(fact.text == "Environment variable API_TOKEN declared."
               and fact.evidence.path == ".env.example" for fact in result.facts)
    assert "Dockerfile" in result.readme
    post = next(route for route in result.routes if route.method == "POST")
    assert post.path == "/items"
    assert post.request_fields[0].name == "name"
    assert post.response_fields[0].name == "id"
    assert post.evidence.path == "openapi.json"
    assert "POST /items" in result.api_markdown
    assert "GET /health" in result.api_markdown
    assert "Unknown" in result.readme


def test_secret_values_examples_headers_and_descriptions_never_leave():
    operation = {
        "description": SECRET,
        "parameters": [{"name": "Authorization", "in": "header", "example": SECRET}],
        "requestBody": {"content": {"application/json": {
            "example": {"password": SECRET},
            "schema": {"type": "object", "properties": {
                "password": {"type": "string"}, "email": {"type": "string"}}}}}},
        "responses": {"200": {"description": SECRET, "content": {
            "application/json": {"example": {"access_token": SECRET},
                "schema": {"type": "object", "properties": {
                    "access_token": {"type": "string"}, "ok": {"type": "boolean"}}}}}}},
    }
    sources = {
        ".env.example": f"API_TOKEN={SECRET}\n",
        "package.json": json.dumps({"name": "demo", "scripts": {"test": f"echo {SECRET}"}}),
        "openapi.json": json.dumps({"paths": {"/login": {"post": operation}}}),
    }
    result = generate_documentation(fixture(sources), sources)
    rendered = result.model_dump_json() + result.readme + result.api_markdown
    assert SECRET not in rendered
    assert "Authorization" not in rendered
    assert "password" not in rendered
    assert "access_token" not in rendered
    assert "email" in rendered and "ok" in rendered


def test_rejects_foreign_source_and_invalid_snapshot():
    sources = {"app.py": '@app.get("/ok")\ndef ok(): pass\n'}
    snapshot = fixture(sources)
    with pytest.raises(DocumentationError, match="snapshot"):
        generate_documentation(snapshot, {**sources, "foreign.py": "pass"})
    with pytest.raises(DocumentationError, match="snapshot"):
        generate_documentation(replace(snapshot, commit_sha="invalid"), sources)


def test_malformed_manifest_and_route_do_not_invent_claims():
    sources = {"package.json": "{broken", "openapi.json": "{broken",
               "app.py": '@app.get(dynamic_path)\ndef x(): pass\n'}
    result = generate_documentation(fixture(sources), sources)
    assert not result.routes
    assert "Unknown" in result.readme
    assert "npm run" not in result.readme
    assert result.uncertainties


def test_env_template_lists_names_but_never_values():
    sources = {".env.template": f"API_TOKEN={SECRET}\nPUBLIC_PORT=8080\n"}
    result = generate_documentation(fixture(sources), sources)
    assert "API_TOKEN" in result.readme
    assert "PUBLIC_PORT" in result.readme
    assert SECRET not in result.model_dump_json()
    assert "8080" not in result.model_dump_json()


def test_documentation_uses_sha_checked_ingestion_fixture():
    documents = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.12"\n',
        "openapi.json": json.dumps({"paths": {"/items": {"get": {
            "responses": {"200": {"description": SECRET}}}}}}),
        "Dockerfile": "FROM python:3.12\n",
        ".env.template": f"API_TOKEN={SECRET}\n",
        ".env": f"REAL_SECRET={SECRET}\n",
        "nested/openapi.json": "x" * 512_001,
    }
    def blob_sha(data):
        return sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

    blobs = {blob_sha(body.encode()): body.encode() for body in documents.values()}
    tree = [{"type": "blob", "path": "app.py", "sha": "f" * 40, "size": 5}]
    tree += [{"type": "blob", "path": path, "sha": blob_sha(body.encode()),
              "size": len(body.encode())} for path, body in documents.items()]

    class API:
        def get_json(self, path, max_bytes):
            if path == "/repos/example/demo":
                return {"id": 42, "name": "demo", "private": False, "default_branch": "main"}
            if path == "/repos/example/demo/commits/main":
                return {"sha": SHA, "commit": {"tree": {"sha": "e" * 40}}}
            if path == "/repos/example/demo/git/trees/" + "e" * 40 + "?recursive=1":
                return {"truncated": False, "tree": tree}
            if "/git/blobs/" in path:
                sha = path.rsplit("/", 1)[-1]
                return {"sha": sha, "encoding": "base64",
                        "content": base64.b64encode(blobs[sha]).decode()}
            raise AssertionError(path)

    service = GitHubPublicService(API())
    snapshot = service.fetch_repository("https://github.com/example/demo")
    candidates = service.document_files(snapshot)
    assert {item.path for item in candidates} == {
        "pyproject.toml", "openapi.json", "Dockerfile", ".env.template"}
    texts = {item.path: service.fetch_document_file(snapshot, item) for item in candidates}
    result = generate_documentation(snapshot, texts)
    assert result.snapshot.commit_sha == SHA
    assert "GET /items" in result.api_markdown
    assert "API_TOKEN" in result.readme
    assert SECRET not in result.model_dump_json()
    assert texts[".env.template"] == "API_TOKEN="
    with pytest.raises(DocumentationError, match="snapshot"):
        generate_documentation(replace(snapshot, files=tuple()), texts)

    class WrongBlobAPI(API):
        def get_json(self, path, max_bytes):
            response = super().get_json(path, max_bytes)
            if "/git/blobs/" in path:
                response["sha"] = "0" * 40
            return response

    with pytest.raises(GitHubPublicError, match="wrong blob"):
        GitHubPublicService(WrongBlobAPI()).fetch_document_file(snapshot, candidates[0])

    class TamperedBlobAPI(API):
        def get_json(self, path, max_bytes):
            response = super().get_json(path, max_bytes)
            if "/git/blobs/" in path:
                sha = path.rsplit("/", 1)[-1]
                response["content"] = base64.b64encode(b"X" * len(blobs[sha])).decode()
            return response

    with pytest.raises(GitHubPublicError, match="invalid text content"):
        GitHubPublicService(TamperedBlobAPI()).fetch_document_file(snapshot, candidates[0])
