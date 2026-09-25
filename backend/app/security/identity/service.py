"""OAuth authorization-code flow with PKCE, one-use state and encrypted tokens."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class IdentityError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str

    def __post_init__(self):
        url = urlsplit(self.redirect_uri)
        if (not self.client_id or not self.client_secret or
                url.scheme != "https" or not url.netloc or url.username or url.password or
                url.query or url.fragment):
            raise IdentityError("CONFIGURATION_ERROR", "GitHub OAuth client and HTTPS callback must be configured")

    @classmethod
    def from_env(cls):
        return cls(os.getenv("ARIADNE_GITHUB_CLIENT_ID", ""),
                   os.getenv("ARIADNE_GITHUB_CLIENT_SECRET", ""),
                   os.getenv("ARIADNE_GITHUB_REDIRECT_URI", ""))


class TokenCipher:
    """Fernet authenticated encryption; first key encrypts, all keys can decrypt."""

    def __init__(self, keys: str):
        try:
            self._fernet = MultiFernet([Fernet(key.strip().encode("ascii"))
                                        for key in keys.split(",") if key.strip()])
        except (ValueError, TypeError) as exc:
            raise IdentityError("CONFIGURATION_ERROR", "Valid OAuth encryption key is required") from exc

    @classmethod
    def from_env(cls):
        return cls(os.getenv("ARIADNE_OAUTH_FERNET_KEYS", ""))

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode("utf-8"))

    def decrypt(self, value: bytes) -> str:
        try:
            return self._fernet.decrypt(value).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise IdentityError("CREDENTIAL_UNAVAILABLE", "Stored GitHub credential cannot be read; reconnect GitHub") from exc


class IdentityStore(Protocol):
    def create_state(self, digest, user_id, purpose, verifier_ciphertext, expires_at): ...
    def consume_state(self, digest, user_id, purpose): ...
    def create_login_attempt(self, digest, browser_digest, verifier_ciphertext, expires_at): ...
    def consume_login_attempt(self, digest, browser_digest): ...
    def bootstrap_verified_login(self, github_id, token_ciphertext, refresh_ciphertext,
                                 scopes, expires_at, refresh_expires_at): ...
    def save_verified_token(self, user_id, github_id, purpose, token_ciphertext,
                            refresh_ciphertext, scopes, expires_at, refresh_expires_at): ...
    def load_token(self, user_id, purpose): ...


class OAuthAPI(Protocol):
    def exchange(self, fields: dict[str, str]) -> dict[str, Any]: ...
    def current_user(self, token: str) -> dict[str, Any]: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class GitHubOAuthHTTP:
    def __init__(self):
        self._opener = build_opener(_NoRedirect)

    def _json(self, request: Request) -> dict[str, Any]:
        try:
            with self._opener.open(request, timeout=15) as response:
                raw = response.read(65_537)
            if len(raw) > 65_536:
                raise ValueError("oversized response")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("invalid object")
            return result
        except HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise IdentityError("GITHUB_ACCESS_DENIED", "GitHub denied the credential") from None
            raise IdentityError("GITHUB_UNAVAILABLE", "GitHub OAuth request failed", retryable=exc.code >= 500) from None
        except (URLError, TimeoutError):
            raise IdentityError("GITHUB_UNAVAILABLE", "GitHub could not be reached", retryable=True) from None
        except (ValueError, UnicodeError):
            raise IdentityError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid OAuth response") from None

    def exchange(self, fields: dict[str, str]) -> dict[str, Any]:
        request = Request("https://github.com/login/oauth/access_token",
                          data=urlencode(fields).encode("ascii"),
                          headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded",
                                   "User-Agent": "Ariadne-OAuth"}, method="POST")
        return self._json(request)

    def current_user(self, token: str) -> dict[str, Any]:
        request = Request("https://api.github.com/user",
                          headers={"Accept": "application/vnd.github+json",
                                   "Authorization": "Bearer " + token,
                                   "User-Agent": "Ariadne-OAuth", "X-GitHub-Api-Version": "2022-11-28"})
        return self._json(request)


def _expiry(value: Any, now: datetime) -> datetime | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise IdentityError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid token lifetime")
    return now + timedelta(seconds=value)


class OAuthService:
    def __init__(self, config: OAuthConfig, cipher: TokenCipher, store: IdentityStore,
                 api: OAuthAPI | None = None, clock: Callable[[], datetime] | None = None):
        self.config, self.cipher, self.store = config, cipher, store
        self.api = api or GitHubOAuthHTTP()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def start(self, local_user_id: str, purpose: str) -> str:
        if not local_user_id or purpose not in ("login", "private"):
            raise IdentityError("INVALID_REQUEST", "A local user and OAuth purpose are required")
        state = "p_" + secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        self.store.create_state(hashlib.sha256(state.encode("ascii")).digest(), local_user_id,
                                purpose, self.cipher.encrypt(verifier), self.clock() + timedelta(minutes=10))
        return self._authorization_url(state, verifier, purpose)

    def start_login(self, browser_binding: str) -> str:
        if not isinstance(browser_binding, str) or not 20 <= len(browser_binding) <= 200:
            raise IdentityError("INVALID_REQUEST", "A fresh browser login binding is required")
        state = "l_" + secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        self.store.create_login_attempt(hashlib.sha256(state.encode("ascii")).digest(),
                                        hashlib.sha256(browser_binding.encode("utf-8")).digest(),
                                        self.cipher.encrypt(verifier), self.clock() + timedelta(minutes=10))
        return self._authorization_url(state, verifier, "login")

    def _authorization_url(self, state: str, verifier: str, purpose: str) -> str:
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        params = {"client_id": self.config.client_id, "redirect_uri": self.config.redirect_uri,
                  "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
                  "scope": "repo offline_access" if purpose == "private" else "offline_access"}
        return "https://github.com/login/oauth/authorize?" + urlencode(params)

    def finish(self, local_user_id: str, purpose: str, state: str, code: str) -> str:
        if (not local_user_id or purpose not in ("login", "private") or
                not isinstance(state, str) or not 20 <= len(state) <= 200 or
                not isinstance(code, str) or not 1 <= len(code) <= 1024):
            raise IdentityError("INVALID_REQUEST", "Invalid GitHub OAuth callback")
        ciphertext = self.store.consume_state(hashlib.sha256(state.encode("utf-8")).digest(),
                                              local_user_id, purpose)
        if ciphertext is None:
            raise IdentityError("INVALID_STATE", "GitHub sign-in expired or was already used")
        verifier = self.cipher.decrypt(ciphertext)
        github_id, token, refresh, scopes, expires_at, refresh_expires_at = self._verified_grant(
            code, verifier, purpose)
        if not self.store.save_verified_token(local_user_id, github_id, purpose,
                                              self.cipher.encrypt(token),
                                              self.cipher.encrypt(refresh) if refresh else None,
                                              scopes, expires_at, refresh_expires_at):
            raise IdentityError("ACCOUNT_MISMATCH", "This local account is linked to another GitHub account")
        return github_id

    def finish_login(self, browser_binding: str, state: str, code: str) -> str:
        if (not isinstance(browser_binding, str) or not 20 <= len(browser_binding) <= 200 or
                not isinstance(state, str) or not state.startswith("l_") or
                not 20 <= len(state) <= 200 or not isinstance(code, str) or
                not 1 <= len(code) <= 1024):
            raise IdentityError("INVALID_REQUEST", "Invalid GitHub login callback")
        ciphertext = self.store.consume_login_attempt(
            hashlib.sha256(state.encode("utf-8")).digest(),
            hashlib.sha256(browser_binding.encode("utf-8")).digest())
        if ciphertext is None:
            raise IdentityError("INVALID_STATE", "GitHub login expired or was already used")
        verifier = self.cipher.decrypt(ciphertext)
        github_id, token, refresh, scopes, expires_at, refresh_expires_at = self._verified_grant(
            code, verifier, "login")
        user_id = self.store.bootstrap_verified_login(
            github_id, self.cipher.encrypt(token),
            self.cipher.encrypt(refresh) if refresh else None,
            scopes, expires_at, refresh_expires_at)
        if user_id is None:
            raise IdentityError("ACCOUNT_CONFLICT", "GitHub account cannot be linked automatically")
        return user_id

    def _verified_grant(self, code: str, verifier: str, purpose: str):
        response = self.api.exchange({"client_id": self.config.client_id,
                                      "client_secret": self.config.client_secret,
                                      "code": code, "redirect_uri": self.config.redirect_uri,
                                      "code_verifier": verifier})
        token = response.get("access_token")
        token_type = response.get("token_type", "bearer")
        if not isinstance(token, str) or not token or not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise IdentityError("GITHUB_ACCESS_DENIED", "GitHub did not grant access; reconnect GitHub")
        scopes = frozenset(response.get("scope", "").split(",")) - {""} if isinstance(response.get("scope"), str) else frozenset()
        if purpose == "private" and "repo" not in scopes:
            raise IdentityError("INSUFFICIENT_SCOPE", "Private repositories require the GitHub repo permission")
        user = self.api.current_user(token)
        github_id = user.get("id")
        if type(github_id) is not int or github_id < 1:
            raise IdentityError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid account")
        now = self.clock()
        refresh = response.get("refresh_token")
        if refresh is not None and (not isinstance(refresh, str) or not refresh):
            raise IdentityError("INVALID_GITHUB_RESPONSE", "GitHub returned an invalid refresh credential")
        expires_at = _expiry(response.get("expires_in"), now)
        refresh_expires_at = _expiry(response.get("refresh_token_expires_in"), now)
        if expires_at and not refresh:
            raise IdentityError("INVALID_GITHUB_RESPONSE", "Expiring GitHub token has no refresh credential")
        return str(github_id), token, refresh, scopes, expires_at, refresh_expires_at

    def valid_token(self, local_user_id: str, purpose: str) -> str:
        if not local_user_id or purpose not in ("login", "private"):
            raise IdentityError("INVALID_REQUEST", "A local user and OAuth purpose are required")
        saved = self.store.load_token(local_user_id, purpose)
        if saved is None:
            raise IdentityError("GITHUB_CONNECTION_REQUIRED", "Connect this account to GitHub")
        github_id, encrypted, refresh_encrypted, scopes, expires_at, refresh_expires_at = saved
        if purpose == "private" and "repo" not in scopes:
            raise IdentityError("INSUFFICIENT_SCOPE", "Private repositories require the GitHub repo permission")
        now = self.clock()
        if expires_at is not None and expires_at <= now + timedelta(seconds=30):
            if not refresh_encrypted or (refresh_expires_at and refresh_expires_at <= now):
                raise IdentityError("GITHUB_CONNECTION_REQUIRED", "GitHub authorization expired; reconnect GitHub")
            response = self.api.exchange({"client_id": self.config.client_id,
                                          "client_secret": self.config.client_secret,
                                          "grant_type": "refresh_token",
                                          "refresh_token": self.cipher.decrypt(refresh_encrypted)})
            token = response.get("access_token")
            new_refresh = response.get("refresh_token")
            if not isinstance(token, str) or not token or not isinstance(new_refresh, str) or not new_refresh:
                raise IdentityError("GITHUB_CONNECTION_REQUIRED", "GitHub authorization expired; reconnect GitHub")
            scope_value = response.get("scope")
            if not isinstance(scope_value, str):
                raise IdentityError("INVALID_GITHUB_RESPONSE", "GitHub returned invalid token permissions")
            new_scopes = frozenset(scope_value.split(",")) - {""}
            if purpose == "private" and "repo" not in new_scopes:
                raise IdentityError("INSUFFICIENT_SCOPE", "Private repository permission was removed")
            user = self.api.current_user(token)
            if user.get("id") != int(github_id):
                raise IdentityError("ACCOUNT_MISMATCH", "GitHub account changed; reconnect GitHub")
            if not self.store.save_verified_token(local_user_id, github_id, purpose,
                                                  self.cipher.encrypt(token), self.cipher.encrypt(new_refresh),
                                                  new_scopes, _expiry(response.get("expires_in"), now),
                                                  _expiry(response.get("refresh_token_expires_in"), now)):
                raise IdentityError("ACCOUNT_MISMATCH", "GitHub account changed; reconnect GitHub")
            return token
        token = self.cipher.decrypt(encrypted)
        user = self.api.current_user(token)
        if user.get("id") != int(github_id):
            raise IdentityError("ACCOUNT_MISMATCH", "GitHub account changed; reconnect GitHub")
        return token
