import pytest
from pydantic import ValidationError

from app.parsers.java import parse_file


def test_java_structure_with_unicode_and_locations() -> None:
    source = """package café.example;
import java.util.List;
import static café.util.Tools.make;
public interface Named extends Base, java.io.Serializable {
  String name();
}
public class Service extends Parent implements Named, AutoCloseable {
  public String name() {
    return make(helper());
  }
  class Nested { void run() { name(); } }
}
"""
    result = parse_file("src/Café.java", source)

    assert result.errors == []
    assert result.package == "café.example"
    assert [(item.name, item.alias, item.location.start_line) for item in result.imports] == [
        ("java.util.List", None, 2), ("café.util.Tools.make", None, 3),
    ]
    assert [(item.kind, item.qualified_name, item.location.start_line, item.location.end_line)
            for item in result.symbols] == [
        ("interface", "café.example.Named", 4, 6),
        ("method", "café.example.Named.name", 5, 5),
        ("class", "café.example.Service", 7, 12),
        ("method", "café.example.Service.name", 8, 10),
        ("class", "café.example.Service.Nested", 11, 11),
        ("method", "café.example.Service.Nested.run", 11, 11),
    ]
    assert [(item.class_name, item.base_name, item.relation) for item in result.inheritance] == [
        ("café.example.Named", "Base", "extends"),
        ("café.example.Named", "java.io.Serializable", "extends"),
        ("café.example.Service", "Parent", "extends"),
        ("café.example.Service", "Named", "implements"),
        ("café.example.Service", "AutoCloseable", "implements"),
    ]
    assert [(item.callee, item.scope, item.location.start_line) for item in result.calls] == [
        ("make", "café.example.Service.name", 9),
        ("helper", "café.example.Service.name", 9),
        ("name", "café.example.Service.Nested.run", 11),
    ]
    assert all(item.location.path == result.path for group in
               (result.symbols, result.imports, result.inheritance, result.calls) for item in group)


def test_bad_syntax_is_local_and_source_is_not_executed() -> None:
    broken = parse_file("Bad.java", "class Bad { void run( { }\n")
    healthy = parse_file("Good.java", "class Good {}")
    assert broken.symbols == broken.imports == broken.calls == broken.inheritance == []
    assert broken.errors[0].code == "JAVA_SYNTAX_ERROR"
    assert broken.errors[0].retryable is False
    assert broken.errors[0].location.path == "Bad.java"
    assert broken.errors[0].location.start_line >= 1
    assert [(item.kind, item.name) for item in healthy.symbols] == [("class", "Good")]
    assert healthy.errors == []


def test_path_validation_and_empty_file() -> None:
    assert parse_file("Empty.java", "").symbols == []
    with pytest.raises(ValidationError):
        parse_file("../Outside.java", "")
    with pytest.raises(ValueError):
        parse_file("Other.kt", "")
