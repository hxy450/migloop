"""阶段切分的统一口径:所有 adapter 与 live 共用,各家只负责把原始记录翻译成信号。

用户定的四条(2026-11-24):

1. **阶段信号**。有 mark-stage(``.migbot/metrics/*/facts/stage-marks.json``,或转录里的
   ``a2h mark-stage <阶段>`` 调用)就只按它切:管线阶段的 mark 打在阶段**结束**时,
   init / ecat-refine 打在**开始**时。没有 mark 才用 skill 调用(含归属戳、斜杠命令)或
   读 SKILL.md,一段至少 ``MIN_SPAN_S`` 秒,短于它不切。缺的阶段不补推断(审计里标「未见」)。
   既没有 mark、也没跑过管线 skill 的会话整段一个 Session。
2. **后续轮**。最后一个管线阶段结束后,从第一条人工输入起单独成段(``TRAILING``),
   不算进最后一个管线阶段。
3. **Workflow**。管线阶段里发起的 Workflow 是该阶段的子段,段尾取 workflow 实际结束时刻,
   之后回到外层阶段;不在任何管线阶段里的才算顶层段。
4. **人工输入** = 人打的文字 + 斜杠命令;SDK / 驱动程序下发的指令记 ``PROGRAM``,不算人工。

时刻一律是 epoch 秒(float);各家转换好再交进来。``segment`` 只吃信号,不读文件。
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PIPELINE = {"a2h-run", "a2h-init", "a2h-build", "mig-arch", "a2h-arch-scaffold",
            "a2h-spec", "a2h-plan", "a2h-execute", "a2h-verify", "a2h-retrospect",
            "arkts-visual-verify", "ecat-refine"}

#: 一段至少多少秒才切(只管 skill / SKILL.md 信号;mark 是权威,不过滤)
MIN_SPAN_S = 90.0
#: 管线阶段在**收尾**时调 ``a2h mark-stage``;其余(a2h-init、ecat-refine 等)在开始时打
END_MARK_STAGES = frozenset({"a2h-spec", "a2h-plan", "a2h-execute", "a2h-verify", "a2h-retrospect", "a2h-build"})
#: a2h 主流水线的规范先后 —— 审计「未见 a2h-plan」只在这条线上找缺口
CANON_PIPELINE = ("a2h-spec", "a2h-plan", "a2h-execute", "a2h-verify", "a2h-retrospect")

SETUP = "setup"
SESSION = "session"
TRAILING = "after-pipeline"
HUMAN = "human"
PROGRAM = "program"

_MARK_CALL = re.compile(r"\ba2h(?:\.exe)?\s+mark-stage\s+([a-z0-9_-]+)")
_COMMAND = re.compile(r"<command-name>\s*/?([^<]+)</command-name>")


def normalize(value: Any) -> Optional[str]:
    name = str(value or "").split(":")[-1]
    if name.endswith("-zh"):
        name = name[:-3]
    return name if name in PIPELINE else None


def is_pipeline_stage(stage: Any) -> bool:
    return str(stage or "") in PIPELINE


def mark_calls(text: Any) -> List[str]:
    """一段命令文本里 ``a2h mark-stage <阶段>`` 调用的阶段名(已归一,认不出的丢掉)。"""
    out = []
    for name in _MARK_CALL.findall(str(text or "")):
        stage = normalize(name)
        if stage:
            out.append(stage)
    return out


def iso_seconds(ts: Any) -> Optional[float]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ── Claude 记录 → 信号(live 与离线共用) ───────────────────────────────────────

def claude_boundaries(records: Sequence[Dict[str, Any]], calls: Iterable[Tuple[Any, ...]]) -> List[Tuple[int, str]]:
    """Claude 转录的 skill 信号:显式 Skill 调用、归属戳切换、斜杠命令。``calls`` 是
    ``(idx, ts, skill, tool_use_id)``。同坐标显式调用优先;陈旧的归属戳不会弹回。"""
    explicit = {}
    for idx, _, skill, _ in calls:
        if normalize(skill):
            explicit[idx] = normalize(skill)
    boundaries, current, last_attr = [], None, None
    for idx, record in enumerate(records):
        attr = normalize(record.get("attributionSkill"))
        changed_attr = attr and attr != last_attr
        if attr:
            last_attr = attr
        candidate = explicit.get(idx) or (attr if changed_attr else None)
        if candidate is None and record.get("type") == "user":
            candidate = command_stage((record.get("message") or {}).get("content"))
        if candidate and candidate != current:
            boundaries.append((idx, candidate))
            current = candidate
    return boundaries


def command_stage(content: Any) -> Optional[str]:
    """``<command-name>/a2h-spec</command-name>`` 这类斜杠命令进入的管线阶段。"""
    if not isinstance(content, str):
        return None
    match = _COMMAND.search(content)
    return normalize(match[1].strip()) if match else None


# ── stage-marks.json ─────────────────────────────────────────────────────────

def marks_from_doc(doc: Any) -> List[Tuple[float, str]]:
    """两种形状都收:Go 运行时 stage-marks.json 的 [{stage, ts}],导出包的 [[ts, stage]]。"""
    marks = doc.get("marks") if isinstance(doc, dict) else doc
    rows: List[Tuple[float, str]] = []
    for m in marks if isinstance(marks, list) else []:
        if isinstance(m, dict):
            ts, stage = m.get("ts"), m.get("stage")
        elif isinstance(m, (list, tuple)) and len(m) >= 2:
            ts, stage = m[0], m[1]
        else:
            continue
        t = iso_seconds(ts) if isinstance(ts, str) else (float(ts) if isinstance(ts, (int, float)) else None)
        name = normalize(stage)
        if t is not None and name:
            rows.append((t, name))
    rows.sort()
    return rows


def find_stage_marks(transcript: str, cwd: Optional[str], first_t: Optional[float]) -> List[Tuple[float, str]]:
    """本会话的 run 级 mark:``<cwd>/.migbot/metrics/*/facts/stage-marks.json`` 或转录同目录的
    ``stage-marks.json``。多份时取起点不晚于本会话首条记录的最新那份,都晚于则取最早那份。
    只读这几份小 JSON,不碰转录。"""
    cands: List[str] = []
    if cwd:
        cands += glob.glob(os.path.join(cwd, ".migbot", "metrics", "*", "facts", "stage-marks.json"))
    cands += glob.glob(os.path.join(os.path.dirname(os.path.abspath(transcript)), "stage-marks.json"))
    best: Optional[Tuple[float, List[Tuple[float, str]]]] = None
    fallback: Optional[Tuple[float, List[Tuple[float, str]]]] = None
    for p in cands:
        try:
            with open(p, encoding="utf-8") as fh:
                rows = marks_from_doc(json.load(fh))
        except (OSError, ValueError):
            continue
        if not rows:
            continue
        start = rows[0][0]
        if first_t is not None and start <= first_t + 1 and (best is None or start > best[0]):
            best = (start, rows)
        if fallback is None or start < fallback[0]:
            fallback = (start, rows)
    return (best or fallback or (0.0, []))[1]


# ── 切分 ─────────────────────────────────────────────────────────────────────

class _Clock:
    """记录下标 ↔ 时刻。转录时刻不严格递增(并行完成通知乱序落盘),按前缀最大值单调化。"""

    def __init__(self, points: Sequence[Tuple[int, Optional[float]]]):
        self.idxs = [i for i, _ in points]
        run, mono = None, []
        for _, t in points:
            if t is not None and (run is None or t > run):
                run = t
            mono.append(run)
        first = next((t for t in mono if t is not None), None)
        self.mono = [first if t is None else t for t in mono] if first is not None else [0.0] * len(mono)
        self.end = self.mono[-1] if self.mono else 0.0

    def time_at(self, idx: int) -> float:
        k = bisect.bisect_right(self.idxs, idx) - 1
        return self.mono[max(k, 0)] if self.mono else 0.0

    def first_after(self, t: float) -> Optional[int]:
        """时刻晚于 t 的第一条记录下标。"""
        k = bisect.bisect_right(self.mono, t)
        return self.idxs[k] if k < len(self.idxs) else None

    def first_at_or_after(self, t: float) -> Optional[int]:
        k = bisect.bisect_left(self.mono, t)
        return self.idxs[k] if k < len(self.idxs) else None

    def last_at_or_before(self, t: float) -> Optional[int]:
        k = bisect.bisect_right(self.mono, t) - 1
        return self.idxs[k] if k >= 0 else None


def _from_marks(clock: _Clock, marks: Sequence[Tuple[float, str]], signals: Sequence[Tuple[int, str]]
                ) -> Tuple[List[Tuple[int, str, str]], Optional[int]]:
    """mark → [(起始下标, 阶段, 'mark')] 与最后一个管线阶段的收尾下标。
    结束 mark 的阶段占 (上一 mark, 本 mark];起始 mark 的阶段从 mark 起。起始 mark 后面紧跟
    别的阶段的结束 mark 时(a2h-init 只有几秒),那一段归结束 mark 的阶段。最后一个 mark 之后
    的尾巴:之后有别的阶段的 skill 信号就按它命名(那个阶段还没打收尾 mark),否则归最后一段。"""
    rows = sorted(marks)
    out: List[Tuple[int, str, str]] = []
    cursor: Optional[int] = clock.idxs[0] if clock.idxs else None
    last_end_t: Optional[float] = None
    for k, (t, st) in enumerate(rows):
        nxt = rows[k + 1] if k + 1 < len(rows) else None
        if st in END_MARK_STAGES:
            if cursor is not None and (not out or out[-1][1] != st):
                out.append((cursor, st, "mark"))
            cursor = clock.first_after(t)
            last_end_t = t
        elif nxt is not None and nxt[1] in END_MARK_STAGES:
            cursor = clock.first_at_or_after(t)
        else:
            start = clock.first_at_or_after(t)
            if start is not None and (not out or out[-1][1] != st):
                if out and out[-1][0] == start:
                    out[-1] = (start, st, "mark")
                else:
                    out.append((start, st, "mark"))
            cursor = None
            last_end_t = None
    # 起始 mark 之前若还有记录,归 setup(由调用方补);首个结束 mark 的阶段从会话开头算起
    if cursor is not None and out:
        marked = {st for _, st in rows}
        later = [(i, s) for i, s in signals if i >= cursor and s not in marked]
        if later:
            # 还没打收尾 mark 的阶段:它没「结束」,不切后续轮
            out.append((cursor, later[0][1], "skill"))
            return out, None
    end_idx = clock.last_at_or_before(last_end_t) if last_end_t is not None else None
    return out, end_idx


def _dedupe(bounds: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for b in bounds:
        if not out or out[-1][1] != b[1]:
            out.append(b)
    return out


def _from_signals(clock: _Clock, signals: Sequence[Tuple[int, str]], min_span: float
                  ) -> List[Tuple[int, str, str]]:
    """短于下限的段(浏览 / 预读 / 回头翻一眼又切走)不切:每次去掉最短的那段、并回前一段,
    相邻同名合并后再看,直到都够长。第一段太短就整段不算(归 setup)。"""
    bounds = _dedupe(sorted(signals, key=lambda x: x[0]))

    def spans() -> List[float]:
        return [(clock.time_at(bounds[k + 1][0]) if k + 1 < len(bounds) else clock.end) - clock.time_at(idx)
                for k, (idx, _) in enumerate(bounds)]

    while len(bounds) > 1:
        lengths = spans()
        short = [k for k in range(1, len(bounds)) if lengths[k] < min_span]
        if not short:
            break
        k = min(short, key=lambda j: (lengths[j], j))
        bounds = _dedupe(bounds[:k] + bounds[k + 1:])
    if bounds and spans()[0] < min_span:
        bounds = bounds[1:]
    return [(idx, st, "skill") for idx, st in bounds]


def segment(points: Sequence[Tuple[int, Optional[float]]], *,
            marks: Sequence[Tuple[float, str]] = (),
            signals: Sequence[Tuple[int, str]] = (),
            human: Sequence[int] = (),
            workflows: Sequence[Dict[str, Any]] = (),
            last_pipeline_idx: Optional[int] = None,
            min_span: float = MIN_SPAN_S) -> List[Dict[str, Any]]:
    """按四条口径切段。``points`` 是全部记录的 (下标, 时刻),下标递增;``signals`` 是已归一的
    (下标, 阶段);``human`` 是人工输入的下标;``workflows`` 是 {idx: 发起下标, end: 结束时刻,
    key: 段名}。返回 [{start_idx, end_idx, stage, signal, parent}]:parent 为 None 的是顶层段,
    彼此相接、覆盖全部记录;子段(管线阶段里的 Workflow)的 parent 是所在顶层段的序号,
    另带 ``start_t`` / ``end_t``(发起与实际结束时刻)。"""
    if not points:
        return []
    clock = _Clock(points)
    first_idx, last_idx = clock.idxs[0], clock.idxs[-1]
    if marks:
        bounds, pipe_end = _from_marks(clock, marks, signals)
    else:
        bounds = _from_signals(clock, signals, min_span)
        pipe_end = last_pipeline_idx if last_pipeline_idx is not None else (
            max((i for i, _ in signals), default=None) if bounds else None)
    if bounds and pipe_end is not None:
        trailing = next((h for h in sorted(human) if h > pipe_end and h > bounds[-1][0]), None)
        if trailing is not None:
            bounds.append((trailing, TRAILING, "rule"))
    if not bounds:
        bounds = [(first_idx, SESSION, "none")]
    elif bounds[0][0] > first_idx:
        bounds.insert(0, (first_idx, SETUP, "none"))
    top: List[Dict[str, Any]] = []
    for k, (idx, st, sig) in enumerate(bounds):
        end = bounds[k + 1][0] - 1 if k + 1 < len(bounds) else last_idx
        if top and top[-1]["start_idx"] == idx:
            continue
        top.append({"start_idx": idx, "end_idx": end, "stage": st, "signal": sig, "parent": None})
    children: List[Dict[str, Any]] = []
    for wf in sorted(workflows, key=lambda w: w["idx"]):
        pos = next((k for k in range(len(top) - 1, -1, -1) if top[k]["start_idx"] <= wf["idx"]), 0)
        seg = top[pos]
        end_t = wf.get("end")
        if is_pipeline_stage(seg["stage"]):
            children.append({"parent_seg": seg, "start_idx": wf["idx"], "stage": "wf:" + wf["key"],
                             "signal": "workflow", "start_t": clock.time_at(wf["idx"]), "end_t": end_t})
            continue
        wf_end = clock.last_at_or_before(end_t) if end_t is not None else None
        wf_end = seg["end_idx"] if wf_end is None else max(min(wf_end, seg["end_idx"]), wf["idx"])
        pieces = []
        if wf["idx"] > seg["start_idx"]:
            pieces.append({**seg, "end_idx": wf["idx"] - 1})
        pieces.append({"start_idx": wf["idx"], "end_idx": wf_end, "stage": "wf:" + wf["key"],
                       "signal": "workflow", "parent": None, "end_t": end_t})
        if wf_end < seg["end_idx"]:
            pieces.append({**seg, "start_idx": wf_end + 1})
        top[pos:pos + 1] = pieces
    out = list(top)
    for ch in children:
        parent_pos = next(k for k, s in enumerate(top) if s is ch["parent_seg"])
        ch = {k: v for k, v in ch.items() if k != "parent_seg"}
        parent_end = top[parent_pos]["end_idx"]
        last = clock.last_at_or_before(ch["end_t"]) if ch["end_t"] is not None else None
        ch["end_idx"] = parent_end if last is None else max(ch["start_idx"], min(parent_end, last))
        ch["parent"] = parent_pos
        out.append(ch)
    return out


def missing_stages(stages: Iterable[Any]) -> List[str]:
    """出现过的 a2h 主流水线阶段之间缺掉的那几个(只在首末出现之间找,不猜后面没跑的)。"""
    seen = {str(s) for s in stages}
    pos = [k for k, name in enumerate(CANON_PIPELINE) if name in seen]
    if len(pos) < 2:
        return []
    return [CANON_PIPELINE[k] for k in range(pos[0], pos[-1] + 1) if CANON_PIPELINE[k] not in seen]


# ── 空闲 = 回合已结束、到下一次活动之间什么都没在跑(Claude / Codex 共用) ──────────────

def merge_busy(busy: Iterable[Tuple[Any, Any]]) -> List[List[Any]]:
    merged: List[List[Any]] = []
    for a0, b0 in sorted(([a, b] for a, b in busy), key=lambda x: x[0]):
        if merged and a0 <= merged[-1][1]:
            if b0 > merged[-1][1]:
                merged[-1][1] = b0
        else:
            merged.append([a0, b0])
    return merged


def stall_pieces(stalls: Iterable[Tuple[Any, Any, str, Any]], busy: Sequence[Sequence[Any]]
                 ) -> List[Tuple[Any, Any, str, Any]]:
    """停摆区间(回合关闭 → 下一条记录)扣掉忙碌覆盖(工具在跑、子代理在跑 = 没停摆)。
    时刻是 datetime 或 float,同一次调用里统一即可。"""
    pieces = []
    for p0, p1, kind, tag in stalls:
        if p0 is None or p1 is None or not p1 > p0:
            continue
        cur = p0
        for a0, b0 in busy:
            if b0 <= cur or a0 >= p1:
                continue
            if a0 > cur:
                pieces.append((cur, min(a0, p1), kind, tag))
            cur = max(cur, b0)
        if cur < p1:
            pieces.append((cur, p1, kind, tag))
    return pieces
