"""Strict JSON boundary shared with the TypeScript analysis contract."""

from enum import StrEnum
import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class FindingSource(StrEnum):
    static = "static"
    ai = "ai"


class Severity(StrEnum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class RepositorySnapshot(WireModel):
    repository_id: str = Field(min_length=1, strict=True)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$", strict=True)


class SourceLocation(WireModel):
    path: str = Field(min_length=1, strict=True)
    start_line: int = Field(ge=1, strict=True)
    end_line: int = Field(ge=1, strict=True)

    @field_validator("path")
    @classmethod
    def relative_posix_path(cls, value: str) -> str:
        if (
            value.startswith("/")
            or "\\" in value
            or re.match(r"^[A-Za-z]:", value)
            or any(part in ("", ".", "..") for part in value.split("/"))
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("path must be a normalized relative POSIX file path")
        return value

    @model_validator(mode="after")
    def ordered_lines(self) -> "SourceLocation":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class AnalysisFinding(WireModel):
    id: str = Field(min_length=1, strict=True)
    source: FindingSource
    issue_type: str = Field(min_length=1, strict=True)
    severity: Severity
    location: SourceLocation
    description: str = Field(min_length=1, strict=True)
    suggestion: str | None = Field(strict=True)


class AnalysisError(WireModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", strict=True)
    message: str = Field(min_length=1, strict=True)
    retryable: StrictBool
    location: SourceLocation | None


class AnalysisResult(WireModel):
    schema_version: int = Field(ge=1, le=1, strict=True)
    analysis_id: str = Field(min_length=1, strict=True)
    snapshot: RepositorySnapshot
    status: AnalysisStatus
    findings: list[AnalysisFinding]
    errors: list[AnalysisError]

    @model_validator(mode="after")
    def coherent_status(self) -> "AnalysisResult":
        if self.status == AnalysisStatus.failed and not self.errors:
            raise ValueError("failed analysis requires at least one error")
        if self.status == AnalysisStatus.succeeded and self.errors:
            raise ValueError("succeeded analysis cannot contain errors")
        if len({item.id for item in self.findings}) != len(self.findings):
            raise ValueError("finding ids must be unique within an analysis")
        return self
