import ast

import pytest

from app.ai.test_generation import TestAuthoringContext, generate_test_drafts
from app.analyzers.testing import analyze_testing
from app.parsers.python.parser import parse_file as python
from app.parsers.typescript.parser import parse_file as typescript
from app.parsers.java.parser import parse_file as java
from app.parsers.csharp.parser import parse_file as csharp
from app.parsers.cpp.parser import parse_file as cpp


def test_python_service_gets_success_and_error_drafts_without_claiming_execution():
    files = [python("pkg/order.py", "class OrderService:\n    def create(self, user, product): pass\n")]
    report = generate_test_drafts(files, analyze_testing(files))

    assert report.ai_status == "unavailable"
    assert len(report.drafts) == 1
    draft = report.drafts[0]
    assert draft.origin == "deterministic"
    assert draft.verification == "draft_unverified"
    assert draft.discovery_status == "potentially_untested"
    assert [scenario.kind for scenario in draft.scenarios] == ["success", "error"]
    assert all(scenario.evidence.path == "pkg/order.py" for scenario in draft.scenarios)
    assert all(scenario.missing_information for scenario in draft.scenarios)
    assert all(scenario.expectation_source == "unknown" for scenario in draft.scenarios)
    assert draft.code is None
    assert draft.framework is None


def test_associated_service_is_not_reported_as_untested():
    files = [
        python("pkg/order.py", "class OrderService: pass"),
        python("tests/test_order.py", "from pkg.order import OrderService\ndef test_order(): OrderService()"),
    ]
    report = generate_test_drafts(files, analyze_testing(files))
    assert report.drafts == []


@pytest.mark.parametrize("parser,path,source", [
    (typescript, "src/order.ts", "export class OrderService { create() {} }"),
    (java, "src/OrderService.java", "public class OrderService { public void create() {} }"),
    (csharp, "src/OrderService.cs", "public class OrderService { public void Create() {} }"),
    (cpp, "src/order.hpp", "class OrderService { public: void create(); };"),
])
def test_non_python_candidate_has_scenarios_but_no_guessed_test_framework(parser, path, source):
    files = [parser(path, source)]
    draft = generate_test_drafts(files, analyze_testing(files)).drafts[0]
    assert [scenario.kind for scenario in draft.scenarios] == ["success", "error"]
    assert draft.code is None
    assert draft.framework is None
    assert any("framework" in item.lower() for item in draft.limitations)


def test_t14_result_must_match_parser_snapshot():
    earlier = [python("pkg/order.py", "class OrderService: pass")]
    current = [python("pkg/order.py", "class PaymentService: pass")]
    with pytest.raises(ValueError, match="T14"):
        generate_test_drafts(current, analyze_testing(earlier))


def test_parse_errors_and_no_service_do_not_produce_drafts():
    files = [python("pkg/broken.py", "class BrokenService("), python("pkg/tool.py", "def run(): pass")]
    assert generate_test_drafts(files, analyze_testing(files)).drafts == []


