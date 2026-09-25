"""T04 OAuth tables against the existing T02 PostgreSQL ownership schema."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import uuid

import psycopg
import pytest

from app.database import Store, apply_schema
from app.security.identity.store import PostgresIdentityStore, apply_identity_schema


@pytest.fixture
def identity_db():
    dsn = os.getenv("ARIADNE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ARIADNE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "t04_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(f'SET search_path TO "{schema}"')
                apply_schema(conn)
                yield conn, schema, dsn
        finally:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_additive_oauth_schema_preserves_user_and_owner_boundaries(identity_db):
    conn, _, _ = identity_db
    base = Store(conn)
    alice = base.create_user("t04-alice@example.test", "hash-a")
    bob = base.create_user("t04-bob@example.test", "hash-b")
    repo = base.create_repository(alice, "https://github.com/example/private", "private")
    apply_identity_schema(conn)
    apply_identity_schema(conn)
    assert base.get_repository(alice, repo)["id"] == repo
    assert base.get_repository(bob, repo) is None

    identity = PostgresIdentityStore(conn)
    digest = bytes(range(32))
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    identity.create_state(digest, alice, "private", b"encrypted-verifier", expires)
    assert identity.consume_state(digest, bob, "private") is None
    assert identity.consume_state(digest, alice, "login") is None
    assert identity.consume_state(digest, alice, "private") == b"encrypted-verifier"
    assert identity.consume_state(digest, alice, "private") is None

    expired_digest = bytes(range(1, 33))
    identity.create_state(
        expired_digest, alice, "private", b"expired-ciphertext",
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert identity.consume_state(expired_digest, alice, "private") is None

    assert identity.save_verified_token(
        alice, "github-alice", "private", b"encrypted-token", None,
        {"repo"}, None, None,
    )
    assert identity.load_token(bob, "private") is None
    assert identity.load_token(alice, "login") is None
    assert identity.load_token(alice, "private")[1] == b"encrypted-token"
    assert identity.save_verified_token(
        alice, "different-github", "private", b"replacement", None,
        {"repo"}, None, None,
    ) is False
    assert identity.load_token(alice, "private")[1] == b"encrypted-token"
    assert identity.save_verified_token(
        bob, "github-alice", "private", b"foreign-token", None,
        {"repo"}, None, None,
    ) is False
    assert identity.load_token(bob, "private") is None


def test_oauth_state_consume_is_atomic_across_connections(identity_db):
    conn, schema, dsn = identity_db
    user = Store(conn).create_user("t04-atomic@example.test", "hash")
    apply_identity_schema(conn)
    digest = bytes(range(32))
    PostgresIdentityStore(conn).create_state(
        digest, user, "login", b"encrypted-verifier",
        datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    with psycopg.connect(dsn, autocommit=True) as second:
        second.execute(f'SET search_path TO "{schema}"')
        stores = (PostgresIdentityStore(conn), PostgresIdentityStore(second))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda store: store.consume_state(digest, user, "login"), stores
            ))
    assert sorted(results, key=lambda value: value is None) == [
        b"encrypted-verifier", None
    ]
