"""Private repository reads pin immutable Git SHAs and recheck identity on each call."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.security.identity.service import OAuthService
from app.services.github_public.service import (
    GitHubPublicError, GitHubPublicService, LANGUAGES, MAX_FILE_BYTES, MAX_SELECTED_BYTES,
    MAX_SELECTED_FILES, MAX_TREE_ENTRIES, SKIP_DIRS, SKIP_NAMES, RepositoryFile,
    RepositorySnapshot, _frameworks, _parse_url, _required_sha, _safe_path,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class GitHubPrivateHTTPClient:
    def __init__(self, token: str):
        self._token = token
        self._opener = build_opener(_NoRedirect)

    def get_json(self, path: str, max_bytes: int) -> dict[str, Any]:
        if not path.startswith("/repos/") or "//" in path or any(c in path for c in "\\\r\n#"):
            raise GitHubPublicError("INVALID_REQUEST", "Invalid GitHub API route")
        request = Request("https://api.github.com" + path, headers={
            "Accept": "application/vnd.github+json", "Authorization": "Bearer " + self._token,
            "User-Agent": "Ariadne-private-repository-reader", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with self._opener.open(request, timeout=15) as response:
                payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise GitHubPublicError("REPOSITORY_TOO_LARGE", "GitHub response exceeds the size limit")
        except HTTPError as exc:
            if exc.code == 429 or (exc.code == 403 and
                (exc.headers.get("X-RateLimit-Remaining") == "0" or exc.headers.get("Retry-After"))):
                raise GitHubPublicError("RATE_LIMITED", "GitHub API rate limit reached", retryable=True) from None
            if exc.code in (401, 403, 404):
                raise GitHubPublicError("ACCESS_DENIED", "Private repository access denied or unavailable") from None
            if exc.code in (301, 302, 307, 308):
                raise GitHubPublicError("INVALID_REPOSITORY", "GitHub redirected the API request") from None
            raise GitHubPublicError("GITHUB_API_ERROR", "GitHub API request failed", retryable=exc.code >= 500) from None
        except (URLError, TimeoutError):
            raise GitHubPublicError("GITHUB_UNAVAILABLE", "GitHub API could not be reached", retryable=True) from None
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned invalid JSON") from None
        if not isinstance(result, dict):
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid object")
        return result


@dataclass(frozen=True)
class PrivateRepositorySnapshot:
    local_user_id: str
    repository: RepositorySnapshot


class GitHubPrivateService:
    def __init__(self, identity: OAuthService,
                 api_factory: Callable[[str], Any] = GitHubPrivateHTTPClient):
        self.identity = identity
        self.api_factory = api_factory

    def fetch_repository(self, local_user_id: str, github_url: str) -> PrivateRepositorySnapshot:
        owner, repo = _parse_url(github_url)
        api = self.api_factory(self.identity.valid_token(local_user_id, "private"))
        route = f"/repos/{quote(owner)}/{quote(repo)}"
        metadata = api.get_json(route, 64_000)
        if metadata.get("private") is not True:
            raise GitHubPublicError("ACCESS_DENIED", "This route requires an accessible private repository")
        full_name = metadata.get("full_name")
        if not isinstance(full_name, str) or full_name.casefold() != f"{owner}/{repo}".casefold():
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned a different repository")
        repository_id = metadata.get("id")
        if type(repository_id) is not int or repository_id < 1:
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid repository id")
        branch = metadata.get("default_branch")
        if not isinstance(branch, str) or not branch or len(branch) > 255 or any(ord(c) < 32 for c in branch):
            raise GitHubPublicError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid default branch")
        commit = api.get_json(route + "/commits/" + quote(branch, safe=""), 128_000)
        commit_sha = _required_sha(commit.get("sha"))
        tree_obj = commit.get("commit", {}).get("tree") if isinstance(commit.get("commit"), dict) else None
        tree_sha = _required_sha(tree_obj.get("sha") if isinstance(tree_obj, dict) else None)
        tree = api.get_json(route + "/git/trees/" + tree_sha + "?recursive=1", 3_000_000)
        if tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Complete repository tree is unavailable")
        if len(tree["tree"]) > MAX_TREE_ENTRIES:
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Repository has too many tree entries")
        files: list[RepositoryFile] = []
        selected_count = selected_size = 0
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
                selected_count += 1
                selected_size += size
            files.append(RepositoryFile(path, sha, size, language, reason is None, reason))
        if selected_count > MAX_SELECTED_FILES or selected_size > MAX_SELECTED_BYTES:
            raise GitHubPublicError("REPOSITORY_TOO_LARGE", "Selected source files exceed import limits")
        if not files:
            raise GitHubPublicError("INVALID_REPOSITORY", "Repository has no files")
        if not selected_count:
            raise GitHubPublicError("UNSUPPORTED_LANGUAGE", "Repository has no supported source files")
        languages = Counter(item.language for item in files if item.included and item.language)
        snapshot = RepositorySnapshot(str(repository_id), f"https://github.com/{owner}/{repo}",
                                      str(metadata.get("name") or repo), branch, commit_sha, tree_sha,
                                      tuple(files), tuple(sorted(languages.items())),
                                      _frameworks({item.path for item in files}))
        return PrivateRepositorySnapshot(local_user_id, snapshot)

    def _authorized_api(self, local_user_id: str, snapshot: PrivateRepositorySnapshot) -> Any:
        if local_user_id != snapshot.local_user_id:
            raise GitHubPublicError("ACCESS_DENIED", "Snapshot is not authorized for this user")
        owner, repo = _parse_url(snapshot.repository.github_url)
        api = self.api_factory(self.identity.valid_token(local_user_id, "private"))
        route = f"/repos/{quote(owner)}/{quote(repo)}"
        metadata = api.get_json(route, 64_000)
        if (metadata.get("private") is not True or
                not isinstance(metadata.get("full_name"), str) or
                metadata["full_name"].casefold() != f"{owner}/{repo}".casefold() or
                type(metadata.get("id")) is not int or
                str(metadata["id"]) != snapshot.repository.repository_id or
                metadata.get("default_branch") != snapshot.repository.default_branch):
            raise GitHubPublicError("ACCESS_DENIED", "Private repository snapshot is no longer current")
        commit = api.get_json(route + "/commits/" + quote(snapshot.repository.default_branch, safe=""),
                              128_000)
        if _required_sha(commit.get("sha")) != snapshot.repository.commit_sha:
            raise GitHubPublicError("ACCESS_DENIED", "Private repository snapshot is no longer current")
        return api

    def fetch_file(self, local_user_id: str, snapshot: PrivateRepositorySnapshot,
                   file: RepositoryFile) -> str:
        if local_user_id != snapshot.local_user_id or file not in snapshot.repository.files or not file.included:
            raise GitHubPublicError("ACCESS_DENIED", "File does not belong to this authorized snapshot")
        api = self._authorized_api(local_user_id, snapshot)
        return GitHubPublicService(api)._read_blob(snapshot.repository, file)

    def document_files(self, local_user_id: str,
                       snapshot: PrivateRepositorySnapshot) -> tuple[RepositoryFile, ...]:
        """Select safe documents only after checking the live private repository."""
        api = self._authorized_api(local_user_id, snapshot)
        return GitHubPublicService(api).document_files(snapshot.repository)

    def fetch_document_file(self, local_user_id: str, snapshot: PrivateRepositorySnapshot,
                            file: RepositoryFile) -> str:
        """Read a bounded document from the current authorized private snapshot."""
        if local_user_id != snapshot.local_user_id:
            raise GitHubPublicError("ACCESS_DENIED", "Snapshot is not authorized for this user")
        api = self._authorized_api(local_user_id, snapshot)
        return GitHubPublicService(api).fetch_document_file(snapshot.repository, file)
