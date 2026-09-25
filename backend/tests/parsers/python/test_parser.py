import pytest
from pydantic import ValidationError

from app.parsers.python import parse_file


SOURCE = """import os.path as path
from collections import Counter as Count

SETTING = 1

class Base:
    pass

class Child(Base, pkg.Mixin):
    value: int = 2

    def run(self, item):
        local = Count(item)
        self.work(local)
        return path.join("a", "b")

def outer():
    def inner():
        return 1
    return inner()
"""


def test_extracts_structure_and_inclusive_locations() -> None:
    result = parse_file("src/example.py", SOURCE)

    assert result.path == "src/example.py"
    assert result.errors == []
    assert [(s.kind, s.qualified_name, s.location.start_line, s.location.end_line)
            for s in result.symbols] == [
        ("variable", "SETTING", 4, 4),
        ("class", "Base", 6, 7),
        ("class", "Child", 9, 15),
        ("variable", "Child.value", 10, 10),
        ("method", "Child.run", 12, 15),
        ("variable", "Child.run.local", 13, 13),
        ("function", "outer", 17, 20),
        ("function", "outer.inner", 18, 19),
    ]
    assert [(i.name, i.alias, i.location.start_line) for i in result.imports] == [
        ("os.path", "path", 1), ("collections.Counter", "Count", 2),
    ]
    assert [(b.class_name, b.base_name, b.location.start_line) for b in result.inheritance] == [
        ("Child", "Base", 9), ("Child", "pkg.Mixin", 9),
    ]
    assert [(c.callee, c.scope, c.location.start_line) for c in result.calls] == [
        ("Count", "Child.run", 13), ("self.work", "Child.run", 14),
        ("path.join", "Child.run", 15), ("inner", "outer", 20),
    ]
    assert all(x.location.path == result.path for group in
               (result.symbols, result.imports, result.inheritance, result.calls)
               for x in group)


def test_syntax_error_is_file_result_and_does_not_poison_next_file() -> None:
    broken = parse_file("src/broken.py", "def broken(:\n    pass\n")
    healthy = parse_file("src/healthy.py", "answer = 42\n")

    assert broken.symbols == broken.imports == broken.calls == broken.inheritance == []
    assert len(broken.errors) == 1
    assert broken.errors[0].code == "PYTHON_SYNTAX_ERROR"
    assert broken.errors[0].retryable is False
    assert broken.errors[0].location.path == "src/broken.py"
    assert broken.errors[0].location.start_line == 1
    assert [(s.kind, s.name) for s in healthy.symbols] == [("variable", "answer")]
    assert healthy.errors == []


def test_nested_scope_and_assignment_targets_are_not_misclassified() -> None:
    source = """class Box:
    async def load(self, values):
        left, right = values
        self.current = left
        for entry in values:
            pass
        return factory().build()
"""
    result = parse_file("box.py", source)

    assert [(s.kind, s.qualified_name) for s in result.symbols] == [
        ("class", "Box"), ("method", "Box.load"),
        ("variable", "Box.load.left"), ("variable", "Box.load.right"),
        ("variable", "Box.load.entry"),
    ]
    assert [(c.callee, c.location.start_line) for c in result.calls] == [
        ("factory().build", 7), ("factory", 7),
    ]


def test_relative_import_and_empty_file_use_shared_location_contract() -> None:
    result = parse_file("pkg/module.py", "from .helpers import build\n")
    assert result.imports[0].name == ".helpers.build"
    assert result.imports[0].location.model_dump() == {
        "path": "pkg/module.py", "start_line": 1, "end_line": 1,
    }
    assert parse_file("empty.py", "").symbols == []
    with pytest.raises(ValidationError):
        parse_file("../outside.py", "")


def test_source_is_parsed_without_execution() -> None:
    result = parse_file("untrusted.py", "raise AssertionError('source was run')\n")
    assert result.errors == []
    assert result.symbols == []
