"""Atomic PostgreSQL transitions for analysis jobs.

Connections must use autocommit=True. Each operation opens its own short
transaction; no database lock is held while analysis code runs.
"""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from psycopg.rows import dict_row

from app.contracts.analysis import AnalysisResult, AnalysisStatus
from app.database import Store


class IdempotencyConflict(ValueError):
    """The same owner's key was already used for another snapshot or policy."""


@dataclass(frozen=True)
class Job:
    id: str
    user_id: str
    repository_id: str
    snapshot_id: str
    commit_sha: str
    status: str
    attempts: int
    max_attempts: int
    cancel_requested: bool
    claim_token: str | None
    error_code: str | None
    result_analysis_id: str | None


def apply_jobs_schema(connection) -> None:
    """Install the additive job schema after the core database schema."""
    connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))


class JobStore:
    def __init__(self, connection):
        if not connection.autocommit:
            raise ValueError("JobStore requires an autocommit PostgreSQL connection")
        self.connection = connection

    def _job(self, row) -> Job | None:
        if row is None:
            return None
        return Job(**{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()})

    def _select(self, where: str, params: tuple) -> Job | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute(
                """SELECT j.id, j.user_id, j.repository_id, j.snapshot_id,
                          s.commit_sha, j.status, j.attempts, j.max_attempts,
                          j.cancel_requested, j.claim_token, j.error_code,
                          j.result_analysis_id
                   FROM analysis_jobs j
                   JOIN repository_snapshots s ON s.id = j.snapshot_id
                   WHERE """ + where,
                params,
            ).fetchone()
        return self._job(row)

    def enqueue(self, user_id: str, repository_id: str, commit_sha: str,
                idempotency_key: str, *, max_attempts: int = 3) -> Job | None:
        """Return an existing identical job for a replay; None for foreign/missing input."""
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key must be nonempty")
        if not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        key_hash = sha256(idempotency_key.encode("utf-8")).hexdigest()
        with self.connection.transaction():
            row = self.connection.execute(
                """INSERT INTO analysis_jobs
                       (user_id, repository_id, snapshot_id, idempotency_hash, max_attempts)
                   SELECT r.user_id, r.id, s.id, %s, %s
                   FROM repositories r
                   JOIN repository_snapshots s ON s.repository_id = r.id
                   WHERE r.id = %s AND r.user_id = %s AND s.commit_sha = %s
                   ON CONFLICT (user_id, idempotency_hash) DO NOTHING
                   RETURNING id""",
                (key_hash, max_attempts, repository_id, user_id, commit_sha),
            ).fetchone()
            if row:
                return self.get(user_id, str(row[0]))
            existing = self._select("j.user_id = %s AND j.idempotency_hash = %s",
                                    (user_id, key_hash))
            if existing is None:
                return None
            if (existing.repository_id != repository_id or existing.commit_sha != commit_sha
                    or existing.max_attempts != max_attempts):
                raise IdempotencyConflict("idempotency key already belongs to another request")
            return existing

    def get(self, user_id: str, job_id: str) -> Job | None:
        return self._select("j.id = %s AND j.user_id = %s", (job_id, user_id))

    def cancel(self, user_id: str, job_id: str) -> Job | None:
        """Cancel queued work immediately; request cooperative cancellation if running."""
        with self.connection.transaction():
            self.connection.execute(
                """UPDATE analysis_jobs SET
                       status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                       cancel_requested = CASE WHEN status IN ('queued', 'running')
                           THEN true ELSE cancel_requested END,
                       updated_at = now()
                   WHERE id = %s AND user_id = %s AND status IN ('queued', 'running')""",
                (job_id, user_id),
            )
            return self.get(user_id, job_id)

    def claim(self, *, lease_seconds: int = 60) -> Job | None:
        if lease_seconds < 2:
            raise ValueError("lease_seconds must be at least 2")
        with self.connection.transaction():
            # Expired jobs at their attempt limit cannot be run again.
            self.connection.execute(
                """UPDATE analysis_jobs SET status = CASE WHEN cancel_requested
                           THEN 'cancelled' ELSE 'failed' END,
                       error_code = CASE WHEN cancel_requested THEN NULL ELSE 'LEASE_EXPIRED' END,
                       claim_token = NULL, lease_until = NULL, updated_at = now()
                   WHERE status = 'running' AND lease_until <= now()
                     AND (cancel_requested OR attempts >= max_attempts)"""
            )
            row = self.connection.execute(
                """WITH candidate AS (
                       SELECT id FROM analysis_jobs
                       WHERE (status = 'queued' AND available_at <= now())
                          OR (status = 'running' AND lease_until <= now()
                              AND attempts < max_attempts AND NOT cancel_requested)
                       ORDER BY available_at, created_at
                       FOR UPDATE SKIP LOCKED LIMIT 1
                   )
                   UPDATE analysis_jobs j SET status = 'running',
                       attempts = j.attempts + 1, claim_token = gen_random_uuid(),
                       lease_until = now() + make_interval(secs => %s),
                       cancel_requested = false, error_code = NULL, updated_at = now()
                   FROM candidate WHERE j.id = candidate.id RETURNING j.id, j.user_id""",
                (lease_seconds,),
            ).fetchone()
            return self.get(str(row[1]), str(row[0])) if row else None

    def heartbeat(self, job: Job, *, lease_seconds: int = 60) -> bool:
        row = self.connection.execute(
            """UPDATE analysis_jobs SET lease_until = now() + make_interval(secs => %s),
                   updated_at = now()
               WHERE id = %s AND claim_token = %s AND status = 'running'
                 AND lease_until > now() AND NOT cancel_requested RETURNING id""",
            (lease_seconds, job.id, job.claim_token),
        ).fetchone()
        return row is not None

    def should_stop(self, job: Job) -> bool:
        row = self.connection.execute(
            """SELECT cancel_requested OR status <> 'running' OR claim_token <> %s
                      OR lease_until <= now()
               FROM analysis_jobs WHERE id = %s""",
            (job.claim_token, job.id),
        ).fetchone()
        return row is None or bool(row[0])

    @staticmethod
    def _check_result(job: Job, result: AnalysisResult, statuses: tuple[AnalysisStatus, ...]) -> None:
        if (result.analysis_id != job.id or result.snapshot.repository_id != job.repository_id
                or result.snapshot.commit_sha != job.commit_sha or result.status not in statuses):
            raise ValueError("result does not match the claimed job and snapshot")

    def acknowledge_cancel(self, job: Job, result: AnalysisResult | None = None) -> bool:
        if result is not None:
            self._check_result(job, result, (AnalysisStatus.cancelled,))
        with self.connection.transaction():
            row = self.connection.execute(
                """SELECT id FROM analysis_jobs WHERE id = %s AND claim_token = %s
                     AND status = 'running' AND cancel_requested
                     AND lease_until > now() FOR UPDATE""",
                (job.id, job.claim_token),
            ).fetchone()
            if row is None:
                return False
            if result is not None and Store(self.connection).save_analysis(job.user_id, result) != job.id:
                raise ValueError("repository ownership or snapshot changed")
            self.connection.execute(
                """UPDATE analysis_jobs SET status = 'cancelled', claim_token = NULL,
                       lease_until = NULL, result_analysis_id = %s, updated_at = now()
                   WHERE id = %s""",
                (job.id if result is not None else None, job.id),
            )
            return True

    def fail(self, job: Job, code: str, *, retryable: bool,
             retry_delay_seconds: int = 1, result: AnalysisResult | None = None) -> bool:
        if not code.isascii() or not code.replace("_", "").isalnum() or code != code.upper():
            raise ValueError("error code must be a stable uppercase identifier")
        if result is not None:
            self._check_result(job, result, (AnalysisStatus.failed,))
        with self.connection.transaction():
            row = self.connection.execute(
                """SELECT cancel_requested, attempts, max_attempts FROM analysis_jobs
                   WHERE id = %s AND claim_token = %s AND status = 'running'
                     AND lease_until > now() FOR UPDATE""",
                (job.id, job.claim_token),
            ).fetchone()
            if row is None:
                return False
            cancelled, attempts, max_attempts = row
            terminal = not retryable or attempts >= max_attempts
            if terminal and not cancelled and result is not None:
                if Store(self.connection).save_analysis(job.user_id, result) != job.id:
                    raise ValueError("repository ownership or snapshot changed")
            self.connection.execute(
                """UPDATE analysis_jobs SET status = %s,
                       available_at = now() + make_interval(secs => %s),
                       error_code = %s, result_analysis_id = %s,
                       claim_token = NULL, lease_until = NULL, updated_at = now()
                   WHERE id = %s""",
                ("cancelled" if cancelled else "failed" if terminal else "queued",
                 retry_delay_seconds, None if cancelled else code,
                 job.id if terminal and not cancelled and result is not None else None,
                 job.id),
            )
            return True

    def complete(self, job: Job, result: AnalysisResult) -> bool:
        """Atomically save a successful or partial result under its live lease."""
        self._check_result(job, result, (AnalysisStatus.succeeded, AnalysisStatus.partial))
        with self.connection.transaction():
            row = self.connection.execute(
                """SELECT id FROM analysis_jobs WHERE id = %s AND claim_token = %s
                     AND status = 'running' AND lease_until > now()
                     AND NOT cancel_requested FOR UPDATE""",
                (job.id, job.claim_token),
            ).fetchone()
            if row is None:
                return False
            if Store(self.connection).save_analysis(job.user_id, result) != job.id:
                raise ValueError("repository ownership or snapshot changed")
            self.connection.execute(
                """UPDATE analysis_jobs SET status = %s, result_analysis_id = %s,
                       claim_token = NULL, lease_until = NULL, updated_at = now()
                   WHERE id = %s""",
                ("completed" if result.status == AnalysisStatus.succeeded else "partial",
                 job.id, job.id),
            )
            return True
