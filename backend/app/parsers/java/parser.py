"""Extract Java syntax with Tree-sitter; analyzed source remains inert text."""

from __future__ import annotations

from typing import Literal

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from app.contracts.analysis import AnalysisError, SourceLocation, WireModel


class Symbol(WireModel):
    kind: Literal["class", "interface", "method"]
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
    relation: Literal["extends", "implements"]
    location: SourceLocation


class FileStructure(WireModel):
    path: str
    package: str | None
    symbols: list[Symbol]
    imports: list[Import]
    calls: list[Call]
    inheritance: list[Inheritance]
    errors: list[AnalysisError]


_JAVA = Language(tree_sitter_java.language())


class _Collector:
    def __init__(self, path: str, source: bytes) -> None:
        self.path = path
        self.source = source
        self.package: str | None = None
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
        return ".".join(part for part in (self.package, *self.scope, name) if part)

    def visit(self, node: Node) -> None:
        if node.type == "package_declaration":
            name = next((child for child in node.named_children
                         if child.type in ("identifier", "scoped_identifier")), None)
            if name is not None:
                self.package = self.text(name)
            return
        if node.type == "import_declaration":
            name = next((child for child in node.named_children
                         if child.type in ("identifier", "scoped_identifier", "asterisk")), None)
            if name is not None:
                imported = self.text(name)
                if any(child.type == "asterisk" for child in node.children):
                    imported += ".*"
                self.imports.append(Import(name=imported, alias=None, location=self.location(node)))
            return
        if node.type in ("class_declaration", "interface_declaration"):
            self._type(node)
            return
        if node.type in ("method_declaration", "constructor_declaration"):
            self._method(node)
            return
        if node.type == "method_invocation":
            name = node.child_by_field_name("name")
            if name is not None:
                obj = node.child_by_field_name("object")
                callee = f"{self.text(obj)}.{self.text(name)}" if obj is not None else self.text(name)
                self.calls.append(Call(callee=callee, scope=self.qualified("") or None,
                                       location=self.location(node)))
        for child in node.named_children:
            self.visit(child)

    def _type(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for child in node.named_children:
                self.visit(child)
            return
        name = self.text(name_node)
        qualified = self.qualified(name)
        kind = "class" if node.type == "class_declaration" else "interface"
        self.symbols.append(Symbol(kind=kind, name=name, qualified_name=qualified,
                                   location=self.location(node, full_range=True)))
        for clause in node.named_children:
            if clause.type not in ("superclass", "super_interfaces", "extends_interfaces"):
                continue
            relation = "implements" if clause.type == "super_interfaces" else "extends"
            types = clause.named_children
            if len(types) == 1 and types[0].type == "type_list":
                types = types[0].named_children
            for base in types:
                self.inheritance.append(Inheritance(class_name=qualified,
                                                    base_name=self.text(base), relation=relation,
                                                    location=self.location(base)))
        self.scope.append(name)
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.named_children:
                self.visit(child)
        self.scope.pop()

    def _method(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for child in node.named_children:
                self.visit(child)
            return
        name = self.text(name_node)
        self.symbols.append(Symbol(kind="method", name=name, qualified_name=self.qualified(name),
                                   location=self.location(node, full_range=True)))
        self.scope.append(name)
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit(body)
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
    """Parse one repository-relative .java file without executing its source."""
    SourceLocation(path=path, start_line=1, end_line=1)
    if not path.endswith(".java"):
        raise ValueError("Java parser requires a .java path")
    data = source.encode("utf-8")
    root = Parser(_JAVA).parse(data).root_node
    collector = _Collector(path, data)
    if root.has_error:
        error_node = _first_error(root) or root
        error = AnalysisError(code="JAVA_SYNTAX_ERROR", message="Invalid Java syntax",
                              retryable=False, location=collector.location(error_node))
        return FileStructure(path=path, package=None, symbols=[], imports=[], calls=[],
                             inheritance=[], errors=[error])
    collector.visit(root)
    return FileStructure(path=path, package=collector.package, symbols=collector.symbols,
                         imports=collector.imports, calls=collector.calls,
                         inheritance=collector.inheritance, errors=[])
