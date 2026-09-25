import pytest
from pydantic import ValidationError

from app.parsers.csharp import parse_file


def test_extracts_namespaces_usings_types_methods_calls_and_bases() -> None:
    source = """global using System.Text;
using Alias = Acme.Tools;
namespace Café.Core {
  using static System.Math;
  public interface IRunner : IDisposable {
    void Run();
  }
  public class Runner : BaseRunner, IRunner {
    public void Run() {
      Alias.Build();
      Console.WriteLine("héllo");
    }
  }
}
"""
    result = parse_file("src/Café.cs", source)

    assert result.errors == []
    assert [(s.kind, s.qualified_name, s.location.start_line, s.location.end_line)
            for s in result.symbols] == [
        ("namespace", "Café.Core", 3, 14),
        ("interface", "Café.Core.IRunner", 5, 7),
        ("method", "Café.Core.IRunner.Run", 6, 6),
        ("class", "Café.Core.Runner", 8, 13),
        ("method", "Café.Core.Runner.Run", 9, 12),
    ]
    assert [(i.name, i.alias, i.location.start_line) for i in result.imports] == [
        ("System.Text", None, 1),
        ("Acme.Tools", "Alias", 2),
        ("System.Math", None, 4),
    ]
    assert [(b.class_name, b.base_name, b.location.start_line) for b in result.inheritance] == [
        ("Café.Core.IRunner", "IDisposable", 5),
        ("Café.Core.Runner", "BaseRunner", 8),
        ("Café.Core.Runner", "IRunner", 8),
    ]
    assert [(c.callee, c.scope, c.location.start_line) for c in result.calls] == [
        ("Alias.Build", "Café.Core.Runner.Run", 10),
        ("Console.WriteLine", "Café.Core.Runner.Run", 11),
    ]
    assert all(item.location.path == result.path for group in
               (result.symbols, result.imports, result.calls, result.inheritance)
               for item in group)


def test_file_scoped_namespace_and_nested_type_scope() -> None:
    source = """namespace App.Core;
using IO = System.IO;
class Outer {
  class Inner : IO.Stream {
    void Go() { this.Run(); }
  }
}
"""
    result = parse_file("src/nested.cs", source)
    assert result.errors == []
    assert [(s.kind, s.qualified_name) for s in result.symbols] == [
        ("namespace", "App.Core"), ("class", "App.Core.Outer"),
        ("class", "App.Core.Outer.Inner"),
        ("method", "App.Core.Outer.Inner.Go"),
    ]
    assert [(i.name, i.alias) for i in result.imports] == [("System.IO", "IO")]
    assert [(b.class_name, b.base_name) for b in result.inheritance] == [
        ("App.Core.Outer.Inner", "IO.Stream"),
    ]
    assert [(c.callee, c.scope) for c in result.calls] == [
        ("this.Run", "App.Core.Outer.Inner.Go"),
    ]


def test_bad_syntax_is_local_and_path_is_validated() -> None:
    broken = parse_file("src/broken.cs", "class Broken { void Go( {\n")
    healthy = parse_file("src/healthy.cs", "class Good {}\n")
    assert broken.symbols == broken.imports == broken.calls == broken.inheritance == []
    assert len(broken.errors) == 1
    assert broken.errors[0].code == "CSHARP_SYNTAX_ERROR"
    assert broken.errors[0].retryable is False
    assert broken.errors[0].location.path == "src/broken.cs"
    assert broken.errors[0].location.start_line >= 1
    assert [(s.kind, s.name) for s in healthy.symbols] == [("class", "Good")]
    with pytest.raises(ValidationError):
        parse_file("../outside.cs", "")
    with pytest.raises(ValueError):
        parse_file("source.cpp", "")


def test_source_is_only_parsed() -> None:
    result = parse_file("safe.cs", "class Safe { void Go() { throw new Exception(\"run\"); } }\n")
    assert result.errors == []
    assert [(s.kind, s.name) for s in result.symbols] == [
        ("class", "Safe"), ("method", "Go"),
    ]
