"""会话总览 —— 一次迁移的全部参与会话放在一处(移植自 hmigbot-plus 72c56b60 的解析部分)。

分析单位是一次迁移,不是一份 transcript(2026-09-20 用户裁定):主迁移、之后的 ECAT 与
能力会话要在同一页里。hmigbot-plus 的链骨架是事件库(events.db)的会话时间线,能分出
主迁移 / 托管评审 / 能力会话与 breather 接力 —— 那是产品侧的记录,不搬。migloop 只有
磁盘上的 transcript,骨架改成:

  · 与锚点同工程的全部 root 会话(CC:同 transcript 目录;codex:cwd 同树的 rollout),时间序;
  · ``<harmony>/.migbot/ecat_runs`` 的各次 run:CC 线 ``.ecat/agents/<role>`` 下的角色会话、
    codex 线按 stream 的 thread id 挂上的 rollout,按轮次标注。

每个会话归约成一格:用量、阶段、审计发现、提示词全文。会话类别只认得出 ECAT 角色,
其余一律记「会话」,不按名字猜主迁移 / 评审。每份 transcript 只解析一次(走
service.extract_trace 的缓存),不另扫。
"""

from __future__ import annotations

import json
import os
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import audit, crosschain, ecat, followups
from .adapters.claude import TRAILING_ROUNDS_LABEL

_SUMMED = ("requests", "input_tokens", "cache_read_tokens", "output_tokens",
           "tool_calls", "tool_failed", "agents", "aborted_agents")


