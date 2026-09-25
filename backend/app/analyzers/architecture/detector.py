"""Conservative architecture signals; repository source is never executed."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.dependencies.graph import DependencyEdge, DependencyGraph
from app.contracts.analysis import SourceLocation, WireModel


Architecture = Literal["mvc", "layered", "clean", "hexagonal", "microservices", "modular_monolith", "event_driven"]
Assessment = Literal["supported", "mixed", "insufficient"]
Confidence = Literal["low", "medium", "high"]


class ArchitectureEvidence(WireModel):
    description: str
    location: SourceLocation


class ArchitectureHypothesis(WireModel):
    architecture: Architecture
    assessment: Assessment
    confidence: Confidence
    reasons: list[ArchitectureEvidence]
    contradictions: list[ArchitectureEvidence]
    uncertainties: list[str]


class ArchitectureReport(WireModel):
    hypotheses: list[ArchitectureHypothesis]
    summary: Literal["single", "mixed", "unknown"]
    primary: Architecture | None


_ROLES = {
    "controller": "presentation", "controllers": "presentation", "view": "view", "views": "view",
    "presentation": "presentation", "api": "presentation", "application": "application",
    "usecases": "application", "use_cases": "application", "domain": "domain",
    "model": "model", "models": "model", "infrastructure": "infrastructure",
    "adapter": "adapter", "adapters": "adapter", "port": "port", "ports": "port",
    "events": "event", "event": "event",
}
_ORDER: tuple[Architecture, ...] = (
    "mvc", "layered", "clean", "hexagonal", "microservices", "modular_monolith", "event_driven"
)


def _role(path: str) -> str | None:
    # Names only locate candidates. Every supported rule also needs a resolved edge.
    for segment in path.lower().split("/")[:-1]:
        if segment in _ROLES:
            return _ROLES[segment]
    return None


def _file(node_id: str, paths: dict[str, str]) -> str | None:
    return paths.get(node_id)


def _group(path: str, root: str) -> str | None:
    parts = path.lower().split("/")
    for index, part in enumerate(parts[:-2]):
        if part == root:
            return parts[index + 1]
    return None


def _evidence(edge: DependencyEdge, description: str) -> ArchitectureEvidence:
    return ArchitectureEvidence(description=description, location=edge.location)


def analyze_architecture(structures: Iterable[object], graph: DependencyGraph | None = None) -> ArchitectureReport:
    """Return hypotheses with source-linked support and counterevidence.

    A supplied T10 graph must describe exactly the same file snapshot. The caller
    owns repository identity and commit SHA, which neither parser nor graph carries.
    """
    files = list(structures)
    expected = {file.path for file in files}
    if len(expected) != len(files):
        raise ValueError("duplicate source path")
    graph = graph if graph is not None else analyze_dependencies(files)
    graph_files = {node.location.path for node in graph.nodes if node.kind == "file"}
    if expected != graph_files:
        raise ValueError("graph file snapshot differs from structures")
    paths = {node.id: node.location.path for node in graph.nodes}
    resolved: list[tuple[DependencyEdge, str, str]] = []
    for edge in graph.edges:
        if edge.status != "resolved" or edge.target is None:
            continue
        source, target = _file(edge.source, paths), _file(edge.target, paths)
        if source is not None and target is not None and source != target:
            resolved.append((edge, source, target))

    pairs: dict[tuple[str, str], list[ArchitectureEvidence]] = defaultdict(list)
    for edge, source, target in resolved:
        left, right = _role(source), _role(target)
        if left and right and left != right:
            pairs[left, right].append(_evidence(edge, f"Resolved {edge.kind}: {source} -> {target}"))

    hypotheses: list[ArchitectureHypothesis] = []

    def add(name: Architecture, required: tuple[tuple[str, str], ...],
            forbidden: tuple[tuple[str, str], ...] = (),
            uncertainty: str = "Static dependencies do not prove runtime composition.") -> None:
        reasons = [pairs[pair][0] for pair in required if pairs[pair]]
        contradictions = [pairs[pair][0] for pair in forbidden if pairs[pair]]
        complete = len(reasons) == len(required)
        assessment: Assessment = "mixed" if complete and contradictions else "supported" if complete else "insufficient"
        # Ordinal evidence strength, never a calibrated probability.
        confidence: Confidence = "high" if complete and len(reasons) >= 3 and not contradictions else "medium" if complete and not contradictions else "low"
        missing = [f"Missing resolved {_a} -> {_b} relationship" for _a, _b in required if not pairs[_a, _b]]
        uncertainties = [*missing, uncertainty]
        if contradictions:
            uncertainties.append("Opposite dependency direction conflicts with this pattern.")
        hypotheses.append(ArchitectureHypothesis(architecture=name, assessment=assessment,
                            confidence=confidence, reasons=reasons, contradictions=contradictions,
                            uncertainties=uncertainties))

    add("mvc", (("presentation", "model"), ("presentation", "view")),
        (("model", "presentation"),), "The graph cannot prove request handling or rendering behavior.")
    add("layered", (("presentation", "application"), ("application", "domain")),
        (("domain", "application"), ("domain", "presentation")),
        "Layer names and imports do not prove all runtime paths follow the layers.")
    add("clean", (("presentation", "application"), ("application", "domain"), ("infrastructure", "domain")),
        (("domain", "infrastructure"), ("domain", "presentation")),
        "Ports and dependency inversion need more than static import direction to verify.")
    add("hexagonal", (("adapter", "port"), ("application", "port")),
        (("port", "adapter"),), "Port interfaces and runtime adapter injection are not proven.")

    def grouped(name: Architecture, root: str, entrypoints: bool) -> None:
        groups = {group for path in expected if (group := _group(path, root))}
        internal: dict[str, ArchitectureEvidence] = {}
        crossing: list[ArchitectureEvidence] = []
        for edge, source, target in resolved:
            left, right = _group(source, root), _group(target, root)
            if left and left == right:
                internal.setdefault(left, _evidence(edge, f"Resolved dependency within {root}/{left}"))
            elif left and right and left != right:
                crossing.append(_evidence(edge, f"Resolved dependency crosses {root}/{left} -> {root}/{right}"))
        entries = {group for path in expected if (group := _group(path, root)) and
                   path.lower().split("/")[-1] in ("main.py", "app.py", "program.cs", "main.java", "index.ts")}
        ready = len(groups) >= 2 and all(group in internal for group in groups)
        if entrypoints:
            ready = ready and groups <= entries
        else:
            # One repository entry point connecting distinct modules is positive evidence.
            used = {right for _, source, target in resolved if _group(source, root) is None
                    if (right := _group(target, root))}
            ready = ready and len(used) >= 2
        reasons = [internal[group] for group in sorted(groups) if group in internal]
        if not entrypoints:
            reasons.extend(_evidence(edge, f"Shared entry point imports {root}/{_group(target, root)}")
                           for edge, source, target in resolved if _group(source, root) is None
                           and _group(target, root) in groups)
        uncertainties = [] if ready else ["Need two connected units and the expected entry point topology."]
        uncertainties.append("Deployment boundaries and runtime processes are unavailable from parser output." if entrypoints
                             else "A shared process cannot be confirmed from parser output.")
        hypotheses.append(ArchitectureHypothesis(architecture=name,
            assessment="mixed" if ready and crossing else "supported" if ready else "insufficient",
            confidence="low" if crossing or not ready or entrypoints else "medium",
            reasons=reasons, contradictions=crossing[:3], uncertainties=uncertainties))

    grouped("microservices", "services", True)
    grouped("modular_monolith", "modules", False)

    publishers: list[ArchitectureEvidence] = []
    subscribers: list[ArchitectureEvidence] = []
    for edge, source, target in resolved:
        if _role(target) != "event" or edge.kind != "call":
            continue
        target_name = edge.target.rsplit(":", 1)[-1].lower()
        if target_name.endswith(("publish", "emit", "dispatch")):
            publishers.append(_evidence(edge, "Resolved event publication call"))
        if target_name.endswith(("subscribe", "register", "on_event")):
            subscribers.append(_evidence(edge, "Resolved event subscription call"))
    event_ready = bool(publishers and subscribers)
    hypotheses.append(ArchitectureHypothesis(architecture="event_driven",
        assessment="supported" if event_ready else "insufficient",
        confidence="medium" if event_ready else "low",
        reasons=publishers[:1] + subscribers[:1], contradictions=[],
        uncertainties=["Calls suggest event flow but do not prove asynchronous delivery or broker semantics."] +
                      ([] if event_ready else ["Need resolved publish and subscribe calls into an event component."])))

    assert tuple(item.architecture for item in hypotheses) == _ORDER
    supported = [item for item in hypotheses if item.assessment == "supported"]
    return ArchitectureReport(hypotheses=hypotheses,
        summary="single" if len(supported) == 1 else "mixed" if len(supported) > 1 or
                any(item.assessment == "mixed" for item in hypotheses) else "unknown",
        primary=supported[0].architecture if len(supported) == 1 else None)
