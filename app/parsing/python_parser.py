"""Static Python parsing with the standard-library ``ast`` module.

Source is parsed, never executed. Only relationships that are visible in the
syntax tree are recorded; runtime/dynamic imports are not inferred.
"""

from __future__ import annotations

import ast
import warnings

from app.core.models import ImportRef, ModuleInfo, Symbol
from app.parsing.symbol_extractor import (
    class_signature,
    decorator_names,
    function_signature,
    module_name_for,
    start_line_with_decorators,
)


def _is_type_checking_test(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, module: str) -> None:
        self.path = path
        self.module = module
        self.symbols: list[Symbol] = []
        self.imports: list[ImportRef] = []
        self._scope: list[tuple[str, str]] = []  # (qualname, kind)
        self._conditional_depth = 0
        self._type_checking_depth = 0

    # --- symbols -------------------------------------------------------
    def _add_symbol(self, node, kind: str, signature: str) -> None:
        parent = self._scope[-1][0] if self._scope else None
        qualname = f"{parent}.{node.name}" if parent else node.name
        self.symbols.append(
            Symbol(
                id=f"{self.path}::{qualname}",
                name=node.name,
                qualname=qualname,
                kind=kind,
                path=self.path,
                module=self.module,
                signature=signature,
                docstring=ast.get_docstring(node),
                start_line=start_line_with_decorators(node),
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                parent=parent,
                decorators=decorator_names(node),
            )
        )
        self._scope.append((qualname, kind))
        self.generic_visit(node)
        self._scope.pop()

    def _function_kind(self, is_async: bool) -> str:
        in_class = bool(self._scope) and self._scope[-1][1] == "class"
        if in_class:
            return "async_method" if is_async else "method"
        return "async_function" if is_async else "function"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_symbol(node, self._function_kind(False), function_signature(node))

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_symbol(node, self._function_kind(True), function_signature(node))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_symbol(node, "class", class_signature(node))

    # --- conditional context -------------------------------------------
    def visit_If(self, node: ast.If) -> None:
        type_checking = _is_type_checking_test(node.test)
        self._conditional_depth += 1
        if type_checking:
            self._type_checking_depth += 1
        for child in node.body:
            self.visit(child)
        if type_checking:
            self._type_checking_depth -= 1
        for child in node.orelse:
            self.visit(child)
        self._conditional_depth -= 1

    def _visit_conditional_block(self, node: ast.AST) -> None:
        self._conditional_depth += 1
        self.generic_visit(node)
        self._conditional_depth -= 1

    visit_Try = _visit_conditional_block
    visit_TryStar = _visit_conditional_block

    # --- imports -------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportRef(
                    module=alias.name,
                    names=[],
                    level=0,
                    line=node.lineno,
                    is_from=False,
                    conditional=self._conditional_depth > 0,
                    type_checking=self._type_checking_depth > 0,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append(
            ImportRef(
                module=node.module or "",
                names=[a.name for a in node.names],
                level=node.level or 0,
                line=node.lineno,
                is_from=True,
                conditional=self._conditional_depth > 0,
                type_checking=self._type_checking_depth > 0,
            )
        )


def parse_python(path: str, source: str) -> ModuleInfo:
    """Parse one Python file. Syntax errors produce a ModuleInfo with ``parse_error`` set."""
    module = module_name_for(path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=path, type_comments=False)
    except SyntaxError as exc:
        return ModuleInfo(
            path=path,
            module=module,
            parse_error=f"SyntaxError at line {exc.lineno}: {exc.msg}",
        )
    except (ValueError, RecursionError, MemoryError) as exc:
        return ModuleInfo(path=path, module=module, parse_error=f"{type(exc).__name__}: {exc}")

    visitor = _Visitor(path, module)
    visitor.visit(tree)
    return ModuleInfo(
        path=path,
        module=module,
        docstring=ast.get_docstring(tree),
        symbols=visitor.symbols,
        imports=visitor.imports,
    )
