"""Live owner, GitHub permission and default-branch SHA resolver for T20."""

from __future__ import annotations

from typing import Any, Callable, Protocol
from urllib.parse import quote
from uuid import UUID

from app.rag.indexing import AuthorizedScope
from app.security.identity import IdentityError, OAuthService
from app.services.github_public.service import (
    GitHubHTTPClient, GitHubPublicError, _parse_url, _required_sha,
)
from .service import GitHubPrivateHTTPClient


class RepositoryStore(Protocol):
    def get_repository(self, user_id: str, repository_id: str) -> dict | None: ...


class ScopeResolutionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(message)


def _canonical_uuid(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


class LiveRepositoryScopeResolver:
    """Callable for QdrantIndex; caller_id must come from a trusted session.

    The local repository ID is a UUID. The GitHub metadata ID is distinct and
    is not accepted from the caller. All GitHub reads are made on each call,
    including QdrantIndex's own pre/post operation rechecks.
    """

    def __init__(self, repository_store: RepositoryStore, identity: OAuthService,
                 public_api: Any | None = None,
                 private_api_factory: Callable[[str], Any] = GitHubPrivateHTTPClient):
        connection = getattr(repository_store, "connection", None)
        if connection is not None and not connection.autocommit:
            raise ScopeResolutionError("CONFIGURATION_ERROR", "Live scope checks require an autocommit database connection")
        self.repository_store = repository_store
        self.identity = identity
        self.public_api = public_api or GitHubHTTPClient()
        self.private_api_factory = private_api_factory

    def __call__(self, authenticated_caller_id: str, repository_id: str) -> AuthorizedScope | None:
        if not _canonical_uuid(authenticated_caller_id) or not _canonical_uuid(repository_id):
            return None
        try:
            repository = self.repository_store.get_repository(authenticated_caller_id, repository_id)
        except Exception:
            raise ScopeResolutionError("STORE_UNAVAILABLE", "Repository ownership could not be verified") from None
        if (not repository or repository.get("id") != repository_id
                or repository.get("user_id") != authenticated_caller_id):
            return None
        try:
            owner, name = _parse_url(repository.get("github_url"))
        except GitHubPublicError:
            return None
        route = f"/repos/{quote(owner)}/{quote(name)}"
        try:
            metadata = self.public_api.get_json(route, 64_000)
        except GitHubPublicError as exc:
            if exc.code != "REPOSITORY_NOT_FOUND":
                raise ScopeResolutionError(exc.code, "GitHub repository check failed",
                                           retryable=exc.retryable) from None
            metadata = None
        if metadata is not None and metadata.get("private") is False:
            api = self.public_api
            private = False
        else:
            # GitHub masks unavailable private repositories as 404. No private
            # token or revoked scope must never expose a cached Qdrant point.
            try:
                token = self.identity.valid_token(authenticated_caller_id, "private")
            except IdentityError as exc:
                if exc.retryable:
                    raise ScopeResolutionError(exc.code, "GitHub identity check failed",
                                               retryable=True) from None
                return None
            api = self.private_api_factory(token)
            try:
                metadata = api.get_json(route, 64_000)
            except GitHubPublicError as exc:
                if exc.code in ("ACCESS_DENIED", "REPOSITORY_NOT_FOUND"):
                    return None
                raise ScopeResolutionError(exc.code, "GitHub repository check failed",
                                           retryable=exc.retryable) from None
            private = True
        if (metadata.get("private") is not private or
                not isinstance(metadata.get("full_name"), str) or
                metadata["full_name"].casefold() != f"{owner}/{name}".casefold() or
                type(metadata.get("id")) is not int or metadata["id"] < 1):
            return None
        branch = metadata.get("default_branch")
        if (not isinstance(branch, str) or not branch or len(branch) > 255
                or any(ord(char) < 32 for char in branch)):
            return None
        try:
            commit = api.get_json(route + "/commits/" + quote(branch, safe=""), 128_000)
            sha = _required_sha(commit.get("sha"))
        except GitHubPublicError as exc:
            if exc.code in ("ACCESS_DENIED", "REPOSITORY_NOT_FOUND"):
                return None
            raise ScopeResolutionError(exc.code, "Current GitHub commit could not be verified",
                                       retryable=exc.retryable) from None
        return AuthorizedScope(authenticated_caller_id, repository_id,
                               str(metadata["id"]), sha, private)
