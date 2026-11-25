"""会话解析层的边界:不 import 返修链路模块,包内 import 全部能解析,语法与运行时 API 守 Python 3.9。

返修链路(两原子账本、返修链页、两原子端点、MCP、调查页)在 fuxi-ailabs/a2h-memory 的 fixchain/,
那边带一份本包的副本。这里只看源码,不 import 任何模块,所以新加的可选依赖也不会让检查漏掉。
"""
from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "migloop"

#: 移到 a2h-memory fixchain/ 的模块(顶层名,含通配);会话解析层不得再 import 它们
FIXCHAIN_MODULES = (
    "atoms", "atoms_collect", "atoms_text", "atom_queries", "atom_scope", "filestory", "filestory_collect",
    "blame", "blame_recovery", "crosschain", "probe", "verdict*", "via", "inquiry", "mcp_server", "coverage*",
    "evidence*", "findings", "guidance*", "submission", "temporal*", "time_*", "draft_check", "event_claims",
    "search_terms", "action_query", "batch_wire", "body_sources", "cc_sources", "change_inventory",
    "delivery_*", "dispatch_scope", "investigation", "raw_events", "recorded_report", "text_window",
    "transcript_store", "fixchain*",
)


def _modules() -> dict[str, Path]:
    out = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = list(path.relative_to(PACKAGE.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        out[".".join(parts)] = path
    return out


def _internal_imports(name: str, path: Path) -> list[tuple[int, str]]:
    """(行号, 被 import 的 migloop 模块名);from x import y 时 y 是子模块就取子模块。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names if a.name.split(".")[0] == "migloop"]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[:len(base) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module.split(".")[0] != "migloop":
                continue
            found += [(node.lineno, module + "." + a.name) for a in node.names]
            found.append((node.lineno, module))
    return found


def test_parsing_layer_never_imports_fixchain_modules() -> None:
    mods = _modules()
    offenders = []
    for name, path in mods.items():
        for line, target in _internal_imports(name, path):
            top = target.split(".")[1] if target.count(".") else ""
            if top and any(fnmatch.fnmatch(top, pattern) for pattern in FIXCHAIN_MODULES):
                offenders.append(f"{path.relative_to(PACKAGE.parent)}:{line} -> {target}")
    assert not offenders, "会话解析层 import 了返修链路模块:\n" + "\n".join(offenders)


def test_every_internal_import_resolves_inside_the_package() -> None:
    mods = _modules()
    missing = []
    for name, path in mods.items():
        for line, target in _internal_imports(name, path):
            # from pkg import attr: either the submodule exists or the attribute lives in pkg itself
            if target in mods or target.rsplit(".", 1)[0] in mods:
                continue
            missing.append(f"{path.relative_to(PACKAGE.parent)}:{line} -> {target}")
    assert not missing, "包内 import 指向不存在的模块:\n" + "\n".join(missing)


def test_no_fixchain_module_files_left_behind() -> None:
    names = {p.stem for p in PACKAGE.glob("*.py")} | {p.name for p in PACKAGE.iterdir() if p.is_dir()}
    left = sorted(n for n in names if any(fnmatch.fnmatch(n, pattern) for pattern in FIXCHAIN_MODULES))
    assert not left, left


def test_sources_parse_as_python_39() -> None:
    bad = []
    for path in _modules().values():
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))
        except SyntaxError as exc:
            bad.append(f"{path.relative_to(PACKAGE.parent)}:{exc.lineno} {exc.msg}")
    assert not bad, bad


def test_no_python_311_datetime_utc() -> None:
    """datetime.UTC 是 3.11 才有的;3.9 用 timezone.utc。"""
    hits = []
    for path in _modules().values():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime" and any(a.name == "UTC" for a in node.names):
                hits.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr == "UTC" and getattr(node.value, "id", "") == "datetime":
                hits.append(f"{path.name}:{node.lineno}")
    assert not hits, hits
