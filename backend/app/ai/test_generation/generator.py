"""Produce test-design drafts without running or transmitting repository code."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import ClassVar, Literal

from pydantic import Field

from app.parsers.python.parser import parse_file as parse_python
from app.parsers.typescript.parser import parse_file as parse_typescript
from app.parsers.java.parser import parse_file as parse_java
from app.parsers.csharp.parser import parse_file as parse_csharp
from app.parsers.cpp.parser import parse_file as parse_cpp
from app.analyzers.dependencies.graph import DependencyGraph
from app.analyzers.testing import TestingReport, analyze_testing
from app.contracts.analysis import SourceLocation, WireModel


class TestScenario(WireModel):
    kind: Literal["success", "error"]
    title: str
    evidence: SourceLocation
    known_fact: str
    inputs: str | None
    expected: str | None
    expectation_source: Literal["supplied", "unknown"]
    missing_information: list[str]


class TestDraft(WireModel):
    service_path: str
    service_name: str
    discovery_status: Literal["potentially_untested"]
    origin: Literal["deterministic"]
    verification: Literal["draft_unverified"]
    scenarios: list[TestScenario]
    framework: str | None
    code: str | None
    limitations: list[str]


class TestGenerationReport(WireModel):
    drafts: list[TestDraft]
    ai_status: Literal["unavailable"] = "unavailable"
    limitations: list[str]


class TestAuthoringContext(WireModel):
    """Caller-supplied API and expected behavior for one reviewable test pair.

    Framework is checked against a discovered test file and the signature is
    checked against reparsed source; semantic expectations remain user supplied.
    """

    __test__: ClassVar[bool] = False

    service_path: str
    service_name: str
    source_text: str
    framework_test_path: str
    framework: Literal["pytest", "vitest", "junit", "xunit", "gtest"]
    method_name: str
    signature_text: str
    call_kind: Literal["sync_instance_value"]
    target_import: str
    additional_imports: list[str] = Field(default_factory=list)
    constructor_expression: str
    success_arguments: str
    success_expected: str
    error_arguments: str
    error_type: str
    result_type: str | None = None


_LANGUAGES = (
    (".py", parse_python, "pytest"),
    ((".ts", ".tsx", ".mts", ".cts"), parse_typescript, "vitest"),
    (".java", parse_java, "junit"),
    (".cs", parse_csharp, "xunit"),
    ((".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"), parse_cpp, "gtest"),
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "service"


def _single_line(value: str, label: str) -> str:
    if not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} must be a nonempty single line")
    return value.strip()


def _language(path: str) -> tuple[object, str] | None:
    for extensions, parser, framework in _LANGUAGES:
        if path.endswith(extensions):
            return parser, framework
    return None


def _validate_context(context: TestAuthoringContext, files: dict[str, object],
                      report: TestingReport) -> SourceLocation:
    file = files.get(context.service_path)
    if file is None:
        raise ValueError("context source path is outside parser snapshot")
    language = _language(context.service_path)
    if language is None:
        raise ValueError("unsupported source language")
    parser, expected_framework = language
    if context.framework != expected_framework:
        raise ValueError("framework does not match source language")
    discovered = next((test for test in report.test_files
                       if test.path == context.framework_test_path), None)
    if discovered is None or discovered.framework != context.framework or discovered.declaration_count < 1:
        raise ValueError("framework lacks a matching T14 test declaration")
    if len(context.source_text.encode("utf-8")) > 1_000_000:
        raise ValueError("source text exceeds 1 MB")
    parsed = parser(context.service_path, context.source_text)
    if parsed != file:
        raise ValueError("context source differs from supplied parser structure")
    separator = "::" if expected_framework == "gtest" else "."
    qualified = context.service_name + separator + context.method_name
    method = next((symbol for symbol in file.symbols
                   if symbol.kind == "method" and symbol.qualified_name == qualified), None)
    if method is None:
        raise ValueError("context method is absent from parsed service source")
    source_lines = context.source_text.splitlines()
    line = source_lines[method.location.start_line - 1]
    signature = _single_line(context.signature_text, "signature")
    if signature not in line:
        raise ValueError("signature is not present at parsed method location")
    declaration = line[:line.index(signature) + len(signature)]
    if re.search(r"\basync\b|\bstatic\b", declaration):
        raise ValueError("signature is not a synchronous instance method")
    if context.framework == "pytest" and method.location.start_line > 1:
        previous = source_lines[method.location.start_line - 2].strip()
        if previous in ("@staticmethod", "@classmethod"):
            raise ValueError("signature is not a synchronous instance method")
    for label in ("target_import", "constructor_expression", "success_arguments",
                  "success_expected", "error_arguments", "error_type"):
        _single_line(getattr(context, label), label)
    for statement in context.additional_imports:
        _single_line(statement, "additional_import")
    if context.framework == "junit":
        expected_declaration = (rf"\b{re.escape(context.result_type or '')}\s+"
                                rf"{re.escape(context.method_name)}\s*\(")
        if (not context.result_type or context.result_type == "void"
                or not re.search(expected_declaration, declaration)):
            raise ValueError("Java result type must be confirmed by signature")
    return method.location


def _render_code(context: TestAuthoringContext, location: SourceLocation) -> str:
    cls = context.service_name.rsplit(".", 1)[-1].rsplit("::", 1)[-1]
    method = context.method_name
    success = f"service.{method}({context.success_arguments})"
    error = f"service.{method}({context.error_arguments})"
    label = _slug(f"{cls}_{method}")
    header = f"DRAFT / UNVERIFIED — {location.path}:{location.start_line}; review expectations before running."
    extra_imports = "".join(statement + "\n" for statement in context.additional_imports)
    if context.framework == "pytest":
        return (f"# {header}\nimport pytest\n{context.target_import}\n\n"
                f"{extra_imports}"
                f"def test_{label}_success():\n"
                f"    service = {context.constructor_expression}\n"
                f"    result = {success}\n"
                f"    assert result == {context.success_expected}\n\n"
                f"def test_{label}_error():\n"
                f"    service = {context.constructor_expression}\n"
                f"    with pytest.raises({context.error_type}):\n"
                f"        {error}\n")
    if context.framework == "vitest":
        return (f"// {header}\nimport {{ test, expect }} from 'vitest';\n{context.target_import}\n{extra_imports}\n"
                f"test('{label} success', () => {{\n"
                f"  const service = {context.constructor_expression};\n"
                f"  const result = {success};\n"
                f"  expect(result).toBe({context.success_expected});\n}});\n\n"
                f"test('{label} error', () => {{\n"
                f"  const service = {context.constructor_expression};\n"
                f"  expect(() => {error}).toThrow({context.error_type});\n}});\n")
    if context.framework == "junit":
        return (f"// {header}\nimport org.junit.jupiter.api.Test;\n"
                f"import static org.junit.jupiter.api.Assertions.*;\n{context.target_import}\n{extra_imports}\n"
                f"class {cls}GeneratedTest {{\n"
                f"  @Test void {label}_success() {{\n"
                f"    {cls} service = {context.constructor_expression};\n"
                f"    {context.result_type} result = {success};\n"
                f"    assertEquals({context.success_expected}, result);\n  }}\n"
                f"  @Test void {label}_error() {{\n"
                f"    {cls} service = {context.constructor_expression};\n"
                f"    assertThrows({context.error_type}.class, () -> {error});\n  }}\n}}\n")
    if context.framework == "xunit":
        return (f"// {header}\nusing Xunit;\n{context.target_import}\n{extra_imports}\n"
                f"public class {cls}GeneratedTests {{\n"
                f"  [Fact] public void {label}_success() {{\n"
                f"    var service = {context.constructor_expression};\n"
                f"    var result = {success};\n"
                f"    Assert.Equal({context.success_expected}, result);\n  }}\n"
                f"  [Fact] public void {label}_error() {{\n"
                f"    var service = {context.constructor_expression};\n"
                f"    Assert.Throws<{context.error_type}>(() => {error});\n  }}\n}}\n")
    return (f"// {header}\n#include <gtest/gtest.h>\n{context.target_import}\n{extra_imports}\n"
            f"TEST({cls}Draft, {method}Success) {{\n"
            f"  auto service = {context.constructor_expression};\n"
            f"  auto result = {success};\n"
            f"  EXPECT_EQ({context.success_expected}, result);\n}}\n\n"
            f"TEST({cls}Draft, {method}Error) {{\n"
            f"  auto service = {context.constructor_expression};\n"
            f"  EXPECT_THROW({error}, {context.error_type});\n}}\n")


def generate_test_drafts(
    structures: Iterable[object],
    testing_report: TestingReport,
    graph: DependencyGraph | None = None,
    *,
    contexts: Iterable[TestAuthoringContext] = (),
) -> TestGenerationReport:
    """Draft scenarios for T14 candidates from one caller-authorized repository snapshot.

    Current contracts do not contain repository ID or SHA. The caller must bind
    structures, graph, and report to the same authorized commit. This function
    checks T14 discovery against the supplied parser snapshot, but cannot prove
    SHA identity when file paths and parsed facts happen to match.
    """
    files = list(structures)
    recomputed = analyze_testing(files, graph=graph)
    if (recomputed.services != testing_report.services
            or recomputed.test_files != testing_report.test_files):
        raise ValueError("T14 discovery differs from supplied parser snapshot")
    by_path = {file.path: file for file in files}
    context_by_service: dict[tuple[str, str], TestAuthoringContext] = {}
    for context in contexts:
        key = context.service_path, context.service_name
        if key in context_by_service:
            raise ValueError("duplicate authoring context for service")
        context_by_service[key] = context
    drafts: list[TestDraft] = []
    for service in sorted(testing_report.services, key=lambda item: (item.path, item.name)):
        if service.status != "potentially_untested":
            continue
        file = by_path[service.path]
        separator = "::" if service.path.endswith((".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx")) else "."
        methods = [symbol for symbol in file.symbols
                   if symbol.kind == "method" and symbol.qualified_name.rpartition(separator)[0] == service.name
                   and symbol.location.path == service.path]
        targets = [(symbol.name, symbol.location) for symbol in methods]
        if not targets:
            targets = [(service.name, service.location)]
        context = context_by_service.pop((service.path, service.name), None)
        method_location = _validate_context(context, by_path, testing_report) if context else None
        scenarios = [TestScenario(
            kind=kind,
            title=f"Review {kind} behavior for {target}",
            evidence=location,
            known_fact=f"Parser found {target} in a potentially untested service; T14 found no associated test declaration.",
            inputs=(context.success_arguments if kind == "success" else context.error_arguments)
                   if context and target == context.method_name else None,
            expected=(context.success_expected if kind == "success" else context.error_type)
                     if context and target == context.method_name else None,
            expectation_source="supplied" if context and target == context.method_name else "unknown",
            missing_information=(["Review supplied setup, inputs, and expected behavior against the business rule"]
                                 if context and target == context.method_name else [
                                     "Actual callable signature and setup/fixtures",
                                     "Business rule and expected successful result" if kind == "success"
                                     else "Failure condition and expected error behavior",
                                 ]),
        ) for target, location in targets for kind in ("success", "error")]
        drafts.append(TestDraft(
            service_path=service.path,
            service_name=service.name,
            discovery_status="potentially_untested",
            origin="deterministic",
            verification="draft_unverified",
            scenarios=scenarios,
            framework=context.framework if context else None,
            code=_render_code(context, method_location) if context else None,
            limitations=[
                "T14's potentially untested classification is a discovery hint, not proof that no test exists.",
                "Supplied call expressions and expectations are not verified business rules; the draft was not run."
                if context else "No verified signature, framework, and expectations were supplied; code was not fabricated.",
            ],
        ))
    if context_by_service:
        raise ValueError("authoring context has no potentially untested T14 service candidate")
    return TestGenerationReport(
        drafts=drafts,
        limitations=[
            "No LLM provider is configured; output is a deterministic template, not AI-generated analysis.",
            "Parser and T14 contracts lack repository ID and commit SHA; caller must enforce the authorized snapshot.",
            "No analyzed repository code or generated user test is executed or sent to an external provider.",
            "Coverage, if supplied to T14, is separate evidence and is not inferred from these drafts.",
        ],
    )
