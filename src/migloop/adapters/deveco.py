# -*- coding: utf-8 -*-
"""DevEco Code (opencode-based) session export -> MigLoop normalized trace.

DevEco Code is Huawei's opencode fork.  Its *native* storage is a SQLite
database (``~/.local/share/deveco/deveco.db``, schema: session / message / part
/ event ...).  Two input paths are supported:

* **bare session id** (``ses_...``) → read the main thread straight from the
  SQLite DB via :func:`extract_from_db` (no export step needed); child-session
  enrichment also comes from the same DB.  The DB is the source of truth — the
  reconstructed data is a superset of the official export, with the overlapping
  fields identical.
* **export file path** → read a self-contained ``.json`` export (backward
  compatible; useful for shared files that aren't in the local DB).  Both paths
  converge on :func:`_parse`, so their traces are identical.

The export is produced by DevEco's "export session" action and looks like::

    Exporting session: ses_0055fed6dffe24Hxww4m5xajNP
    {
      "info": {
        "id": "ses_0055fed6dffe24Hxww4m5xajNP",
        "directory": "C:\\Users\\...\\migration",
        "agent": "DynamicWorkflow",
        "model": {"id": "deepseek-v4-pro", "providerID": "deepseek", "variant": "max"},
        "version": "0.1.7",
        "tokens": {"input": 514417, "output": 125927, "reasoning": 83288,
                   "cache": {"read": 78621952, "write": 0}},
        "time": {"created": 1786616222354, "updated": 1786691611295}
      },
      "messages": [
        {"info": {"role": "user", "id": "msg_...", "sessionID": "ses_...", ...},
         "parts": [{"type": "text", "text": "..."}]},
        {"info": {"role": "assistant", "parentID": "msg_...",
                  "tokens": {"total": 14133, "input": 13908, "output": 101,
                             "reasoning": 124, "cache": {"read": 0, "write": 0}},
                  "time": {"created": ..., "completed": ...},
                  "finish": "tool-calls", "error": null, ...},
         "parts": [
           {"type": "step-start", ...},
           {"type": "reasoning", "text": "..."},
           {"type": "tool", "tool": "read", "callID": "...",
            "state": {"status": "completed",
                      "input": {"filePath": "...", "offset": 0, "limit": 100},
                      "output": "<path>...</path><content>\n1: ...\n2: ...\n"}},
           {"type": "step-finish", "tokens": {...}, ...}
         ]}
      ]
    }

Key differences from Claude Code / Codex that this adapter absorbs:

* **single self-contained JSON**, not JSONL — skip the ``Exporting session:``
  prefix and ``json.loads`` the rest.
* **timestamps are Unix milliseconds** (not ISO strings); convert once here.
* **tools are inline ``part.type == "tool"``** with ``state.input`` /
  ``state.output`` / ``state.status`` / ``state.time`` — no separate
  ``toolUseResult`` pass needed.
* **no subagents** — every message belongs to the same ``agent``
  (``DynamicWorkflow``).  The ``agents[]`` list is therefore empty and all
  lineage is reconstructed from the single main thread.
* **stage signal** — two sources: the ``workflow`` tool's ``name``/``runName``
  (``explore`` / ``implement`` / ``verify_fix`` / ``acceptance_audit`` ...) opens
  a ``wf:<name>`` stage; a pipeline ``skill`` tool call (``a2h-spec`` /
  ``a2h-plan`` / ``a2h-execute`` / ...) opens a pipeline stage (aligned with
  ``claude.py``).  There is no ``attributionSkill`` field here, so the ``skill``
  tool call is one pipeline signal; non-pipeline ``skill`` calls remain
  helper markers.  The other one is a **user message that is itself a SKILL.md
  body**: DevEco's ``/<skill>`` command expands the skill text into the user
  prompt without any ``skill`` tool call, so the first H1 heading (``# a2h-spec — …``)
  is taken as the skill name (see :func:`_prompt_skill`).

Known limitation (not a bug in this module): ``build_lineage`` classifies an
Android source file as "Android reference" only when its path stays **absolute
after ``_rel``** (i.e. it lives *outside* ``cwd``).  In this DevEco migration
workspace the Android sources (``AntennaPod-develop/``), the Harmony target
(``AntennaPod_Harmony/``) and ``spec/`` all live *inside* ``cwd``, so spec
reads/writes and ``.ets`` writes resolve correctly, but Android-source reads
fall into the "project reads" bucket rather than the dedicated Android column.
Restoring the purple "read Android" edges for an in-workspace Android tree is a
follow-up (either teach ``build_lineage`` a source-root, or a devEco-specific
source directory config).

Run standalone (without touching the CLI registry):

    python -m migloop.adapters.deveco --list
    python -m migloop.adapters.deveco <path-to-export.json>
    python -m migloop.adapters.deveco ses_0055fed6dffe24Hxww4m5xajNP  # 只给 session id,直接读 DB
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

from . import claude as common
from .base import SessionCandidate

FORMAT = "deveco"
SUPPORTS_LIVE = False  # export is a snapshot; incremental SQLite reader is future work


# --------------------------------------------------------------------------- #
# Layout / field constants (adjust to a concrete DevEco build without touching
# the parsing logic below).
# --------------------------------------------------------------------------- #

#: DevEco tool name -> MigLoop tool name.  Everything else keeps its own name.
TOOL_MAP = {
    "read": "Read",
    "write": "Write",
    "edit": "Edit",
    "bash": "Bash",
    "grep": "Grep",
    "glob": "Glob",
    "workflow": "Workflow",
    "skill": "Skill",
    "plan_write": "PlanWrite",
    "start_app": "StartApp",
    "hdc_log": "HdcLog",
}

# 阶段展示标签统一复用 claude 的 common.STAGE_LABELS(setup/session/管线 skill 全覆盖),
# workflow 阶段用 ``wf:<name>`` 命名(见 _build_stages),故此处不再维护本地映射。

#: ``read`` output is XML-wrapped with ``N: text`` line prefixes.  Parse those
#: back into precise read spans (mirrors Claude's ``_spans_from_numbered_text``
#: but for the ``N:`` delimiter instead of ``N\\t``).
_READ_LINE_RE = re.compile(r"(?m)^\s*(\d+):\s")

#: DevEco 会话 id 形如 ``ses_<alnum>``,用于识别「裸 session id」(非文件路径)输入,
#: 从而跳过导出步骤、直接读 SQLite 还原。
_SESSION_ID_RE = re.compile(r"^ses_[0-9A-Za-z]+$")


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _to_num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _ms_to_iso(value):
    """Unix millis (or seconds) -> ISO-8601 string; None if unparseable."""
    n = _to_num(value)
    if n is None:
        return None
    if abs(n) > 1e11:  # millis (epoch millis ~1.7e12); seconds are ~1.7e9
        n /= 1000.0
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _iso_ms(iso):
    """ISO-8601 string -> Unix millis (float); None if unparseable."""
    d = common.parse_ts(iso)
    return d.timestamp() * 1000.0 if d is not None else None


def _union_ms(intervals):
    """合并 [start_ms, end_ms] 区间,返回 (merged, total_ms)。

    输入是若干活动区间(主代理 + 子代理的 reasoning ∪ tool 执行),重叠部分只算一次;
    并行子代理之间的时间轴重叠、相邻区间合并都由这里统一处理。
    """
    spans = sorted((float(s), float(e)) for s, e in intervals if e > s)
    merged = []
    for s, e in spans:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    total = sum(int(e - s) for s, e in merged)
    return merged, total


def _to_text(value):
    """Best-effort flatten of a tool output (str / list / dict) to text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(_to_text(x) for x in value)
    if isinstance(value, dict):
        for key in ("text", "output", "content", "message", "stdout", "title", "summary"):
            v = value.get(key)
            if v is not None:
                t = _to_text(v)
                if t:
                    return t
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return str(value)


