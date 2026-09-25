"""Cache integration checks require an isolated PostgreSQL test database."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import uuid

import psycopg
import pytest

from app.cache import AnalysisCache, CacheKey, apply_cache_schema, config_digest
from app.contracts.analysis import AnalysisResult
from app.database import Store, apply_schema
from app.jobs import JobStore, apply_jobs_schema


@pytest.fixture
def db():
    dsn = os.getenv("ARIADNE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ARIADNE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "t23_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
        try:
            def connect():
                connection = psycopg.connect(dsn, autocommit=True)
                connection.execute(f'SET search_path TO "{schema}"')
                return connection

            with connect() as connection:
                apply_schema(connection)
                apply_jobs_schema(connection)
                apply_cache_schema(connection)
                store = Store(connection)
                alice = store.create_user("alice@test", "hash")
                bob = store.create_user("bob@test", "hash")
                repo = store.create_repository(alice, "https://github.com/example/r", "r")
                other = store.create_repository(bob, "https://github.com/example/r", "r")
                store.create_snapshot(alice, repo, "a" * 40)
                store.create_snapshot(alice, repo, "b" * 40)
                store.create_snapshot(bob, other, "a" * 40)
            yield connect, alice, bob, repo, other
        finally:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def key(user, repo, **changes):
    return replace(CacheKey(user, repo, "main", "a" * 40, config_digest({"mode": "full"}),
                            "model-1", "analysis-1"), **changes)


def complete_job(connection, user, repo, sha="a" * 40):
    jobs = JobStore(connection)
    job = jobs.enqueue(user, repo, sha, uuid.uuid4().hex)
    claimed = jobs.claim()
    assert claimed.id == job.id
    result = AnalysisResult.model_validate({
        "schema_version": 1, "analysis_id": job.id,
        "snapshot": {"repository_id": repo, "commit_sha": sha},
        "status": "succeeded", "findings": [], "errors": [],
    })
    assert jobs.complete(claimed, result)
    return result


def v2_report(job, status):
    role_statuses = (
        ("succeeded", "failed", "succeeded", "succeeded", "succeeded")
        if status == "partial" else
        ("failed",) * 5 if status == "failed" else
        ("cancelled",) * 5 if status == "cancelled" else
        ("succeeded",) * 5
    )
    return AnalysisResult.model_validate({
        "schema_version": 2, "analysis_id": job.id,
        "snapshot": {"repository_id": job.repository_id, "commit_sha": job.commit_sha},
        "status": status, "findings": [],
        "errors": [{"code": "ROLE_FAILED", "message": "Role failed",
                    "retryable": False, "location": None}]
        if status in ("partial", "failed") else [],
        "partial": status == "partial", "ai_status": "unavailable",
        "roles": [{"role": name, "status": role_status}
                  for name, role_status in zip(
                      ("architect", "security", "testing", "refactoring", "documentation"),
                      role_statuses)],
        "items": [], "conflicts": [], "architecture": None, "testing": None,
        "refactoring": None, "documentation": None, "dependencies": None,
    })


def test_reuse_requires_every_key_part_and_current_access(db):
    connect, alice, bob, repo, other = db
    checks = []

    def permission(user, repository):
        checks.append((user, repository))
        return True

    with connect() as connection:
        result = complete_job(connection, alice, repo)
        cache = AnalysisCache(connection, permission)
        original = key(alice, repo)
        assert cache.put(original, result.analysis_id, ttl_seconds=3600)
        assert cache.get(original) == result
        for altered in (
            replace(original, user_id=bob),
            replace(original, repository_id=other),
            replace(original, branch="develop"),
            replace(original, commit_sha="b" * 40),
            replace(original, config_digest=config_digest({"mode": "fast"})),
            replace(original, model_version="model-2"),
            replace(original, analysis_version="analysis-2"),
        ):
            assert cache.get(altered) is None
        assert not cache.put(key(bob, other), result.analysis_id, ttl_seconds=60)
        assert not cache.put(key(alice, repo, commit_sha="b" * 40),
                             result.analysis_id, ttl_seconds=60)
        assert len(checks) == 11

        denied = AnalysisCache(connection, lambda *_: False)
        assert denied.get(original) is None
        assert not denied.put(original, result.analysis_id, ttl_seconds=60)
        failing = AnalysisCache(connection, lambda *_: (_ for _ in ()).throw(RuntimeError("denied")))
        with pytest.raises(RuntimeError, match="denied"):
            failing.get(original)
        assert cache.get(original) == result


def test_only_completed_success_is_cacheable(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        cache = AnalysisCache(connection, lambda *_: True)
        original = key(alice, repo)
        pending = JobStore(connection).enqueue(alice, repo, "a" * 40, "pending")
        assert not cache.put(original, pending.id, ttl_seconds=60)
        claimed = JobStore(connection).claim()
        assert claimed.id == pending.id
        assert JobStore(connection).fail(claimed, "FAILED", retryable=False)
        assert not cache.put(original, pending.id, ttl_seconds=60)
        assert cache.get(original) is None

        result = complete_job(connection, alice, repo)
        assert cache.put(original, result.analysis_id, ttl_seconds=60)
        connection.execute("UPDATE analyses SET result = jsonb_set(result, '{status}', '\"failed\"') WHERE id = %s",
                           (result.analysis_id,))
        assert cache.get(original) is None
        assert not cache.put(original, result.analysis_id, ttl_seconds=60)


def test_v2_terminal_reports_never_become_successful_hits(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        cache = AnalysisCache(connection, lambda *_: True)
        original = key(alice, repo)
        terminal_ids = []
        for status in ("partial", "failed", "cancelled"):
            job = jobs.enqueue(alice, repo, "a" * 40, "v2-" + status)
            claimed = jobs.claim()
            assert claimed.id == job.id
            report = v2_report(claimed, status)
            if status == "partial":
                assert jobs.complete(claimed, report)
            elif status == "failed":
                assert jobs.fail(claimed, "ROLE_FAILED", retryable=False, result=report)
            else:
                jobs.cancel(alice, job.id)
                assert jobs.acknowledge_cancel(claimed, report)
            assert jobs.get(alice, job.id).status == status
            assert Store(connection).get_analysis(alice, job.id) == report
            assert not cache.put(original, job.id, ttl_seconds=60)
            assert cache.get(original) is None
            terminal_ids.append(job.id)

        success = jobs.enqueue(alice, repo, "a" * 40, "v2-success")
        claimed = jobs.claim()
        assert claimed.id == success.id
        result = v2_report(claimed, "succeeded")
        assert jobs.complete(claimed, result)
        assert cache.put(original, success.id, ttl_seconds=60)
        assert cache.get(original) == result

        # A stale or directly modified mapping must also fail closed on lookup.
        for analysis_id in terminal_ids:
            connection.execute("UPDATE analysis_cache SET analysis_id = %s", (analysis_id,))
            assert cache.get(original) is None
        connection.execute("UPDATE analysis_cache SET analysis_id = %s", (success.id,))
        connection.execute(
            "UPDATE analyses SET result = jsonb_set(result, '{partial}', 'true') WHERE id = %s",
            (success.id,),
        )
        assert cache.get(original) is None
        assert not cache.put(original, success.id, ttl_seconds=60)


def test_expiry_invalidation_and_concurrent_writes(db):
    connect, alice, bob, repo, _ = db
    with connect() as connection:
        result = complete_job(connection, alice, repo)
        original = key(alice, repo)

    def write(_):
        with connect() as connection:
            return AnalysisCache(connection, lambda *_: True).put(
                original, result.analysis_id, ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(pool.map(write, range(12)))
    with connect() as connection:
        cache = AnalysisCache(connection, lambda *_: True)
        assert connection.execute("SELECT count(*) FROM analysis_cache").fetchone()[0] == 1
        assert cache.get(original) == result
        connection.execute("UPDATE analysis_cache SET expires_at = now() - interval '1 second'")
        assert cache.get(original) is None
        assert cache.prune_expired() == 1
        assert cache.prune_expired() == 0
        assert cache.put(original, result.analysis_id, ttl_seconds=60)
        assert cache.get(original) == result
        assert cache.invalidate(bob, repo) == 0
        assert cache.invalidate(alice, repo, branch="develop") == 0
        assert cache.invalidate(alice, repo, branch="main") == 1
        assert cache.get(original) is None


def test_invalid_key_and_ttl_are_rejected(db):
    connect, alice, _, repo, _ = db
    with pytest.raises(ValueError, match="commit_sha"):
        key(alice, repo, commit_sha="short")
    with connect() as connection:
        cache = AnalysisCache(connection, lambda *_: True)
        with pytest.raises(ValueError, match="ttl_seconds"):
            cache.put(key(alice, repo), "unused", ttl_seconds=0)
