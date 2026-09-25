"""Real PostgreSQL queue checks against a fresh schema in a disposable DB."""

from concurrent.futures import ThreadPoolExecutor
import logging
import os
import uuid

import psycopg
import pytest

from app.contracts.analysis import AnalysisResult
from app.database import Store, apply_schema
from app.jobs import IdempotencyConflict, JobStore, Worker, apply_jobs_schema


@pytest.fixture
def db():
    dsn = os.getenv("ARIADNE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ARIADNE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "t22_" + uuid.uuid4().hex
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
                alice = connection.execute(
                    "INSERT INTO users(email,password_hash) VALUES ('a@test','x') RETURNING id"
                ).fetchone()[0]
                bob = connection.execute(
                    "INSERT INTO users(email,password_hash) VALUES ('b@test','x') RETURNING id"
                ).fetchone()[0]
                repo = connection.execute(
                    "INSERT INTO repositories(user_id,github_url,name) VALUES (%s,'https://github.com/a/r','r') RETURNING id",
                    (alice,),
                ).fetchone()[0]
                snapshot = connection.execute(
                    "INSERT INTO repository_snapshots(repository_id,commit_sha) VALUES (%s,%s) RETURNING id",
                    (repo, "a" * 40),
                ).fetchone()[0]
            yield connect, str(alice), str(bob), str(repo), str(snapshot)
        finally:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


def test_owner_sha_and_idempotency(db):
    connect, alice, bob, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        assert jobs.enqueue(bob, repo, "a" * 40, "key") is None
        assert jobs.enqueue(alice, repo, "b" * 40, "key") is None
        job = jobs.enqueue(alice, repo, "a" * 40, "key")
        assert job.status == "queued" and job.attempts == 0
        assert jobs.enqueue(alice, repo, "a" * 40, "key").id == job.id
        with pytest.raises(IdempotencyConflict):
            jobs.enqueue(alice, repo, "a" * 40, "key", max_attempts=4)
        assert jobs.get(bob, job.id) is None
        assert jobs.cancel(bob, job.id) is None
        assert connection.execute(
            "SELECT idempotency_hash FROM analysis_jobs WHERE id = %s", (job.id,)
        ).fetchone()[0] != "key"


def test_concurrent_idempotency_replay_creates_one_job(db):
    connect, alice, _, repo, _ = db

    def enqueue():
        with connect() as connection:
            return JobStore(connection).enqueue(alice, repo, "a" * 40, "same-key")

    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: enqueue(), range(4)))
    assert len({job.id for job in jobs}) == 1
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM analysis_jobs").fetchone()[0] == 1


def test_claim_is_exclusive_and_expired_lease_is_reclaimed(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        job = JobStore(connection).enqueue(alice, repo, "a" * 40, "claim")

    def claim():
        with connect() as connection:
            return JobStore(connection).claim(lease_seconds=3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(), range(2)))
    winner = next(item for item in claims if item is not None)
    assert sum(item is not None for item in claims) == 1
    assert winner.id == job.id and winner.attempts == 1
    with connect() as connection:
        connection.execute(
            "UPDATE analysis_jobs SET lease_until = now() - interval '1 second' WHERE id = %s",
            (job.id,),
        )
        replacement = JobStore(connection).claim(lease_seconds=3)
        assert replacement.id == job.id and replacement.attempts == 2
        assert replacement.claim_token != winner.claim_token
        assert not JobStore(connection).heartbeat(winner, lease_seconds=3)
        assert not JobStore(connection).fail(winner, "STALE", retryable=False)
        stale_result = AnalysisResult.model_validate({
            "schema_version": 1, "analysis_id": winner.id,
            "snapshot": {"repository_id": repo, "commit_sha": "a" * 40},
            "status": "succeeded", "findings": [], "errors": [],
        })
        assert not JobStore(connection).complete(winner, stale_result)
        assert connection.execute("SELECT count(*) FROM analyses").fetchone()[0] == 0


