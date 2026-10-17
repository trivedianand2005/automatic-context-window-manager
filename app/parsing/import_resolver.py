"""Resolve Python import statements to repository files.

Resolution strategy (confidence in brackets):
1. Exact dotted-module match against modules found in the repository [high].
2. For ``from pkg import name``, ``pkg.name`` is tried first as a submodule [high].
3. Relative imports are resolved against the importing module's package [high].
4. A unique *suffix* match (e.g. ``app.auth`` matching ``src/app/auth.py`` when the
   repository is indexed from a parent directory) [medium].
5. Multiple suffix matches are ambiguous: recorded as unresolved [low], no edge.

Anything else is classified as external (stdlib/third-party) or unresolved.
No dependency is invented without a matching file.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from app.core.models import ImportRef, ModuleInfo, ResolvedImport

_STDLIB = set(getattr(sys, "stdlib_module_names", ()))


class ModuleIndex:
    def __init__(self, modules: list[ModuleInfo]) -> None:
        self.by_name: dict[str, str] = {}
        self.package_paths: set[str] = set()
        self._suffixes: dict[str, list[str]] = defaultdict(list)
        for info in modules:
            self.by_name[info.module] = info.path
            if info.path.endswith("__init__.py"):
                self.package_paths.add(info.path)
            parts = info.module.split(".")
            for i in range(1, len(parts)):
                self._suffixes[".".join(parts[i:])].append(info.path)
        self.top_level = {name.split(".")[0] for name in self.by_name}

    def exact(self, dotted: str) -> str | None:
        return self.by_name.get(dotted)

    def suffix(self, dotted: str) -> list[str]:
        return sorted(set(self._suffixes.get(dotted, [])))


def _package_of(info: ModuleInfo) -> list[str]:
    parts = info.module.split(".") if info.module else []
    if info.path.endswith("__init__.py"):
        return parts  # a package's __init__ is its own package
    return parts[:-1]


def _candidates(info: ModuleInfo, ref: ImportRef) -> list[str]:
    """Dotted names to try, most specific first."""
    if ref.level:
        base = _package_of(info)
        up = ref.level - 1
        if up > len(base):
            return []
        base = base[: len(base) - up] if up else base
        prefix = ".".join(base)
        root = f"{prefix}.{ref.module}" if ref.module and prefix else (ref.module or prefix)
    else:
        root = ref.module
    out: list[str] = []
    if ref.is_from:
        out.extend(f"{root}.{name}" if root else name for name in ref.names if name != "*")
    if root:
        out.append(root)
    return out


def resolve_import(info: ModuleInfo, ref: ImportRef, index: ModuleIndex) -> list[ResolvedImport]:
    raw = ("." * ref.level) + ref.module
    if ref.is_from:
        raw = f"from {raw} import {', '.join(ref.names)}"
    note_bits = []
    if ref.type_checking:
        note_bits.append("TYPE_CHECKING-only import")
    elif ref.conditional:
        note_bits.append("conditional import")
    note = "; ".join(note_bits)
    base_conf = "medium" if (ref.conditional or ref.type_checking) else "high"

    results: dict[str, ResolvedImport] = {}
    candidates = _candidates(info, ref)
    # For `from pkg import a, b` the leading candidates are submodules `pkg.a`, `pkg.b`
    # and the last one is `pkg`. The package itself is a dependency only when at least
    # one imported name is *not* a submodule (i.e. it is an attribute of the package).
    has_root = bool(candidates) and (
        not ref.is_from or len(candidates) > len([n for n in ref.names if n != "*"])
    )
    name_candidates = candidates[:-1] if has_root and ref.is_from else candidates
    if not ref.is_from:
        name_candidates = []
    targets = [index.exact(d) for d in name_candidates]
    if has_root and (not ref.is_from or not all(targets) or "*" in ref.names):
        targets.append(index.exact(candidates[-1]))
    for target in targets:
        if target and target != info.path:
            results.setdefault(
                target,
                ResolvedImport(
                    source_path=info.path,
                    raw=raw,
                    target_path=target,
                    status="local",
                    confidence=base_conf,
                    line=ref.line,
                    note=note,
                ),
            )
    if results:
        return list(results.values())

    if not ref.level:
        top = ref.module.split(".")[0]
        if top in _STDLIB and top not in index.top_level:
            return [
                ResolvedImport(
                    source_path=info.path,
                    raw=raw,
                    status="external",
                    confidence="high",
                    line=ref.line,
                    note="stdlib",
                )
            ]
        for dotted in candidates:
            matches = [m for m in index.suffix(dotted) if m != info.path]
            if len(matches) == 1:
                return [
                    ResolvedImport(
                        source_path=info.path,
                        raw=raw,
                        target_path=matches[0],
                        status="local",
                        confidence="medium",
                        line=ref.line,
                        note="; ".join([*note_bits, f"suffix match for '{dotted}'"]),
                    )
                ]
            if len(matches) > 1:
                return [
                    ResolvedImport(
                        source_path=info.path,
                        raw=raw,
                        status="unresolved",
                        confidence="low",
                        line=ref.line,
                        note=f"ambiguous: {len(matches)} files match '{dotted}'; no edge created",
                    )
                ]
        if top not in index.top_level:
            return [
                ResolvedImport(
                    source_path=info.path,
                    raw=raw,
                    status="external",
                    confidence="high",
                    line=ref.line,
                    note="third-party or not in repository",
                )
            ]
    return [
        ResolvedImport(
            source_path=info.path,
            raw=raw,
            status="unresolved",
            confidence="low",
            line=ref.line,
            note="no matching module in repository",
        )
    ]


def resolve_all(modules: list[ModuleInfo]) -> list[ResolvedImport]:
    index = ModuleIndex([m for m in modules])
    resolved: list[ResolvedImport] = []
    for info in modules:
        for ref in info.imports:
            resolved.extend(resolve_import(info, ref, index))
    return resolved
