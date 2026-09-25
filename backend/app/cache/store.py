"""PostgreSQL cache for completed, owner-scoped analysis jobs.

The access callback is a trusted integration boundary. It must revalidate
current GitHub permission for private repositories on every lookup.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable

from app.contracts.analysis import AnalysisResult


AccessCheck = Callable[[str, str], bool]


def config_digest(config: object) -> str:
    """Hash canonical JSON configuration; callers must include every analysis option."""
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CacheKey:
    user_id: str
    repository_id: str
    branch: str
    commit_sha: str
    config_digest: str
    model_version: str
    analysis_version: str

    def __post_init__(self) -> None:
        if not self.user_id or not self.repository_id:
            raise ValueError("owner and repository are required")
        if (not self.branch or len(self.branch) > 255
                or any(ord(char) < 32 for char in self.branch)):
            raise ValueError("branch must be a nonempty Git branch name")
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit_sha):
            raise ValueError("commit_sha must be a lowercase full SHA")
        if not re.fullmatch(r"[0-9a-f]{64}", self.config_digest):
            raise ValueError("config_digest must be a SHA-256 digest")
        for name in ("model_version", "analysis_version"):
            value = getattr(self, name)
            if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
                raise ValueError(f"{name} must be nonempty and at most 128 characters")

    def parts(self) -> tuple[str, ...]:
        return (self.user_id, self.repository_id, self.branch, self.commit_sha,
                self.config_digest, self.model_version, self.analysis_version)


def apply_cache_schema(connection) -> None:
    """Install additive cache schema after core and job schemas."""
    connection.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))


class AnalysisCache:
    """A caller must supply the authenticated owner and a live access check.

    Connections use autocommit so each operation is atomic and independent.
    Access checks execute outside SQL transactions because they can use GitHub.
    """

    def __init__(self, connection, revalidate_access: AccessCheck):
        if not connection.autocommit:
            raise ValueError("AnalysisCache requires an autocommit PostgreSQL connection")
        if not callable(revalidate_access):
            raise ValueError("a live access revalidation callback is required")
        self.connection = connection
        self.revalidate_access = revalidate_access

    def _authorized(self, key: CacheKey) -> bool:
        # False and errors fail closed. An exception is allowed to surface, never a hit.
        return self.revalidate_access(key.user_id, key.repository_id) is True

    def get(self, key: CacheKey) -> AnalysisResult | None:
        """Return only an unexpired result from a completed job after live access check."""
        if not self._authorized(key):
            return None
        row = self.connection.execute(
            """SELECT a.result FROM analysis_cache c
               JOIN repositories r ON r.id = c.repository_id AND r.user_id = c.user_id
               JOIN repository_snapshots s ON s.repository_id = r.id
                   AND s.commit_sha = c.commit_sha
               JOIN analyses a ON a.id = c.analysis_id AND a.repository_id = r.id
                   AND a.snapshot_id = s.id
               JOIN analysis_jobs j ON j.result_analysis_id = a.id
                   AND j.user_id = c.user_id AND j.repository_id = r.id
                   AND j.snapshot_id = s.id AND j.status = 'completed'
               WHERE c.user_id = %s AND c.repository_id = %s AND c.branch = %s
                 AND c.commit_sha = %s AND c.config_digest = %s
                 AND c.model_version = %s AND c.analysis_version = %s
                 AND c.expires_at > now() AND a.result->>'status' = 'succeeded'
                 AND COALESCE(a.result->'partial', 'false'::jsonb) = 'false'::jsonb
                 AND jsonb_array_length(a.result->'errors') = 0""",
            key.parts(),
        ).fetchone()
        return AnalysisResult.model_validate(row[0]) if row else None

    def put(self, key: CacheKey, analysis_id: str, *, ttl_seconds: int) -> bool:
        """Map a key to a completed job result; concurrent writers use one row."""
        if not 1 <= ttl_seconds <= 90 * 24 * 60 * 60:
            raise ValueError("ttl_seconds must be between 1 second and 90 days")
        if not self._authorized(key):
            return False
        row = self.connection.execute(
            """INSERT INTO analysis_cache
                   (user_id, repository_id, branch, commit_sha, config_digest,
                    model_version, analysis_version, analysis_id, expires_at)
               SELECT r.user_id, r.id, %s, s.commit_sha, %s, %s, %s, a.id,
                      now() + make_interval(secs => %s)
               FROM repositories r
               JOIN repository_snapshots s ON s.repository_id = r.id
               JOIN analyses a ON a.repository_id = r.id AND a.snapshot_id = s.id
               JOIN analysis_jobs j ON j.result_analysis_id = a.id
                   AND j.user_id = r.user_id AND j.repository_id = r.id
                   AND j.snapshot_id = s.id AND j.status = 'completed'
               WHERE r.user_id = %s AND r.id = %s AND s.commit_sha = %s
                 AND a.id = %s AND a.result->>'status' = 'succeeded'
                 AND COALESCE(a.result->'partial', 'false'::jsonb) = 'false'::jsonb
                 AND jsonb_array_length(a.result->'errors') = 0
               ON CONFLICT (user_id, repository_id, branch, commit_sha,
                            config_digest, model_version, analysis_version)
               DO UPDATE SET analysis_id = EXCLUDED.analysis_id,
                             expires_at = EXCLUDED.expires_at, updated_at = now()
               RETURNING analysis_id""",
            (key.branch, key.config_digest, key.model_version, key.analysis_version,
             ttl_seconds, key.user_id, key.repository_id, key.commit_sha, analysis_id),
        ).fetchone()
        return row is not None

    def invalidate(self, user_id: str, repository_id: str, *, branch: str | None = None) -> int:
        """Remove one owner's repository entries, optionally limited to a branch."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """DELETE FROM analysis_cache c USING repositories r
                   WHERE c.repository_id = r.id AND r.user_id = c.user_id
                     AND c.user_id = %s AND c.repository_id = %s
                     AND (%s::text IS NULL OR c.branch = %s)""",
                (user_id, repository_id, branch, branch),
            )
            return cursor.rowcount

    def prune_expired(self) -> int:
        """Physically remove expired rows; expiry is enforced on reads regardless."""
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM analysis_cache WHERE expires_at <= now()")
            return cursor.rowcount
