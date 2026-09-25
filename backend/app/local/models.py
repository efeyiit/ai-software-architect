"""Persisted local inputs; content revisions are never Git commit IDs."""

from typing import Literal

from pydantic import Field, field_validator

from app.contracts.analysis import SourceLocation, WireModel


class LocalSnapshot(WireModel):
    repository_id: str = Field(min_length=1, strict=True)
    snapshot_id: str = Field(pattern=r"^local:[0-9a-f]{64}$", strict=True)
    name: str = Field(min_length=1, max_length=200, strict=True)
    sources: dict[str, str]
    excluded: dict[str, str] = Field(default_factory=dict)

    @field_validator("sources", "excluded")
    @classmethod
    def safe_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for path in value:
            SourceLocation(path=path, start_line=1, end_line=1)
        return value


class StoredJob(WireModel):
    job_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    status: Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
    error_code: str | None = None
    analysis_id: str | None = None
