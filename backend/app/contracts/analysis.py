"""Strict JSON boundary shared with the TypeScript analysis contract."""

from enum import StrEnum
import re

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator, model_serializer


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    partial = "partial"
    cancelled = "cancelled"


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


RoleName = Literal["architect", "security", "testing", "refactoring", "documentation"]
ROLE_NAMES = frozenset(("architect", "security", "testing", "refactoring", "documentation"))


class AnalysisRole(WireModel):
    role: RoleName
    status: Literal["succeeded", "failed", "timed_out", "cancelled"]
    error_code: str | None = None


class AnalysisItem(WireModel):
    id: str
    kind: Literal["static_finding", "architecture_support", "architecture_contradiction",
                  "testing_observation", "refactoring_candidate", "documentation_fact"]
    roles: list[RoleName]
    origin: Literal["static", "deterministic"]
    location: SourceLocation | None
    text: str
    finding: AnalysisFinding | None = None


class AnalysisConflict(WireModel):
    key: str
    item_ids: list[str]


class ArchitectureEvidence(WireModel):
    description: str
    location: SourceLocation


class ArchitectureHypothesis(WireModel):
    architecture: Literal["mvc", "layered", "clean", "hexagonal", "microservices", "modular_monolith", "event_driven"]
    assessment: Literal["supported", "mixed", "insufficient"]
    confidence: Literal["low", "medium", "high"]
    reasons: list[ArchitectureEvidence]
    contradictions: list[ArchitectureEvidence]
    uncertainties: list[str]


class ArchitectureData(WireModel):
    hypotheses: list[ArchitectureHypothesis]
    summary: Literal["single", "mixed", "unknown"]
    primary: Literal["mvc", "layered", "clean", "hexagonal", "microservices", "modular_monolith", "event_driven"] | None


class TestFileData(WireModel):
    path: str
    framework: str | None
    declaration_count: int


class ServiceCandidateData(WireModel):
    path: str
    name: str
    location: SourceLocation
    status: str
    test_paths: list[str]


class CoverageData(WireModel):
    artifact_path: str
    format: str
    metric: str
    covered: int
    total: int
    percent: float


class TestingData(WireModel):
    test_files: list[TestFileData]
    services: list[ServiceCandidateData]
    coverage: CoverageData | None
    coverage_status: str
    coverage_errors: list[str]


class RefactoringEvidenceData(WireModel):
    id: str
    kind: Literal["class", "method", "quality", "architecture"]
    description: str
    location: SourceLocation


class ExtractionData(WireModel):
    responsibility: str
    method_names: list[str]
    action: str


class RefactoringRecommendationData(WireModel):
    principle: Literal["srp"]
    certainty: Literal["candidate"]
    origin: Literal["deterministic"]
    location: SourceLocation
    subject: str
    rationale: str
    evidence_ids: list[str]
    extractions: list[ExtractionData]


class RefactoringContextData(WireModel):
    architecture: str
    assessment: Literal["supported", "mixed"]
    evidence_ids: list[str]


class RefactoringData(WireModel):
    evidence: list[RefactoringEvidenceData]
    recommendations: list[RefactoringRecommendationData]
    architecture_context: list[RefactoringContextData]
    ai_status: Literal["unavailable"]
    limitations: list[str]


class DocumentEvidenceData(WireModel):
    path: str
    line: int


class DocumentFactData(WireModel):
    text: str
    evidence: DocumentEvidenceData


class APIFieldData(WireModel):
    name: str
    type: str


