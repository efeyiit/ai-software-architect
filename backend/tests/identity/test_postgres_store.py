"""Real PostgreSQL checks run when ARIADNE_TEST_DATABASE_URL points to disposable DB."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import uuid
from urllib.parse import parse_qs, urlsplit

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Store, apply_schema
from app.security.identity import (
    OAuthConfig, OAuthService, PostgresIdentityStore, TokenCipher, apply_identity_schema,
)
from app.security.identity.http import IdentityHTTP, create_identity_router
from app.services.github_private.scope import LiveRepositoryScopeResolver
from app.services.github_public import GitHubPublicError


@pytest.fixture
def db():
    dsn = os.getenv("ARIADNE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ARIADNE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "t04_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(f'SET search_path TO "{schema}"')
                apply_schema(connection)
                apply_identity_schema(connection)
                yield dsn, schema, connection
        finally:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_encrypted_owner_scoped_persistence_and_identity_conflict(db):
    _, _, connection = db
    store = PostgresIdentityStore(connection)
    alice = connection.execute("INSERT INTO users(email,password_hash) VALUES ('a@test','x') RETURNING id").fetchone()[0]
    bob = connection.execute("INSERT INTO users(email,password_hash) VALUES ('b@test','x') RETURNING id").fetchone()[0]
    cipher = TokenCipher(Fernet.generate_key().decode())
    ciphertext = cipher.encrypt("fixture-secret")
    assert store.save_verified_token(alice, "42", "private", ciphertext, None, {"repo"}, None, None)
    assert store.load_token(bob, "private") is None
    assert store.load_token(alice, "private")[1] == ciphertext
    row = connection.execute("SELECT token_ciphertext FROM oauth_connections WHERE user_id = %s", (alice,)).fetchone()
    assert b"fixture-secret" not in bytes(row[0])
    assert not store.save_verified_token(bob, "42", "private", ciphertext, None, {"repo"}, None, None)
    assert store.load_token(bob, "private") is None
    assert not store.save_verified_token(alice, "99", "private", ciphertext, None, {"repo"}, None, None)
    assert store.load_token(alice, "private")[0] == "42"


def test_atomic_state_consume_owner_expiry_and_concurrent_replay(db):
    dsn, schema, connection = db
    alice = connection.execute("INSERT INTO users(email,password_hash) VALUES ('c@test','x') RETURNING id").fetchone()[0]
    bob = connection.execute("INSERT INTO users(email,password_hash) VALUES ('d@test','x') RETURNING id").fetchone()[0]
    store = PostgresIdentityStore(connection)
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    store.create_state(b"a" * 32, alice, "private", b"encrypted-verifier", future)
    assert store.consume_state(b"a" * 32, bob, "private") is None
    assert store.consume_state(b"a" * 32, alice, "login") is None
    def consume():
        with psycopg.connect(dsn, autocommit=True) as worker:
            worker.execute(f'SET search_path TO "{schema}"')
            return PostgresIdentityStore(worker).consume_state(b"a" * 32, alice, "private")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert results.count(b"encrypted-verifier") == 1
    assert results.count(None) == 1
    store.create_state(b"b" * 32, alice, "private", b"encrypted-verifier",
                       datetime.now(timezone.utc) - timedelta(seconds=1))
    assert store.consume_state(b"b" * 32, alice, "private") is None


def test_live_scope_resolver_with_real_owner_store(db):
    _, _, connection = db
    base = Store(connection)
    alice = base.create_user("scope-a@test", "hash")
    bob = base.create_user("scope-b@test", "hash")
    repo = base.create_repository(alice, "https://github.com/owner/secret", "secret")

    class Public:
        def get_json(self, path, max_bytes):
            raise GitHubPublicError("REPOSITORY_NOT_FOUND", "Not public")

    class Identity:
        calls = 0
        def valid_token(self, caller, purpose):
            self.calls += 1
            assert caller == alice and purpose == "private"
            return "fixture-token"

    class Private:
        sha = "a" * 40
        def get_json(self, path, max_bytes):
            if path == "/repos/owner/secret":
                return {"id": 42, "full_name": "owner/secret", "private": True,
                        "default_branch": "main"}
            if path == "/repos/owner/secret/commits/main":
                return {"sha": self.sha}
            raise AssertionError(path)

    identity, private = Identity(), Private()
    resolver = LiveRepositoryScopeResolver(base, identity, Public(), lambda token: private)
    assert resolver(bob, repo) is None
    assert identity.calls == 0
    scope = resolver(alice, repo)
    assert (scope.owner_id, scope.repository_id, scope.source_repository_id,
            scope.commit_sha, scope.private) == (alice, repo, "42", "a" * 40, True)
    private.sha = "b" * 40
    assert resolver(alice, repo).commit_sha == "b" * 40


def test_real_database_http_bootstrap_session_and_disabled_password(db):
    _, _, connection = db

    class GitHub:
        def exchange(self, fields):
            return {"access_token": "fixture-access-token", "scope": "",
                    "token_type": "bearer"}
        def current_user(self, token):
            return {"id": 98765, "email": "unverified@example.test"}

    store = PostgresIdentityStore(connection)
    config = OAuthConfig("client", "secret", "https://app.example/auth/github/callback")
    oauth = OAuthService(config, TokenCipher(Fernet.generate_key().decode()), store, GitHub())
    app = FastAPI()
    app.state.identity_http = IdentityHTTP(oauth, store)
    app.include_router(create_identity_router())
    client = TestClient(app, base_url="https://app.example", follow_redirects=False)
    start = client.get("/auth/github/login")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    assert client.get("/auth/github/callback", params={"state": state, "code": "fixture"}).status_code == 303
    user_id = client.get("/auth/me").json()["user_id"]
    row = connection.execute(
        "SELECT email, password_hash, github_id FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    assert row[0] == "github-98765@ariadne.invalid"
    assert row[0] != "unverified@example.test"
    assert row[1].startswith("!oauth-disabled:")
    assert not row[1].startswith(("$2", "$argon2", "pbkdf2:"))
    assert row[2] == "98765"
    assert connection.execute("SELECT count(*) FROM users WHERE github_id = '98765'").fetchone()[0] == 1
    assert client.get("/auth/github/callback", params={"state": state, "code": "replay"}).status_code == 400
    second = client.get("/auth/github/login")
    next_state = parse_qs(urlsplit(second.headers["location"]).query)["state"][0]
    assert client.get("/auth/github/callback", params={"state": next_state, "code": "fixture"}).status_code == 303
    assert client.get("/auth/me").json()["user_id"] == user_id
    assert connection.execute("SELECT count(*) FROM users WHERE github_id = '98765'").fetchone()[0] == 1
    session_cookie = client.cookies.get("__Host-ariadne_session")
    csrf = client.get("/auth/me").json()["csrf_token"]
    assert client.post("/auth/logout", headers={"X-Ariadne-CSRF": csrf}).status_code == 200
    assert client.get("/auth/me").status_code == 401
    replay = TestClient(app, base_url="https://app.example", follow_redirects=False)
    replay.cookies.set("__Host-ariadne_session", session_cookie,
                       domain="app.example", path="/")
    assert replay.get("/auth/me").status_code == 401


def test_concurrent_first_login_maps_one_github_id_to_one_user(db):
    dsn, schema, connection = db
    cipher = TokenCipher(Fernet.generate_key().decode())
    for github_id in (str(number) for number in range(8888, 8896)):
        def bootstrap():
            with psycopg.connect(dsn, autocommit=True) as worker:
                worker.execute(f'SET search_path TO "{schema}"')
                return PostgresIdentityStore(worker).bootstrap_verified_login(
                    github_id, cipher.encrypt("token"), None, frozenset(), None, None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(lambda _: bootstrap(), range(2))
        assert first == second
        assert connection.execute(
            "SELECT count(*) FROM users WHERE github_id = %s", (github_id,)
        ).fetchone()[0] == 1
    # A synthetic email occupied by an unrelated account is never auto-linked.
    connection.execute("INSERT INTO users(email,password_hash) VALUES ('github-9999@ariadne.invalid','hash')")
    assert PostgresIdentityStore(connection).bootstrap_verified_login(
        "9999", cipher.encrypt("token"), None, frozenset(), None, None) is None
    assert connection.execute("SELECT count(*) FROM users WHERE github_id = '9999'").fetchone()[0] == 0


def test_anonymous_login_state_is_atomic_and_browser_bound(db):
    dsn, schema, connection = db
    store = PostgresIdentityStore(connection)
    state_digest = bytes(range(32))
    browser_digest = bytes(range(1, 33))
    store.create_login_attempt(state_digest, browser_digest, b"encrypted-pkce",
                               datetime.now(timezone.utc) + timedelta(minutes=5))
    assert store.consume_login_attempt(state_digest, bytes(range(2, 34))) is None
    def consume():
        with psycopg.connect(dsn, autocommit=True) as worker:
            worker.execute(f'SET search_path TO "{schema}"')
            return PostgresIdentityStore(worker).consume_login_attempt(state_digest, browser_digest)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert results.count(b"encrypted-pkce") == 1
    assert results.count(None) == 1
    store.create_login_attempt(b"z" * 32, browser_digest, b"encrypted-pkce",
                               datetime.now(timezone.utc) - timedelta(seconds=1))
    assert store.consume_login_attempt(b"z" * 32, browser_digest) is None
