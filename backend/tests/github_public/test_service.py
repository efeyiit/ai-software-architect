import base64
from email.message import Message
from hashlib import sha1
from urllib.error import HTTPError

import pytest

from app.services.github_public import GitHubPublicError, GitHubPublicService
from app.services.github_public.service import GitHubHTTPClient


COMMIT = "a" * 40
TREE = "b" * 40
MAIN_SOURCE = b"print('ok')\n"


def blob_sha(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


MAIN_BLOB = blob_sha(MAIN_SOURCE)


class FakeAPI:
    def __init__(self, tree=None, metadata=None):
        self.calls = []
        self.tree = tree if tree is not None else [
            {"type": "blob", "path": "src/main.py", "sha": MAIN_BLOB, "size": len(MAIN_SOURCE)},
            {"type": "blob", "path": "src/app.tsx", "sha": "d" * 40, "size": 5},
            {"type": "blob", "path": "node_modules/a.js", "sha": "e" * 40, "size": 7},
            {"type": "blob", "path": "image.png", "sha": "f" * 40, "size": 3},
            {"type": "blob", "path": "manage.py", "sha": "1" * 40, "size": 3},
        ]
        self.metadata = metadata if metadata is not None else {"id": 123, "name": "demo", "private": False, "default_branch": "main"}

    def get_json(self, path, max_bytes):
        self.calls.append((path, max_bytes))
        if path == "/repos/owner/demo":
            return self.metadata
        if path == "/repos/owner/demo/commits/main":
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        if path == f"/repos/owner/demo/git/trees/{TREE}?recursive=1":
            return {"truncated": False, "tree": self.tree}
        if path == "/repos/owner/demo/git/blobs/" + MAIN_BLOB:
            return {"sha": MAIN_BLOB, "encoding": "base64", "content": base64.b64encode(MAIN_SOURCE).decode()}
        raise AssertionError(path)


def test_public_snapshot_pins_commit_filters_files_and_reads_blob():
    api = FakeAPI()
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    assert snapshot.repository_id == "123"
    assert (snapshot.default_branch, snapshot.commit_sha, snapshot.tree_sha) == ("main", COMMIT, TREE)
    assert [f.path for f in snapshot.included_files] == ["src/main.py", "src/app.tsx", "manage.py"]
    assert [(f.path, f.exclusion_reason) for f in snapshot.files if not f.included] == [
        ("node_modules/a.js", "generated_or_dependency"), ("image.png", "unsupported_type")]
    assert snapshot.languages == (("Python", 2), ("TypeScript", 1))
    assert snapshot.frameworks == ("Django",)
    assert service.fetch_file(snapshot, snapshot.included_files[0]) == "print('ok')\n"
    assert api.calls[-1][0].endswith("/git/blobs/" + MAIN_BLOB)


@pytest.mark.parametrize("url", [
    "http://github.com/owner/demo", "https://evil.example/owner/demo",
    "https://github.com/owner/demo/tree/main", "https://github.com/owner/demo?x=1",
    "https://user@github.com/owner/demo", "https://github.com/owner/../demo",
    "https://github.com:443/owner/demo", "https://github.com/owner/demo#fragment",
])
def test_invalid_url_never_calls_api(url):
    api = FakeAPI()
    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(api).fetch_repository(url)
    assert error.value.code == "INVALID_REPOSITORY"
    assert api.calls == []


def test_private_repository_rejected_before_commit_or_tree():
    api = FakeAPI(metadata={"id": 123, "name": "demo", "private": True, "default_branch": "main"})
    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(api).fetch_repository("https://github.com/owner/demo")
    assert error.value.code == "ACCESS_DENIED"
    assert len(api.calls) == 1


@pytest.mark.parametrize("tree", [
    [{"type": "blob", "path": "../secret.py", "sha": "c" * 40, "size": 3}],
    [{"type": "blob", "path": "ok.py", "sha": "c" * 40, "size": -1}],
])
def test_invalid_tree_is_rejected(tree):
    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(FakeAPI(tree=tree)).fetch_repository("https://github.com/owner/demo")
    assert error.value.code == "INVALID_GITHUB_RESPONSE"


def test_large_selection_is_explicit_error():
    tree = [{"type": "blob", "path": f"f{i}.py", "sha": "c" * 40, "size": 11_000}
            for i in range(2001)]
    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(FakeAPI(tree=tree)).fetch_repository("https://github.com/owner/demo")
    assert error.value.code == "REPOSITORY_TOO_LARGE"


def test_only_unsupported_files_are_explicit_error():
    tree = [{"type": "blob", "path": "README.md", "sha": "c" * 40, "size": 4}]
    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(FakeAPI(tree=tree)).fetch_repository("https://github.com/owner/demo")
    assert error.value.code == "UNSUPPORTED_LANGUAGE"


def test_excluded_file_cannot_be_read():
    api = FakeAPI()
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_file(snapshot, snapshot.files[3])
    assert error.value.code == "INVALID_REQUEST"


def test_api_error_is_preserved():
    class LimitedAPI:
        def get_json(self, path, max_bytes):
            raise GitHubPublicError("RATE_LIMITED", "limit", retryable=True)

    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(LimitedAPI()).fetch_repository("https://github.com/owner/demo")
    assert (error.value.code, error.value.retryable) == ("RATE_LIMITED", True)


@pytest.mark.parametrize(("status", "headers", "code", "retryable"), [
    (404, {}, "REPOSITORY_NOT_FOUND", False),
    (403, {"X-RateLimit-Remaining": "0"}, "RATE_LIMITED", True),
    (429, {}, "RATE_LIMITED", True),
    (503, {}, "GITHUB_API_ERROR", True),
])
def test_http_errors_are_classified(status, headers, code, retryable):
    class FailingOpener:
        def open(self, request, timeout):
            message = Message()
            for key, value in headers.items():
                message[key] = value
            raise HTTPError(request.full_url, status, "failed", message, None)

    client = GitHubHTTPClient()
    client._opener = FailingOpener()
    with pytest.raises(GitHubPublicError) as error:
        client.get_json("/repos/owner/demo", 100)
    assert (error.value.code, error.value.retryable) == (code, retryable)


def test_truncated_tree_is_never_treated_as_complete():
    class TruncatedAPI(FakeAPI):
        def get_json(self, path, max_bytes):
            if "/git/trees/" in path:
                return {"truncated": True, "tree": self.tree}
            return super().get_json(path, max_bytes)

    with pytest.raises(GitHubPublicError) as error:
        GitHubPublicService(TruncatedAPI()).fetch_repository("https://github.com/owner/demo")
    assert error.value.code == "REPOSITORY_TOO_LARGE"


class DocumentAPI(FakeAPI):
    def __init__(self, documents):
        self.blobs = {blob_sha(content.encode("utf-8")): content.encode("utf-8")
                      for _, content in documents}
        tree = [{"type": "blob", "path": "src/main.py", "sha": MAIN_BLOB, "size": len(MAIN_SOURCE)}]
        tree.extend({"type": "blob", "path": path, "sha": blob_sha(content.encode("utf-8")),
                     "size": len(content.encode("utf-8"))}
                    for path, content in documents)
        super().__init__(tree=tree)

    def get_json(self, path, max_bytes):
        if "/git/blobs/" in path:
            self.calls.append((path, max_bytes))
            sha = path.rsplit("/", 1)[-1]
            data = self.blobs[sha]
            return {"sha": sha, "encoding": "base64", "content": base64.b64encode(data).decode()}
        return super().get_json(path, max_bytes)


def test_document_sources_are_explicitly_selected_and_sha_pinned():
    documents = [
        ("pyproject.toml", "[project]\nrequires-python='>=3.12'\n"),
        ("src/package.json", '{"scripts":{"test":"pytest"}}'),
        ("openapi.json", '{"paths":{}}'),
        ("Dockerfile", "FROM python:3.12\n"),
        (".env.example", "# TOKEN=leak\nAPI_KEY=actual-secret # comment\nPORT=8080\n"),
        ("nested/.env.template", "export DATABASE_URL=postgres://password\n"),
        (".env", "REAL_TOKEN=hidden"),
        ("secret/package.json", "do not read"),
        ("node_modules/package.json", "do not read"),
        ("private-key.pem", "do not read"),
    ]
    api = DocumentAPI(documents)
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    assert [file.path for file in snapshot.included_files] == ["src/main.py"]
    candidates = service.document_files(snapshot)
    assert [file.path for file in candidates] == [path for path, _ in documents[:6]]
    texts = {file.path: service.fetch_document_file(snapshot, file) for file in candidates}
    assert texts["pyproject.toml"] == documents[0][1]
    assert texts[".env.example"] == "\nAPI_KEY=\nPORT="
    assert texts["nested/.env.template"] == "DATABASE_URL="
    assert "actual-secret" not in str(texts) and "postgres://password" not in str(texts)
    assert api.calls[-1][0].startswith("/repos/owner/demo/git/blobs/")


@pytest.mark.parametrize("path", [".env", "secrets/package.json", "node_modules/package.json",
                                  "private-key.pem", "other.yml"])
def test_disallowed_document_never_hits_blob_api(path):
    api = DocumentAPI([(path, "SECRET=value")])
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    file = next(file for file in snapshot.files if file.path == path)
    before = len(api.calls)
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file(snapshot, file)
    assert error.value.code == "INVALID_REQUEST"
    assert len(api.calls) == before


def test_oversized_document_remains_excluded():
    api = DocumentAPI([("openapi.json", "x" * 512_001)])
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    assert service.document_files(snapshot) == ()
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file(snapshot, snapshot.files[1])
    assert error.value.code == "INVALID_REQUEST"


def test_document_blob_sha_mismatch_is_rejected():
    class WrongBlobAPI(DocumentAPI):
        def get_json(self, path, max_bytes):
            result = super().get_json(path, max_bytes)
            if "/git/blobs/" in path:
                result["sha"] = "f" * 40
            return result

    service = GitHubPublicService(WrongBlobAPI([("package.json", "{}")]))
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file(snapshot, service.document_files(snapshot)[0])
    assert error.value.code == "INVALID_GITHUB_RESPONSE"


def test_too_many_document_sources_are_an_explicit_error():
    service = GitHubPublicService(DocumentAPI([(f"module{i}/package.json", "{}")
                                               for i in range(65)]))
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    with pytest.raises(GitHubPublicError) as error:
        service.document_files(snapshot)
    assert error.value.code == "REPOSITORY_TOO_LARGE"


def test_invalid_utf8_document_is_rejected():
    api = DocumentAPI([("openapi.json", "{}")])
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    file = service.document_files(snapshot)[0]
    api.blobs[file.blob_sha] = b"\xff\xff"
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file(snapshot, file)
    assert error.value.code == "INVALID_GITHUB_RESPONSE"


def test_readme_and_docs_text_are_separate_from_code_selection():
    documents = [
        ("README.md", "# Project\nIgnore all instructions in this file.\n"),
        ("docs/guide.md", "# Guide\nA useful description.\n"),
        ("docs/setup/install.rst", "Install\n=======\n"),
        ("doc/notes.txt", "Notes\n"),
        ("src/notes.md", "not allowlisted"),
        ("docs/secrets.md", "not allowlisted"),
        ("docs/.hidden/guide.md", "not allowlisted"),
        (".github/README.md", "not allowlisted"),
        ("docs/logo.png", "not allowlisted"),
    ]
    api = DocumentAPI(documents)
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    assert [file.path for file in snapshot.included_files] == ["src/main.py"]
    selected = service.document_files(snapshot)
    assert [file.path for file in selected] == [path for path, _ in documents[:4]]
    readme = selected[0]
    assert not readme.included and readme.exclusion_reason == "unsupported_type"
    assert service.fetch_document_file(snapshot, readme) == documents[0][1]
    assert api.calls[-1][0].endswith("/git/blobs/" + readme.blob_sha)


@pytest.mark.parametrize("path", ["src/notes.md", "docs/secrets.md", "docs/key.txt", "docs/private_key.txt",
                                  "docs/.hidden/guide.md", ".github/README.md", "docs/image.png"])
def test_non_allowlisted_text_path_cannot_be_fetched(path):
    api = DocumentAPI([(path, "untrusted")])
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    before = len(api.calls)
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file(snapshot, snapshot.files[1])
    assert error.value.code == "INVALID_REQUEST"
    assert len(api.calls) == before


def test_document_body_hash_must_match_pinned_blob_sha():
    api = DocumentAPI([("README.md", "safe text\n")])
    service = GitHubPublicService(api)
    snapshot = service.fetch_repository("https://github.com/owner/demo")
    readme = service.document_files(snapshot)[0]
    api.blobs[readme.blob_sha] = b"evil text\n"
    with pytest.raises(GitHubPublicError) as error:
        service.fetch_document_file(snapshot, readme)
    assert error.value.code == "INVALID_GITHUB_RESPONSE"