def identity(harmony: str) -> dict[str, str]:
    """``<harmony>/.migbot/config.json`` 里记的迁移身份(没有就是空串)。"""
    cfg: Any = {}
    with suppress(OSError, json.JSONDecodeError):
        cfg = json.loads((Path(harmony) / ".migbot" / "config.json").read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        cfg = {}
    return {k: str(cfg.get(k) or "") for k in ("project", "run_id", "hmigbot_session_id", "android")}


def _instant(ts: Any) -> datetime | None:
    """带时区的时刻;transcript 的 ``…Z`` 与归一后的 ``…-07:00`` 都认。"""
    try:
        moment = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def stage_of(ts: str, stages: list[dict[str, Any]]) -> str | None:
    """某一刻落在哪个阶段:阶段内给阶段名,阶段之前「开跑前」,阶段之间或最后一段之后
    「<前一段> 之后」。时刻缺失、或会话没有阶段时给 None。"""
    moment = _instant(ts)
    spans = sorted(((a, b, str(st.get("label") or "")) for st in stages
                    if (a := _instant(st.get("start_ts"))) and (b := _instant(st.get("end_ts")))),
                   key=lambda span: span[0])
    if moment is None or not spans:
        return None
    if moment < spans[0][0]:
        return "开跑前"
    previous = spans[0][2]
    for start, end, label in spans:
        if start <= moment <= end:
            return label
        if moment > end:
            previous = label
    # 末段本身就是「管线完成后」时不再叠「之后」
    return previous if previous == TRAILING_ROUNDS_LABEL else f"{previous} 之后"


def summarize(trace: dict[str, Any]) -> dict[str, Any]:
    """一份 trace → 链上的一格:用量、阶段、审计发现。"""
    totals, meta = trace.get("totals") or {}, trace.get("meta") or {}
    bill = {"req": 0, "inp": 0, "cread": 0, "out": 0}
    for model in (trace.get("billing") or {}).values():
        for k in bill:
            bill[k] += model.get(k) or 0
    tools = trace.get("tools") or []
    return {
        "model": meta.get("model"), "started_at": meta.get("started_at"), "ended_at": meta.get("ended_at"),
        "duration_ms": totals.get("duration_ms") or 0,
        "requests": bill["req"], "input_tokens": bill["inp"],
        "cache_read_tokens": bill["cread"], "output_tokens": bill["out"],
        "tool_calls": totals.get("tool_calls") or 0,
        "tool_failed": sum(1 for t in tools if t.get("ok") is False),
        "agents": totals.get("agent_calls") or 0, "aborted_agents": totals.get("aborted_agents") or 0,
        "stages": [{"label": s.get("label"), "start_ts": s.get("start_ts"), "end_ts": s.get("end_ts"),
                    "duration_ms": s.get("duration_ms") or 0,
                    "tool_calls": sum((s.get("tool_counts") or {}).values()),
                    "agents": s.get("agent_count") or 0}
                   for s in trace.get("stages") or [] if s.get("stage") != "setup"],
        "findings": audit.build_audit(trace)["findings"],
        "prompts": [{"ts": p.get("ts"), "text": p.get("text") or ""} for p in trace.get("prompts") or []],
    }


def _project_roots(path: str, trace: dict[str, Any]) -> list[str]:
    meta = trace.get("meta") or {}
    fmt = str(meta.get("session_format") or "claude")
    if fmt == "codex":
        return crosschain.collect_project_roots(path, str(meta.get("cwd") or ""), limit=64)
    if fmt == "claude":
        return crosschain.collect_claude_project_roots(path, limit=64)
    return [os.path.abspath(path)]


def _thread(path: str, role: str, extract: Callable[[str], dict[str, Any]], *,
            dimension: str | None = None, iterations: list[int] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"thread_id": "", "transcript": path, "role": role, "dimension": dimension,
                           "ecat_iterations": list(iterations or []), "href": None}
    try:
        trace = extract(path)
    except Exception:  # noqa: BLE001 - 一份读不出不拖垮整页
        out["transcript"] = None
        return out
    out["thread_id"] = str((trace.get("meta") or {}).get("session_id") or os.path.basename(path).split(".")[0])
    out["href"] = followups.report_href(path)
    out.update(summarize(trace))
    return out


def _ecat_sessions(harmony: str, extract: Callable[[str], dict[str, Any]],
                   claimed: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """每次 run 一行,行里是各角色各轮次的运行时会话;同一 rollout 跨轮复用时并成一格。"""
    runs = ecat.list_runs(harmony)
    rows: list[dict[str, Any]] = []
    judge_tids = {tid: roles for tid, roles in ecat.stream_sessions(harmony).items()
                  if any(r.get("role") == "judge" for r in roles)}
    for run in reversed(runs):                     # list_runs 最新在前;总览按时间序
        by_path: dict[str, dict[str, Any]] = {}
        for it in run.get("iterations") or []:
            for s in it.get("sessions") or []:
                slot = by_path.setdefault(os.path.normcase(os.path.abspath(str(s["transcript"]))),
                                          {"path": str(s["transcript"]), "role": s.get("role") or "", "its": []})
                if it.get("iteration") is not None and it["iteration"] not in slot["its"]:
                    slot["its"].append(it["iteration"])
        for s in run.get("unmatched_sessions") or []:
            by_path.setdefault(os.path.normcase(os.path.abspath(str(s["transcript"]))),
                               {"path": str(s["transcript"]), "role": s.get("role") or "", "its": []})
        threads = []
        for key, slot in by_path.items():
            claimed.add(key)
            threads.append(_thread(slot["path"], slot["role"], extract, iterations=slot["its"]))
        # codex 线的判官是 runner 另起的会话:按 transcripts/judge_<维度>.stream.jsonl 的 thread id 找
        index = None
        for tid, roles in judge_tids.items():
            mine = [r for r in roles if r.get("run_id") == run["run_id"] and r.get("role") == "judge"]
            if not mine:
                continue
            index = index or ecat._CodexRollouts()
            jpath = index.path(tid)
            if jpath and os.path.normcase(os.path.abspath(jpath)) not in claimed:
                claimed.add(os.path.normcase(os.path.abspath(jpath)))
                threads.append(_thread(jpath, "judge", extract, dimension=mine[0].get("dimension")))
        rows.append({"session_id": run["run_id"], "kind": "ecat", "role": "ecat", "name": run["run_id"],
                     "started_at": run.get("started_at"), "threads": threads, "timeline": []})
    return rows, runs


def build_chain(path: str, extract: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """锚点会话 → 它所在迁移的会话总览。**逐个归约 transcript,大工程要几十秒。**"""
    if extract is None:
        from . import service
        extract = service.extract_trace
    with ecat.shared_scan():
        return _build_chain(os.path.abspath(path), extract)


def _build_chain(path: str, extract: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    anchor = extract(path)
    meta = anchor.get("meta") or {}
    harmony = ecat.harmony_of(path) or str(meta.get("cwd") or "")
    claimed: set[str] = set()
    sessions: list[dict[str, Any]] = []
    ecat_rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    if harmony and os.path.isdir(harmony):
        ecat_rows, runs = _ecat_sessions(harmony, extract, claimed)
    roots = [] if ecat.role_of(path) else _project_roots(path, anchor)
    orphans: list[dict[str, Any]] = []
    for root in roots:
        key = os.path.normcase(os.path.abspath(root))
        if key in claimed:
            continue
        claimed.add(key)
        # run 目录没登记的 ECAT 会话(判官流每轮覆盖,早先轮次的判官只剩开工提示能认出;
        # DevEco 线角色流不记会话 id):只读文件头的开工提示认角色
        dimension = ecat.judge_dimension(root)
        loop_role = None if dimension else ecat.loop_role(root)
        if dimension or loop_role:
            orphans.append(_thread(root, "judge" if dimension else str(loop_role), extract, dimension=dimension))
            continue
        thread = _thread(root, "", extract)
        sessions.append({"session_id": thread["thread_id"] or os.path.basename(root).split(".")[0],
                         "kind": "session", "role": "", "name": "",
                         "started_at": thread.get("started_at"), "threads": [thread], "timeline": []})
    sessions.extend(ecat_rows)
    if orphans:
        sessions.append({"session_id": "ecat", "kind": "ecat", "role": "ecat", "name": "run 目录未登记的 ECAT 会话",
                         "started_at": min((str(t.get("started_at") or "") for t in orphans), default=""),
                         "threads": orphans, "timeline": []})
    sessions.sort(key=lambda s: str(s.get("started_at") or ""))
    threads = [t for s in sessions for t in s["threads"]]
    found = [t for t in threads if t["transcript"]]
    totals: dict[str, Any] = {k: sum(t.get(k) or 0 for t in found) for k in _SUMMED}
    totals.update(sessions=len(sessions), threads=len(threads), threads_missing=len(threads) - len(found))
    started = [t["started_at"] for t in found if t.get("started_at")]
    ended = [t["ended_at"] for t in found if t.get("ended_at")]
    return {
        **(identity(harmony) if harmony else {}),
        "anchor": str(meta.get("session_id") or os.path.basename(path).split(".")[0]),
        "harmony": harmony,
        "started_at": min(started, default=None), "ended_at": max(ended, default=None),
        "sessions": sessions, "totals": totals,
        "ecat_runs": list(reversed(runs)),
        "findings": [{"session_id": s["session_id"], "thread_id": t["thread_id"],
                      "role": t["dimension"] or t["role"] or s["kind"], **f}
                     for s in sessions for t in s["threads"] for f in t.get("findings") or []],
    }
