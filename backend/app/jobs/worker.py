"""A polling worker that never holds a transaction across repository analysis."""

from dataclasses import dataclass
import logging
import re
from threading import Event, Thread
from typing import Callable

from app.contracts.analysis import AnalysisResult, AnalysisStatus

from .store import Job, JobStore

logger = logging.getLogger(__name__)


class JobFailure(Exception):
    """A classified, safe failure. The message is never persisted or logged."""

    def __init__(self, code: str, *, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass
class JobContext:
    job: Job
    _store_factory: Callable[[], object]
    _lost: Event

    def should_stop(self) -> bool:
        """Handlers should check between bounded stages and stop promptly."""
        if self._lost.is_set():
            return True
        with self._store_factory() as connection:
            return JobStore(connection).should_stop(self.job)


class Worker:
    def __init__(self, connection_factory: Callable[[], object],
                 handler: Callable[[JobContext], AnalysisResult], *,
                 lease_seconds: int = 60, heartbeat_seconds: float = 15,
                 retry_delay_seconds: int = 1):
        if lease_seconds < 2 or not 0 < heartbeat_seconds < lease_seconds / 2:
            raise ValueError("heartbeat interval must be less than half the lease")
        self.connection_factory = connection_factory
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.retry_delay_seconds = retry_delay_seconds

    def _with_store(self, action):
        with self.connection_factory() as connection:
            return action(JobStore(connection))

    def process_one(self) -> Job | None:
        """Claim one due job, run the injected analysis, then persist its result."""
        job = self._with_store(lambda store: store.claim(lease_seconds=self.lease_seconds))
        if job is None:
            return None
        logger.info("analysis_job_claimed", extra={"job_id": job.id, "attempt": job.attempts})
        stop, lost = Event(), Event()

        def keep_lease() -> None:
            while not stop.wait(self.heartbeat_seconds):
                try:
                    alive = self._with_store(
                        lambda store: store.heartbeat(job, lease_seconds=self.lease_seconds))
                except Exception:
                    # A lost database connection must not allow an old worker to write.
                    lost.set()
                    return
                if not alive:
                    lost.set()
                    return

        thread = Thread(target=keep_lease, daemon=True)
        thread.start()
        context = JobContext(job, self.connection_factory, lost)
        result = None
        failure = None
        try:
            if context.should_stop():
                failure = JobFailure("CANCELLED", retryable=False)
            else:
                result = self.handler(context)
                if result.status == AnalysisStatus.failed:
                    first = result.errors[0]
                    failure = JobFailure(first.code, retryable=first.retryable)
                elif result.status not in (AnalysisStatus.succeeded, AnalysisStatus.partial):
                    failure = JobFailure("INVALID_RESULT", retryable=False)
        except JobFailure as exc:
            failure = exc
        except Exception:
            # Exception text may include repository code, paths, URLs or secrets.
            failure = JobFailure("ANALYSIS_FAILED", retryable=True)
        finally:
            stop.set()
            thread.join()

        if context.should_stop():
            cancelled_result = result if result is not None and result.status == AnalysisStatus.cancelled else None
            cancelled = self._with_store(lambda store: store.acknowledge_cancel(job, cancelled_result))
            if cancelled:
                logger.info("analysis_job_cancelled", extra={"job_id": job.id})
            return job
        if failure is not None:
            delay = min(self.retry_delay_seconds * (2 ** (job.attempts - 1)), 300)
            code = failure.code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", failure.code) else "ANALYSIS_FAILED"
            try:
                updated = self._with_store(lambda store: store.fail(
                    job, code, retryable=failure.retryable, retry_delay_seconds=delay,
                    result=result if result is not None and result.status == AnalysisStatus.failed else None))
            except Exception:
                logger.error("analysis_job_persist_failed", extra={"job_id": job.id})
                return job
            if updated:
                logger.warning("analysis_job_failed", extra={
                    "job_id": job.id, "attempt": job.attempts,
                    "retryable": failure.retryable,
                })
            return job
        try:
            completed = self._with_store(lambda store: store.complete(job, result))
        except Exception:
            # Persistence failure leaves the lease available for a later attempt.
            logger.error("analysis_job_persist_failed", extra={"job_id": job.id})
            return job
        if completed:
            logger.info("analysis_job_result_saved", extra={
                "job_id": job.id,
                "job_status": "completed" if result.status == AnalysisStatus.succeeded else "partial",
            })
        return job

    def run_forever(self, stop: Event, *, idle_seconds: float = 1) -> None:
        """Poll from a dedicated worker process; HTTP code only enqueues jobs."""
        while not stop.is_set():
            job = self.process_one()
            if job is None:
                stop.wait(idle_seconds)
