import pytest
from pydantic import ValidationError

from app.parsers.cpp import parse_file


def test_source_extracts_includes_namespaces_types_functions_calls_and_bases() -> None:
    source = '''#include <vector>
#include "café.hpp"
namespace Café::Core {
class Runner : public Base, private Traits<Item> {
public:
  void go() { helper(); this->run(); }
};
void free_fn() { Runner r; r.go(); }
}
void Café::Core::Runner::run() { helper(); }
'''
    result = parse_file("src/café.cpp", source)

    assert result.errors == []
    assert [(item.name, item.alias, item.location.start_line) for item in result.imports] == [
        ("vector", None, 1), ("café.hpp", None, 2),
    ]
    assert [(item.kind, item.qualified_name, item.location.start_line) for item in result.symbols] == [
        ("namespace", "Café::Core", 3),
        ("class", "Café::Core::Runner", 4),
        ("method", "Café::Core::Runner::go", 6),
        ("function", "Café::Core::free_fn", 8),
        ("method", "Café::Core::Runner::run", 10),
    ]
    assert [(item.class_name, item.base_name) for item in result.inheritance] == [
        ("Café::Core::Runner", "Base"),
        ("Café::Core::Runner", "Traits<Item>"),
    ]
    assert [(item.callee, item.scope) for item in result.calls] == [
        ("helper", "Café::Core::Runner::go"),
        ("this->run", "Café::Core::Runner::go"),
        ("r.go", "Café::Core::free_fn"),
        ("helper", "Café::Core::Runner::run"),
    ]
    assert all(item.location.path == result.path for group in
               (result.symbols, result.imports, result.calls, result.inheritance)
               for item in group)


def test_header_declarations_and_macro_uncertainties() -> None:
    source = '''#pragma once
#include HEADER_NAME
#define DECL(T) class T {};
namespace API {
struct Box : Base {
  Box();
  void run();
};
DECL(Generated)
}
#ifdef DEBUG
void debug_only() {}
#endif
'''
    result = parse_file("include/api.hpp", source)

    assert result.errors == []
    assert [(item.name, item.location.start_line) for item in result.imports] == [("HEADER_NAME", 2)]
    assert [(item.kind, item.qualified_name) for item in result.symbols] == [
        ("namespace", "API"), ("struct", "API::Box"),
        ("method", "API::Box::Box"), ("method", "API::Box::run"),
    ]
    assert [(item.class_name, item.base_name) for item in result.inheritance] == [
        ("API::Box", "Base"),
    ]
    assert [(item.name, item.reason, item.location.start_line)
            for item in result.macro_uncertainties] == [
        ("HEADER_NAME", "dynamic_include", 2),
        ("DECL", "definition", 3),
        ("DECL", "invocation", 9),
        ("DEBUG", "conditional", 11),
    ]
    assert result.calls == []


def test_invalid_syntax_is_local_and_path_is_validated() -> None:
    broken = parse_file("src/broken.cc", "class Broken { void go( {\n")
    broken_macro = parse_file("src/broken_macro.cpp", "#define M(x) x\nM(\n")
    healthy = parse_file("include/good.h", "class Good {};\n")

    assert broken.symbols == broken.imports == broken.calls == broken.inheritance == []
    assert len(broken.errors) == 1
    assert broken.errors[0].code == "CPP_SYNTAX_ERROR"
    assert broken.errors[0].retryable is False
    assert broken.errors[0].location.path == "src/broken.cc"
    assert [error.code for error in broken_macro.errors] == ["CPP_SYNTAX_ERROR"]
    assert [(item.kind, item.name) for item in healthy.symbols] == [("class", "Good")]
    with pytest.raises(ValidationError):
        parse_file("../outside.cpp", "")
    with pytest.raises(ValueError):
        parse_file("source.c", "")


def test_source_is_only_parsed() -> None:
    result = parse_file("safe.cxx", 'int main() { system("do not run"); }\n')
    assert result.errors == []
    assert [(item.kind, item.name) for item in result.symbols] == [("function", "main")]
    assert [(item.callee, item.scope) for item in result.calls] == [("system", "main")]
