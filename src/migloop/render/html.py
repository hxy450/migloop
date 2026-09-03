"""Build the provider-neutral, self-contained MigLoop report.

渲染层的契约面（本文件 + ``__init__.py``）纳入类型检查；``compare.py``
里那套 vendored 的统计逻辑仍在 pyproject 的豁免名单上，经 ``__init__``
的门面调用。
"""

from __future__ import annotations

import json
import os
from importlib import resources
from typing import Any

#: 模板里的数据占位符 —— 缺了说明模板被换过，宁可炸也不出一张空页。
_PLACEHOLDER = "__TRACE_JSON__"
_DEFAULT_TITLE = "<title>MigLoop Trace</title>"


def load_asset(name: str) -> str:
    return (
        resources.files("migloop.render.templates")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def load_template() -> str:
    return load_asset("viewer.html")


def page_title(trace: dict[str, Any]) -> str:
    """``<工程名> · <sid8>`` —— tab 与画廊靠它区分，别退回通用名。"""
    meta = trace.get("meta") or {}
    label = os.path.basename((meta.get("cwd") or "").rstrip("\\/")) or "Trace"
    sid8 = (meta.get("session_id") or "")[:8]
    return f"{label} · {sid8}" if sid8 else str(label)


def build_html(trace: dict[str, Any], template: str | None = None) -> str:
    template = template or load_template()
    payload = json.dumps(trace, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    payload = payload.replace("�", "?")
    if _PLACEHOLDER not in template:
        raise ValueError("viewer template is missing " + _PLACEHOLDER)
    html = template.replace(_PLACEHOLDER, payload)
    return html.replace(_DEFAULT_TITLE, f"<title>{page_title(trace)}</title>", 1)
