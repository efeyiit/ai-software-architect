"""Extract C# syntax from text using the native Tree-sitter grammar."""

from __future__ import annotations

from typing import Literal

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser

from app.contracts.analysis import AnalysisError, SourceLocation, WireModel


class Symbol(WireModel):
    kind: Literal["namespace", "class", "interface", "method"]
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


_CSHARP = Language(tree_sitter_c_sharp.language())


class _Collector:
    def __init__(self, path: str, source: bytes) -> None:
        self.path = path
        self.source = source
        self.scope: list[str] = []
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []
        self.inheritance: list[Inheritance] = []

    def text(self, node: Node) -> str:
        return self.source[node.start_byte:node.end_byte].decode("utf-8")

    def location(self, node: Node, *, full_range: bool = False) -> SourceLocation:
        start = node.start_point.row + 1
        end = max(start, node.end_point.row + (1 if node.end_point.column else 0)) if full_range else start
        return SourceLocation(path=self.path, start_line=start, end_line=end)

    def qualified(self, name: str) -> str:
        return ".".join([*self.scope, name])

    def visit_children(self, node: Node) -> None:
        for child in node.named_children:
            self.visit(child)

    def visit(self, node: Node) -> None:
        kind = node.type
        if kind == "compilation_unit":
            previous_scope = self.scope.copy()
            for child in node.named_children:
                if child.type == "file_scoped_namespace_declaration":
                    self._file_namespace(child)
                else:
                    self.visit(child)
            self.scope = previous_scope
            return
        if kind == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = self.text(name_node)
                self.symbols.append(Symbol(kind="namespace", name=name,
                                           qualified_name=self.qualified(name),
                                           location=self.location(node, full_range=True)))
                self.scope.append(name)
                body = node.child_by_field_name("body")
                if body is not None:
                    self.visit_children(body)
                self.scope.pop()
            return
        if kind == "using_directive":
            alias_node = node.child_by_field_name("name")
            target = next((child for child in reversed(node.named_children)
                           if child != alias_node), None)
            if target is not None:
                self.imports.append(Import(name=self.text(target),
                                           alias=self.text(alias_node) if alias_node else None,
                                           location=self.location(node)))
            return
        if kind in ("class_declaration", "interface_declaration"):
            self._type(node, "class" if kind == "class_declaration" else "interface")
            return
        if kind == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = self.text(name_node)
                self.symbols.append(Symbol(kind="method", name=name,
                                           qualified_name=self.qualified(name),
                                           location=self.location(node, full_range=True)))
                self.scope.append(name)
                body = node.child_by_field_name("body")
                if body is not None:
                    self.visit(body)
                self.scope.pop()
            return
        if kind == "invocation_expression":
            function = node.child_by_field_name("function")
            if function is not None:
                self.calls.append(Call(callee=self.text(function), scope=".".join(self.scope) or None,
                                       location=self.location(node)))
        self.visit_children(node)

    def _file_namespace(self, node: Node) -> None:
        name_node = next((child for child in node.named_children
                          if child.type in ("qualified_name", "identifier")), None)
        if name_node is not None:
            name = self.text(name_node)
            self.symbols.append(Symbol(kind="namespace", name=name,
                                       qualified_name=self.qualified(name),
                                       location=self.location(node)))
            self.scope.append(name)

    def _type(self, node: Node, kind: Literal["class", "interface"]) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = self.text(name_node)
        qualified = self.qualified(name)
        self.symbols.append(Symbol(kind=kind, name=name, qualified_name=qualified,
                                   location=self.location(node, full_range=True)))
        base_list = next((child for child in node.named_children if child.type == "base_list"), None)
        if base_list is not None:
            for base in base_list.named_children:
                self.inheritance.append(Inheritance(class_name=qualified, base_name=self.text(base),
                                                    location=self.location(base)))
        self.scope.append(name)
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit_children(body)
        self.scope.pop()


def _first_error(node: Node) -> Node | None:
    if node.type == "ERROR" or node.is_missing:
        return node
    for child in node.children:
        if child.has_error or child.is_missing:
            result = _first_error(child)
            if result is not None:
                return result
    return None


def parse_file(path: str, source: str) -> FileStructure:
    """Parse one repository-relative .cs file without running its source."""
    SourceLocation(path=path, start_line=1, end_line=1)
    if not path.endswith(".cs"):
        raise ValueError("C# parser requires a .cs path")
    data = source.encode("utf-8")
    root = Parser(_CSHARP).parse(data).root_node
    collector = _Collector(path, data)
    if root.has_error:
        error_node = _first_error(root) or root
        error = AnalysisError(code="CSHARP_SYNTAX_ERROR", message="Invalid C# syntax",
                              retryable=False, location=collector.location(error_node))
        return FileStructure(path=path, symbols=[], imports=[], calls=[], inheritance=[], errors=[error])
    collector.visit(root)
    return FileStructure(path=path, symbols=collector.symbols, imports=collector.imports,
                         calls=collector.calls, inheritance=collector.inheritance, errors=[])
