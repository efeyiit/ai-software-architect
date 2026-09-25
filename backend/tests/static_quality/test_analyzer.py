"""Real parser and dependency graph fixtures for static quality checks."""

import pytest

from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.static_quality import QualityThresholds, analyze_static_quality
from app.parsers.python import parse_file as parse_python
from app.parsers.typescript import parse_file as parse_typescript
from app.parsers.java import parse_file as parse_java
from app.parsers.csharp import parse_file as parse_csharp
from app.parsers.cpp import parse_file as parse_cpp


def _analyze(path, source, parser, limits=None):
    structure = parser(path, source)
    assert structure.errors == []
    return analyze_static_quality([structure], {path: source}, thresholds=limits or QualityThresholds())


def test_python_all_local_rules_have_source_locations() -> None:
    source = '''import os
class Service:
    def first(self, a, b, c):
        if a:
            if b:
                return 713 + c
        return 9
    def second(self, a, b, c):
        if a:
            if b:
                return 713 + c
        return 9
'''
    limits = QualityThresholds(function_lines=3, class_lines=5, class_methods=1,
                               nesting_depth=1, parameters=2, duplicate_tokens=4)
    findings = _analyze("src/service.py", source, parse_python, limits)
    kinds = {item.issue_type for item in findings}
    assert kinds == {"long_function", "large_class", "duplicate_code", "magic_number",
                     "deep_nesting", "too_many_parameters", "unused_import"}
    assert all(item.source == "static" and item.location.path == "src/service.py" for item in findings)
    assert all(item.location.start_line >= 1 and item.location.end_line >= item.location.start_line
               for item in findings)


@pytest.mark.parametrize(("path", "source", "parser"), [
    ("src/a.ts", "class A { run(a: number, b: number) { return a + 713 + b; } }", parse_typescript),
    ("src/A.java", "class A { int run(int a, int b) { return a + 713 + b; } }", parse_java),
    ("src/A.cs", "class A { int Run(int a, int b) { return a + 713 + b; } }", parse_csharp),
    ("src/a.cpp", "class A { public: int run(int a, int b) { return a + 713 + b; } };", parse_cpp),
])
def test_five_language_boundary_finds_parameters_and_number(path, source, parser) -> None:
    findings = _analyze(path, source, parser, QualityThresholds(parameters=1))
    assert "too_many_parameters" in {item.issue_type for item in findings}
    assert "magic_number" in {item.issue_type for item in findings}


def test_comments_strings_constants_and_dynamic_import_use_do_not_trigger_false_findings() -> None:
    source = '''import os
LIMIT = 713
message = "if if 713 import os"
# if if 713
value = globals()["os"]
'''
    findings = _analyze("src/quiet.py", source, parse_python)
    assert findings == []


def test_import_name_only_in_text_is_still_unused() -> None:
    source = 'import os\nmessage = "os and 713"\n# os and 713\n'
    findings = _analyze("src/text.py", source, parse_python)
    assert [(item.issue_type, item.location.start_line) for item in findings] == [
        ("unused_import", 1),
    ]


def test_python_public_export_is_not_claimed_unused() -> None:
    source = 'from .widget import Widget\n__all__ = ["Widget"]\n'
    assert _analyze("pkg/api.py", source, parse_python) == []


def test_resolved_cycle_reports_import_locations_only() -> None:
    sources = {"pkg/a.py": "from . import b\n", "pkg/b.py": "from . import a\n"}
    structures = [parse_python(path, source) for path, source in sources.items()]
    graph = analyze_dependencies(structures)
    assert graph.cycles
    findings = analyze_static_quality(structures, sources, graph)
    assert [item.issue_type for item in findings].count("circular_dependency") == 2
    assert {item.location.path for item in findings if item.issue_type == "circular_dependency"} == set(sources)


def test_broken_file_is_skipped_and_inputs_are_snapshot_exact() -> None:
    broken = parse_python("src/bad.py", "def broken(:\n")
    assert analyze_static_quality([broken], {broken.path: "def broken(:\n"}) == []
    with pytest.raises(ValueError, match="exactly match"):
        analyze_static_quality([broken], {})


def test_unresolved_import_is_not_claimed_unused_in_non_python_language() -> None:
    source = 'import { missing } from "./absent";\nexport const value = 1;\n'
    findings = _analyze("src/a.ts", source, parse_typescript)
    assert all(item.issue_type != "unused_import" for item in findings)
