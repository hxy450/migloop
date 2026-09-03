"""跨会话:同工程 root 会话的发现(前序 / 后继 / 全程)与迁移全程的轮卡。

跨会话返修链本身已由两原子账本接管:同工程的兄弟会话进同一本账,
链由 filestory.build_fix_chains 按逐笔版本的阶段算(修复方判定只此一处),
链上 gen_session / fix_session 标出生成方、修复方各在哪一轮。这里只剩
"哪些 root 属于同一个工程、谁先谁后"这类文件系统层面的事实。
"""

from __future__ import annotations

from typing import Any


def _same_project(cwd_a: str, cwd_b: str) -> bool:
    a = cwd_a.replace("\\", "/").rstrip("/").lower()
    b = cwd_b.replace("\\", "/").rstrip("/").lower()
    return bool(a and b) and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))


def find_prior_codex_roots(cur_path: str, cur_cwd: str, limit: int = 3) -> list[str]:
    """同一工程树里、时间早于当前会话的 codex 主会话(rollout 文件名即时间序)。

    工程同树 = 两个 cwd 相等或一方是另一方的父目录(真实案例:生成会话 cwd 在
    工程父目录,verify 会话 cwd 在工程根)。子代理 rollout 由 iter_sessions 排除。
    """
    import os

    from migloop import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    cur_base = os.path.basename(cur_path)
    out = []
    for cand in codex.iter_sessions(codex.default_root()):
        if os.path.abspath(cand.path) == cur_abs:
            continue
        if os.path.basename(cand.path) >= cur_base:
            continue
        summary = codex.session_summary(cand.path) or {}
        if _same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand.path)
    out.sort(key=lambda x: str(x).rsplit("rollout-", 1)[-1], reverse=True)
    return out[:limit]


def find_later_codex_roots(cur_path: str, cur_cwd: str, limit: int = 3) -> list[str]:
    """镜像方向:同工程树里时间晚于当前会话的主会话 —— 生成轮反查
    "我的产出后来被谁修了"用(链页给出后继轮的入口)。"""
    import os

    from migloop import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    cur_base = os.path.basename(cur_path)
    out = []
    for cand in codex.iter_sessions(codex.default_root()):
        if os.path.abspath(cand.path) == cur_abs:
            continue
        if os.path.basename(cand.path) <= cur_base:
            continue
        summary = codex.session_summary(cand.path) or {}
        if _same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand.path)
    out.sort(key=lambda x: str(x).rsplit("rollout-", 1)[-1])
    return out[:limit]


def collect_project_roots(cur_path: str, cur_cwd: str, limit: int = 8) -> list[str]:
    """同工程树的全部主会话(含当前),按 rollout 文件名时间序 —— 迁移全程视图用。"""
    import os

    from migloop import adapters

    codex: Any = adapters.get("codex")
    cur_abs = os.path.abspath(cur_path)
    out = [cur_abs]
    for cand in codex.iter_sessions(codex.default_root()):
        cand_abs = os.path.abspath(cand.path)
        if cand_abs == cur_abs:
            continue
        summary = codex.session_summary(cand.path) or {}
        if _same_project(str(summary.get("cwd") or ""), cur_cwd):
            out.append(cand_abs)
    out.sort(key=lambda x: str(os.path.basename(x)))
    return out[:limit]


def journey_rounds(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """多轮 trace(时间序) → 轮卡数据:每轮的阶段构成/规模/修复方数量。"""
    rounds = []
    for tr in traces:
        meta = tr.get("meta") or {}
        cwd = str(meta.get("cwd") or "")
        agents = tr.get("agents") or []
        fixers = [a for a in agents
                  if any(m in str(a.get("type") or "").lower()
                         for m in ("fixer", "visual"))]
        files = (tr.get("lineage") or {}).get("files") or []
        rounds.append({
            "sid8": str(meta.get("session_id") or "")[:8],
            "project": next((x for x in reversed(cwd.replace("\\", "/").split("/")) if x), ""),
            "started_at": meta.get("started_at"),
            "ended_at": meta.get("ended_at"),
            "stages": [{"label": st.get("label") or st.get("stage"),
                        "duration_ms": st.get("duration_ms") or 0}
                       for st in tr.get("stages") or []],
            "agents": (tr.get("totals") or {}).get("subagent_transcripts") or 0,
            "ets_files": sum(1 for f in files if f.get("kind") == "ets" and f.get("writers")),
            "fixers": len(fixers),
        })
    return rounds


def _first_record_ts(path: str) -> str:
    """首条带 timestamp 的记录 —— CC transcript 的会话开始时间。
    文件 mtime 在拷贝/归档后不可靠,时间序一律以内容为准。"""
    import json

    try:
        with open(path, encoding="utf-8", errors="ignore") as stream:
            for line in stream:
                try:
                    ts = json.loads(line).get("timestamp")
                except Exception:
                    continue
                if ts:
                    return str(ts)
    except OSError:
        pass
    return ""


def collect_claude_project_roots(cur_path: str, limit: int = 8) -> list[str]:
    """CC 同工程 = 同 transcript 目录(projects/<cwd-slug>/);全部主会话时间序。"""
    import glob
    import os

    d = os.path.dirname(os.path.abspath(cur_path))
    rows = []
    for f in glob.glob(os.path.join(d, "*.jsonl")):
        ts = _first_record_ts(f)
        if ts:
            rows.append((ts, os.path.abspath(f)))
    rows.sort()
    return [f for _, f in rows][:limit]


def find_prior_claude_roots(cur_path: str, limit: int = 3) -> list[str]:
    import os

    cur_abs = os.path.abspath(cur_path)
    cur_ts = _first_record_ts(cur_path)
    out = [f for f in collect_claude_project_roots(cur_path, 64)
           if f != cur_abs and _first_record_ts(f) < cur_ts]
    return out[-limit:][::-1]


def find_later_claude_roots(cur_path: str, limit: int = 3) -> list[str]:
    import os

    cur_abs = os.path.abspath(cur_path)
    cur_ts = _first_record_ts(cur_path)
    out = [f for f in collect_claude_project_roots(cur_path, 64)
           if f != cur_abs and _first_record_ts(f) > cur_ts]
    return out[:limit]