@pytest.mark.parametrize("parser,service_path,source,test_path,test_source,framework,signature,method,import_line,constructor,success_expected,error_type", [
    (python, "pkg/order.py", "class OrderService:\n    def create(self, amount):\n        if amount < 0: raise ValueError()\n        return amount\n",
     "tests/test_other.py", "import pytest\ndef test_other(): pass", "pytest",
     "def create(self, amount):", "create", "from pkg.order import OrderService", "OrderService()", "5", "ValueError"),
    (typescript, "src/order.ts", "export class OrderService { create(amount: number): number { if (amount < 0) throw new Error(); return amount; } }",
     "src/other.test.ts", "import { test } from 'vitest'; test('other', () => {});", "vitest",
     "create(amount: number): number", "create", "import { OrderService } from './order';", "new OrderService()", "5", "Error"),
    (java, "src/OrderService.java", "package demo; public class OrderService { public int create(int amount) { if (amount < 0) throw new IllegalArgumentException(); return amount; } }",
     "tests/OtherTest.java", "import org.junit.jupiter.api.Test; class OtherTest { void testOther() {} }", "junit",
     "create(int amount)", "create", "import demo.OrderService;", "new OrderService()", "5", "IllegalArgumentException"),
    (csharp, "src/OrderService.cs", "namespace Demo { public class OrderService { public int Create(int amount) { if (amount < 0) throw new System.ArgumentException(); return amount; } } }",
     "tests/OtherTests.cs", "using Xunit; public class OtherTests { public void TestOther() {} }", "xunit",
     "Create(int amount)", "Create", "using Demo;", "new OrderService()", "5", "System.ArgumentException"),
    (cpp, "src/order.hpp", "#include <stdexcept>\nclass OrderService { public: int create(int amount) { if (amount < 0) throw std::invalid_argument(\"amount\"); return amount; } };",
     "tests/other_test.cpp", '#include <gtest/gtest.h>\nTEST(Other, Works) {}', "gtest",
     "create(int amount)", "create", '#include "../src/order.hpp"', "OrderService{}", "5", "std::invalid_argument"),
])
def test_context_renders_api_bound_draft_for_five_languages(
    parser, service_path, source, test_path, test_source, framework, signature,
    method, import_line, constructor, success_expected, error_type,
):
    files = [parser(service_path, source), parser(test_path, test_source)]
    discovery = analyze_testing(files)
    context = TestAuthoringContext(
        service_path=service_path, service_name=discovery.services[0].name, source_text=source,
        framework_test_path=test_path, framework=framework,
        method_name=method, signature_text=signature, call_kind="sync_instance_value",
        target_import=import_line,
        additional_imports=["#include <stdexcept>"] if framework == "gtest" else [],
        constructor_expression=constructor, success_arguments="5",
        success_expected=success_expected, error_arguments="-1", error_type=error_type,
        result_type="int" if framework == "junit" else None,
    )
    draft = generate_test_drafts(files, discovery, contexts=[context]).drafts[0]
    assert draft.code is not None
    assert draft.framework == framework
    assert f".{method}(5)" in draft.code
    assert f".{method}(-1)" in draft.code
    assert import_line in draft.code
    assert {"pytest": "pytest.raises", "vitest": "toThrow(",
            "junit": "assertThrows(", "xunit": "Assert.Throws<",
            "gtest": "EXPECT_THROW("}[framework] in draft.code
    assert success_expected in draft.code
    assert error_type in draft.code
    assert "pytest.fail" not in draft.code
    assert draft.verification == "draft_unverified"
    assert [(scenario.inputs, scenario.expected, scenario.expectation_source)
            for scenario in draft.scenarios] == [
                ("5", success_expected, "supplied"), ("-1", error_type, "supplied")]
    if framework == "pytest":
        ast.parse(draft.code)
    assert parser(test_path, draft.code).errors == []


def test_context_rejects_unverified_signature_and_framework():
    source = "class OrderService:\n    def create(self, amount): return amount"
    files = [python("pkg/order.py", source),
             python("tests/test_other.py", "import pytest\ndef test_other(): pass")]
    base = dict(service_path="pkg/order.py", service_name="OrderService", source_text=source,
                framework_test_path="tests/test_other.py", framework="pytest", method_name="create",
                signature_text="def create(self, amount):", call_kind="sync_instance_value",
                target_import="from pkg.order import OrderService",
                constructor_expression="OrderService()", success_arguments="5", success_expected="5",
                error_arguments="-1", error_type="ValueError")
    with pytest.raises(ValueError, match="signature"):
        generate_test_drafts(files, analyze_testing(files), contexts=[TestAuthoringContext(
            **{**base, "signature_text": "def create(self, phantom):"})])
    with pytest.raises(ValueError, match="framework"):
        generate_test_drafts(files, analyze_testing(files), contexts=[TestAuthoringContext(
            **{**base, "framework": "vitest"})])
    no_framework = [files[0], python("tests/test_other.py", "def test_other(): pass")]
    with pytest.raises(ValueError, match="framework"):
        generate_test_drafts(no_framework, analyze_testing(no_framework), contexts=[TestAuthoringContext(**base)])
    with pytest.raises(ValueError, match="source"):
        generate_test_drafts(files, analyze_testing(files), contexts=[TestAuthoringContext(
            **{**base, "source_text": source.replace("create", "change")})])


def test_async_method_is_not_rendered_as_synchronous():
    source = "class OrderService:\n    async def create(self, amount): return amount"
    files = [python("pkg/order.py", source),
             python("tests/test_other.py", "import pytest\ndef test_other(): pass")]
    context = TestAuthoringContext(
        service_path="pkg/order.py", service_name="OrderService", source_text=source,
        framework_test_path="tests/test_other.py", framework="pytest",
        method_name="create", signature_text="def create(self, amount):",
        call_kind="sync_instance_value", target_import="from pkg.order import OrderService",
        constructor_expression="OrderService()", success_arguments="5", success_expected="5",
        error_arguments="-1", error_type="ValueError",
    )
    with pytest.raises(ValueError, match="synchronous"):
        generate_test_drafts(files, analyze_testing(files), contexts=[context])
