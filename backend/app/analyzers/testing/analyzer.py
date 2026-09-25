"""Discover likely tests without executing the analyzed repository."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET

from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.dependencies.graph import DependencyGraph
from app.contracts.analysis import SourceLocation, WireModel


class TestFile(WireModel):
    path: str
    framework: str | None
    declaration_count: int


class ServiceCandidate(WireModel):
    path: str
    name: str
    location: SourceLocation
    status: str  # associated_with_test or potentially_untested
    test_paths: list[str]


class CoverageEvidence(WireModel):
    artifact_path: str
    format: str
    metric: str
    covered: int
    total: int
    percent: float


class TestingReport(WireModel):
    test_files: list[TestFile]
    services: list[ServiceCandidate]
    coverage: CoverageEvidence | None
    coverage_status: str  # available, missing, invalid
    coverage_errors: list[str]


_EXTENSIONS = (".py", ".ts", ".tsx", ".mts", ".cts", ".java", ".cs",
               ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h")
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
_FRAMEWORK_IMPORTS = {
    "pytest": ("pytest",),
    "unittest": ("unittest",),
    "jest": ("@jest/", "jest"),
    "vitest": ("vitest",),
    "mocha": ("mocha",),
    "junit": ("org.junit",),
    "testng": ("org.testng",),
    "xunit": ("xunit",),
    "nunit": ("nunit",),
    "mstest": ("microsoft.visualstudio.testtools",),
    "gtest": ("gtest/", "gmock/"),
    "catch2": ("catch2/",),
    "doctest": ("doctest/",),
}


def _test_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    stem = name.rsplit(".", 1)[0]
    return (any(part.lower() in _TEST_DIRS for part in parts[:-1])
            or stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec", "tests", "test")))


def _framework(file: object) -> str | None:
    names = [item.name.lower() for item in file.imports]
    for framework, prefixes in _FRAMEWORK_IMPORTS.items():
        if any(name == prefix or (prefix.endswith(("/", ".")) and name.startswith(prefix))
               or name.startswith(prefix + ".") or name.startswith(prefix + "/")
               for name in names for prefix in prefixes):
            return framework
    return None


def _test_declarations(file: object, framework: str | None) -> int:
    path = file.path.lower()
    symbols = file.symbols
    calls = file.calls
    if path.endswith(".py"):
        return sum(s.kind in ("function", "method") and s.name.startswith("test_") for s in symbols)
    if path.endswith((".ts", ".tsx", ".mts", ".cts")):
        return sum(c.callee.rsplit(".", 1)[-1] in {"test", "it"} for c in calls)
    if path.endswith(".java"):
        return sum(s.kind == "method" and s.name.lower().startswith("test")
                   for s in symbols)
    if path.endswith(".cs"):
        return sum(s.kind == "method" and s.name.lower().startswith("test") for s in symbols)
    if framework not in ("gtest", "catch2", "doctest"):
        return 0
    macros = {"TEST", "TEST_F", "TEST_P"} if framework == "gtest" else {"SCENARIO", "TEST_CASE"}
    return sum(s.kind == "function" and s.name in macros for s in symbols)


def _artifact_path(path: str) -> None:
    SourceLocation(path=path, start_line=1, end_line=1)
    if path.lower().split("/")[-1] not in {"coverage.xml", "jacoco.xml"}:
        raise ValueError("unsupported coverage artifact name")


def parse_coverage_xml(path: str, data: bytes | str) -> CoverageEvidence:
    """Read bounded aggregate XML counters; no file access or entity expansion."""
    _artifact_path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > 2_000_000:
        raise ValueError("coverage artifact exceeds 2 MB")
    if b"\x00" in raw:
        raise ValueError("NUL or UTF-16 XML is unsupported")
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.IGNORECASE):
        raise ValueError("DTD and entities are forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("malformed coverage XML") from exc
    if root.tag == "coverage":
        format_name = "cobertura"
        covered_text, total_text = root.get("lines-covered"), root.get("lines-valid")
    elif root.tag == "report":
        format_name = "jacoco"
        counters = [child for child in root if child.tag == "counter" and child.get("type") == "LINE"]
        if len(counters) != 1:
            raise ValueError("JaCoCo report needs exactly one root LINE counter")
        covered_text = counters[0].get("covered")
        missed_text = counters[0].get("missed")
        if missed_text is None or not re.fullmatch(r"\d+", missed_text):
            raise ValueError("invalid missed line counter")
        total_text = str(int(covered_text or "-1") + int(missed_text)) if covered_text and covered_text.isdecimal() else None
    else:
        raise ValueError("unsupported coverage XML format")
    if not covered_text or not total_text or not covered_text.isdecimal() or not total_text.isdecimal():
        raise ValueError("invalid line counters")
    covered, total = int(covered_text), int(total_text)
    if total <= 0 or covered > total:
        raise ValueError("inconsistent line counters")
    return CoverageEvidence(artifact_path=path, format=format_name, metric="line", covered=covered,
                            total=total, percent=round(100 * covered / total, 2))


def analyze_testing(structures: Iterable[object], graph: DependencyGraph | None = None,
                    coverage_artifacts: Mapping[str, bytes | str] | None = None) -> TestingReport:
    """Accept five parser outputs and optional existing coverage bytes from the same snapshot.

    The caller must bind all inputs to one repository ID and commit SHA. A resolved
    test-to-service dependency is an association, never proof of executed tests.
    """
    files = list(structures)
    by_path = {file.path: file for file in files}
    if len(by_path) != len(files):
        raise ValueError("duplicate source path")
    for file in files:
        SourceLocation(path=file.path, start_line=1, end_line=1)
        if not file.path.lower().endswith(_EXTENSIONS):
            raise ValueError(f"unsupported source path: {file.path}")
    graph = graph if graph is not None else analyze_dependencies(files)
    graph_paths = {node.location.path for node in graph.nodes if node.kind == "file"}
    if graph_paths != set(by_path):
        raise ValueError("graph file snapshot differs from structures")
    node_paths = {node.id: node.location.path for node in graph.nodes}

    tests: list[TestFile] = []
    test_paths: set[str] = set()
    for file in sorted(files, key=lambda item: item.path):
        if not _test_path(file.path) or file.errors:
            continue
        framework = _framework(file)
        count = _test_declarations(file, framework)
        tests.append(TestFile(path=file.path, framework=framework, declaration_count=count))
        if count:
            test_paths.add(file.path)

    associated: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.status != "resolved" or edge.target is None or edge.kind not in ("import", "call"):
            continue
        source = node_paths.get(edge.source)
        target = node_paths.get(edge.target)
        if source in test_paths and target in by_path and source != target:
            associated.setdefault(target, set()).add(source)

    services: list[ServiceCandidate] = []
    for file in sorted(files, key=lambda item: item.path):
        if _test_path(file.path) or file.errors:
            continue
        for symbol in file.symbols:
            if symbol.kind in ("class", "struct", "interface") and symbol.name.lower().endswith("service"):
                paths = sorted(associated.get(file.path, set()))
                services.append(ServiceCandidate(path=file.path, name=symbol.qualified_name,
                                                 location=symbol.location,
                                                 status="associated_with_test" if paths else "potentially_untested",
                                                 test_paths=paths))

    coverage: CoverageEvidence | None = None
    errors: list[str] = []
    artifacts = coverage_artifacts or {}
    if artifacts:
        for path in sorted(artifacts):
            try:
                parsed = parse_coverage_xml(path, artifacts[path])
                if coverage is not None:
                    raise ValueError("multiple coverage artifacts; select one for the snapshot")
                coverage = parsed
            except (ValueError, TypeError) as exc:
                errors.append(f"{path}: {exc}")
        if errors:
            coverage = None
    return TestingReport(test_files=tests, services=services, coverage=coverage,
                         coverage_status="invalid" if errors else "available" if coverage else "missing",
                         coverage_errors=errors)
