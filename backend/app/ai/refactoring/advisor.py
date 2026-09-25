"""Keep parser/T11 facts separate from tentative SOLID recommendations."""

from __future__ import annotations

import re
from collections.abc import Iterable
from hashlib import sha256
from typing import Literal

from app.analyzers.architecture.detector import ArchitectureReport
from app.contracts.analysis import AnalysisFinding, FindingSource, SourceLocation, WireModel


class RefactoringEvidence(WireModel):
    id: str
    kind: Literal["class", "method", "quality", "architecture"]
    description: str
    location: SourceLocation


class Extraction(WireModel):
    responsibility: str
    method_names: list[str]
    action: str


class RefactoringRecommendation(WireModel):
    principle: Literal["srp"]
    certainty: Literal["candidate"]
    origin: Literal["deterministic"]
    location: SourceLocation
    subject: str
    rationale: str
    evidence_ids: list[str]
    extractions: list[Extraction]


class ArchitectureContext(WireModel):
    architecture: str
    assessment: Literal["supported", "mixed"]
    evidence_ids: list[str]


class RefactoringReport(WireModel):
    evidence: list[RefactoringEvidence]
    recommendations: list[RefactoringRecommendation]
    architecture_context: list[ArchitectureContext]
    ai_status: Literal["unavailable"] = "unavailable"
    limitations: list[str]


_RESPONSIBILITIES: dict[str, frozenset[str]] = {
    "payments": frozenset({"pay", "payment", "charge", "refund", "invoice", "billing"}),
    "notifications": frozenset({"email", "mail", "notify", "notification", "message"}),
    "documents": frozenset({"pdf", "report", "document", "export"}),
    "persistence": frozenset({"save", "load", "persist", "store", "database"}),
}


def _tokens(name: str) -> set[str]:
    return set(re.findall(r"[a-z]+", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()))


def _id(kind: str, location: SourceLocation, description: str) -> str:
    value = f"{kind}:{location.path}:{location.start_line}:{location.end_line}:{description}"
    return sha256(value.encode()).hexdigest()[:20]


def analyze_refactoring(
    structures: Iterable[object],
    quality_findings: Iterable[AnalysisFinding],
    architecture: ArchitectureReport,
) -> RefactoringReport:
    """Suggest reviewable SRP splits from same-snapshot parser/T11/T12 results.

    Inputs contain no repository identity or SHA. The caller must bind all three
    to the same authorized snapshot. No analyzed source or external model runs.
    """
    files = list(structures)
    paths = {file.path for file in files}
    if len(paths) != len(files):
        raise ValueError("duplicate source path")
    evidence: list[RefactoringEvidence] = []
    recommendations: list[RefactoringRecommendation] = []
    architecture_context: list[ArchitectureContext] = []

    def add(kind: Literal["class", "method", "quality", "architecture"],
            location: SourceLocation, description: str) -> str:
        if location.path not in paths:
            raise ValueError(f"{kind} evidence belongs to a different file snapshot")
        evidence_id = _id(kind, location, description)
        evidence.append(RefactoringEvidence(id=evidence_id, kind=kind,
                                            description=description, location=location))
        return evidence_id

    quality_by_path: dict[str, list[tuple[AnalysisFinding, str]]] = {path: [] for path in paths}
    for finding in quality_findings:
        if finding.source != FindingSource.static or finding.location.path not in paths:
            raise ValueError("quality finding must be static and from this file snapshot")
        evidence_id = add("quality", finding.location,
                          f"T11 {finding.issue_type}: {finding.description}")
        quality_by_path[finding.location.path].append((finding, evidence_id))

    for hypothesis in architecture.hypotheses:
        if hypothesis.assessment == "insufficient":
            continue
        ids: list[str] = []
        for fact in (*hypothesis.reasons, *hypothesis.contradictions):
            if fact.location.path not in paths:
                raise ValueError("architecture evidence belongs to a different file snapshot")
            ids.append(add("architecture", fact.location,
                           f"T12 {hypothesis.architecture} {hypothesis.assessment}: {fact.description}"))
        if ids:
            architecture_context.append(ArchitectureContext(
                architecture=hypothesis.architecture, assessment=hypothesis.assessment,
                evidence_ids=ids))

    for file in sorted(files, key=lambda item: item.path):
        if file.errors:
            continue
        if any(symbol.location.path != file.path for symbol in file.symbols):
            raise ValueError("parser symbol belongs to a different file snapshot")
        classes = [symbol for symbol in file.symbols if symbol.kind == "class"]
        methods = [symbol for symbol in file.symbols if symbol.kind == "method"]
        separator = "::" if file.path.endswith((".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx")) else "."
        for cls in classes:
            class_id = add("class", cls.location, f"Parsed class {cls.qualified_name}")
            groups: dict[str, list[tuple[str, str]]] = {}
            for method in methods:
                if method.qualified_name.rpartition(separator)[0] != cls.qualified_name:
                    continue
                method_id = add("method", method.location,
                                f"Parsed method {method.qualified_name}")
                words = _tokens(method.name)
                matches = [name for name, terms in _RESPONSIBILITIES.items() if words & terms]
                # Ambiguous names are facts but do not steer a proposed split.
                if len(matches) == 1:
                    groups.setdefault(matches[0], []).append((method.name, method_id))
            if len(groups) < 2:
                continue
            group_ids = [evidence_id for items in groups.values() for _, evidence_id in items]
            large_ids = [evidence_id for finding, evidence_id in quality_by_path[file.path]
                         if finding.issue_type == "large_class" and
                         finding.location.start_line <= cls.location.start_line and
                         finding.location.end_line >= cls.location.end_line]
            extractions = [Extraction(
                responsibility=name,
                method_names=[method_name for method_name, _ in items],
                action=f"Consider moving {name} behavior into a focused collaborator; preserve the public interface and add behavior tests first.",
            ) for name, items in sorted(groups.items())]
            recommendations.append(RefactoringRecommendation(
                principle="srp", certainty="candidate", origin="deterministic",
                location=cls.location, subject=cls.qualified_name,
                rationale="Method names suggest distinct concerns; inspect behavior and dependencies before changing the class."
                          + (" T11 also measured this class above its configured size threshold." if large_ids else ""),
                evidence_ids=[class_id, *group_ids, *large_ids], extractions=extractions))

    return RefactoringReport(
        evidence=evidence, recommendations=recommendations,
        architecture_context=architecture_context, ai_status="unavailable",
        limitations=[
            "Method names are candidate hints, not proof of separate reasons to change or a SOLID violation.",
            "Open/closed, Liskov substitution, interface segregation, and dependency inversion are not asserted without stronger behavioral evidence.",
            "Parser, quality, and architecture types do not carry repository ID or commit SHA; the caller must enforce snapshot identity.",
            "No LLM provider is configured; recommendations are deterministic and no analyzed code is transmitted or modified.",
        ])
