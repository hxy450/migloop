"""执行拓扑的后续节点:主会话之后、同一鸿蒙工程里跑起来的能力会话与 ECAT run。

移植自 hmigbot-plus insight/followups.py(fe468482)。

DT / ECAT 各自是独立 transcript,主会话的 transcript 里没有一条记录提到它们,
拓扑只画本会话的阶段与子代理,于是「执行拓扑看不到 DT 和 ECAT」(2026-09-11
用户实测)。这里只吃会话自己的信息,不按能力名识别:

  · 同 transcript 目录(= 同 cwd)里开工晚于本会话结束、且真干过活的会话 ——
    至少一次非只读工具调用(托管审查只会 Glob/Read 验盘,不算);标签用 harness
    的 skill 归属戳,没有就叫 Session;
  · ``<harmony>/.migbot/ecat_runs`` 里开跑晚于本会话开始的 run,按 ecat.list_runs
    聚合(轮数、熵值首末)。

读盘纪律:本会话不重读(起止取自已解析的 trace);后继会话先按首条时间戳筛,
真正要单趟扫的那几份按 (mtime, size) 记住,文件不变不重扫。
"""

from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime
from typing import Any

from . import ecat, project_sessions
from .cc_records import is_request_replay

#: 后续会话最多接几条 —— 同目录里可能堆着几百条别的会话,全扫一遍读不完
_MAX_LATER_SESSIONS = 8
#: 只读工具:一场会话若只有这些调用,是在看不是在干(托管审查验盘就是这形态)
_READ_ONLY_TOOLS = frozenset({"Glob", "Read", "Grep", "LS", "TaskList", "TaskGet", "ToolSearch"})

#: path -> ((mtime, size), _scan 结果)
_SCAN_CACHE: dict[str, tuple[tuple[float, int], dict[str, Any]]] = {}
_SCAN_CACHE_MAX = 256


def _scan(path: str) -> dict[str, Any]:
    """单趟扫一份 transcript:起止、工具/子代理调用数、归属戳集合。"""
    try:
        st = os.stat(path)
        sig: tuple[float, int] | None = (st.st_mtime, st.st_size)
    except OSError:
        sig = None
    hit = _SCAN_CACHE.get(path)
    if sig is not None and hit is not None and hit[0] == sig:
        return {**hit[1], "attrs": set(hit[1]["attrs"])}
    first: datetime | None = None
    last: datetime | None = None
    tools = 0
    agents = 0
    worked = False
    attrs: set[str] = set()
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or is_request_replay(rec):
                continue
            ts = ecat._parse_ts(rec.get("timestamp"))
            if ts is not None:
                first = ts if first is None or ts < first else first
                last = ts if last is None or ts > last else last
            attr = str(rec.get("attributionSkill") or "").split(":")[-1]
            if attr:
                attrs.add(attr)
            if rec.get("type") != "assistant":
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools += 1
                    if block.get("name") not in _READ_ONLY_TOOLS:
                        worked = True
                    if block.get("name") in ("Agent", "Task"):
                        agents += 1
    out = {"first": first, "last": last, "tools": tools, "agents": agents,
           "worked": worked, "attrs": attrs}
    if sig is not None:
        if len(_SCAN_CACHE) >= _SCAN_CACHE_MAX:
            _SCAN_CACHE.pop(next(iter(_SCAN_CACHE)))
        _SCAN_CACHE[path] = (sig, {**out, "attrs": frozenset(attrs)})
    return out


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def report_href(path: str) -> str:
    """``--serve`` 的报告页地址。按 transcript 路径寻址:ECAT 角色会话落在
    ``<harmony>/.ecat/agents/…`` 下,不在会话发现的根里,按会话号找不到。"""
    return "/insight1/report/" + urllib.parse.quote(os.path.abspath(path), safe="")


def _later_sessions(path: str, ended: datetime, link: bool) -> list[dict[str, Any]]:
    cur = os.path.abspath(path)
    out: list[dict[str, Any]] = []
    for sibling in project_sessions.claude_project_roots(path, 64):
        if os.path.abspath(sibling) == cur:
            continue
        first = ecat._parse_ts(project_sessions.first_record_ts(sibling))
        if first is None or first <= ended:
            continue
        info = _scan(sibling)
        if not info["worked"] or info["first"] is None:
            continue
        sid = os.path.basename(sibling).split(".")[0]
        dur = (info["last"] - info["first"]) if info["last"] and info["first"] else None
        out.append({
            "kind": "session",
            "label": next(iter(info["attrs"])) if len(info["attrs"]) == 1 else "Session",
            "sub": f"{info['tools']} 调用 · {info['agents']} 子代理",
            "start_ts": _iso(info["first"]),
            "end_ts": _iso(info["last"]),
            "duration_ms": int(dur.total_seconds() * 1000) if dur else None,
            "tool_calls": info["tools"],
            "agent_count": info["agents"],
            "sid": sid,
            "href": report_href(sibling) if link else None,
        })
        if len(out) >= _MAX_LATER_SESSIONS:
            break
    return out


def _ecat_runs(harmony: str, started: datetime, link: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in ecat.list_runs(harmony):
        start = ecat._parse_ts(run.get("started_at"))
        if start is None or start <= started:
            continue
        iterations = run.get("iterations") or []
        hs = [it.get("total_H") for it in iterations if it.get("total_H") is not None]
        sub = f"H {hs[0]:.3f} → {hs[-1]:.3f}" if hs else "无熵记录"
        sessions = [s for it in iterations for s in it.get("sessions") or []]
        last_sid = str(sessions[-1].get("session_id") or "") if sessions else ""
        last_path = str(sessions[-1].get("transcript") or "") if sessions else ""
        out.append({
            "kind": "ecat",
            "label": f"ECAT 精修 · {len(iterations)} 轮",
            "sub": f"{sub} · {run.get('session_count') or 0} 会话",
            "start_ts": run.get("started_at"),
            "end_ts": run.get("ended_at"),
            "duration_ms": run.get("duration_ms"),
            "tool_calls": 0,
            "agent_count": 0,
            "sid": last_sid or None,
            "href": report_href(last_path) if last_path and link else None,
            "run_id": run.get("run_id"),
        })
    return out


def collect(path: str, trace: dict[str, Any], *, link: bool = True) -> list[dict[str, Any]]:
    """本会话的后续节点,按开跑时间排,id 为 f0/f1/…;ECAT 角色会话不挂。

    ``link=False``(导出的自包含 HTML 没有服务端)时节点照画、不给跳转地址。
    """
    meta = trace.get("meta") or {}
    if meta.get("ecat") or ecat.role_of(path):
        return []
    # 「同 transcript 目录 = 同工程」只对 CC 成立;codex 的目录是日期分区,
    # 里面是当天所有工程的 rollout,按目录找后继会把它们逐个全读一遍
    if str(meta.get("session_format") or "claude") != "claude":
        return []
    started = ecat._parse_ts(meta.get("started_at"))
    ended = ecat._parse_ts(meta.get("ended_at")) or started
    if started is None or ended is None:
        return []
    cwd = str(meta.get("cwd") or "")
    nodes = _later_sessions(path, ended, link)
    if cwd and os.path.isdir(cwd):
        nodes.extend(_ecat_runs(cwd, started, link))
    nodes.sort(key=lambda n: str(n.get("start_ts") or ""))
    for i, node in enumerate(nodes):
        node["id"] = f"f{i}"
    return nodes