def _read_export(path):
    """Read an export file, skip any leading banner, parse the JSON object."""
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            text = stream.read()
    except OSError:
        return None
    i = text.find("{")
    if i < 0:
        return None
    try:
        data = json.loads(text[i:])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _file_path(inp):
    if not isinstance(inp, dict):
        return None
    for key in ("filePath", "file_path", "path"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _brief(name, inp):
    if not isinstance(inp, dict):
        return ""
    if name in ("Read", "Write", "Edit"):
        fp = _file_path(inp)
        if fp:
            return fp
    for key in ("command", "pattern", "name", "runName", "scriptPath", "path",
                "filePath", "description", "query", "url", "action", "hvd"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return " ".join(v.split())[:300]
    return ""


def _content_lines(text):
    return text.count("\n") + 1 if isinstance(text, str) else 0


def _read_spans(output):
    """Reconstruct read intervals from ``N:`` line prefixes in read output."""
    nums = []
    for m in _READ_LINE_RE.finditer(output or ""):
        try:
            nums.append(int(m.group(1)))
        except ValueError:
            pass
    if not nums:
        return []
    return common._merge_line_intervals([(n, 1) for n in sorted(set(nums))])


def _tool_failed(state, output):
    status = (state or {}).get("status")
    if status in ("error", "failed", "cancelled"):
        return True
    low = (output or "").lower()
    return ("iserror" in low.replace(" ", "") and "true" in low.replace(" ", ""))


# --------------------------------------------------------------------------- #
# Tool-entry construction (feeds build_lineage's main-thread contributor)
# --------------------------------------------------------------------------- #

def _attach_read(entry, inp, output):
    if not isinstance(inp, dict) or not _file_path(inp):
        return
    offset, limit = inp.get("offset"), inp.get("limit")
    if isinstance(offset, (int, float)) and isinstance(limit, (int, float)) and int(limit) > 0:
        entry["rstart"] = int(offset) + 1
        entry["rlines"] = int(limit)
    else:
        spans = _read_spans(output)
        if spans:
            entry["_rspans"] = spans
            entry["rlines"] = sum(count for _, count in spans)
            entry["rstart"] = spans[0][0]
            last = spans[-1]
            entry["rtotal"] = last[0] + last[1] - 1


def _attach_write(entry, inp):
    if not isinstance(inp, dict):
        return
    content = inp.get("content")
    wl = _content_lines(content) if isinstance(content, str) else 0
    entry["wlines"] = wl
    entry["wevent"] = ["set", wl]


def _attach_edit(entry, inp):
    # DevEco `edit` uses camelCase oldString/newString (like Claude's Edit).
    if not isinstance(inp, dict):
        return
    new = inp.get("newString")
    old = inp.get("oldString")
    nl = _content_lines(new) if isinstance(new, str) else 0
    ol = _content_lines(old) if isinstance(old, str) else 0
    entry["wlines"] = nl
    entry["wevent"] = ["delta", nl - ol]


def _attach_bash(entry, inp, output, cwd):
    if not isinstance(inp, dict):
        return
    cmd = inp.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return
    workdir = inp.get("workdir") or cwd
    visible = common._infer_visible_source_lines("Bash", {"command": cmd}, output, workdir)
    if visible:
        entry["_visible_source_lines"] = visible
    probed = common._script_probed_paths("Bash", {"command": cmd}, workdir)
    if probed:
        entry["_probed_paths"] = probed


def _build_tool_entry(seq, idx, ts, name, inp, call_id, output, state, cwd):
    state = state or {}
    display = TOOL_MAP.get(name, name)
    entry = {
        "seq": seq,
        "idx": idx,
        "ts": ts,
        "name": display,
        "brief": _brief(display, inp),
        "ok": not _tool_failed(state, output),
        "dur_ms": None,
        "tuid": call_id,
        "result": (output or "").strip()[:220],
        "_inp": inp,
    }
    st = state.get("time")
    if isinstance(st, dict) and isinstance(st.get("start"), (int, float)) \
            and isinstance(st.get("end"), (int, float)):
        entry["dur_ms"] = max(0, int(st["end"] - st["start"]))

    if display == "Read":
        _attach_read(entry, inp, output)
    elif display == "Write":
        _attach_write(entry, inp)
    elif display == "Edit":
        _attach_edit(entry, inp)
    elif display == "Bash":
        _attach_bash(entry, inp, output, cwd)
    elif display == "Skill" and isinstance(inp, dict):
        entry["skill"] = inp.get("name") or inp.get("skill")
    elif display == "Workflow" and isinstance(inp, dict):
        # 对应 Claude 的 Agent/Task 与 Codex 的 spawn_agent:派发工具携带 agent_type/
        # agent_desc,供 tooltip 显示「Workflow → <类型>」。DevEco 的 workflow 工具即
        # 编排派发动作,name/runName 是类型,args.goal 是任务描述。
        entry["agent_type"] = inp.get("name") or inp.get("runName") or ""
        args = inp.get("args")
        goal = args.get("goal") if isinstance(args, dict) else None
        entry["agent_desc"] = (goal or "")[:240] if isinstance(goal, str) else ""
    return entry


# --------------------------------------------------------------------------- #
# Part / message parsing
# --------------------------------------------------------------------------- #

def _tool_part(part):
    if not isinstance(part, dict) or part.get("type") != "tool":
        return None
    name = part.get("tool")
    if not name:
        return None
    call_id = part.get("callID") or part.get("call_id") or part.get("id")
    state = part.get("state")
    if not isinstance(state, dict):
        state = {}
    inp = state.get("input")
    if not isinstance(inp, dict):
        inp = part.get("input") if isinstance(part.get("input"), dict) else {}
    output = state.get("output") if state.get("output") is not None else part.get("output")
    return name, call_id, inp, _to_text(output), state


def _parts_chars(parts):
    """(thinking, text, tool) char counts, for splitting output tokens."""
    th = tx = tu = 0
    for p in parts:
        t = p.get("type")
        if t == "text":
            tx += len(p.get("text") or "")
        elif t == "reasoning":
            th += len(p.get("text") or p.get("summary") or "")
        elif t == "tool":
            inp = (p.get("state") or {}).get("input") or {}
            try:
                tu += len(json.dumps(inp, ensure_ascii=False))
            except (TypeError, ValueError):
                pass
    return th, tx, tu


def _user_prompt(parts):
    chunks = [p.get("text") for p in parts
              if p.get("type") == "text" and isinstance(p.get("text"), str)]
    return "\n".join(chunks)


_FIRST_H1_RE = re.compile(r"^#[ \t]+(\S+)", re.MULTILINE)


def _prompt_skill(text):
    """user 消息本身是一篇 SKILL.md 时返回管线技能名,否则 None。

    DevEco 的 ``/<skill>`` 命令把整篇技能正文展开成 user 消息,没有 skill 工具调用
    (wugang 09-09 的会话:a2h-spec 与 arkts-visual-verify 都是这样进来的,报告只切出
    Setup → Plan)。只看第一个一级标题的首个词,且必须命中管线技能名:正文里顺带提到
    别的技能、或标题不是技能名(a2h-functional-registry 的「§M 合账段」)都不算。"""
    m = _FIRST_H1_RE.search(text or "")
    if not m:
        return None
    name = m.group(1)
    return name if name in common.PIPELINE_SKILLS else None


def _session_model(info):
    m = info.get("model")
    if isinstance(m, dict):
        return m.get("id") or m.get("modelID") or m.get("providerID")
    return None


def _parse_model_column(model_str):
    """session.model 列是 JSON 字符串(如 {"id":"deepseek-v4-pro",...}),解析成单一模型 id。"""
    if isinstance(model_str, str) and model_str.strip():
        try:
            m = json.loads(model_str)
        except json.JSONDecodeError:
            return model_str.strip()
        if isinstance(m, dict):
            return m.get("id") or m.get("modelID") or m.get("providerID")
    return None


def _message_model(mi):
    """返回单一模型 id(与 _session_model 对齐),而非 providerID/modelID 拼接。

    Claude Code 的 message.model 是单一模型名(如 claude-sonnet-4-5),不带 provider;
    DevEco(基于 opencode)把模型拆成 modelID + providerID,这里的对等物是 modelID。
    主路径 _session_model 返回 info.model.id(即 modelID),故兜底也返回 modelID,
    保证两条路径产出的 model 字符串一致(也避免 billing 键被斜杠拼接拆成两套)。
    """
    mid = mi.get("modelID") or mi.get("id")
    if mid:
        return mid
    m = mi.get("model")
    if isinstance(m, dict):
        return m.get("modelID") or m.get("id") or m.get("providerID")
    return mi.get("providerID")


def _accumulate_usage(billing, context_timeline, mi, model):
    tk = mi.get("tokens")
    if not isinstance(tk, dict):
        return
    cache = tk.get("cache") or {}
    inp = tk.get("input") or 0
    cread = cache.get("read") or 0
    cwrite = cache.get("write") or 0
    out = (tk.get("output") or 0) + (tk.get("reasoning") or 0)  # output 桶不含 reasoning,对齐 claude 的 output_tokens
    key = model or "unknown"
    bucket = billing.setdefault(key, {"req": 0, "inp": 0, "cread": 0,
                                      "cw5": 0, "cw1h": 0, "out": 0})
    bucket["req"] += 1
    bucket["inp"] += inp
    bucket["cread"] += cread
    bucket["cw1h"] += cwrite  # opencode has no 5m/1h cache split; fold into 1h
    bucket["out"] += out
    context_timeline.append({
        "ts": _ms_to_iso((mi.get("time") or {}).get("created")),
        "ctx": inp + cread + cwrite,
        "out": out, "inp": inp, "cread": cread, "cwrite": cwrite,
    })


# --------------------------------------------------------------------------- #
# Stage boundaries from `workflow` tool calls
# --------------------------------------------------------------------------- #

def _workflow_key(t):
    inp = t.get("_inp") or {}
    # 用 runName(运行实例,唯一)而非 name(类型,多 run 共享)做段名,否则 implement_w0..wN
    # 会共用一个段 key,阶段血缘按 stage 过滤时把全体 implement 子代理并进每一段。
    for key in ("runName", "name"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    sp = inp.get("scriptPath")
    if isinstance(sp, str) and sp.strip():
        return os.path.splitext(os.path.basename(sp))[0]
    # 兜底：内联调用模式——spec.script 里塞了完整 JS 源码，从 meta.name 提取 workflow 名
    spec = inp.get("spec")
    script = spec.get("script") if isinstance(spec, dict) else spec
    if isinstance(script, str):
        m = re.search(r"meta\s*=\s*\{[^}]*?name\s*:\s*['\"]([^'\"]+)['\"]", script)
        if m:
            return m.group(1).strip()
    return None


def _stage_boundaries(tools, prompt_skills=()):
    # 三条阶段信号(DevEco 没有 attributionSkill,故用 codex 的 current 变更检测——
    # 正确处理 execute→verify→execute 回环):
    #   1) 管线 skill(Skill 工具调用,归一后命中 common.PIPELINE_SKILLS)= 阶段边界,段名取 skill 名;
    #   2) user 消息就是管线技能正文(/<skill> 命令展开,见 _prompt_skill)= 同 1),
    #      prompt_skills 为 [(message idx, skill)];
    #   3) workflow 模式(Workflow 工具调用)= 一个阶段,段名取 wf:<workflow name>。
    # 三条边界按 message idx 合并(稳定排序,同 idx 保持原顺序)、去重,setup 兜底逻辑不变。
    events = []
    for t in tools:
        if t["name"] == "Skill" and t.get("skill"):
            events.append((t["idx"], "skill", (t["skill"] or "").split(":")[-1]))
        elif t["name"] == "Workflow":
            events.append((t["idx"], "wf", _workflow_key(t)))
    events.extend((idx, "skill", skill) for idx, skill in prompt_skills if skill)
    events.sort(key=lambda e: e[0])
    transitions = []
    current = None
    for idx, kind, key in events:
        if kind == "skill":
            if key in common.PIPELINE_SKILLS and key != current:
                transitions.append((idx, key))
                current = key
        elif key:
            transitions.append((idx, "wf:" + key))
    if not transitions:
        return [(0, "session")]
    # 去重(保留先出现者),避免退化出空段(对齐 claude 的 dedup):
    #   * 同一 idx —— Skill 与 Workflow 落在同一条消息时只留一个边界;
    #   * 相邻 key 相同 —— DynamicWorkflow 分阶段派发(如 acceptance_audit_a 先发一条
    #     explore 预扫描、再发真正的 audit),两次调用同属一个 runName,若都开阶段会拆出
    #     一个空的 explore 段 + 一个真正的 audit 段。合并成一个阶段。
    deduped = []
    for bnd in transitions:
        if deduped and (deduped[-1][0] == bnd[0] or deduped[-1][1] == bnd[1]):
            continue
        deduped.append(bnd)
    rows = [(0, "setup")] if deduped[0][0] > 0 else []
    rows.extend(deduped)
    return rows


def _build_stages(boundaries, points, max_idx):
    stages = []
    seen = Counter()
    for pos, (start_idx, key) in enumerate(boundaries):
        end_idx = boundaries[pos + 1][0] - 1 if pos + 1 < len(boundaries) else max_idx
        nums = [ts for idx, ts in points if start_idx <= idx <= end_idx and ts is not None]
        start = _ms_to_iso(min(nums)) if nums else None
        end = _ms_to_iso(max(nums)) if nums else None
        label = key[3:] if key.startswith("wf:") else common.STAGE_LABELS.get(key, key)
        seen[key] += 1
        if seen[key] > 1:
            label += " ·%d" % seen[key]
        stages.append({
            "id": "s%d" % pos, "stage": key, "label": label,
            "start_idx": start_idx, "end_idx": end_idx,
            "start_ts": start, "end_ts": end,
            "duration_ms": common.ms_between(start, end),
            "tool_counts": {}, "output_tokens": 0, "cache_read_tokens": 0,
            "helper_skills": [], "artifacts": [], "agent_count": 0,
            "prompt_idxs": [], "active_ms": None,
        })
    return stages


def _stage_of_idx(stages, idx):
    for s in reversed(stages):
        if idx >= s["start_idx"]:
            return s
    return stages[0]


# --------------------------------------------------------------------------- #
# Workflow subagents (DynamicWorkflow parallel units/areas)
# --------------------------------------------------------------------------- #

_RESULT_FENCE_RE = re.compile(r"Result:\s*```json\s*", re.DOTALL)
_DUR_RE = re.compile(r"\[(\d+(?:\.\d+)?)([smh])\]")


def _extract_workflow_result(output):
    """Pull the embedded ``Result: ```json ...`` `` object out of a workflow
    tool's output text.  ``raw_decode`` skips nested backticks inside string
    values (subagent summaries can themselves embed fenced code blocks)."""
    if not isinstance(output, str):
        return None
    m = _RESULT_FENCE_RE.search(output)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(output, m.end())
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_durations(text):
    """Collect ``[15.1m]`` / ``[37s]`` durations from a workflow summary, in
    the order they appear (units first, then gate/other)."""
    out = []
    for m in _DUR_RE.finditer(text or ""):
        v = float(m.group(1))
        unit = m.group(2)
        ms = v * 1000 if unit == "s" else (v * 60000 if unit == "m" else v * 3600000)
        out.append(int(ms))
    return out


def _count_lines(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _make_workflow_agent(aid, run_name, item, files, stage, seg, ts, dur, model):
    ok = bool(item.get("ok"))
    summary = (item.get("summary") or "").strip()
    writes, write_lines, write_events = [], {}, []
    for f in files:
        p = f.replace("\\", "/")
        if not p:
            continue
        writes.append(p)
        n = _count_lines(p)
        write_lines[p] = n
        write_events.append((ts or "", p, "set", n))
    return {
        "agent_id": "subagent:%s:%s" % (run_name or "wf", aid),
        "type": "subagent",
        "desc": ("%s — %s" % (aid, summary[:160])) if summary else str(aid),
        "wf_run": run_name or None,
        "wf_name": None,
        "wf_phase": None,
        "tuid": None,
        "stage": stage,
        "seg": seg,
        "start_ts": ts,
        "end_ts": ts,
        "dur_ms": dur,
        "output_tokens": 0,
        "tool_uses": 0,
        "tool_counts": {},
        "status": "completed" if ok else "failed",
        "aborted": None if ok else "interrupted",
        "model": model,
        "result": summary[:300],
        "skills": {},
        "skill_calls": [],
        "out_split": {"thinking": 0, "text": 0, "tool": 0},
        "_prompt": "",
        "_probed": [],
        "_reads": [],
        "_writes": writes,
        "_read_lines": {},
        "_write_lines": write_lines,
        "_read_iv": {},
        "_read_total": {},
        "_read_sources": {},
        "_write_events": write_events,
    }


def _build_workflow_agents(workflow_calls, model):
    """Rebuild DynamicWorkflow subagents from each workflow's result JSON.

    DevEco Code runs every workflow's units/areas as parallel subagents; their
    full transcripts live in on-disk ``*.run.md`` files, but the export embeds
    a compact result (id / ok / summary / produced files) — enough to restore
    the orchestration and attribute produced files to individual subagents.
    """
    agents = []
    for entry, output in workflow_calls:
        result = _extract_workflow_result(output)
        if not result:
            continue
        stage = entry.get("stage") or "?"
        seg = entry.get("seg")
        ts = entry.get("ts")
        inp = entry.get("_inp") or {}
        run_name = inp.get("runName") or inp.get("name") or ""
        durations = _parse_durations(output or "")
        di = 0
        for kind, key, fkey in (("units", "id", "files"), ("areas", "area", "doc")):
            items = result.get(kind)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                aid = item.get(key)
                if not aid:
                    continue
                files = item.get(fkey)
                if fkey == "doc":
                    files = [files] if isinstance(files, str) and files else []
                elif not isinstance(files, list):
                    files = []
                files = [f for f in files if isinstance(f, str) and f.strip()]
                dur = durations[di] if di < len(durations) else None
                di += 1
                agents.append(_make_workflow_agent(
                    aid, run_name, item, files, stage, seg, ts, dur, model))
    return agents


def _build_workflows(workflow_calls, agents=None):
    """从 workflow 工具调用聚合出 workflow 运行元数据,等价于 Claude 的 wf_*.json。

    DevEco 的 workflow 工具即编排派发动作,每次调用 = 一个 workflow 运行:
    - run_id/name/script_path 来自工具输入;
    - status(aborted/completed/unknown)与 duration 来自 output 文本;
    - agent_count 来自 output 里 "✓ Xxx (N units|areas)" 摘要(导出里 Result JSON 常被
      截断,但这段摘要没被截),否则退结果 JSON 的 units/areas/audited/results 计数;
    - tokens 按 dispatch 时间窗把子代理(DB 子会话)归到各 run 汇总。
    """
    ordered = sorted(workflow_calls, key=lambda wc: _iso_ms(wc[0].get("ts")) or 0.0)
    # 按 dispatch 时间窗把子代理归到各 run,统计数量 + output token
    starts = [_iso_ms(e.get("ts")) or 0.0 for e, _ in ordered]
    agent_counts = [0] * len(ordered)
    token_buckets = [0] * len(ordered)
    if agents:
        for a in agents:
            st = _iso_ms(a.get("start_ts"))
            if st is None:
                continue
            idx = -1
            for i, s in enumerate(starts):
                if s <= st:
                    idx = i
                else:
                    break
            if idx >= 0:
                agent_counts[idx] += 1
                token_buckets[idx] += a.get("output_tokens") or 0

    workflows = []
    for i, (entry, output) in enumerate(ordered):
        inp = entry.get("_inp") or {}
        out = output or ""
        # run_id 唯一实例:runName → name → scriptPath 基名 → tuid
        run_id = inp.get("runName") or inp.get("name")
        if not run_id:
            sp = inp.get("scriptPath")
            if isinstance(sp, str) and sp.strip():
                run_id = os.path.splitext(os.path.basename(sp))[0]
        run_id = run_id or entry.get("tuid") or ""
        name = inp.get("name") or inp.get("runName") or ""
        # status
        if "Workflow aborted" in out:
            status = "aborted"
        elif "Workflow completed" in out:
            status = "completed"
        else:
            status = "unknown"
        # duration
        dur = None
        m = re.search(r"\bin\s+([\d.]+)s\b", out)
        if m:
            try:
                dur = int(float(m.group(1)) * 1000)
            except ValueError:
                dur = None
        # agent_count:子会话精确计数优先,退 "✓ (N units|areas)" 或结果 JSON
        result = _extract_workflow_result(out)
        agent_count = agent_counts[i]
        if not agent_count:
            mm = re.search(r"✓\s+\S+\s+\((\d+)\s+(?:unit|area)s?\)", out)
            if mm:
                agent_count = int(mm.group(1))
            elif result:
                for kind in ("units", "areas", "audited", "results"):
                    items = result.get(kind)
                    if isinstance(items, list):
                        agent_count += len(items)
        # summary
        summary = (result.get("goal") or "")[:240] if result else ""
        if not summary and out.strip():
            summary = out.strip().split("\n")[0][:240]
        workflows.append({
            "run_id": run_id,
            "name": name,
            "task_id": entry.get("tuid"),
            "summary": summary,
            "phases": [],
            "status": status,
            "duration_ms": dur,
            "agent_count": agent_count,
            "tokens": token_buckets[i],
            "tool_calls": 0,
            "script_path": inp.get("scriptPath"),
        })
    return workflows


# --------------------------------------------------------------------------- #
# SQLite child-session enrichment (subagent tokens + read/write details)
# --------------------------------------------------------------------------- #

def _find_db(storage_root=None):
    if storage_root:
        if os.path.isfile(storage_root):
            return storage_root
        db = os.path.join(storage_root, "deveco.db")
        return db if os.path.isfile(db) else None
    root = default_root()
    if not root:
        return None
    db = os.path.join(root, "deveco.db")
    return db if os.path.isfile(db) else None


def _find_harmony_root(paths):
    """从鸿蒙产物(.ets/配置)写入路径反推目标工程根。

    build_lineage 只把「cwd 之外的绝对路径 .java/.kt」归为 Android 参考;DevEco 迁移
    工作区把 Android 源码(AntennaPod-develop/)、鸿蒙目标(AntennaPod_Harmony/)、spec/
    都放在同一 cwd 下,导致 Android 源码被相对化成"工程内读取"。这里反推鸿蒙目标根,
    把它作为 lineage 的 cwd,让 Android 源码重新成为"cwd 之外"的绝对路径。

    两套信号:
    1) 文件系统:向上找 hvigorfile.ts / AppScope(本地工作区最准);
    2) 路径结构:鸿蒙模块几乎都是 ``<root>/<module>/src/main/ets/...`` 布局,取
       ``src/main/ets`` 之上两层(模块目录的父目录)即工程根。分析他人机器导出、
       本机没有这些文件的会话时只能靠它。
    """
    votes = {}
    for p in paths:
        if not p:
            continue
        norm = p.replace("\\", "/")
        # 1) 文件系统信号(仅本地工作区命中)
        d = os.path.dirname(norm)
        for _ in range(12):
            if not d or len(d) < 4:
                break
            if os.path.isfile(os.path.join(d, "hvigorfile.ts")) \
                    or os.path.isdir(os.path.join(d, "AppScope")):
                votes[d] = votes.get(d, 0) + 1
                break
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
        # 2) 路径结构信号(不依赖本机文件存在)
        i = norm.lower().find("/src/main/ets")
        if i > 0:
            module = norm[:i]                    # .../<root>/<module>
            root = module.rsplit("/", 1)[0]      # .../<root>
            if root:
                votes[root] = votes.get(root, 0) + 1
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]


def _mark_aborted(agents, workflow_calls):
    """给被中断 workflow 的子代理回填 aborted(等价于 Claude 的 _abort_reason)。

    DevEco 的 SQLite 子会话没有逐子代理的收尾状态;失败信号只有 workflow 输出里的
    "Workflow aborted"(整个 run 被中断)。按 dispatch 时间窗把子代理归到 run,被中断
    run 的子代理记为 aborted。这是 workflow 级近似(aborted run 内已完成的部分子代理
    也会被记为 aborted,数据源没有更细的信号)。
    """
    runs = sorted(
        ((_iso_ms(e.get("ts")) or 0.0, "Workflow aborted" in (out or ""))
         for e, out in workflow_calls),
        key=lambda r: r[0],
    )
    starts = [r[0] for r in runs]
    for a in agents:
        if a.get("aborted"):
            continue
        st = _iso_ms(a.get("start_ts"))
        if st is None:
            continue
        idx = -1
        for i, s in enumerate(starts):
            if s <= st:
                idx = i
            else:
                break
        if idx >= 0 and runs[idx][1]:
            a["aborted"] = "interrupted"


def _open_db(db_path):
    try:
        return sqlite3.connect("file:///" + os.path.abspath(db_path).replace("\\", "/")
                               + "?mode=ro", uri=True)
    except sqlite3.Error:
        return None


def _load_session_from_db(db, session_id):
    """从 SQLite 还原出与官方 export 等价(且是其超集)的 ``{info, messages}``。

    ``session`` 表列 -> export 顶层 ``info``;``message`` / ``part`` 表的 ``data`` 列
    就是 export 里 ``messages[i].info`` / ``messages[i].parts`` 去掉外键列
    (``id`` / ``sessionID`` / ``messageID``)后的内容。这里按 ``message_id`` 分组
    并把外键字段补回,保证还原结果与 export 的重叠部分逐字段一致。
    """
    cur = db.cursor()
    cur.execute(
        "SELECT id, slug, project_id, directory, path, title, agent, model, version, "
        "summary_additions, summary_deletions, summary_files, cost, tokens_input, "
        "tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, "
        "time_created, time_updated FROM session WHERE id=? AND parent_id IS NULL",
        (session_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError("DevEco 数据库中不存在该会话(或非顶层会话): %s" % session_id)
    (sid, slug, project_id, directory, path, title, agent, model_str, version,
     sa, sd, sf, cost, ti, to, tr, cr, cw, tc, tu) = row

    model = None
    if isinstance(model_str, str) and model_str.strip():
        try:
            model = json.loads(model_str)
        except json.JSONDecodeError:
            model = model_str

    info = {
        "id": sid,
        "slug": slug,
        "projectID": project_id,
        # 与 export 对齐:DevEco 在 Windows 上导出时 directory 用反斜杠,DB 里是正斜杠。
        # 仅对带盘符的 Windows 绝对路径做正斜杠→反斜杠归一;POSIX 路径(/Users/...)保持
        # 原样——os.path.normpath 在 Windows 上会把 /Users/... 错化成 \Users\...(丢根语义)。
        "directory": directory.replace("/", "\\")
                     if directory and re.match(r"^[A-Za-z]:/", directory) else directory,
        "path": path,
        "title": title,
        "agent": agent,
        "model": model,
        "version": version,
        "summary": {"additions": sa or 0, "deletions": sd or 0, "files": sf or 0},
        "cost": cost,
        "tokens": {"input": ti or 0, "output": to or 0, "reasoning": tr or 0,
                   "cache": {"read": cr or 0, "write": cw or 0}},
        "time": {"created": tc, "updated": tu},
    }

    cur.execute("SELECT id, data FROM message WHERE session_id=? ORDER BY time_created, id",
                (session_id,))
    msg_rows = cur.fetchall()
    cur.execute("SELECT message_id, id, data FROM part WHERE session_id=? "
                "ORDER BY time_created, id", (session_id,))
    parts_by_msg = {}
    for message_id, pid, pdata in cur.fetchall():
        parts_by_msg.setdefault(message_id, []).append((pid, pdata))

    messages = []
    for mid, mdata in msg_rows:
        info_m = json.loads(mdata)
        info_m["id"] = mid
        info_m["sessionID"] = session_id
        parts = []
        for pid, pdata in parts_by_msg.get(mid, []):
            p = json.loads(pdata)
            p["id"] = pid
            p["sessionID"] = session_id
            p["messageID"] = mid
            parts.append(p)
        messages.append({"info": info_m, "parts": parts})

    return {"info": info, "messages": messages}


def _load_child_sessions(db, session_id):
    cur = db.cursor()
    try:
        cur.execute(
            "SELECT id, title, agent, model, tokens_input, tokens_output, tokens_reasoning, "
            "tokens_cache_read, tokens_cache_write, cost, time_created, time_updated "
            "FROM session WHERE parent_id=? ORDER BY time_created", (session_id,))
    except sqlite3.Error:
        return []
    rows = []
    for (sid, title, agent, model_str, ti, to, tr, cr, cw, cost, tc, tu) in cur.fetchall():
        rows.append({
            "id": sid, "title": title or "", "agent": agent or "",
            "model": _parse_model_column(model_str),
            "tokens": {"input": ti or 0, "output": to or 0, "reasoning": tr or 0,
                       "cache_read": cr or 0, "cache_write": cw or 0},
            "cost": cost or 0.0,
            "created": tc, "updated": tu,
        })
    return rows


def _load_child_parts(db, child_id):
    cur = db.cursor()
    try:
        cur.execute("SELECT data FROM part WHERE session_id=? ORDER BY time_created",
                    (child_id,))
    except sqlite3.Error:
        return []
    parts = []
    for (d,) in cur.fetchall():
        try:
            j = json.loads(d)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(j, dict):
            parts.append(j)
    return parts


def _aggregate_reads(agent, tools):
    for tool in tools:
        path = tool.get("brief")
        name = tool.get("name")
        if name == "Read" and path:
            agent["_reads"].append(path)
            agent["_read_sources"].setdefault(path, set()).add("Read")
            if tool.get("rlines"):
                agent["_read_lines"][path] = agent["_read_lines"].get(path, 0) + tool["rlines"]
                agent["_read_iv"].setdefault(path, []).append((tool.get("rstart") or 1, tool["rlines"]))
            else:
                for s0, c0 in (tool.get("_rspans") or []):
                    agent["_read_iv"].setdefault(path, []).append((s0, c0))
                    agent["_read_lines"][path] = agent["_read_lines"].get(path, 0) + c0
            if tool.get("rtotal"):
                agent["_read_total"][path] = max(agent["_read_total"].get(path, 0), tool["rtotal"])
        if name in ("Write", "Edit") and path and tool.get("ok") is not False:
            agent["_writes"].append(path)
            if tool.get("wlines"):
                agent["_write_lines"][path] = agent["_write_lines"].get(path, 0) + tool["wlines"]
            if tool.get("wevent"):
                agent["_write_events"].append((tool.get("ts") or "", path,
                                               tool["wevent"][0], tool["wevent"][1]))
        for probed in tool.get("_probed_paths") or []:
            agent["_probed"].append(probed)
        for event in tool.get("_visible_source_lines") or []:
            p = event["path"]
            agent["_reads"].append(p)
            agent["_read_sources"].setdefault(p, set()).add(event.get("via") or name)
            for start, count in event.get("intervals") or []:
                agent["_read_iv"].setdefault(p, []).append((start, count))
                agent["_read_lines"][p] = agent["_read_lines"].get(p, 0) + count
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    total = sum(1 for _ in f)
            except OSError:
                total = 0
            if total:
                agent["_read_total"][p] = max(agent["_read_total"].get(p, 0), total)


def _stage_of_time(stages, ts):
    if ts:
        for s in stages:
            if s.get("start_ts") and s.get("end_ts") and s["start_ts"] <= ts <= s["end_ts"]:
                return s
        for s in reversed(stages):
            if s.get("start_ts") and ts >= s["start_ts"]:
                return s
    return stages[0]


_TITLE_RE = re.compile(r"^\[([^\]]+)\]\s*(.+)$")


def _parse_title(title):
    """拆子会话 title(如 '[Implement (2 units)] B01实体模型')为 (工作流类型, 单元 label)。"""
    m = _TITLE_RE.match((title or "").strip())
    if not m:
        return "workflow", (title or "").strip()
    head = m.group(1).lower()
    label = m.group(2).strip()
    if head.startswith("explore"):
        return "explore", label
    if head.startswith("implement"):
        return "implement", label
    if head.startswith("verify"):
        return "verify", label
    if "audit" in head or head.startswith("acceptance"):
        return "audit", label
    if head.startswith("fix"):
        return "fix", label
    return head.split()[0] if head else "workflow", label


def _workflow_result_index(workflow_calls):
    """把 workflow 工具的输入(args.units/areas 的 label)与输出(Result JSON 的 summary)
    关联,得到 label -> {summary, ok, run_name, name} 索引,供 DB 子会话回填最终产出与归属。"""
    index = {}
    for entry, output in workflow_calls:
        inp = entry.get("_inp") or {}
        run_name = inp.get("runName") or ""
        name = inp.get("name") or ""
        result = _extract_workflow_result(output)
        if not result:
            continue
        args = inp.get("args")
        id_to_label = {}
        if isinstance(args, dict):
            for kind, key in (("units", "id"), ("areas", "name")):
                items = args.get(kind)
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, dict) and it.get(key) and it.get("label"):
                        id_to_label[it[key]] = it["label"]
        for kind, key in (("units", "id"), ("areas", "area")):
            items = result.get(kind)
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                aid = it.get(key)
                if not aid:
                    continue
                label = id_to_label.get(aid)
                if not label:
                    continue
                index[label] = {
                    "summary": (it.get("summary") or "").strip(),
                    "ok": bool(it.get("ok")),
                    "run_name": run_name,
                    "name": name,
                }
    return index


def _build_db_agents(db, session_id, stages, cwd, model, billing, wf_index):
    children = _load_child_sessions(db, session_id)
    if not children:
        return [], []
    agents = []
    sub_act = []  # 子代理活动区间 [(stage_id, start_ms, end_ms)]
    for ch in children:
        child_parts = _load_child_parts(db, ch["id"])
        tools = []
        child_act = []  # 该子代理自己的活动区间 [(start_ms, end_ms)]
        for i, part in enumerate(child_parts):
            ptype = part.get("type")
            if ptype == "reasoning":
                rt = part.get("time")
                if isinstance(rt, dict) and isinstance(rt.get("start"), (int, float)) \
                        and isinstance(rt.get("end"), (int, float)) and rt["end"] > rt["start"]:
                    child_act.append((float(rt["start"]), float(rt["end"])))
                continue
            tool = _tool_part(part)
            if not tool:
                continue
            name, call_id, inp, output, state = tool
            st = (state or {}).get("time") or {}
            ts = _ms_to_iso(st.get("start")) if isinstance(st.get("start"), (int, float)) else None
            # 工具执行区间:workflow 工具自身不算(它的活是子代理),其余算活动。
            if name.lower() != "workflow" and isinstance(st.get("start"), (int, float)) \
                    and isinstance(st.get("end"), (int, float)) and st["end"] > st["start"]:
                child_act.append((float(st["start"]), float(st["end"])))
            tools.append(_build_tool_entry(i, 0, ts, name, inp, call_id, output, state, cwd))
        tk = ch["tokens"]
        created = _ms_to_iso(ch["created"])
        updated = _ms_to_iso(ch["updated"])
        stage = _stage_of_time(stages, created)
        for s0, s1 in child_act:
            sub_act.append((stage["id"], s0, s1))
        reasoning = tk["reasoning"]
        # 子代理的 output 同样按 text/tool 字符占比拆(工具参数不只主线才有)
        _th, tx, tu = _parts_chars(child_parts)
        _out = tk["output"]
        if tx + tu:
            text = int(round(_out * tx / (tx + tu)))
            tool = max(0, _out - text)
        else:
            text, tool = _out, 0
        # 子代理的 skill 工具调用(对齐 claude.py:名字 -> 次数 + 明细)
        skills = {}
        skill_calls = []
        for t in tools:
            if t["name"] == "Skill" and t.get("skill"):
                sk = t["skill"]
                skills[sk] = skills.get(sk, 0) + 1
                skill_calls.append({"skill": sk, "ts": t.get("ts"),
                                    "ok": t.get("ok"), "dur_ms": t.get("dur_ms")})
        wtype, label = _parse_title(ch["title"])
        info = wf_index.get(label) if wf_index else None
        # 最终产出:优先取子代理 transcript 的末条 text(排除 workflow 注入的 prompt,
        # 以 "Workflow phase:" 开头),退回 workflow 结果 JSON 的 summary(导出里常被截断)。
        _texts = [(p.get("text") or "").strip() for p in child_parts
                  if p.get("type") == "text" and (p.get("text") or "").strip()]
        if _texts and _texts[0].lower().startswith("workflow phase:"):
            _texts = _texts[1:]
        result = _texts[-1] if _texts else ((info or {}).get("summary") or "")
        entry = {
            "agent_id": "subagent:" + ch["id"],
            "type": wtype,
            "desc": ch["title"][:240],
            "wf_run": (info or {}).get("run_name"),
            "wf_name": (info or {}).get("name"),
            "wf_phase": None,
            "tuid": None,
            "stage": stage["stage"], "seg": stage["id"],
            "start_ts": created, "end_ts": updated,
            "dur_ms": common.ms_between(created, updated),
            "output_tokens": tk["output"] + reasoning,
            "tool_uses": len(tools),
            "tool_counts": dict(Counter(t["name"] for t in tools)),
            "status": "completed",
            "aborted": None,
            "model": ch.get("model") or model,
            "result": result[:300],
            "skills": skills, "skill_calls": skill_calls,
            "out_split": {"thinking": reasoning, "text": text, "tool": tool},
            "_prompt": "", "_probed": [], "_reads": [], "_writes": [],
            "_read_lines": {}, "_read_iv": {}, "_read_total": {}, "_read_sources": {},
            "_write_lines": {}, "_write_events": [],
        }
        _aggregate_reads(entry, tools)
        # bill subagent tokens
        key = model or "unknown"
        b = billing.setdefault(key, {"req": 0, "inp": 0, "cread": 0, "cw5": 0, "cw1h": 0, "out": 0})
        b["req"] += 1
        b["inp"] += tk["input"]
        b["cread"] += tk["cache_read"]
        b["cw1h"] += tk["cache_write"]
        b["out"] += tk["output"] + tk["reasoning"]
        agents.append(entry)
    return agents, sub_act


# --------------------------------------------------------------------------- #
# Adapter contract
# --------------------------------------------------------------------------- #

def default_root():
    for var in ("DEVECO_DATA_DIR", "OPENCODE_DATA_DIR"):
        v = os.environ.get(var)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), ".local", "share", "deveco")


def session_summary(path):
    # Cheap pre-check: a DevEco export is one JSON object whose top level holds
    # both "info" and "messages".  Bail after a small head read so broad
    # iter_sessions() scans never fully parse unrelated files (raw tool
    # outputs, Claude/Codex JSONL, etc.).
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            head = stream.read(8192)
    except OSError:
        return None
    if '"info"' not in head or '"messages"' not in head:
        return None
    data = _read_export(path)
    if not isinstance(data, dict):
        return None
    info = data.get("info")
    if not isinstance(info, dict) or not info.get("id") or not isinstance(data.get("messages"), list):
        return None
    t = info.get("time") or {}
    return {
        "id": info.get("id"), "session_id": info.get("id"),
        "title": info.get("title"),
        "cwd": info.get("directory") or info.get("path"),
        "version": info.get("version"),
        "created": t.get("created"), "updated": t.get("updated"),
    }


def is_session(path):
    if not isinstance(path, str):
        return False
    if os.path.isfile(path):
        return session_summary(path) is not None
    # 裸 session id:ses_ 前缀是 DevEco 会话 id 的唯一格式(Claude/Codex 用 hex)。
    # 这里只做格式识别;是否真实存在交给 extract_from_db 校验(它持有 --deveco-db 指定的库),
    # 这样指定自定义 db 路径时 detect 也能正确识别为 DevEco。
    return bool(_SESSION_ID_RE.match(path))


def iter_sessions(root):
    # 1) 数据库顶层会话(主源):能覆盖尚未导出的会话;path 直接给 session id,
    #    下游 extract() 据此走 extract_from_db。size 用 message/part 数据长度粗略估计。
    db_sids = set()
    db = _find_db(root)
    if db:
        conn = _open_db(db)
        if conn is not None:
            try:
                rows = conn.execute(
                    "SELECT s.id, s.directory, s.time_updated, "
                    "(SELECT COALESCE(SUM(LENGTH(data)),0) FROM message m WHERE m.session_id=s.id) "
                    "+ (SELECT COALESCE(SUM(LENGTH(data)),0) FROM part p WHERE p.session_id=s.id) "
                    "FROM session s WHERE s.parent_id IS NULL ORDER BY s.time_updated DESC"
                ).fetchall()
            except sqlite3.Error:
                rows = []
            finally:
                conn.close()
            for sid, directory, updated, size in rows:
                db_sids.add(sid)
                project = os.path.basename((directory or "deveco-session").rstrip("\\/")) \
                    or "deveco-session"
                yield SessionCandidate(
                    mtime=(updated or 0) / 1000.0, path=sid, project=project,
                    size=size or 0, format=FORMAT, session_id=sid,
                )

    # 2) 导出文件(补充):仅列出数据库中没有的会话(如外部分享的导出),避免同一会话重复。
    if not root or not os.path.isdir(root):
        return
    candidates = []
    candidates += glob.glob(os.path.join(root, "tool-output", "*"))
    candidates += glob.glob(os.path.join(root, "**", "ses_*.json"), recursive=True)
    candidates += glob.glob(os.path.join(root, "**", "*export*.json"), recursive=True)
    for path in sorted(set(candidates)):
        summary = session_summary(path)
        if not summary or summary.get("id") in db_sids:
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        project = os.path.basename((summary.get("cwd") or "deveco-session").rstrip("\\/")) \
            or "deveco-session"
        yield SessionCandidate(
            mtime=stat.st_mtime, path=path, project=project,
            size=stat.st_size, format=FORMAT,
            session_id=summary.get("id") or "",
        )


def _load_export(path):
    data = _read_export(path)
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict) \
            or not isinstance(data.get("messages"), list):
        raise ValueError("not a DevEco/opencode session export: %s" % path)
    return data


def extract(path, storage_root=None):
    # 裸 session id(非文件路径)直接读 SQLite 还原,无需先导出;文件路径仍走自包含
    # export(向后兼容,例如他人分享的导出文件)。
    if isinstance(path, str) and not os.path.isfile(path) and _SESSION_ID_RE.match(path):
        return extract_from_db(path, storage_root=storage_root)
    return _parse(_load_export(path), storage_root=storage_root,
                  source_file=os.path.abspath(path))


def extract_from_db(session_id, storage_root=None):
    """仅凭 session id 从 deveco.db 还原并解析;结果是官方 export 的超集(重叠部分一致)。"""
    db_path = _find_db(storage_root)
    if not db_path:
        raise ValueError(
            "找不到 DevEco 数据库(可用 DEVECO_DATA_DIR / OPENCODE_DATA_DIR 环境变量或 "
            "--deveco-db 指定),无法按 session id 分析: %s" % session_id)
    db = _open_db(db_path)
    if db is None:
        raise ValueError("无法以只读方式打开 DevEco 数据库: %s" % db_path)
    try:
        data = _load_session_from_db(db, session_id)
    finally:
        db.close()
    return _parse(data, storage_root=db_path,
                  source_file="deveco.db:" + session_id)


def _parse(data, storage_root=None, source_file=None):
    info = data["info"]
    messages = data["messages"]
    session_id = info.get("id")
    cwd = info.get("directory") or info.get("path")
    model = _session_model(info)

    def sort_key(m):
        mi = m.get("info") or {}
        return ((mi.get("time") or {}).get("created") or 0, mi.get("id") or "")

    messages = sorted(messages, key=sort_key)
    for i, m in enumerate(messages):
        m["_idx"] = i

    tools, prompts = [], []
    prompt_skills = []  # [(message idx, 管线技能名)]:/<skill> 命令展开成的 user 消息
    workflow_calls = []
    billing, context_timeline = {}, []
    text_chars = tool_chars = reasoning_tokens = main_out = 0
    first_num = last_num = None
    main_act = []  # 主代理活动区间 [(消息 idx, start_ms, end_ms)]

    for m in messages:
        mi = m.get("info") or {}
        parts = m.get("parts") or []
        t = mi.get("time") or {}
        created_num, completed_num = _to_num(t.get("created")), _to_num(t.get("completed"))
        if created_num is not None and (first_num is None or created_num < first_num):
            first_num = created_num
        # ended_at 取每个消息 completed(缺省退回 created)的最大值,对齐 claude「所有
        # 时间戳的最大值」语义;否则遇到只有 created 的记录(如 user 消息)会被漏掉,
        # 极端情况下(全无 completed)ended_at 会变成空、duration 也随之变空。
        end_num = completed_num if completed_num is not None else created_num
        if end_num is not None and (last_num is None or end_num > last_num):
            last_num = end_num
        ts = _ms_to_iso(t.get("created"))
        if cwd is None and isinstance(mi.get("path"), dict):
            cwd = mi["path"].get("cwd")
        if model is None:
            model = _message_model(mi)

        if mi.get("role") == "user":
            # 对应 Claude 的 promptSource=="typed":opencode/DevEco 没有该字段,user 消息
            # 即人键入(tool_result/通知不以 user 消息出现)。唯一要排除的是压缩/分叉
            # 摘要(summary 被填了 title/body),据此对齐 Claude 的 typed 语义。
            summary = mi.get("summary")
            if isinstance(summary, dict) and (summary.get("title") or summary.get("body")):
                continue
            txt = _user_prompt(parts)
            if txt.strip():
                prompts.append({"idx": m["_idx"], "ts": ts, "wait_ms": 0,
                                "text": " ".join(txt.split())[:400]})
                skill = _prompt_skill(txt)
                if skill:
                    prompt_skills.append((m["_idx"], skill))
            continue

        # assistant
        if not mi.get("error"):
            # 中断/错误消息不是真实 LLM 请求(对齐 claude 的 <synthetic> 跳过),
            # 不进 usage/字符统计/上下文曲线;其 tool 部分仍提取(可能含未完成的中断工具调用)。
            th, tx, tu = _parts_chars(parts)
            text_chars += tx
            tool_chars += tu
            tk = mi.get("tokens") or {}
            reasoning_tokens += tk.get("reasoning") or 0
            main_out += tk.get("output") or 0
            _accumulate_usage(billing, context_timeline, mi, model)

        for part in parts:
            ptype = part.get("type")
            # 思考活动区间:reasoning part 自带 time{start,end},是"真正思考"的时长
            # (区别于消息 created->completed,后者会被 API 卡顿/排队撑大)。
            if ptype == "reasoning":
                rt = part.get("time")
                if isinstance(rt, dict) and isinstance(rt.get("start"), (int, float)) \
                        and isinstance(rt.get("end"), (int, float)) and rt["end"] > rt["start"]:
                    main_act.append((m["_idx"], float(rt["start"]), float(rt["end"])))
                continue
            tool = _tool_part(part)
            if not tool:
                continue
            name, call_id, inp, output, state = tool
            entry = _build_tool_entry(
                len(tools), m["_idx"], ts, name, inp, call_id, output, state, cwd)
            if entry["name"] == "Workflow":
                workflow_calls.append((entry, output))
            else:
                # 工具执行区间:workflow 工具自身不算(它的活是子代理),其余工具算活动。
                st = (state or {}).get("time") or {}
                if isinstance(st.get("start"), (int, float)) \
                        and isinstance(st.get("end"), (int, float)) and st["end"] > st["start"]:
                    main_act.append((m["_idx"], float(st["start"]), float(st["end"])))
            tools.append(entry)

    # ---- stages ----
    max_idx = len(messages) - 1
    boundaries = _stage_boundaries(tools, prompt_skills)
    points = []
    for m in messages:
        n = _to_num(((m.get("info") or {}).get("time") or {}).get("created"))
        if n is not None:
            points.append((m["_idx"], n))
    stages = _build_stages(boundaries, points, max_idx)

    for t in tools:
        s = _stage_of_idx(stages, t["idx"])
        t["stage"] = s["stage"]
        t["seg"] = s["id"]
        s["tool_counts"][t["name"]] = s["tool_counts"].get(t["name"], 0) + 1
        if t["name"] in ("Write", "Edit") and t.get("brief") and t["brief"] not in s["artifacts"]:
            s["artifacts"].append(t["brief"])
        if t["name"] == "Skill" and t.get("skill") \
                and (t["skill"] or "").split(":")[-1] not in common.PIPELINE_SKILLS:
            s["helper_skills"].append({"idx": t["idx"], "ts": t["ts"], "skill": t["skill"]})
    for p in prompts:
        s = _stage_of_idx(stages, p["idx"])
        p["stage"] = s["stage"]
        p["seg"] = s["id"]
        s["prompt_idxs"].append(p["idx"])

    for m in messages:
        mi = m.get("info") or {}
        if mi.get("role") != "assistant":
            continue
        s = _stage_of_idx(stages, m["_idx"])
        tk = mi.get("tokens") or {}
        # output + reasoning:与 main_output_tokens(= main_out + reasoning)同口径,
        # 否则各阶段 output 之和会对不上顶部的「Output Tokens(主线)」。
        s["output_tokens"] += (tk.get("output") or 0) + (tk.get("reasoning") or 0)
        s["cache_read_tokens"] += (tk.get("cache") or {}).get("read") or 0

    # ---- subagents: prefer SQLite child sessions (tokens + read/write detail);
    #      fall back to the export's workflow result JSON when no DB is present.
    wf_index = _workflow_result_index(workflow_calls)
    agents = []
    sub_act = []  # 子代理活动区间 [(stage_id, start_ms, end_ms)]
    db_path = _find_db(storage_root)
    if db_path:
        db = _open_db(db_path)
        if db is not None:
            try:
                agents, sub_act = _build_db_agents(db, session_id, stages, cwd, model, billing, wf_index)
            except Exception:
                agents, sub_act = [], []
            finally:
                db.close()
    if not agents:
        agents = _build_workflow_agents(workflow_calls, model)
        # 无 DB 兜底:子代理只有 workflow 结果里的 ts/dur,用它粗估活动区间。
        for a in agents:
            st = _iso_ms(a.get("start_ts"))
            if st is not None and a.get("dur_ms"):
                sub_act.append((a.get("seg"), st, st + a["dur_ms"]))
    for a in agents:
        for s in stages:
            if s["id"] == a["seg"]:
                s["agent_count"] += 1
                break

    # ---- 失败信号:"Workflow aborted" → aborted ----
    _mark_aborted(agents, workflow_calls)

    # ---- 有效活动时间 = (主代理 reasoning ∪ tool) ∪ (子代理 reasoning ∪ tool) 的并集 ----
    # 自底向上:凡是没有代理在"思考"或"动手"的时间(等待用户/API 卡顿/编排空档)都不算
    # 活跃;workflow 工具自身不算(它的活就是子代理)。等待用户不再单列,并入非活跃。
    main_act_resolved = []
    for m_idx, s0, s1 in main_act:
        stg = _stage_of_idx(stages, m_idx)
        main_act_resolved.append((stg["id"], s0, s1))
    all_act = main_act_resolved + sub_act
    merged_global, global_active = _union_ms([(s0, s1) for _, s0, s1 in all_act])
    for s in stages:
        ivs = [(s0, s1) for sid, s0, s1 in all_act if sid == s["id"]]
        merged, act = _union_ms(ivs)
        s["active_ms"] = act

    # ---- 阶段墙钟/甘特轴并入真实起止 ----
    # DevEco 的子代理活在 SQLite 子会话、不在主线 messages;纯派发的 workflow 阶段
    # (如 reaudit)主线只有一条派发消息,start_idx==end_idx → start_ts==end_ts,墙钟
    # 算成 0、甘特轴退化成一个点,而其子代理实际跑了好几分钟。这里用「该阶段子代理
    # 的 start_ts/end_ts ∪ 主线 reasoning/tool 活动」把墙钟与甘特轴扩到真实跨度
    # (子代理 assignment 已定、主线活动按 msg idx 归属,只扩区间不改归属)。注意甘特
    # 条画的是子代理的 start_ts/end_ts,故用这两个而非 sub_act 活动区间(后者不含
    # 收尾空转,会偏短、把最后一根甘特条裁到轴外)。
    for s in stages:
        ivs = [(s0, s1) for sid, s0, s1 in main_act_resolved if sid == s["id"]]
        for a in agents:
            if a.get("seg") == s["id"]:
                st, en = _iso_ms(a.get("start_ts")), _iso_ms(a.get("end_ts"))
                if st is not None and en is not None:
                    ivs.append((st, en))
        if not ivs:
            continue
        lo = min(s0 for s0, _ in ivs)
        hi = max(s1 for _, s1 in ivs)
        cur_lo = _iso_ms(s["start_ts"]) if s.get("start_ts") else None
        cur_hi = _iso_ms(s["end_ts"]) if s.get("end_ts") else None
        if cur_lo is None or lo < cur_lo:
            s["start_ts"] = _ms_to_iso(lo)
        if cur_hi is None or hi > cur_hi:
            s["end_ts"] = _ms_to_iso(hi)
        s["duration_ms"] = common.ms_between(s["start_ts"], s["end_ts"])

    # ---- lineage:反推鸿蒙目标根作为 cwd,让工作区内的 Android 源码重新成为
    #      cwd 之外的绝对路径(否则落入"工程内读取"而非"Android 参考")。
    write_paths = []
    for a in agents:
        write_paths.extend(a.get("_writes") or [])
    for t in tools:
        if t["name"] in ("Write", "Edit") and t.get("brief"):
            write_paths.append(t["brief"])
    target_root = _find_harmony_root(write_paths)
    # DevEco 工作流的分析/契约文档放在 .deveco/workflows/**/*.md,而 common._spec_kind
    # 只认 spec/ 与 .migration/analysis/;这里临时扩一个 DevEco 专属口径,让这些文档
    # 进入血缘的 Spec 列(否则 Spec 产出恒空)。
    _orig_spec_kind = common._spec_kind

    def _deveco_spec_kind(rel):
        k = _orig_spec_kind(rel)
        if k:
            return k
        low = (rel or "").lower()
        # rel 可能是相对路径(.deveco/workflows/...)或绝对路径(工程内但不在 lineage cwd 下),
        # 统一用子串匹配 ".deveco/workflows/"。
        if ".deveco/workflows/" in low and low.endswith(".md") \
                and not low.endswith(".run.md"):
            if "/explore/" in low:
                return "analysis"
            if low.endswith("plan.md"):
                return "plan"
            return "shared"
        return None

    common._spec_kind = _deveco_spec_kind
    lineage = common.build_lineage(agents, tools, target_root or cwd)
    common._spec_kind = _orig_spec_kind
    if lineage and target_root:
        lineage["cwd"] = cwd  # 分类用 target_root,血缘展示仍用迁移工作区 cwd

    # ---- 压缩标记:等价于 Claude 的 compact_boundary。opencode 没有该系统记录,
    #      用消息的 summary 字段(压缩/分叉摘要)作为压缩信号。
    markers = []
    for m in messages:
        mi = m.get("info") or {}
        summary = mi.get("summary")
        if summary is True or (isinstance(summary, dict)
                               and (summary.get("title") or summary.get("body"))):
            markers.append({
                "idx": m.get("_idx"),
                "ts": _ms_to_iso((mi.get("time") or {}).get("created")),
                "kind": "compact",
            })

    # ---- workflow 运行元数据(等价于 Claude 的 wf_*.json)----
    workflows = _build_workflows(workflow_calls, agents)

    # ---- totals ----
    split = {"thinking": int(reasoning_tokens), "text": 0, "tool": 0}
    # 正确口径:reasoning 与 output 是独立加法桶(total = input + output +
    # reasoning + cache),「正文 + 工具参数」就是 output 本身,不要再扣 reasoning。
    remaining = max(0, main_out)
    if text_chars + tool_chars:
        split["text"] = int(round(remaining * text_chars / (text_chars + tool_chars)))
        split["tool"] = max(0, remaining - split["text"])
    else:
        split["text"] = remaining
    for a in agents:
        os_ = a.get("out_split") or {}
        split["thinking"] += os_.get("thinking", 0)
        split["text"] += os_.get("text", 0)
        split["tool"] += os_.get("tool", 0)

    started_at = _ms_to_iso(first_num)
    ended_at = _ms_to_iso(last_num)
    duration = common.ms_between(started_at, ended_at)

    meta = {
        "source_file": source_file,
        "schema_version": "deveco-1.0",
        "session_format": "deveco",
        "session_id": session_id,
        "cc_version": info.get("version"),
        "cwd": cwd,
        "model": model,
        "started_at": started_at,
        "ended_at": ended_at,
        "record_count": len(messages),
    }
    totals = {
        "duration_ms": duration,
        "active_ms": global_active,
        "tool_calls": len(tools),
        "agent_calls": len(agents),
        "subagent_transcripts": len(agents),
        "main_output_tokens": main_out + reasoning_tokens,
        "subagent_output_tokens": sum(a["output_tokens"] for a in agents),
        "aborted_agents": sum(1 for a in agents if a.get("aborted")),
        "waste_output_tokens": sum(a["output_tokens"] for a in agents if a.get("aborted")),
        "output_split": {k: int(v) for k, v in split.items()},
        "user_prompts": len(prompts),
        "files_touched": len({t.get("brief") for t in tools
                              if t["name"] in ("Write", "Edit") and t.get("brief")}),
        "compactions": len(markers),
    }

    # strip lineage-only temp fields
    for t in tools:
        t.pop("_inp", None)
        t.pop("_visible_source_lines", None)
        t.pop("_probed_paths", None)
    for a in agents:
        for key in ("_prompt", "_reads", "_writes", "_read_lines", "_write_lines",
                    "_read_iv", "_read_total", "_read_sources", "_write_events", "_probed"):
            a.pop(key, None)

    return {"meta": meta, "totals": totals, "stages": stages,
            "tools": tools, "agents": agents, "prompts": prompts, "markers": markers,
            "context_timeline": context_timeline, "billing": billing,
            "lineage": lineage, "workflows": workflows,
            "activity_intervals": [[_ms_to_iso(s0), _ms_to_iso(s1)] for s0, s1 in merged_global]}


# --------------------------------------------------------------------------- #
# Standalone CLI (no changes to cli.py / registry required)
# --------------------------------------------------------------------------- #

def _resolve(target, root):
    if os.path.isfile(target):
        return target
    rows = sorted(iter_sessions(root), key=lambda r: r.mtime, reverse=True)
    by_sid = [r.path for r in rows if r.session_id.startswith(target)]
    if len(by_sid) == 1:
        return by_sid[0]
    if len(by_sid) > 1:
        sys.exit("session-id 前缀不唯一,命中 %d 个,请给更长前缀" % len(by_sid))
    low = target.lower()
    by_proj = [r.path for r in rows if low in r.project.lower()]
    if by_proj:
        return by_proj[0]
    sys.exit("找不到匹配 %r 的 DevEco session 导出" % target)


def main():
    ap = argparse.ArgumentParser(
        prog="migloop.adapters.deveco",
        description="DevEco Code (opencode) 会话导出 -> MigLoop trace")
    ap.add_argument("target", nargs="?",
                    help="导出文件路径 | session-id 前缀 | 项目名片段")
    ap.add_argument("--list", action="store_true", help="列出最近的 DevEco session")
    ap.add_argument("--root", default=None, help="DevEco 数据目录覆盖(默认 ~/.local/share/deveco)")
    ap.add_argument("--out", default=None, help="输出 trace JSON 路径")
    args = ap.parse_args()

    root = args.root or default_root()
    if args.list or not args.target:
        rows = sorted(iter_sessions(root), key=lambda r: r.mtime, reverse=True)
        if not rows:
            print("未在 %s 找到 DevEco session 导出" % root)
            return
        print("最近的 DevEco session:\n")
        for r in rows[:20]:
            t = datetime.fromtimestamp(r.mtime).strftime("%m-%d %H:%M")
            print("  %-24s %-14s %8.1fK  %s" %
                  (r.project[:24], r.session_id[:14], r.size / 1024, t))
        return

    path = _resolve(args.target, root)
    data = extract(path, storage_root=root)
    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "trace-%s.json" % (data["meta"]["session_id"] or "deveco")[:8])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    m, t = data["meta"], data["totals"]
    print("session   %s  (deveco %s, %s)" % (m["session_id"], m.get("cc_version"), m["model"]))
    print("time      %s -> %s  (%.1f h)" % (m["started_at"], m["ended_at"],
                                            (t["duration_ms"] or 0) / 3600000))
    print("records   %d  tool_calls %d  subagents %d" %
          (m["record_count"], t["tool_calls"], t["subagent_transcripts"]))
    print("tokens    main-out %d  reasoning %d" %
          (t["main_output_tokens"], t["output_split"]["thinking"]))
    print("stages:")
    for s in data["stages"]:
        n_tools = sum(s["tool_counts"].values())
        print("  %-18s idx %4d-%-4d %6.0f min  tools %3d  out %8d" %
              (s["label"], s["start_idx"], s["end_idx"],
               (s["duration_ms"] or 0) / 60000, n_tools, s["output_tokens"]))
    print("\nwritten -> %s" % out)


if __name__ == "__main__":
    main()
