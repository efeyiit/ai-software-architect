"""Extract source-linked Python structures from text using the standard AST."""

from __future__ import annotations

import ast
from typing import Literal

from app.contracts.analysis import AnalysisError, SourceLocation, WireModel


class Symbol(WireModel):
    kind: Literal["class", "function", "method", "variable"]
    name: str
    qualified_name: str
    location: SourceLocation


class Import(WireModel):
    name: str
    alias: str | None
    location: SourceLocation


class Call(WireModel):
    callee: str
    scope: str | None
    location: SourceLocation


class Inheritance(WireModel):
    class_name: str
    base_name: str
    location: SourceLocation


class FileStructure(WireModel):
    path: str
    symbols: list[Symbol]
    imports: list[Import]
    calls: list[Call]
    inheritance: list[Inheritance]
    errors: list[AnalysisError]


class _Collector(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[tuple[str, str]] = []
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []
        self.inheritance: list[Inheritance] = []

    def _location(self, node: ast.AST, *, full_range: bool = False) -> SourceLocation:
        start = node.lineno
        end = getattr(node, "end_lineno", start) if full_range else start
        return SourceLocation(path=self.path, start_line=start, end_line=end)

    def _qualified(self, name: str) -> str:
        return ".".join([*(part for _, part in self.scope), name])

    def _definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
                    kind: Literal["class", "function", "method"]) -> None:
        self.symbols.append(Symbol(kind=kind, name=node.name,
                                   qualified_name=self._qualified(node.name),
                                   location=self._location(node, full_range=True)))
        self.scope.append((kind, node.name))
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_name = self._qualified(node.name)
        self.symbols.append(Symbol(kind="class", name=node.name, qualified_name=class_name,
                                   location=self._location(node, full_range=True)))
        for base in node.bases:
            self.inheritance.append(Inheritance(class_name=class_name,
                                                base_name=ast.unparse(base),
                                                location=self._location(base)))
        self.scope.append(("class", node.name))
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self.scope and self.scope[-1][0] == "class" else "function"
        self._definition(node, kind)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        kind = "method" if self.scope and self.scope[-1][0] == "class" else "function"
        self._definition(node, kind)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(Import(name=alias.name, alias=alias.asname,
                                       location=self._location(node)))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * node.level + (node.module or "")
        for alias in node.names:
            name = f"{prefix}.{alias.name}" if node.module else f"{prefix}{alias.name}"
            self.imports.append(Import(name=name, alias=alias.asname,
                                       location=self._location(node)))

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.symbols.append(Symbol(kind="variable", name=node.id,
                                       qualified_name=self._qualified(node.id),
                                       location=self._location(node)))

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(Call(callee=ast.unparse(node.func),
                               scope=".".join(part for _, part in self.scope) or None,
                               location=self._location(node)))
        self.generic_visit(node)


def parse_file(path: str, source: str) -> FileStructure:
    """Parse one repository-relative file; syntax failures stay local to that file."""
    SourceLocation(path=path, start_line=1, end_line=1)
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, RecursionError) as exc:
        line = max(1, getattr(exc, "lineno", None) or 1)
        error = AnalysisError(code="PYTHON_SYNTAX_ERROR", message=str(exc), retryable=False,
                              location=SourceLocation(path=path, start_line=line, end_line=line))
        return FileStructure(path=path, symbols=[], imports=[], calls=[], inheritance=[],
                             errors=[error])
    collector = _Collector(path)
    collector.visit(tree)
    return FileStructure(path=path, symbols=collector.symbols, imports=collector.imports,
                         calls=collector.calls, inheritance=collector.inheritance, errors=[])
