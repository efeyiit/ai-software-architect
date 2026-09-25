"""Transactional SQLite storage, with immutable source snapshots."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from app.local.models import LocalSnapshot, StoredJob


class LocalStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f"Unsupported local database version: {version}")
            if version == 0:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                    repository_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(repository_id, snapshot_id))""")
                db.execute("""CREATE TABLE IF NOT EXISTS repositories (
                    repository_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL,
                    FOREIGN KEY(repository_id, snapshot_id)
                    REFERENCES snapshots(repository_id, snapshot_id))""")
                db.execute("""CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL, report TEXT NOT NULL,
                    FOREIGN KEY(repository_id, snapshot_id)
                    REFERENCES snapshots(repository_id, snapshot_id))""")
                db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL, status TEXT NOT NULL,
                    error_code TEXT, analysis_id TEXT,
                    FOREIGN KEY(repository_id, snapshot_id)
                    REFERENCES snapshots(repository_id, snapshot_id))""")
                db.execute("PRAGMA user_version=1")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_snapshot(self, snapshot: LocalSnapshot) -> None:
        payload = json.dumps(snapshot.model_dump(), sort_keys=True, ensure_ascii=False)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload FROM snapshots WHERE repository_id=? AND snapshot_id=?",
                             (snapshot.repository_id, snapshot.snapshot_id)).fetchone()
            if old is not None and old[0] != payload:
                raise ValueError("Source snapshots are immutable")
            db.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?)",
                       (snapshot.repository_id, snapshot.snapshot_id, payload))
            db.execute("INSERT INTO repositories VALUES (?, ?) ON CONFLICT(repository_id) "
                       "DO UPDATE SET snapshot_id=excluded.snapshot_id",
                       (snapshot.repository_id, snapshot.snapshot_id))

    def load_snapshot(self, repository_id: str, snapshot_id: str) -> LocalSnapshot | None:
        with self._connect() as db:
            row = db.execute("SELECT payload FROM snapshots WHERE repository_id=? AND snapshot_id=?",
                             (repository_id, snapshot_id)).fetchone()
        return LocalSnapshot.model_validate_json(row[0]) if row else None

    def list_repositories(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT s.payload FROM repositories r JOIN snapshots s "
                              "ON s.repository_id=r.repository_id AND s.snapshot_id=r.snapshot_id "
                              "ORDER BY r.repository_id").fetchall()
        return [{key: value for key, value in json.loads(row[0]).items()
                 if key not in ("sources", "excluded")} for row in rows]

    def save_analysis(self, analysis_id: str, repository_id: str, snapshot_id: str, report: dict) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO analyses VALUES (?, ?, ?, ?)",
                       (analysis_id, repository_id, snapshot_id, json.dumps(report)))

    def load_analysis(self, analysis_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM analyses WHERE analysis_id=?", (analysis_id,)).fetchone()
        return dict(row) | {"report": json.loads(row["report"])} if row else None

    def latest_analysis(self, repository_id: str, snapshot_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT analysis_id FROM analyses WHERE repository_id=? AND snapshot_id=? "
                             "ORDER BY rowid DESC LIMIT 1", (repository_id, snapshot_id)).fetchone()
        return self.load_analysis(row[0]) if row else None

    def save_job(self, job: StoredJob) -> None:
        with self._connect() as db:
            cursor = db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(job_id) "
                       "DO UPDATE SET status=excluded.status, error_code=excluded.error_code, "
                       "analysis_id=excluded.analysis_id WHERE jobs.repository_id=excluded.repository_id "
                       "AND jobs.snapshot_id=excluded.snapshot_id",
                       (job.job_id, job.repository_id, job.snapshot_id, job.status,
                        job.error_code, job.analysis_id))
            if cursor.rowcount != 1:
                raise ValueError("Job identity cannot change")

    def load_job(self, job_id: str) -> StoredJob | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return StoredJob.model_validate(dict(row)) if row else None

    def recover_interrupted_jobs(self) -> int:
        """Call once at startup, before starting any new background work."""
        with self._connect() as db:
            return db.execute("UPDATE jobs SET status='failed', error_code='INTERRUPTED' "
                              "WHERE status IN ('queued', 'running')").rowcount
