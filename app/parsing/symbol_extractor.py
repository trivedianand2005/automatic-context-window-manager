"""Helpers to build signatures and pull source excerpts by line range."""

from __future__ import annotations

import ast


def module_name_for(rel_path: str) -> str:
    """Convert a repository-relative path to a dotted module name."""
    parts = rel_path.replace("\\", "/").split("/")
    last = parts[-1]
    if last.endswith(".pyi"):
        parts[-1] = last[:-4]
    elif last.endswith(".py"):
        parts[-1] = last[:-3]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(p for p in parts if p)


def _safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - unparse can fail on odd synthetic nodes
        return "..."


def function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = _safe_unparse(node.args)
    returns = f" -> {_safe_unparse(node.returns)}" if node.returns is not None else ""
    return f"{prefix} {node.name}({args}){returns}"


def class_signature(node: ast.ClassDef) -> str:
    bases = [_safe_unparse(b) for b in node.bases]
    bases += [f"{k.arg}={_safe_unparse(k.value)}" for k in node.keywords if k.arg]
    return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"


def decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    return [_safe_unparse(d) for d in node.decorator_list]


def start_line_with_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    lines = [node.lineno] + [d.lineno for d in node.decorator_list]
    return min(lines)


def extract_lines(source: str, start: int, end: int) -> str:
    """Return lines ``start..end`` (1-indexed, inclusive) from ``source``."""
    lines = source.splitlines()
    start = max(1, start)
    end = min(len(lines), end)
    return "\n".join(lines[start - 1 : end])


def first_docstring_line(doc: str | None, limit: int = 160) -> str:
    if not doc:
        return ""
    line = doc.strip().splitlines()[0].strip()
    return line if len(line) <= limit else line[: limit - 3] + "..."