def test_retry_exhaustion_and_cancellation(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        retry = jobs.enqueue(alice, repo, "a" * 40, "retry", max_attempts=2)
        claimed = jobs.claim()
        assert jobs.fail(claimed, "RATE_LIMITED", retryable=True, retry_delay_seconds=0)
        assert jobs.get(alice, retry.id).status == "queued"
        claimed = jobs.claim()
        assert claimed.attempts == 2
        assert jobs.fail(claimed, "RATE_LIMITED", retryable=True, retry_delay_seconds=0)
        assert jobs.get(alice, retry.id).status == "failed"
        assert jobs.get(alice, retry.id).error_code == "RATE_LIMITED"

        pending = jobs.enqueue(alice, repo, "a" * 40, "pending")
        assert jobs.cancel(alice, pending.id).status == "cancelled"
        assert jobs.claim() is None
        active = jobs.enqueue(alice, repo, "a" * 40, "active")
        running = jobs.claim()
        assert running.id == active.id
        assert jobs.cancel(alice, active.id).cancel_requested
        assert not jobs.heartbeat(running)
        assert jobs.acknowledge_cancel(running)
        assert jobs.get(alice, active.id).status == "cancelled"


def test_worker_persists_result_and_redacts_handler_exception(db, caplog):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        success = jobs.enqueue(alice, repo, "a" * 40, "success")

    def handler(context):
        return AnalysisResult.model_validate({
            "schema_version": 1, "analysis_id": context.job.id,
            "snapshot": {"repository_id": context.job.repository_id,
                         "commit_sha": context.job.commit_sha},
            "status": "succeeded", "findings": [], "errors": [],
        })

    worker = Worker(connect, handler, lease_seconds=4, heartbeat_seconds=0.5)
    assert worker.process_one().id == success.id
    with connect() as connection:
        assert JobStore(connection).get(alice, success.id).status == "completed"
        assert connection.execute("SELECT count(*) FROM analyses WHERE id = %s", (success.id,)).fetchone()[0] == 1

        failed = JobStore(connection).enqueue(alice, repo, "a" * 40, "error", max_attempts=1)

    def bad_handler(_):
        raise RuntimeError("secret repository source and token")

    with caplog.at_level(logging.WARNING, logger="app.jobs.worker"):
        assert Worker(connect, bad_handler, lease_seconds=4, heartbeat_seconds=0.5).process_one().id == failed.id
    assert "secret repository source and token" not in caplog.text
    with connect() as connection:
        assert JobStore(connection).get(alice, failed.id).status == "failed"
        assert JobStore(connection).get(alice, failed.id).error_code == "ANALYSIS_FAILED"


def test_completion_rejects_wrong_snapshot_without_writing_analysis(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        job = jobs.enqueue(alice, repo, "a" * 40, "wrong-sha")
        claimed = jobs.claim()
        invalid = AnalysisResult.model_validate({
            "schema_version": 1, "analysis_id": job.id,
            "snapshot": {"repository_id": repo, "commit_sha": "b" * 40},
            "status": "succeeded", "findings": [], "errors": [],
        })
        with pytest.raises(ValueError, match="does not match"):
            jobs.complete(claimed, invalid)
        assert jobs.get(alice, job.id).status == "running"
        assert connection.execute("SELECT count(*) FROM analyses").fetchone()[0] == 0


def test_worker_cancel_during_execution_discards_result(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        job = JobStore(connection).enqueue(alice, repo, "a" * 40, "cancel-running")

    def handler(context):
        with connect() as connection:
            JobStore(connection).cancel(alice, context.job.id)
        assert context.should_stop()
        return AnalysisResult.model_validate({
            "schema_version": 1, "analysis_id": context.job.id,
            "snapshot": {"repository_id": repo, "commit_sha": "a" * 40},
            "status": "succeeded", "findings": [], "errors": [],
        })

    assert Worker(connect, handler, lease_seconds=4, heartbeat_seconds=0.5).process_one().id == job.id
    with connect() as connection:
        assert JobStore(connection).get(alice, job.id).status == "cancelled"
        assert connection.execute("SELECT count(*) FROM analyses WHERE id = %s", (job.id,)).fetchone()[0] == 0


def report(job, status: str) -> AnalysisResult:
    roles = [
        {"role": name, "status": role_status, "error_code": None}
        for name, role_status in zip(
            ("architect", "security", "testing", "refactoring", "documentation"),
            ("succeeded", "timed_out", "succeeded", "succeeded", "succeeded")
            if status == "partial" else
            ("failed", "failed", "failed", "failed", "failed")
            if status == "failed" else
            ("cancelled", "cancelled", "cancelled", "cancelled", "cancelled"),
        )
    ]
    return AnalysisResult.model_validate({
        "schema_version": 2, "analysis_id": job.id,
        "snapshot": {"repository_id": job.repository_id, "commit_sha": job.commit_sha},
        "status": status,
        "findings": [{
            "id": "retained-finding", "source": "static", "issue_type": "example",
            "severity": "low", "location": {"path": "src/main.py", "start_line": 1,
                                              "end_line": 1},
            "description": "retained evidence", "suggestion": None,
        }],
        "errors": [{"code": "ROLE_TIMEOUT", "message": "Role timed out",
                    "retryable": True, "location": None}]
        if status in ("partial", "failed") else [],
        "partial": status == "partial", "ai_status": "unavailable",
        "roles": roles, "items": [], "conflicts": [],
        "architecture": None, "testing": None, "refactoring": None,
        "documentation": None, "dependencies": None,
    })


def test_partial_is_terminal_and_report_is_owner_scoped(db):
    connect, alice, bob, repo, _ = db
    with connect() as connection:
        job = JobStore(connection).enqueue(alice, repo, "a" * 40, "partial")

    worker = Worker(connect, lambda context: report(context.job, "partial"),
                    lease_seconds=4, heartbeat_seconds=0.5)
    assert worker.process_one().id == job.id
    with connect() as connection:
        jobs = JobStore(connection)
        saved = jobs.get(alice, job.id)
        assert saved.status == "partial" and saved.result_analysis_id == job.id
        assert jobs.claim() is None
        assert Store(connection).get_analysis(alice, job.id).findings[0].id == "retained-finding"
        assert Store(connection).get_analysis(bob, job.id) is None


def test_final_failed_report_survives_retry(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        job = JobStore(connection).enqueue(alice, repo, "a" * 40, "failed-report",
                                           max_attempts=2)
    worker = Worker(connect, lambda context: report(context.job, "failed"),
                    lease_seconds=4, heartbeat_seconds=0.5, retry_delay_seconds=0)
    assert worker.process_one().id == job.id
    with connect() as connection:
        assert JobStore(connection).get(alice, job.id).status == "queued"
        assert Store(connection).get_analysis(alice, job.id) is None
    assert worker.process_one().id == job.id
    with connect() as connection:
        saved = JobStore(connection).get(alice, job.id)
        assert saved.status == "failed" and saved.result_analysis_id == job.id
        assert saved.attempts == 2
        assert Store(connection).get_analysis(alice, job.id).status == "failed"
        assert Store(connection).get_analysis(alice, job.id).findings[0].id == "retained-finding"


def test_cancelled_report_is_saved_only_under_current_claim(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        job = JobStore(connection).enqueue(alice, repo, "a" * 40, "cancel-report")

    def handler(context):
        with connect() as connection:
            JobStore(connection).cancel(alice, context.job.id)
        return report(context.job, "cancelled")

    assert Worker(connect, handler, lease_seconds=4, heartbeat_seconds=0.5).process_one().id == job.id
    with connect() as connection:
        saved = JobStore(connection).get(alice, job.id)
        assert saved.status == "cancelled" and saved.result_analysis_id == job.id
        assert Store(connection).get_analysis(alice, job.id).status == "cancelled"


def test_expired_cancel_claim_cannot_save_report(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        job = jobs.enqueue(alice, repo, "a" * 40, "expired-cancel")
        claimed = jobs.claim()
        jobs.cancel(alice, job.id)
        connection.execute(
            "UPDATE analysis_jobs SET lease_until = now() - interval '1 second' WHERE id = %s",
            (job.id,),
        )
        assert not jobs.acknowledge_cancel(claimed, report(claimed, "cancelled"))
        assert Store(connection).get_analysis(alice, job.id) is None
        assert jobs.claim() is None
        assert jobs.get(alice, job.id).status == "cancelled"


def test_schema_upgrade_preserves_existing_jobs(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        job = JobStore(connection).enqueue(alice, repo, "a" * 40, "before-upgrade")
        connection.execute("ALTER TABLE analysis_jobs DROP CONSTRAINT analysis_jobs_status_check")
        connection.execute("""ALTER TABLE analysis_jobs ADD CONSTRAINT analysis_jobs_status_check
                            CHECK (status IN ('queued','running','completed','failed','cancelled'))""")
        apply_jobs_schema(connection)
        assert JobStore(connection).get(alice, job.id).status == "queued"
        claimed = JobStore(connection).claim()
        assert JobStore(connection).complete(claimed, report(claimed, "partial"))
        assert JobStore(connection).get(alice, job.id).status == "partial"


def test_report_insert_failure_does_not_mark_job_terminal(db):
    connect, alice, _, repo, _ = db
    with connect() as connection:
        jobs = JobStore(connection)
        job = jobs.enqueue(alice, repo, "a" * 40, "atomic-result")
        claimed = jobs.claim()
        result = report(claimed, "partial")
        assert Store(connection).save_analysis(alice, result) == job.id
        with pytest.raises(psycopg.errors.UniqueViolation):
            jobs.complete(claimed, result)
        saved = jobs.get(alice, job.id)
        assert saved.status == "running" and saved.result_analysis_id is None
