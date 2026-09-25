import pytest
from pydantic import ValidationError

from app.parsers.typescript import parse_file


def test_typescript_structure_with_unicode_and_locations() -> None:
    source = """import Widget, { build as make } from './tools';
import './setup';
export class Café extends pkg.Base {
  run() {
    return make(Widget());
  }
}
export function start() { return new Café().run(); }
export { make as create };
export { remote as linked } from './remote';
export * from './all';
export * as allNames from './everything';
"""
    result = parse_file("src/café.ts", source)

    assert result.errors == []
    assert [(s.kind, s.qualified_name, s.location.start_line, s.location.end_line)
            for s in result.symbols] == [
        ("class", "Café", 3, 7), ("method", "Café.run", 4, 6),
        ("function", "start", 8, 8),
    ]
    assert [(i.name, i.alias) for i in result.imports] == [
        ("./tools", "Widget"), ("./tools.build", "make"), ("./setup", None),
    ]
    assert [(e.name, e.alias, e.source) for e in result.exports] == [
        ("Café", None, None), ("start", None, None), ("make", "create", None),
        ("remote", "linked", "./remote"), ("*", None, "./all"),
        ("*", "allNames", "./everything"),
    ]
    assert [(b.class_name, b.base_name, b.location.start_line) for b in result.inheritance] == [
        ("Café", "pkg.Base", 3),
    ]
    assert [(c.callee, c.scope, c.location.start_line) for c in result.calls] == [
        ("make", "Café.run", 5), ("Widget", "Café.run", 5),
        ("new Café().run", "start", 8),
    ]
    assert all(item.location.path == result.path for group in
               (result.symbols, result.imports, result.exports, result.calls, result.inheritance)
               for item in group)


def test_tsx_uses_jsx_grammar_and_tracks_embedded_call() -> None:
    source = """import { render } from './ui';
export default function App() {
  return <Panel title="é" value={render()} />;
}
"""
    result = parse_file("src/App.tsx", source)
    assert result.errors == []
    assert [(s.kind, s.name, s.location.start_line, s.location.end_line)
            for s in result.symbols] == [("function", "App", 2, 4)]
    assert [(e.name, e.alias, e.source) for e in result.exports] == [("App", "default", None)]
    assert [(c.callee, c.scope, c.location.start_line) for c in result.calls] == [
        ("render", "App", 3),
    ]


def test_syntax_error_is_local_and_has_shared_location() -> None:
    broken = parse_file("src/broken.ts", "export function f( {\n")
    healthy = parse_file("src/healthy.ts", "export const okay = 1;\n")
    assert broken.symbols == broken.imports == broken.exports == broken.calls == broken.inheritance == []
    assert len(broken.errors) == 1
    assert broken.errors[0].code == "TYPESCRIPT_SYNTAX_ERROR"
    assert broken.errors[0].retryable is False
    assert broken.errors[0].location.path == "src/broken.ts"
    assert broken.errors[0].location.start_line >= 1
    assert [(s.kind, s.name) for s in healthy.symbols] == [("variable", "okay")]
    assert healthy.errors == []


def test_untrusted_source_is_never_executed_and_path_is_checked() -> None:
    result = parse_file("safe.ts", "throw new Error('source was run');\n")
    assert result.errors == []
    assert result.symbols == []
    with pytest.raises(ValidationError):
        parse_file("../outside.ts", "")
    with pytest.raises(ValueError):
        parse_file("source.js", "")
