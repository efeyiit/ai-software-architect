"""Extract TypeScript syntax with the native Tree-sitter TS and TSX grammars."""

from __future__ import annotations

from typing import Literal

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

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


class Export(WireModel):
    name: str
    alias: str | None
    source: str | None
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
    exports: list[Export]
    calls: list[Call]
    inheritance: list[Inheritance]
    errors: list[AnalysisError]


_TYPESCRIPT = Language(tree_sitter_typescript.language_typescript())
_TSX = Language(tree_sitter_typescript.language_tsx())


class _Collector:
    def __init__(self, path: str, source: bytes) -> None:
        self.path = path
        self.source = source
        self.scope: list[str] = []
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.exports: list[Export] = []
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

    def visit(self, node: Node) -> None:
        kind = node.type
        if kind == "import_statement":
            self._import(node)
            return
        if kind == "export_statement":
            self._export(node)
        if kind in ("class_declaration", "abstract_class_declaration", "class"):
            self._class(node)
            return
        if kind in ("function_declaration", "generator_function_declaration"):
            self._function(node, "function")
            return
        if kind == "method_definition":
            self._function(node, "method")
            return
        if kind == "variable_declarator":
            name = node.child_by_field_name("name")
            if name is not None and name.type == "identifier":
                value = self.text(name)
                self.symbols.append(Symbol(kind="variable", name=value,
                                           qualified_name=self.qualified(value),
                                           location=self.location(name)))
        if kind == "call_expression":
            function = node.child_by_field_name("function")
            if function is not None:
                self.calls.append(Call(callee=self.text(function),
                                       scope=".".join(self.scope) or None,
                                       location=self.location(node)))
        for child in node.named_children:
            self.visit(child)

    def _class(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for child in node.named_children:
                self.visit(child)
            return
        name = self.text(name_node)
        qualified = self.qualified(name)
        self.symbols.append(Symbol(kind="class", name=name, qualified_name=qualified,
                                   location=self.location(node, full_range=True)))
        heritage = next((c for c in node.named_children if c.type == "class_heritage"), None)
        if heritage is not None:
            for clause in heritage.named_children:
                if clause.type == "extends_clause":
                    base = clause.child_by_field_name("value")
                    if base is not None:
                        self.inheritance.append(Inheritance(class_name=qualified,
                                                            base_name=self.text(base),
                                                            location=self.location(base)))
        self.scope.append(name)
        for child in node.named_children:
            if child != name_node and child != heritage:
                self.visit(child)
        self.scope.pop()

    def _function(self, node: Node, kind: Literal["function", "method"]) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for child in node.named_children:
                self.visit(child)
            return
        name = self.text(name_node)
        self.symbols.append(Symbol(kind=kind, name=name,
                                   qualified_name=self.qualified(name),
                                   location=self.location(node, full_range=True)))
        self.scope.append(name)
        for child in node.named_children:
            if child != name_node:
                self.visit(child)
        self.scope.pop()

    def _import(self, node: Node) -> None:
        source = node.child_by_field_name("source")
        if source is None:
            return
        module = self.text(source)[1:-1]
        clause = next((c for c in node.named_children if c.type == "import_clause"), None)
        if clause is None:
            self.imports.append(Import(name=module, alias=None, location=self.location(node)))
            return
        for child in clause.named_children:
            if child.type == "identifier":
                self.imports.append(Import(name=module, alias=self.text(child),
                                           location=self.location(node)))
            elif child.type == "namespace_import":
                binding = next(iter(child.named_children), None)
                if binding is not None:
                    self.imports.append(Import(name=module, alias=self.text(binding),
                                               location=self.location(node)))
            elif child.type == "named_imports":
                for specifier in child.named_children:
                    original = specifier.child_by_field_name("name")
                    alias = specifier.child_by_field_name("alias")
                    if original is not None:
                        self.imports.append(Import(name=f"{module}.{self.text(original)}",
                                                   alias=self.text(alias) if alias else self.text(original),
                                                   location=self.location(specifier)))

    def _export(self, node: Node) -> None:
        declaration = node.child_by_field_name("declaration")
        source_node = node.child_by_field_name("source")
        source = self.text(source_node)[1:-1] if source_node is not None else None
        clause = next((c for c in node.named_children if c.type == "export_clause"), None)
        namespace = next((c for c in node.named_children if c.type == "namespace_export"), None)
        is_default = any(c.type == "default" for c in node.children)
        if declaration is not None:
            names: list[Node] = []
            direct = declaration.child_by_field_name("name")
            if direct is not None:
                names.append(direct)
            else:
                names.extend(c.child_by_field_name("name") for c in declaration.named_children
                             if c.type == "variable_declarator" and c.child_by_field_name("name") is not None)
            for name in names:
                self.exports.append(Export(name=self.text(name), alias="default" if is_default else None,
                                           source=source,
                                           location=self.location(node)))
        elif clause is not None:
            for specifier in clause.named_children:
                name = specifier.child_by_field_name("name")
                alias = specifier.child_by_field_name("alias")
                if name is not None:
                    self.exports.append(Export(name=self.text(name),
                                               alias=self.text(alias) if alias else None,
                                               source=source,
                                               location=self.location(specifier)))
        elif namespace is not None:
            alias = next(iter(namespace.named_children), None)
            self.exports.append(Export(name="*", alias=self.text(alias) if alias else None,
                                       source=source, location=self.location(node)))
        else:
            value = node.child_by_field_name("value")
            self.exports.append(Export(name=self.text(value) if value is not None else "*",
                                       alias="default" if is_default else None,
                                       source=source,
                                       location=self.location(node)))


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
    """Parse one .ts/.tsx file as text; syntax failures stay local to that file."""
    SourceLocation(path=path, start_line=1, end_line=1)
    if not path.endswith((".ts", ".tsx", ".mts", ".cts")):
        raise ValueError("TypeScript parser requires a .ts, .tsx, .mts or .cts path")
    data = source.encode("utf-8")
    language = _TSX if path.endswith(".tsx") else _TYPESCRIPT
    root = Parser(language).parse(data).root_node
    collector = _Collector(path, data)
    if root.has_error:
        error_node = _first_error(root) or root
        error = AnalysisError(code="TYPESCRIPT_SYNTAX_ERROR",
                              message="Invalid TypeScript syntax",
                              retryable=False, location=collector.location(error_node))
        return FileStructure(path=path, symbols=[], imports=[], exports=[], calls=[],
                             inheritance=[], errors=[error])
    collector.visit(root)
    return FileStructure(path=path, symbols=collector.symbols, imports=collector.imports,
                         exports=collector.exports, calls=collector.calls,
                         inheritance=collector.inheritance, errors=[])
