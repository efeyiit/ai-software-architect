"""HTTP OAuth and server-side cookie behavior with fake GitHub responses."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import base64
from urllib.parse import parse_qs, urlsplit
from uuid import uuid5, NAMESPACE_URL

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.security.identity import OAuthConfig, OAuthService, TokenCipher
from app.security.identity.http import (
    BROWSER_COOKIE, SESSION_COOKIE, IdentityHTTP, create_identity_router,
    require_session_user,
)


NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self):
        self.login_attempts = {}
        self.states = {}
        self.users = {}
        self.tokens = {}
        self.sessions = {}

    def create_login_attempt(self, digest, browser_digest, ciphertext, expiry):
        self.login_attempts[digest] = browser_digest, ciphertext, expiry

    def consume_login_attempt(self, digest, browser_digest):
        attempt = self.login_attempts.get(digest)
        if not attempt or attempt[0] != browser_digest or attempt[2] <= NOW:
            return None
        del self.login_attempts[digest]
        return attempt[1]

    def create_state(self, digest, user, purpose, ciphertext, expiry):
        self.states[digest] = user, purpose, ciphertext, expiry

    def consume_state(self, digest, user, purpose):
        attempt = self.states.get(digest)
        if not attempt or attempt[0:2] != (user, purpose) or attempt[3] <= NOW:
            return None
        del self.states[digest]
        return attempt[2]

    def bootstrap_verified_login(self, github_id, encrypted, refresh, scopes, expiry, refresh_expiry):
        user = self.users.setdefault(github_id, str(uuid5(NAMESPACE_URL, github_id)))
        self.tokens[user, "login"] = (github_id, encrypted, refresh, scopes, expiry, refresh_expiry)
        return user

    def save_verified_token(self, user, github_id, purpose, encrypted, refresh, scopes, expiry, refresh_expiry):
        if self.users.get(github_id) != user:
            return False
        self.tokens[user, purpose] = (github_id, encrypted, refresh, scopes, expiry, refresh_expiry)
        return True

    def replace_session(self, user, digest, expires, previous_digest=None):
        if previous_digest:
            self.sessions.pop(previous_digest, None)
        for key, (owner, _) in list(self.sessions.items()):
            if owner == user:
                del self.sessions[key]
        self.sessions[digest] = (user, expires)

    def load_session(self, digest):
        saved = self.sessions.get(digest)
        return saved[0] if saved and saved[1] > NOW else None

    def delete_session(self, digest):
        self.sessions.pop(digest, None)


class FakeGitHub:
    def __init__(self):
        self.scope = ""
        self.github_id = 42
        self.exchanges = 0
        self.last_fields = None

    def exchange(self, fields):
        self.exchanges += 1
        self.last_fields = fields
        return {"access_token": "fixture-token", "token_type": "bearer", "scope": self.scope}

    def current_user(self, token):
        return {"id": self.github_id}


def fixture(configured=True):
    store, github = FakeStore(), FakeGitHub()
    app = FastAPI()
    if configured:
        config = OAuthConfig("client", "server-secret", "https://app.example/auth/github/callback")
        oauth = OAuthService(config, TokenCipher(Fernet.generate_key().decode()),
                             store, github, lambda: NOW)
        app.state.identity_http = IdentityHTTP(oauth, store, lambda: NOW)
    app.include_router(create_identity_router())

    @app.get("/protected")
    def protected(user: str = Depends(require_session_user)):
        return {"user_id": user}

    @app.post("/protected")
    def protected_post(user: str = Depends(require_session_user)):
        return {"user_id": user}

    return TestClient(app, base_url="https://app.example", follow_redirects=False), store, github


def state_from(response):
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def login(client):
    start = client.get("/auth/github/login")
    assert start.status_code == 302
    state = state_from(start)
    completed = client.get("/auth/github/callback", params={"state": state, "code": "fixture-code"})
    assert completed.status_code == 303
    return state, completed


def test_first_login_bootstrap_cookie_flags_csrf_logout_and_replay():
    client, store, github = fixture()
    assert client.get("/protected", headers={"X-User-ID": "forged"}).status_code == 401
    state, completed = login(client)
    cookie = client.cookies.get(SESSION_COOKIE)
    assert cookie and client.cookies.get(BROWSER_COOKIE) is None
    header = " ".join(completed.headers.get_list("set-cookie"))
    assert "Secure" in header and "HttpOnly" in header and "SameSite=lax" in header
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert set(me.json()) == {"user_id", "csrf_token"}
    assert me.json()["user_id"] == store.users["42"]
    assert client.post("/protected").status_code == 403
    csrf = me.json()["csrf_token"]
    assert client.post("/protected", headers={"X-Ariadne-CSRF": csrf,
                                              "X-User-ID": "forged"}).json()["user_id"] == store.users["42"]
    assert client.get("/auth/github/callback", params={"state": state, "code": "again"}).status_code == 400
    assert github.exchanges == 1
    assert client.post("/auth/logout", headers={"X-Ariadne-CSRF": csrf}).status_code == 200
    assert client.get("/auth/me").status_code == 401
    replay = TestClient(client.app, base_url="https://app.example", follow_redirects=False)
    replay.cookies.set(SESSION_COOKIE, cookie, domain="app.example", path="/")
    assert replay.get("/auth/me").status_code == 401


def test_browser_binding_wrong_browser_and_session_rotation():
    client, store, github = fixture()
    start = client.get("/auth/github/login")
    state = state_from(start)
    wrong = TestClient(client.app, base_url="https://app.example", follow_redirects=False)
    assert wrong.get("/auth/github/callback", params={"state": state, "code": "x"}).status_code == 400
    assert github.exchanges == 0
    assert client.get("/auth/github/callback", params={"state": state, "code": "x"}).status_code == 303
    old_cookie = client.cookies.get(SESSION_COOKIE)
    csrf = client.get("/auth/me").json()["csrf_token"]
    assert client.post("/auth/github/private").status_code == 403
    github.scope = "repo"
    private = client.post("/auth/github/private", headers={"X-Ariadne-CSRF": csrf})
    assert private.status_code == 302
    assert state_from(private).startswith("p_")
    connected = client.get("/auth/github/callback", params={"state": state_from(private), "code": "x"})
    assert connected.status_code == 303
    assert client.cookies.get(SESSION_COOKIE) != old_cookie
    old = TestClient(client.app, base_url="https://app.example", follow_redirects=False)
    old.cookies.set(SESSION_COOKIE, old_cookie, domain="app.example", path="/")
    assert old.get("/auth/me").status_code == 401
    assert client.get("/auth/me").status_code == 200


def test_bootstrap_pkce_and_private_state_rejects_other_session():
    client, store, github = fixture()
    start = client.get("/auth/github/login")
    params = parse_qs(urlsplit(start.headers["location"]).query)
    state = params["state"][0]
    assert params["code_challenge_method"] == ["S256"]
    assert client.get("/auth/github/callback", params={"state": state, "code": "x"}).status_code == 303
    verifier = github.last_fields["code_verifier"]
    expected = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert params["code_challenge"] == [expected]
    csrf = client.get("/auth/me").json()["csrf_token"]
    private = client.post("/auth/github/private", headers={"X-Ariadne-CSRF": csrf})
    private_state = state_from(private)
    second = TestClient(client.app, base_url="https://app.example", follow_redirects=False)
    github.github_id = 43
    login(second)
    github.scope = "repo"
    prior_exchanges = github.exchanges
    assert second.get("/auth/github/callback", params={"state": private_state,
                                                        "code": "x"}).status_code == 400
    assert github.exchanges == prior_exchanges


def test_expired_session_and_missing_configuration_fail_closed():
    client, store, _ = fixture()
    login(client)
    digest = sha256(client.cookies.get(SESSION_COOKIE).encode()).digest()
    user, _ = store.sessions[digest]
    store.sessions[digest] = user, NOW - timedelta(seconds=1)
    assert client.get("/auth/me").status_code == 401
    missing, _, _ = fixture(False)
    for path in ("/auth/me", "/auth/github/login", "/protected"):
        response = missing.get(path)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "configuration_unavailable"
