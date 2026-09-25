import pytest

from app.analyzers.testing import analyze_testing, parse_coverage_xml
from app.parsers.python.parser import parse_file as python
from app.parsers.typescript.parser import parse_file as typescript
from app.parsers.java.parser import parse_file as java
from app.parsers.csharp.parser import parse_file as csharp
from app.parsers.cpp.parser import parse_file as cpp


@pytest.mark.parametrize("parser,source_path,source,test_path,test_source", [
    (python, "pkg/order.py", "class OrderService:\n    def send(self): pass\n",
     "tests/test_order.py", "from pkg.order import OrderService\ndef test_send():\n    OrderService().send()\n"),
    (typescript, "src/order.ts", "export class OrderService { send() {} }",
     "src/order.test.ts", "import { OrderService } from './order'; test('send', () => { new OrderService().send(); });"),
    (java, "src/OrderService.java", "package demo; public class OrderService { public void send() {} }",
     "tests/OrderServiceTest.java", "package demo; import org.junit.jupiter.api.Test; import demo.OrderService; class OrderServiceTest { void testSend() { new OrderService().send(); } }"),
    (csharp, "src/OrderService.cs", "namespace Demo { public class OrderService { public void Send() {} } }",
     "tests/OrderServiceTests.cs", "using Xunit; using Demo; public class OrderServiceTests { public void TestSend() { new OrderService().Send(); } }"),
    (cpp, "src/order.hpp", "class OrderService { public: void send(); };",
     "tests/order_test.cpp", '#include "../src/order.hpp"\n#include <gtest/gtest.h>\nTEST(OrderService, Send) { OrderService service; service.send(); }'),
])
def test_five_parser_inputs_discover_tests_and_services(parser, source_path, source, test_path, test_source):
    report = analyze_testing([parser(source_path, source), parser(test_path, test_source)])
    assert len(report.services) == 1
    assert report.services[0].path == source_path
    assert report.services[0].name.endswith("OrderService")
    assert report.test_files[0].path == test_path
    assert report.test_files[0].declaration_count >= 1
    assert report.services[0].status == "associated_with_test"
    assert report.coverage is None
    assert report.coverage_status == "missing"


def test_resolved_python_dependency_associates_but_does_not_infer_coverage():
    report = analyze_testing([
        python("pkg/order.py", "class OrderService: pass"),
        python("tests/test_order.py", "from pkg.order import OrderService\ndef test_order():\n    OrderService()"),
    ])
    assert report.services[0].status == "associated_with_test"
    assert report.services[0].test_paths == ["tests/test_order.py"]
    assert report.coverage is None


def test_filename_similarity_and_non_test_files_do_not_prove_association():
    report = analyze_testing([
        python("pkg/order.py", "class OrderService: pass"),
        python("tests/test_order.py", "def test_unrelated(): pass"),
        python("tests/test_empty.py", "from pkg.order import OrderService"),
    ])
    assert report.services[0].status == "potentially_untested"
    assert report.services[0].test_paths == []
    assert [(test.path, test.declaration_count) for test in report.test_files] == [
        ("tests/test_empty.py", 0), ("tests/test_order.py", 1)]


def test_framework_import_alone_is_not_a_test_declaration():
    report = analyze_testing([
        java("src/OrderService.java", "package demo; public class OrderService {}"),
        java("tests/OrderServiceTest.java", "package demo; import org.junit.jupiter.api.Test; import demo.OrderService; class OrderServiceTest { void helper() { new OrderService(); } }"),
    ])
    assert report.test_files[0].framework == "junit"
    assert report.test_files[0].declaration_count == 0
    assert report.services[0].status == "potentially_untested"


def test_valid_existing_cobertura_and_jacoco_are_separate_evidence():
    files = [python("pkg/order.py", "class OrderService: pass")]
    cobertura = analyze_testing(files, coverage_artifacts={
        "coverage.xml": b'<coverage lines-covered="3" lines-valid="4" line-rate="0.75"/>'})
    assert cobertura.coverage.percent == 75.0
    assert cobertura.coverage.metric == "line"
    assert cobertura.services[0].status == "potentially_untested"
    jacoco = parse_coverage_xml("reports/jacoco.xml", b'<report name="demo"><counter type="LINE" missed="2" covered="8"/></report>')
    assert (jacoco.covered, jacoco.total, jacoco.percent) == (8, 10, 80.0)


@pytest.mark.parametrize("path,data", [
    ("../coverage.xml", b'<coverage lines-covered="1" lines-valid="1"/>'),
    ("C:/coverage.xml", b'<coverage lines-covered="1" lines-valid="1"/>'),
    ("report.xml", b'<coverage lines-covered="1" lines-valid="1"/>'),
    ("coverage.xml", b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><coverage lines-covered="1" lines-valid="1"/>'),
    ("coverage.xml", b'<coverage lines-covered="3" lines-valid="2"/>'),
    ("coverage.xml", b'<coverage lines-covered="1" lines-valid="2"'),
    ("coverage.xml", '<!DOCTYPE x [<!ENTITY x "boom">]><coverage lines-covered="1" lines-valid="1"/>'.encode("utf-16")),
    ("jacoco.xml", b'<report><package><counter type="LINE" missed="0" covered="3"/></package></report>'),
])
def test_bad_coverage_is_rejected(path, data):
    with pytest.raises(ValueError):
        parse_coverage_xml(path, data)
    report = analyze_testing([], coverage_artifacts={path: data})
    assert report.coverage is None
    assert report.coverage_status == "invalid"


def test_oversized_coverage_is_rejected():
    with pytest.raises(ValueError, match="2 MB"):
        parse_coverage_xml("coverage.xml", b"x" * 2_000_001)


def test_graph_must_match_parser_snapshot():
    from app.analyzers.dependencies import analyze_dependencies

    graph = analyze_dependencies([python("a.py", "class AService: pass")])
    with pytest.raises(ValueError, match="snapshot"):
        analyze_testing([python("b.py", "class BService: pass")], graph=graph)
