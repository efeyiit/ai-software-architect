"""Diagram fixtures built from the real Python and TypeScript parser outputs."""

import pytest

from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.dependencies.graph import DependencyGraph, DependencyNode
from app.diagrams import render_diagrams, render_mermaid, render_plantuml
from app.parsers import python, typescript


def parsed(parser, path, source):
    result = parser.parse_file(path, source)
    assert not result.errors, result.errors
    return result


def structures():
    return [
        parsed(python, "pkg/base.py", "class Base:\n    def work(self): pass\n"),
        parsed(python, "pkg/app.py", "from .base import Base\nclass App(Base):\n    def run(self):\n        self.work()\n        print('ok')\n"),
        parsed(typescript, "web/client.ts", "import { send } from './service';\nexport class Client { run() { send(); } }\n"),
        parsed(typescript, "web/service.ts", "export function send() {}\n"),
    ]


def graph():
    return analyze_dependencies(structures())


def test_all_views_in_both_formats_from_real_parser_graph():
    result = render_diagrams(graph(), structures())
    assert set(result) == {"mermaid", "plantuml"}
    for bundle in result.values():
        assert "classDiagram" in bundle.class_diagram or "@startuml" in bundle.class_diagram
        assert "inferred" in bundle.sequence_diagram.lower()
        assert "runtime trace" in bundle.sequence_diagram.lower()
        assert "flowchart LR" in bundle.component_diagram or "@startuml" in bundle.component_diagram
        assert "external" in bundle.component_diagram or "ambiguous" in bundle.component_diagram or "resolved" in bundle.component_diagram


def test_static_calls_are_marked_inferred_and_external_call_is_not_resolved():
    result = graph()
    sequence = render_mermaid(result, "sequence")
    assert "Inferred static call order, not a runtime trace" in sequence
    assert "(inferred)" in sequence
    assert "call ambiguous print" in sequence


def test_untrusted_labels_cannot_create_diagram_directives_or_markup():
    node = DependencyNode(id="file:evil.py", kind="file", language="python",
                          name='Injected"\n!include https://bad.example<img>',
                          location={"path": "evil.py", "start_line": 1, "end_line": 1})
    source = DependencyGraph(nodes=[node], edges=[], cycles=[], critical_nodes=[])
    rendered = render_plantuml(source, "component")
    mermaid = render_mermaid(source, "component")
    assert "!include https://bad.example" not in rendered
    assert "<img>" not in rendered
    assert "&lt;img&gt;" in rendered
    assert rendered.count("@startuml") == rendered.count("@enduml") == 1
    assert "!include https://bad.example" not in mermaid
    assert "<img>" not in mermaid
    assert "&lt;img&gt;" in mermaid
    assert "＂" in mermaid
    # IDs are generated from hashes, never copied from repository labels.
    assert " as n_" in rendered


def test_deterministic_order_unicode_and_special_characters():
    first = graph()
    second = DependencyGraph(nodes=list(reversed(first.nodes)), edges=list(reversed(first.edges)),
                             cycles=list(reversed(first.cycles)), critical_nodes=list(reversed(first.critical_nodes)))
    assert render_diagrams(first) == render_diagrams(second)
    assert "pkg/app.py" in render_mermaid(first, "component")
    unicode_node = DependencyNode(id="file:unicode.py", kind="file", language="python",
                                  name="Sınıf λ", location={"path": "unicode.py", "start_line": 1, "end_line": 1})
    unicode_graph = DependencyGraph(nodes=[unicode_node], edges=[], cycles=[], critical_nodes=[])
    assert "Sınıf λ" in render_mermaid(unicode_graph, "component")


def test_parser_symbol_kinds_limit_class_view_to_actual_classes():
    source_structures = [parsed(python, "kinds.py", "class RealClass:\n    pass\ndef helper():\n    pass\n")]
    parsed_graph = analyze_dependencies(source_structures)
    diagram = render_mermaid(parsed_graph, "class", source_structures)
    assert "RealClass" in diagram
    assert "helper" not in diagram


def test_empty_graph_is_valid_and_explicitly_inferred():
    empty = DependencyGraph(nodes=[], edges=[], cycles=[], critical_nodes=[])
    result = render_diagrams(empty)
    assert result["mermaid"].component_diagram == "flowchart LR\n"
    assert "not a runtime trace" in result["mermaid"].sequence_diagram
    assert "@enduml" in result["plantuml"].class_diagram


def test_graph_size_and_reference_limits_are_enforced():
    oversized = DependencyGraph(nodes=[
        {"id": str(i), "kind": "file", "language": "python", "name": str(i),
         "location": {"path": f"{i}.py", "start_line": 1, "end_line": 1}}
        for i in range(501)
    ], edges=[], cycles=[], critical_nodes=[])
    with pytest.raises(ValueError, match="exceeds limits"):
        render_mermaid(oversized, "component")
    malformed = {"nodes": [], "edges": [{"source": "missing", "target": None, "kind": "call",
                  "status": "external", "expression": "x", "location": {"path": "x.py", "start_line": 1, "end_line": 1},
                  "candidates": [], "reason": "external"}], "cycles": [], "critical_nodes": []}
    with pytest.raises(ValueError, match="unknown node"):
        render_plantuml(malformed, "sequence")