class APIRouteData(WireModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    request_fields: list[APIFieldData]
    response_fields: list[APIFieldData]
    evidence: DocumentEvidenceData
    status: Literal["draft"]


class DocumentationData(WireModel):
    snapshot: RepositorySnapshot
    ai_status: Literal["unavailable"]
    readme: str
    api_markdown: str
    facts: list[DocumentFactData]
    routes: list[APIRouteData]
    uncertainties: list[str]


class DependencyNodeData(WireModel):
    id: str
    kind: Literal["file", "symbol"]
    language: Literal["python", "typescript", "java", "csharp", "cpp"]
    name: str
    location: SourceLocation


class DependencyEdgeData(WireModel):
    source: str
    target: str | None
    kind: Literal["import", "call", "inheritance"]
    status: Literal["resolved", "external", "ambiguous"]
    expression: str
    location: SourceLocation
    candidates: list[str]
    reason: str | None


class DependencyData(WireModel):
    nodes: list[DependencyNodeData]
    edges: list[DependencyEdgeData]
    cycles: list[list[str]]
    critical_nodes: list[str]


class AnalysisResult(WireModel):
    schema_version: Literal[1, 2]
    analysis_id: str = Field(min_length=1, strict=True)
    snapshot: RepositorySnapshot
    status: AnalysisStatus
    findings: list[AnalysisFinding]
    errors: list[AnalysisError]
    partial: StrictBool | None = None
    ai_status: Literal["unavailable"] | None = None
    roles: list[AnalysisRole] | None = None
    items: list[AnalysisItem] | None = None
    conflicts: list[AnalysisConflict] | None = None
    architecture: ArchitectureData | None = None
    testing: TestingData | None = None
    refactoring: RefactoringData | None = None
    documentation: DocumentationData | None = None
    dependencies: DependencyData | None = None

    @model_validator(mode="after")
    def coherent_status(self) -> "AnalysisResult":
        if self.status == AnalysisStatus.failed and not self.errors:
            raise ValueError("failed analysis requires at least one error")
        if self.status == AnalysisStatus.succeeded and self.errors:
            raise ValueError("succeeded analysis cannot contain errors")
        if len({item.id for item in self.findings}) != len(self.findings):
            raise ValueError("finding ids must be unique within an analysis")
        v2_fields = {"partial", "ai_status", "roles", "items", "conflicts", "architecture",
                     "testing", "refactoring", "documentation", "dependencies"}
        if self.schema_version == 1:
            if self.model_fields_set & v2_fields:
                raise ValueError("v1 cannot contain v2 report fields")
            if self.status in (AnalysisStatus.partial, AnalysisStatus.cancelled):
                raise ValueError("v1 cannot use v2 statuses")
        else:
            if not v2_fields <= self.model_fields_set or self.partial is None or self.ai_status is None or self.roles is None or self.items is None or self.conflicts is None:
                raise ValueError("v2 report fields are required")
            if self.partial != (self.status == AnalysisStatus.partial):
                raise ValueError("partial flag must match status")
            if self.status in (AnalysisStatus.succeeded, AnalysisStatus.partial, AnalysisStatus.failed, AnalysisStatus.cancelled):
                if len(self.roles) != 5 or {role.role for role in self.roles} != ROLE_NAMES:
                    raise ValueError("terminal v2 analysis requires exactly five roles")
            if self.status == AnalysisStatus.succeeded and any(role.status != "succeeded" for role in self.roles):
                raise ValueError("succeeded analysis requires all roles to succeed")
            if self.status == AnalysisStatus.partial and not (any(role.status == "succeeded" for role in self.roles) and any(role.status in ("failed", "timed_out") for role in self.roles) and self.errors):
                raise ValueError("partial analysis requires success, failure and errors")
            item_ids = {item.id for item in self.items}
            if len(item_ids) != len(self.items) or any(not set(conflict.item_ids) <= item_ids for conflict in self.conflicts):
                raise ValueError("report items and conflicts must be internally linked")
        return self

    @model_serializer(mode="wrap")
    def serialize_versioned(self, handler):
        result = handler(self)
        if self.schema_version == 1:
            for name in ("partial", "ai_status", "roles", "items", "conflicts", "architecture",
                         "testing", "refactoring", "documentation", "dependencies"):
                result.pop(name, None)
        return result
