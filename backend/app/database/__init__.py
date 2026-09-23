"""Owner-scoped PostgreSQL operations for repository snapshots and analysis."""

import json
from pathlib import Path

from psycopg.rows import dict_row

from app.contracts.analysis import AnalysisResult


def apply_schema(connection) -> None:
    """Create the initial schema in the connection's current search path."""
    connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))


class Store:
    """All repository reads and writes require an authenticated caller's user id.

    The caller must resolve and authenticate that id. This module does not implement
    OAuth or expose unrestricted repository query methods.
    """

    def __init__(self, connection):
        self.connection = connection

    def create_user(self, email: str, password_hash: str) -> str:
        row = self.connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (email, password_hash),
        ).fetchone()
        return str(row[0])

    def create_repository(self, user_id: str, github_url: str, name: str) -> str:
        row = self.connection.execute(
            """INSERT INTO repositories (user_id, github_url, name)
               VALUES (%s, %s, %s) RETURNING id""",
            (user_id, github_url, name),
        ).fetchone()
        return str(row[0])

    def get_repository(self, user_id: str, repository_id: str) -> dict | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(
                """SELECT id::text, user_id::text, github_url, name, language,
                          framework, status, created_at
                   FROM repositories WHERE id = %s AND user_id = %s""",
                (repository_id, user_id),
            ).fetchone()

    def create_snapshot(self, user_id: str, repository_id: str, commit_sha: str) -> str | None:
        row = self.connection.execute(
            """INSERT INTO repository_snapshots (repository_id, commit_sha)
               SELECT id, %s FROM repositories
               WHERE id = %s AND user_id = %s
               ON CONFLICT (repository_id, commit_sha)
               DO UPDATE SET commit_sha = EXCLUDED.commit_sha
               RETURNING id""",
            (commit_sha, repository_id, user_id),
        ).fetchone()
        return str(row[0]) if row else None

    def get_snapshot(self, user_id: str, snapshot_id: str) -> dict | None:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(
                """SELECT s.id::text, s.repository_id::text, s.commit_sha, s.created_at
                   FROM repository_snapshots s
                   JOIN repositories r ON r.id = s.repository_id
                   WHERE s.id = %s AND r.user_id = %s""",
                (snapshot_id, user_id),
            ).fetchone()

    def save_analysis(self, user_id: str, result: AnalysisResult) -> str | None:
        row = self.connection.execute(
            """INSERT INTO analyses (id, repository_id, snapshot_id, type, result)
               SELECT %s, r.id, s.id, %s, %s::jsonb
               FROM repositories r
               JOIN repository_snapshots s ON s.repository_id = r.id
               WHERE r.id = %s AND r.user_id = %s AND s.commit_sha = %s
               RETURNING id""",
            (
                result.analysis_id, "structured", result.model_dump_json(),
                result.snapshot.repository_id, user_id, result.snapshot.commit_sha,
            ),
        ).fetchone()
        return row[0] if row else None

    def get_analysis(self, user_id: str, analysis_id: str) -> AnalysisResult | None:
        row = self.connection.execute(
            """SELECT a.result FROM analyses a
               JOIN repositories r ON r.id = a.repository_id
               WHERE a.id = %s AND r.user_id = %s""",
            (analysis_id, user_id),
        ).fetchone()
        return AnalysisResult.model_validate(row[0]) if row else None
