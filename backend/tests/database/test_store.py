"""PostgreSQL integration tests; require ARIADNE_TEST_DATABASE_URL."""

import os
import uuid

import psycopg
import pytest

from app.contracts.analysis import AnalysisResult
from app.database import Store, apply_schema


@pytest.fixture
def store():
    dsn = os.getenv("ARIADNE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ARIADNE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "t02_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            with psycopg.connect(dsn) as conn:
                conn.execute(f'SET search_path TO "{schema}"')
                apply_schema(conn)
                conn.commit()
                yield Store(conn)
        finally:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_same_url_is_independent_per_owner(store):
    alice = store.create_user("alice@example.test", "hash-a")
    bob = store.create_user("bob@example.test", "hash-b")
    url = "https://github.com/example/project"
    first = store.create_repository(alice, url, "project")
    second = store.create_repository(bob, url, "project")
    assert first != second
    assert store.get_repository(alice, first)["id"] == first
    assert store.get_repository(bob, second)["id"] == second
    assert store.get_repository(alice, second) is None
    assert store.get_repository(bob, first) is None
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.create_repository(alice, url, "duplicate")
    store.connection.rollback()


def test_snapshots_and_analysis_stay_with_repository_and_sha(store):
    alice = store.create_user("alice@example.test", "hash-a")
    bob = store.create_user("bob@example.test", "hash-b")
    url = "https://github.com/example/project"
    first = store.create_repository(alice, url, "project")
    second = store.create_repository(bob, url, "project")
    sha_a, sha_b = "a" * 40, "b" * 40
    snapshot = store.create_snapshot(alice, first, sha_a)
    assert store.create_snapshot(bob, first, sha_b) is None
    assert store.create_snapshot(bob, second, sha_a) != snapshot
    assert store.create_snapshot(alice, first, sha_b) != snapshot
    result = AnalysisResult.model_validate({
        "schema_version": 1, "analysis_id": "analysis-1",
        "snapshot": {"repository_id": first, "commit_sha": sha_a},
        "status": "succeeded", "findings": [], "errors": [],
    })
    assert store.save_analysis(alice, result) == "analysis-1"
    assert store.get_analysis(alice, "analysis-1") == result
    assert store.get_analysis(bob, "analysis-1") is None
    assert store.get_snapshot(bob, snapshot) is None
    assert store.get_snapshot(alice, snapshot)["commit_sha"] == sha_a
    wrong_sha = result.model_copy(update={"snapshot": result.snapshot.model_copy(update={"commit_sha": "c" * 40})})
    assert store.save_analysis(alice, wrong_sha) is None
    assert store.save_analysis(bob, result) is None


def test_child_rows_cannot_cross_repository_or_snapshot(store):
    alice = store.create_user("alice@example.test", "hash-a")
    bob = store.create_user("bob@example.test", "hash-b")
    a = store.create_repository(alice, "https://github.com/a/repo", "repo")
    b = store.create_repository(bob, "https://github.com/b/repo", "repo")
    snapshot = store.create_snapshot(alice, a, "a" * 40)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        store.connection.execute(
            "INSERT INTO analyses (id, repository_id, snapshot_id, type, result) VALUES (%s,%s,%s,%s,%s)",
            ("cross", b, snapshot, "static", "{}"),
        )
    store.connection.rollback()


def test_file_and_issue_must_share_snapshot(store):
    alice = store.create_user("alice@example.test", "hash-a")
    repo = store.create_repository(alice, "https://github.com/a/repo", "repo")
    one = store.create_snapshot(alice, repo, "a" * 40)
    two = store.create_snapshot(alice, repo, "b" * 40)
    file_id = store.connection.execute(
        """INSERT INTO repository_files (repository_id, snapshot_id, path)
           VALUES (%s, %s, %s) RETURNING id""",
        (repo, one, "src/main.py"),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with store.connection.transaction():
            store.connection.execute(
                """INSERT INTO code_issues
                   (repository_id, snapshot_id, file_id, line_number, issue_type,
                    severity, description)
                   VALUES (%s, %s, %s, 1, 'style', 'low', 'example')""",
                (repo, two, file_id),
            )
    assert store.connection.execute(
        "SELECT count(*) FROM code_issues"
    ).fetchone()[0] == 0
