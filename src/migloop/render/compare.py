# -*- coding: utf-8 -*-
"""跨会话对比页构建:trace JSON 列表 -> 摘要 -> 自包含 HTML。
被 build_compare.py(开发)与 migloop.py --compare(分发)共用。"""
import json
import os
import re
from collections import Counter


def _basename(p):
    return os.path.basename((p or "").rstrip("\\/")) or "session"


def digest(trace):
    """把完整 trace 压成对比页所需的紧凑摘要。"""
    m, t = trace["meta"], trace["totals"]
    proj = _basename(m.get("cwd"))
    label = proj.replace("transfer-app-", "")
    stages = []
    for s in trace["stages"]:
        if s["stage"] == "setup":
            continue
        stages.append({
            "stage": s["stage"], "label": s["label"],
            "dur_ms": s["duration_ms"] or 0,
            "active_ms": s.get("active_ms"),
            "tools": sum(s["tool_counts"].values()),
            "agents": s["agent_count"],
            "out": s["output_tokens"],
        })
    agent_types = Counter(a["type"] for a in trace["agents"])
    skills = {}
    for x in trace["tools"]:
        if x["name"] == "Skill" and x.get("skill"):
            skills.setdefault(x["skill"], [0, 0])[0] += 1
    for a in trace["agents"]:
        for k, v in (a.get("skills") or {}).items():
            skills.setdefault(k, [0, 0])[1] += v
    ct = trace.get("context_timeline") or []
    peak = max((p["ctx"] for p in ct), default=0)
    spark = []
    if len(ct) > 1:
        step = max(1, len(ct) // 140)
        n = len(ct)
        for i in range(0, n, step):
            spark.append([round(i / (n - 1), 4), ct[i]["ctx"]])
        if spark[-1][0] != 1.0:
            spark.append([1.0, ct[-1]["ctx"]])
    fails = sum(1 for x in trace["tools"] if x["ok"] is False)
    billing = trace.get("billing") or {}
    return {
        "label": label, "proj": proj,
        "sid8": (m.get("session_id") or "")[:8],
        "cc": m.get("cc_version"), "model": m.get("model"),
        "start": m.get("started_at"), "end": m.get("ended_at"),
        "dur_ms": t.get("duration_ms") or 0,
        "active_ms": t.get("active_ms"),
        "wait_ms": t.get("user_wait_ms") or 0,
        "tool_calls": t.get("tool_calls") or 0,
        "fails": fails,
        "agents": t.get("subagent_transcripts") or 0,
        "prompts": t.get("user_prompts") or 0,
        "compactions": t.get("compactions") or 0,
        "ctx_peak": peak,
        "out_total": (t.get("main_output_tokens") or 0) + (t.get("subagent_output_tokens") or 0),
        "stages": stages,
        "agent_types": dict(agent_types),
        "skills": {k: {"m": v[0], "s": v[1]} for k, v in skills.items()},
        "spark": spark,
        "billing": billing,
    }


def extract_font_face(viewer_template_text):
    """从单会话模板里取出 @font-face 块(内嵌字体 data URI),避免仓库存两份。"""
    i = viewer_template_text.find("@font-face")
    if i < 0:
        return ""
    j = viewer_template_text.find("}", i)
    return viewer_template_text[i:j + 1] if j > 0 else ""


def build_compare_html(traces, compare_template_text, font_face=""):
    sessions = sorted((digest(tr) for tr in traces), key=lambda d: d["start"] or "")
    payload = json.dumps({"sessions": sessions}, ensure_ascii=False,
                         separators=(",", ":")).replace("</", "<\\/")
    payload = payload.replace("�", "?")
    html = compare_template_text.replace("/*__FONT_FACE__*/", font_face)
    assert "__COMPARE_JSON__" in html
    return html.replace("__COMPARE_JSON__", payload)
