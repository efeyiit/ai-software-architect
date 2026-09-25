"""Bounded public GitHub metadata and file retrieval; repository code is never run."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
from hashlib import sha1
import json
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SHA = re.compile(r"[0-9a-f]{40}\Z")
SEGMENT = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
LANGUAGES = {
    ".py": "Python", ".pyi": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".java": "Java",
    ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".hpp": "C++", ".h": "C++", ".c": "C",
}
SKIP_DIRS = {"node_modules", "dist", "build", "vendor", ".git", ".venv", "venv", "__pycache__", "coverage"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
MAX_TREE_ENTRIES = 10_000
MAX_SELECTED_FILES = 2_000
MAX_FILE_BYTES = 512_000
MAX_SELECTED_BYTES = 20_000_000
DOCUMENT_NAMES = frozenset({"pyproject.toml", "package.json", "openapi.json", "dockerfile"})
ENV_EXAMPLE_NAMES = frozenset({".env.example", ".env.sample", ".env.template"})
README_NAMES = frozenset({"readme.md", "readme.rst", "readme.txt"})
DOC_TEXT_SUFFIXES = frozenset({".md", ".rst", ".txt"})
DOC_ROOTS = frozenset({"docs", "doc"})
MAX_DOCUMENT_FILES = 64
MAX_DOCUMENT_BYTES = 2_000_000
_SENSITIVE_PATH = re.compile(r"(?:password|passwd|secret|token|credential|private|key|authorization|auth)", re.I)
_ENV_NAME = re.compile(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]{0,79})\s*=", re.ASCII)


class GitHubPublicError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class GitHubAPI(Protocol):
    def get_json(self, path: str, max_bytes: int) -> dict[str, Any]: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class GitHubHTTPClient:
    """Only relative API routes are accepted; no redirects or arbitrary hosts."""

    def __init__(self) -> None:
        self._opener = build_opener(_NoRedirect)

    def get_json(self, path: str, max_bytes: int) -> dict[str, Any]:
        if not path.startswith("/repos/") or "//" in path or any(c in path for c in "\\\r\n#"):
            raise GitHubPublicError("INVALID_REQUEST", "Invalid GitHub API route")
        request = Request("https://api.github.com" + path, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "Ariadne-public-repository-reader",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with self._opener.open(request, timeout=15) as response:
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise GitHubPublicError("REPOSITORY_TOO_LARGE", "GitHub response exceeds the size limit")
        except HTTPError as exc:
            if exc.code == 404:
                raise GitHubPublicError("REPOSITORY_NOT_FOUND", "Public repository or object not found") from exc
            if exc.code == 429 or (exc.code == 403 and (exc.headers.get("X-RateLimit-Remaining") == "0" or exc.headers.get("Retry-After"))):
                raise GitHubPublicError("RATE_LIMITED", "GitHub API rate limit reached", retryable=True) from exc
            if exc.code in (401, 403):
                raise GitHubPublicError("ACCESS_DENIED", "GitHub denied access to the repository") from exc
            if exc.code in (301, 302, 307, 308):
                raise GitHubPublicError("INVALID_REPOSITORY", "GitHub redirected the API request") from exc
            raise GitHubPublicError("GITHUB_API_ERROR", f"GitHub API returned HTTP {exc.code}", retryable=exc.code >= 500) from exc
        except (URLError, TimeoutError) as exc:
            raise GitHubPublicError("GITHUB_UNAVAILABLE", "GitHub API could not be reached", retryable=True) from exc
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid object")
        return result


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    blob_sha: str
    size: int
    language: str | None
    included: bool
    exclusion_reason: str | None


@dataclass(frozen=True)
class RepositorySnapshot:
    repository_id: str
    github_url: str
    name: str
    default_branch: str
    commit_sha: str | None
    tree_sha: str
    files: tuple[RepositoryFile, ...]
    languages: tuple[tuple[str, int], ...]
    frameworks: tuple[str, ...]
    snapshot_id: str | None = None

    @property
    def included_files(self) -> tuple[RepositoryFile, ...]:
        return tuple(item for item in self.files if item.included)


def _required_sha(value: Any) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid SHA")
    return value


def _parse_url(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or len(value) > 300:
        raise GitHubPublicError("INVALID_REPOSITORY", "Expected a short GitHub repository URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
            or parsed.query or parsed.fragment):
        raise GitHubPublicError("INVALID_REPOSITORY", "Expected a public https://github.com/owner/repo URL")
    parts = parsed.path.removesuffix("/").split("/")
    if len(parts) != 3 or parts[0] or not all(SEGMENT.fullmatch(part) for part in parts[1:]):
        raise GitHubPublicError("INVALID_REPOSITORY", "Expected a GitHub owner and repository name")
    owner, repo = parts[1:]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not repo or owner in (".", "..") or repo in (".", ".."):
        raise GitHubPublicError("INVALID_REPOSITORY", "Invalid GitHub owner or repository name")
    return owner, repo


def _safe_path(path: Any) -> str:
    if (not isinstance(path, str) or not path or len(path) > 1024 or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
            or any(ord(char) < 32 for char in path)):
        raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an unsafe file path")
    return path


def _frameworks(paths: set[str]) -> tuple[str, ...]:
    names = {p.rsplit("/", 1)[-1].lower() for p in paths}
    found = []
    for marker, framework in (("manage.py", "Django"), ("angular.json", "Angular"),
                              ("next.config.js", "Next.js"), ("next.config.mjs", "Next.js"),
                              ("next.config.ts", "Next.js"), ("vite.config.ts", "Vite"),
                              ("vite.config.js", "Vite"), ("pom.xml", "Maven"),
                              ("build.gradle", "Gradle")):
        if marker in names and framework not in found:
            found.append(framework)
    return tuple(found)


def _document_kind(path: str) -> str | None:
    """Only named manifests, root READMEs and docs text in safe paths qualify."""
    parts = _safe_path(path).split("/")
    if any(part.lower() in SKIP_DIRS or _SENSITIVE_PATH.search(part) for part in parts[:-1]):
        return None
    name = parts[-1].lower()
    if parts[-1] in ENV_EXAMPLE_NAMES:
        return "env_example"
    if name in DOCUMENT_NAMES:
        return "document"
    if (not parts[-1].startswith(".") and not _SENSITIVE_PATH.search(parts[-1])
            and (len(parts) == 1 and name in README_NAMES
                 or len(parts) > 1 and parts[0].lower() in DOC_ROOTS
                 and not any(part.startswith(".") for part in parts[1:-1])
                 and any(name.endswith(suffix) for suffix in DOC_TEXT_SUFFIXES))):
        return "text_document"
    return None


def _redact_env_example(source: str) -> str:
    """Keep only env key names and source line positions; never expose values or comments."""
    lines = []
    for line in source.splitlines():
        match = _ENV_NAME.match(line)
        lines.append(match.group(1) + "=" if match else "")
    return "\n".join(lines)


class GitHubPublicService:
    def __init__(self, api: GitHubAPI | None = None) -> None:
        self._api = api or GitHubHTTPClient()

    def fetch_repository(self, github_url: str) -> RepositorySnapshot:
        owner, repo = _parse_url(github_url)
        route = f"/repos/{quote(owner)}/{quote(repo)}"
        metadata = self._api.get_json(route, 64_000)
        if metadata.get("private") is not False:
            raise GitHubPublicError("ACCESS_DENIED", "Only public repositories can be imported")
        branch = metadata.get("default_branch")
        if not isinstance(branch, str) or not branch or len(branch) > 255 or any(ord(c) < 32 for c in branch):
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid default branch")
        commit = self._api.get_json(route + "/commits/" + quote(branch, safe=""), 128_000)
        commit_sha = _required_sha(commit.get("sha"))
        tree_obj = commit.get("commit", {}).get("tree") if isinstance(commit.get("commit"), dict) else None
        tree_sha = _required_sha(tree_obj.get("sha") if isinstance(tree_obj, dict) else None)
        tree = self._api.get_json(route + "/git/trees/" + tree_sha + "?recursive=1", 3_000_000)
        if tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Complete repository tree is unavailable")
        if len(tree["tree"]) > MAX_TREE_ENTRIES:
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Repository has too many tree entries")
        files: list[RepositoryFile] = []
        selected_size = 0
        selected_count = 0
        for entry in tree["tree"]:
            if not isinstance(entry, dict):
                raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "Invalid tree entry")
            if entry.get("type") != "blob":
                continue
            path = _safe_path(entry.get("path"))
            sha = _required_sha(entry.get("sha"))
            size = entry.get("size")
            if type(size) is not int or size < 0:
                raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "Invalid file size")
            filename = path.rsplit("/", 1)[-1]
            suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            language = LANGUAGES.get(suffix)
            reason = None
            if any(part.lower() in SKIP_DIRS for part in path.split("/")[:-1]) or filename.lower() in SKIP_NAMES:
                reason = "generated_or_dependency"
            elif language is None:
                reason = "unsupported_type"
            elif size > MAX_FILE_BYTES:
                reason = "file_too_large"
            if reason is None:
                selected_size += size
                selected_count += 1
            files.append(RepositoryFile(path, sha, size, language, reason is None, reason))
        if selected_count > MAX_SELECTED_FILES or selected_size > MAX_SELECTED_BYTES:
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Selected source files exceed import limits")
        if not files:
            raise GitHubPublicError("INVALID_REPOSITORY", "Repository has no files")
        if selected_count == 0:
            raise GitHubPublicError("UNSUPPORTED_LANGUAGE", "Repository has no supported source files")
        languages = Counter(item.language for item in files if item.included and item.language)
        repo_id = metadata.get("id")
        if type(repo_id) is not int or repo_id < 1:
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid repository id")
        return RepositorySnapshot(str(repo_id), f"https://github.com/{owner}/{repo}",
                                  str(metadata.get("name") or repo), branch, commit_sha, tree_sha,
                                  tuple(files), tuple(sorted(languages.items())),
                                  _frameworks({item.path for item in files}))

    def fetch_file(self, snapshot: RepositorySnapshot, file: RepositoryFile) -> str:
        """Read one selected text blob by immutable blob SHA, never by moving branch."""
        if file not in snapshot.files or not file.included:
            raise GitHubPublicError("INVALID_REQUEST", "File is not selected in this snapshot")
        return self._read_blob(snapshot, file)

    def document_files(self, snapshot: RepositorySnapshot) -> tuple[RepositoryFile, ...]:
        """List bounded manifest/API/container/README/docs candidates from the pinned tree."""
        candidates = tuple(file for file in snapshot.files
                           if _document_kind(file.path) and file.size <= MAX_FILE_BYTES)
        if len(candidates) > MAX_DOCUMENT_FILES or sum(file.size for file in candidates) > MAX_DOCUMENT_BYTES:
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Document sources exceed import limits")
        return candidates

    def fetch_document_file(self, snapshot: RepositorySnapshot, file: RepositoryFile) -> str:
        """Read an allowlisted document by blob SHA; env templates return redacted names only."""
        if file not in snapshot.files or not _document_kind(file.path) or file.size > MAX_FILE_BYTES:
            raise GitHubPublicError("INVALID_REQUEST", "File is not an allowed document source")
        if file not in self.document_files(snapshot):
            raise GitHubPublicError("INVALID_REQUEST", "File is not in the bounded document set")
        content = self._read_blob(snapshot, file)
        return _redact_env_example(content) if _document_kind(file.path) == "env_example" else content

    def _read_blob(self, snapshot: RepositorySnapshot, file: RepositoryFile) -> str:
        _required_sha(file.blob_sha)
        if type(file.size) is not int or file.size < 0 or file.size > MAX_FILE_BYTES:
            raise GitHubPublicError("INVALID_REQUEST", "Invalid file size")
        owner, repo = _parse_url(snapshot.github_url)
        response = self._api.get_json(f"/repos/{quote(owner)}/{quote(repo)}/git/blobs/{file.blob_sha}",
                                      750_000)
        if response.get("sha") != file.blob_sha or response.get("encoding") != "base64":
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned the wrong blob")
        encoded = response.get("content")
        if not isinstance(encoded, str):
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned invalid blob content")
        try:
            content = base64.b64decode("".join(encoded.split()), validate=True)
            if len(content) != file.size or len(content) > MAX_FILE_BYTES or b"\0" in content:
                raise ValueError("Unexpected blob size or binary content")
            actual_sha = sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
            if actual_sha != file.blob_sha:
                raise ValueError("Git blob SHA does not match content")
            return content.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned invalid text content") from exc
