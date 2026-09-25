"""Bounded, source-linked coordination of the existing deterministic analyzers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from hashlib import sha1, sha256
from time import monotonic
from typing import Callable, Literal, Mapping

from app.ai.documentation import DocumentationResult, generate_documentation
from app.ai.refactoring import RefactoringReport, analyze_refactoring
from app.analyzers.architecture import ArchitectureReport, analyze_architecture
from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.dependencies.graph import DependencyGraph
from app.analyzers.security import analyze_security
from app.analyzers.static_quality import analyze_static_quality
from app.analyzers.testing import TestingReport, analyze_testing
from app.contracts.analysis import AnalysisFinding, RepositorySnapshot as SnapshotIdentity, SourceLocation, WireModel
from app.parsers.python import parse_file as parse_python
from app.parsers.typescript import parse_file as parse_typescript
from app.parsers.java import parse_file as parse_java
from app.parsers.csharp import parse_file as parse_csharp
from app.parsers.cpp import parse_file as parse_cpp
from app.services.github_public.service import RepositorySnapshot


Role = Literal["architect", "security", "testing", "refactoring", "documentation"]
ROLES: tuple[Role, ...] = ("architect", "security", "testing", "refactoring", "documentation")
_PARSERS = {".py": parse_python, ".ts": parse_typescript, ".tsx": parse_typescript,
            ".mts": parse_typescript, ".cts": parse_typescript, ".java": parse_java,
            ".cs": parse_csharp, ".cpp": parse_cpp, ".cc": parse_cpp,
            ".cxx": parse_cpp, ".h": parse_cpp, ".hpp": parse_cpp,
            ".hh": parse_cpp, ".hxx": parse_cpp}


class ScopeChanged(ValueError):
    """Authorization, selected commit, or its file manifest changed."""


@dataclass(frozen=True)
class SnapshotMaterial:
    """Texts retrieved by the caller from the declared blob SHAs."""

    snapshot: RepositorySnapshot
    sources: Mapping[str, str]
    document_sources: Mapping[str, str]
    coverage_artifacts: Mapping[str, bytes | str]


class RoleState(WireModel):
    role: Role
    status: Literal["succeeded", "failed", "timed_out", "cancelled"]
    error_code: str | None = None


class MergeItem(WireModel):
    id: str
    kind: Literal["static_finding", "architecture_support", "architecture_contradiction",
                  "testing_observation", "refactoring_candidate", "documentation_fact"]
    roles: list[Role]
    origin: Literal["static", "deterministic"]
    location: SourceLocation | None
    text: str
    finding: AnalysisFinding | None = None


class MergeConflict(WireModel):
    key: str
    item_ids: list[str]


class OrchestrationReport(WireModel):
    snapshot: SnapshotIdentity
    status: Literal["succeeded", "partial", "failed", "cancelled"]
    ai_status: Literal["unavailable"] = "unavailable"
    roles: list[RoleState]
    items: list[MergeItem]
    conflicts: list[MergeConflict]
    dependency_graph: DependencyGraph | None
    architecture: ArchitectureReport | None
    testing: TestingReport | None
    refactoring: RefactoringReport | None
    documentation: DocumentationResult | None


def _stamp(snapshot: RepositorySnapshot) -> tuple:
    return (snapshot.repository_id, SnapshotIdentity.from_source(snapshot).revision, snapshot.tree_sha,
            tuple(sorted((file.path, file.blob_sha, file.included) for file in snapshot.files)))


def _blob_sha(text: str) -> str:
    raw = text.encode("utf-8")
    return sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def _validate(material: SnapshotMaterial, *, max_files: int, max_bytes: int) -> None:
    snapshot = material.snapshot
    SnapshotIdentity.from_source(snapshot)
    files = {file.path: file for file in snapshot.files}
    if len(files) != len(snapshot.files):
        raise ValueError("duplicate snapshot path")
    if set(material.sources) != {f.path for f in snapshot.included_files}:
        raise ValueError("source file set differs from selected snapshot")
    if set(material.document_sources) & set(material.sources):
        raise ValueError("document and source paths overlap")
    if len(material.sources) > max_files:
        raise ValueError("source file budget exceeded")
    total = 0
    for path, source in (*material.sources.items(), *material.document_sources.items()):
        SourceLocation(path=path, start_line=1, end_line=1)
        file = files.get(path)
        if file is None or not isinstance(source, str) or _blob_sha(source) != file.blob_sha:
            raise ValueError("source text does not match snapshot blob")
        total += len(source.encode("utf-8"))
    if total > max_bytes:
        raise ValueError("source byte budget exceeded")
    if set(material.coverage_artifacts) & (set(material.sources) | set(material.document_sources)):
        raise ValueError("coverage and source paths overlap")
    if len(material.coverage_artifacts) > 1:
        raise ValueError("only one coverage artifact may be selected")
    for path, data in material.coverage_artifacts.items():
        SourceLocation(path=path, start_line=1, end_line=1)
        file = files.get(path)
        if file is None or not isinstance(data, (bytes, str)):
            raise ValueError("coverage artifact absent from snapshot")
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != file.blob_sha:
            raise ValueError("coverage artifact does not match snapshot blob")
        total += len(raw)
    if total > max_bytes:
        raise ValueError("snapshot byte budget exceeded")


def _parse(material: SnapshotMaterial) -> list[object]:
    structures = []
    for path, source in sorted(material.sources.items()):
        parser = next((function for extension, function in _PARSERS.items() if path.endswith(extension)), None)
        if parser is None:
            raise ValueError("unsupported selected source")
        structures.append(parser(path, source))
    return structures


def _item(kind: MergeItem.__annotations__["kind"], role: Role, text: str,
          location: SourceLocation | None = None, finding: AnalysisFinding | None = None) -> MergeItem:
    origin = "static" if kind == "static_finding" else "deterministic"
    key = (kind, location.model_dump_json() if location else "", text,
           finding.issue_type if finding else "", finding.severity if finding else "")
    identifier = sha256(repr(key).encode()).hexdigest()[:24]
    return MergeItem(id=identifier, kind=kind, roles=[role], origin=origin,
                     location=location, text=text, finding=finding)


def _merge(results: dict[Role, object], quality: list[AnalysisFinding]) -> tuple[list[MergeItem], list[MergeConflict]]:
    candidates: list[MergeItem] = []
    for finding in quality:
        candidates.append(_item("static_finding", "refactoring", finding.description,
                                finding.location, finding))
    architecture = results.get("architect")
    if isinstance(architecture, ArchitectureReport):
        for hypothesis in architecture.hypotheses:
            for evidence in hypothesis.reasons:
                candidates.append(_item("architecture_support", "architect",
                                        f"{hypothesis.architecture}: {evidence.description}", evidence.location))
            for evidence in hypothesis.contradictions:
                candidates.append(_item("architecture_contradiction", "architect",
                                        f"{hypothesis.architecture}: {evidence.description}", evidence.location))
    security = results.get("security")
    if isinstance(security, list):
        for finding in security:
            candidates.append(_item("static_finding", "security", finding.description,
                                    finding.location, finding))
    testing = results.get("testing")
    if isinstance(testing, TestingReport):
        for service in testing.services:
            candidates.append(_item("testing_observation", "testing",
                                    f"{service.name}: {service.status}", service.location))
    refactoring = results.get("refactoring")
    if isinstance(refactoring, RefactoringReport):
        for recommendation in refactoring.recommendations:
            candidates.append(_item("refactoring_candidate", "refactoring",
                                    f"{recommendation.subject}: {recommendation.rationale}",
                                    recommendation.location))
    documentation = results.get("documentation")
    if isinstance(documentation, DocumentationResult):
        for fact in documentation.facts:
            candidates.append(_item("documentation_fact", "documentation", fact.text,
                                    SourceLocation(path=fact.evidence.path,
                                                   start_line=fact.evidence.line,
                                                   end_line=fact.evidence.line)))
    unique: dict[str, MergeItem] = {}
    for item in candidates:
        if item.id in unique:
            unique[item.id].roles = sorted(set([*unique[item.id].roles, *item.roles]), key=ROLES.index)
        else:
            unique[item.id] = item
    items = sorted(unique.values(), key=lambda item: (item.location.path if item.location else "",
                    item.location.start_line if item.location else 0, item.kind, item.id))
    groups: dict[str, list[str]] = {}
    for item in items:
        if item.finding:
            key = f"{item.finding.location.path}:{item.finding.location.start_line}:{item.finding.issue_type}"
            groups.setdefault(key, []).append(item.id)
        if item.kind in {"architecture_support", "architecture_contradiction"}:
            key = "architecture:" + item.text.partition(":")[0]
            groups.setdefault(key, []).append(item.id)
    conflicts = [MergeConflict(key=key, item_ids=ids) for key, ids in sorted(groups.items())
                 if len(ids) > 1 and (not key.startswith("architecture:") or
                    {item.kind for item in items if item.id in ids} ==
                    {"architecture_support", "architecture_contradiction"})]
    return items, conflicts


class Coordinator:
    def __init__(self, current_snapshot: Callable[[str, str], RepositorySnapshot | None], *,
                 max_files: int = 2000, max_bytes: int = 20_000_000,
                 timeout_seconds: float = 30, max_concurrency: int = 3):
        if not 1 <= max_files <= 2000 or not 1 <= max_bytes <= 20 * 1024 * 1024:
            raise ValueError("invalid input budget")
        if not 0 < timeout_seconds <= 300 or not 1 <= max_concurrency <= 5:
            raise ValueError("invalid execution budget")
        self.current_snapshot = current_snapshot
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds
        self.max_concurrency = max_concurrency

    def run(self, caller_id: str, material: SnapshotMaterial,
            should_stop: Callable[[], bool] = lambda: False) -> OrchestrationReport:
        snapshot = material.snapshot
        def check_scope() -> None:
            current = self.current_snapshot(caller_id, snapshot.repository_id)
            if current is None or _stamp(current) != _stamp(snapshot):
                raise ScopeChanged("repository authorization or snapshot changed")

        check_scope()
        _validate(material, max_files=self.max_files, max_bytes=self.max_bytes)
        check_scope()
        if should_stop():
            return self._report(snapshot, {}, [RoleState(role=role, status="cancelled") for role in ROLES], [], None)
        structures = _parse(material)
        check_scope()
        if should_stop():
            return self._report(snapshot, {}, [RoleState(role=role, status="cancelled") for role in ROLES], [], None)
        graph = analyze_dependencies(structures)
        quality = analyze_static_quality(structures, dict(material.sources), graph)
        check_scope()
        if should_stop():
            return self._report(snapshot, {}, [RoleState(role=role, status="cancelled") for role in ROLES], [], None)

        def run_role(role: Role) -> object:
            if role == "architect":
                return analyze_architecture(structures, graph)
            if role == "security":
                return analyze_security(structures, dict(material.sources))
            if role == "testing":
                return analyze_testing(structures, graph, material.coverage_artifacts)
            if role == "refactoring":
                return analyze_refactoring(structures, quality, analyze_architecture(structures, graph))
            return generate_documentation(snapshot, material.document_sources)

        pool = ThreadPoolExecutor(max_workers=self.max_concurrency)
        futures = {role: pool.submit(run_role, role) for role in ROLES}
        deadline = monotonic() + self.timeout_seconds
        try:
            pending = set(futures.values())
            completed = set()
            while pending and not should_stop():
                done, pending = wait(pending, timeout=min(.05, max(0, deadline - monotonic())))
                completed.update(done)
                check_scope()
                if monotonic() >= deadline:
                    break
            cancelled = should_stop()
            results: dict[Role, object] = {}
            states = []
            for role, future in futures.items():
                if cancelled:
                    states.append(RoleState(role=role, status="cancelled"))
                elif future not in completed:
                    states.append(RoleState(role=role, status="timed_out", error_code="ROLE_TIMEOUT"))
                else:
                    try:
                        results[role] = future.result()
                        states.append(RoleState(role=role, status="succeeded"))
                    except Exception:
                        states.append(RoleState(role=role, status="failed", error_code="ROLE_FAILED"))
            check_scope()
            return self._report(snapshot, {} if cancelled else results, states,
                                [] if cancelled else quality, None if cancelled else graph)
        finally:
            for future in futures.values():
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _report(snapshot: RepositorySnapshot, results: dict[Role, object],
                states: list[RoleState], quality: list[AnalysisFinding],
                graph: DependencyGraph | None) -> OrchestrationReport:
        items, conflicts = _merge(results, quality)
        successes = sum(state.status == "succeeded" for state in states)
        status = ("cancelled" if any(state.status == "cancelled" for state in states)
                  else "succeeded" if successes == len(ROLES)
                  else "partial" if successes else "failed")
        return OrchestrationReport(
            snapshot=SnapshotIdentity.from_source(snapshot),
            status=status, roles=states, items=items, conflicts=conflicts,
            dependency_graph=graph,
            architecture=results.get("architect"), testing=results.get("testing"),
            refactoring=results.get("refactoring"), documentation=results.get("documentation"))
