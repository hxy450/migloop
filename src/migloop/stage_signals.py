"""阶段切分的统一口径:所有 adapter 与 live 共用,各家只负责把原始记录翻译成信号。

用户定的四条(2026-11-24,11-25 补充口径):

1. **阶段信号**。有 mark-stage 就只按它切。mark 先读 ``.migbot/metrics/*/facts/stage-marks.json``,
   再收转录里真跑成了的 ``a2h mark-stage <阶段>`` / ``a2h-codex mark-stage <阶段>``(看工具回执,
   只出现在文字里的不算),两处合并去重。除 ecat-refine(ECAT 开跑时由插件打,算开始)外,
   mark 都是「完成水位」,打在阶段结束时,a2h-init 也一样;第一个阶段从它自己的 skill 信号起算,
   之前归 setup。最后一个 mark 之后没有收尾 mark 的那段不再按 skill 切:段名取段内的管线 skill
   信号、标「缺结束标记」;没有信号就叫「未标记(X 之后)」,段内的人工输入不触发后续轮。
   没有 mark 才用 skill 调用(含归属戳、斜杠命令)或读 SKILL.md,一段至少 ``MIN_SPAN_S`` 秒,
   短于它不切。缺的阶段不补推断(审计里标「未见」)。既没有 mark、也没跑过管线 skill 的会话
   整段一个 Session。
2. **后续轮**。最后一个管线阶段结束后,从第一条人工输入起单独成段(``TRAILING``),
   不算进最后一个管线阶段。有 mark 时,收尾 mark 到第一条人工输入之间单列 ``AFTER``;
   没有 mark 时,「继续 / continue / resume / 接着 / 跑完」这类只要求接着干的输入算同一阶段继续。
3. **Workflow**。管线阶段里发起的 Workflow 是该阶段的子段,段尾取 workflow 实际结束时刻,
   之后回到外层阶段;不在任何管线阶段里的才算顶层段。
4. **人工输入** = 人打的文字 + 斜杠命令,按来源字段判,老版本没有来源字段才看内容;
   SDK / 驱动程序下发的指令记 ``PROGRAM``,不算人工。

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
#: 只有 ecat-refine 的 mark 打在**开始**(插件随 ECAT 开跑上报);其余都是完成水位,打在收尾
START_MARK_STAGES = frozenset({"ecat-refine"})
#: 收尾 mark 落在这几个阶段上,管线就算走完了(之后是收尾段与后续轮);更早的阶段收尾后
#: 再没有 mark,说明下一个阶段没打收尾
DONE_STAGES = frozenset({"a2h-execute", "a2h-verify", "a2h-retrospect"})
#: a2h 流水线的规范先后 —— 审计「未见 a2h-plan」只在这条线上、首末出现之间找缺口
CANON_PIPELINE = ("a2h-init", "a2h-build", "a2h-run", "a2h-spec", "a2h-plan", "a2h-execute",
                  "a2h-verify", "a2h-retrospect")

SETUP = "setup"
SESSION = "session"
TRAILING = "follow-up"
AFTER = "after-pipeline"
UNMARKED = "unmarked"
HUMAN = "human"
PROGRAM = "program"

_MARK_CALL = re.compile(r"\ba2h(?:-codex)?(?:\.exe)?\s+mark-stage\s+([a-z0-9_-]+)")
_MARK_ECHO = re.compile(r"mark-stage(?::\s*[a-z0-9_-]+|\s+ok\b)")
_RESUME = re.compile(r"^[\s\W]*(?:请|please\s+)?(?:继续|接着|跑完|恢复|continue|resume|go\s+on|keep\s+going|"
                     r"carry\s+on|proceed)", re.IGNORECASE)
_RESUME_WORD = re.compile(r"继续|接着|跑完|恢复|continue|resume|go\s+on|keep\s+going|carry\s+on|proceed", re.IGNORECASE)
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


def mark_ran(ok: Any, result: Any) -> bool:
    """转录里的 mark-stage 调用真跑成了:回执没报错;报错时(串在后面的别的命令失败)要输出里
    有 mark-stage 的回显。被拒、被打断、没有回执的都不算。"""
    if ok is True:
        return True
    return ok is False and bool(_MARK_ECHO.search(str(result or "")))


def merge_marks(*sources: Iterable[Tuple[float, str]], window: float = 120.0) -> List[Tuple[float, str]]:
    """stage-marks.json 与转录里的 mark 合并:同一阶段相隔 ``window`` 秒内的算一次,取早的。"""
    rows = sorted(((float(t), st) for src in sources for t, st in src), key=lambda m: m[0])
    out: List[Tuple[float, str]] = []
    for t, st in rows:   # 同一时刻的按原顺序(一条命令里先后打的几个 mark)
        if any(s == st and abs(t - u) <= window for u, s in out):
            continue
        out.append((t, st))
    return out


#: 短输入里出现续跑词也算(「一直跑完，自己推荐方案」「不是你继续啊」)
_RESUME_SHORT = 20


def is_resume_request(text: Any) -> bool:
    """人工输入只是要求接着干:以「继续 / continue / resume / 接着 / 跑完」开头,或是不超过
    ``_RESUME_SHORT`` 个字、里面带这类词。"""
    text = str(text or "").strip()
    if _RESUME.match(text):
        return True
    return len(text) <= _RESUME_SHORT and bool(_RESUME_WORD.search(text))


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
                ) -> Tuple[List[Tuple[int, str, str, Dict[str, Any]]], Optional[int]]:
    """mark → [(起始下标, 阶段, 信号, 附注)] 与管线收尾的下标(没走完为 None)。

    收尾 mark 的阶段占 (上一 mark, 本 mark];第一个阶段从它自己(本 mark 之前)最早的 skill 信号
    起算,之前归 setup。起始 mark(ecat-refine)从 mark 起;它后面紧跟别的阶段的收尾 mark 时,
    那一段归收尾 mark 的阶段。最后一个 mark 之后的尾巴:有还没打过 mark 的阶段的 skill 信号,
    按第一个这样的信号命名、标缺结束标记;没有信号时,最后收尾的是 execute 及之后的阶段就是
    管线收尾段(``AFTER``),否则是「未标记(X 之后)」。只有收尾段那种情况管线算走完。"""
    rows = sorted(marks, key=lambda m: m[0])
    out: List[Tuple[int, str, str, Dict[str, Any]]] = []
    cursor: Optional[int] = clock.idxs[0] if clock.idxs else None
    last_end: Optional[Tuple[float, str]] = None
    for k, (t, st) in enumerate(rows):
        nxt = rows[k + 1] if k + 1 < len(rows) else None
        if st in START_MARK_STAGES:
            if nxt is not None and nxt[1] not in START_MARK_STAGES:
                cursor = clock.first_at_or_after(t)
                continue
            start = clock.first_at_or_after(t)
            if start is not None and (not out or out[-1][1] != st):
                if out and out[-1][0] == start:
                    out[-1] = (start, st, "mark", {})
                else:
                    out.append((start, st, "mark", {}))
            cursor, last_end = None, None
            continue
        if cursor is not None and (not out or out[-1][1] != st):
            start = cursor
            if not out:
                upto = clock.last_at_or_before(t)
                own = [i for i, s in signals if s == st and i >= cursor and (upto is None or i <= upto)]
                if own:
                    start = min(own)
            out.append((start, st, "mark", {}))
        cursor = clock.first_after(t)
        last_end = (t, st)
    if cursor is None or last_end is None or not out:
        return out, None
    marked = {st for _, st in rows}
    later = next(((i, s) for i, s in sorted(signals) if i >= cursor and s not in marked), None)
    if later is not None:
        out.append((cursor, later[1], "unterminated", {"after": last_end[1]}))
        return out, None
    if last_end[1] in DONE_STAGES:
        out.append((cursor, AFTER, "after-marks", {"after": last_end[1]}))
        return out, clock.last_at_or_before(last_end[0])
    out.append((cursor, UNMARKED, "unterminated", {"after": last_end[1]}))
    return out, None


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
    return [(idx, st, "skill", {}) for idx, st in bounds]


def segment(points: Sequence[Tuple[int, Optional[float]]], *,
            marks: Sequence[Tuple[float, str]] = (),
            signals: Sequence[Tuple[int, str]] = (),
            human: Sequence[int] = (),
            resumes: Iterable[int] = (),
            workflows: Sequence[Dict[str, Any]] = (),
            last_pipeline_idx: Optional[int] = None,
            min_span: float = MIN_SPAN_S) -> List[Dict[str, Any]]:
    """按四条口径切段。``points`` 是全部记录的 (下标, 时刻),下标递增;``signals`` 是已归一的
    (下标, 阶段);``human`` 是人工输入的下标,``resumes`` 是其中只要求接着干的那些;
    ``workflows`` 是 {idx: 发起下标, end: 结束时刻, key: 段名}。返回 [{start_idx, end_idx, stage,
    signal, parent, after?}]:parent 为 None 的是顶层段,彼此相接、覆盖全部记录;``signal`` 取
    mark / skill / unterminated(缺结束标记)/ after-marks(收尾段)/ rule(后续轮)/ none /
    workflow;``after`` 是缺结束标记的段之前最后收尾的阶段。子段(管线阶段里的 Workflow)的
    parent 是所在顶层段的序号,另带 ``start_t`` / ``end_t``(发起与实际结束时刻)。"""
    if not points:
        return []
    clock = _Clock(points)
    first_idx, last_idx = clock.idxs[0], clock.idxs[-1]
    lo, hi = clock.mono[0] - 60, clock.end + 60
    marks = [(t, st) for t, st in marks if lo <= t <= hi]
    resume_set = set(resumes)
    if marks:
        bounds, pipe_end = _from_marks(clock, marks, signals)
        if bounds and pipe_end is not None:
            # 管线已收尾:收尾段起第一条人工输入(不论内容)开始是后续轮
            tail = bounds[-1]
            trailing = next((h for h in sorted(human) if h >= tail[0]), None)
            if trailing is not None:
                if trailing == tail[0]:
                    bounds.pop()
                bounds.append((trailing, TRAILING, "rule", {}))
    else:
        bounds = _from_signals(clock, signals, min_span)
        pipe_end = last_pipeline_idx if last_pipeline_idx is not None else (
            max((i for i, _ in signals), default=None) if bounds else None)
        if bounds and pipe_end is not None:
            trailing = next((h for h in sorted(human)
                             if h > pipe_end and h > bounds[-1][0] and h not in resume_set), None)
            if trailing is not None:
                bounds.append((trailing, TRAILING, "rule", {}))
    if not bounds:
        bounds = [(first_idx, SESSION, "none", {})]
    elif bounds[0][0] > first_idx:
        if clock.time_at(bounds[0][0]) <= clock.time_at(first_idx):
            # 开头几条没有时刻 / 同一时刻:不单列零长的 setup
            bounds[0] = (first_idx,) + tuple(bounds[0][1:])
        else:
            bounds.insert(0, (first_idx, SETUP, "none", {}))
    top: List[Dict[str, Any]] = []
    for k, (idx, st, sig, extra) in enumerate(bounds):
        end = bounds[k + 1][0] - 1 if k + 1 < len(bounds) else last_idx
        if top and top[-1]["start_idx"] == idx:
            continue
        top.append({"start_idx": idx, "end_idx": end, "stage": st, "signal": sig, "parent": None, **extra})
    children: List[Dict[str, Any]] = []
    for wf in sorted(workflows, key=lambda w: w["idx"]):
        pos = next((k for k in range(len(top) - 1, -1, -1) if top[k]["start_idx"] <= wf["idx"]), 0)
        seg = top[pos]
        end_t = wf.get("end")
        if is_pipeline_stage(seg["stage"]) or seg["stage"] == UNMARKED:
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
    """出现过的 a2h 流水线阶段之间缺掉的那几个(只在首末出现之间找,不猜后面没跑的)。"""
    seen = {str(s) for s in stages}
    pos = [k for k, name in enumerate(CANON_PIPELINE) if name in seen]
    if len(pos) < 2:
        return []
    return [CANON_PIPELINE[k] for k in range(pos[0], pos[-1] + 1) if CANON_PIPELINE[k] not in seen]


# ── live:逐条喂信号、随时给出当前阶段(Claude monitor 与 codexlive 共用) ───────────────

class LiveStages:
    """与 ``segment`` 同一套口径的增量版。状态全在调用方给的 dict 里(随 checkpoint 落盘),
    ``emit(kind, text, ts)`` 用来报事件。没有 mark 时 skill 信号先挂起,满 ``MIN_SPAN_S`` 才进入;
    打过 mark 后只认 mark,skill 信号只给缺结束标记的段起名。"""

    def __init__(self, state: Dict[str, Any], emit: Any):
        self.st = state
        self.emit = emit
        for key, value in (("current_stage", SESSION), ("stage_pending", None), ("marked_stages", []),
                           ("unmarked_after", None), ("current_workflow", None), ("pipeline_seen", False),
                           ("last_attr", None), ("stage_history", [])):
            state.setdefault(key, value)

    #: 阶段历史最多记多少段(总览只要个轮廓)
    HISTORY_MAX = 200

    def _enter(self, stage: str, ts: Any) -> None:
        """切到 ``stage``,并在 ``stage_history`` 里记一段 {stage, start_ts, tools_at_start}。"""
        st = self.st
        st["current_stage"] = stage
        hist = st.setdefault("stage_history", [])
        if hist and hist[-1].get("stage") == stage:
            return
        hist.append({"stage": stage, "start_ts": ts, "tools_at_start": int(st.get("tool_calls") or 0)})
        if len(hist) > self.HISTORY_MAX:
            del hist[1:len(hist) - self.HISTORY_MAX + 1]

    @property
    def marks_mode(self) -> bool:
        return bool(self.st.get("marked_stages"))

    def signal(self, stage: str, ts: Any) -> None:
        st = self.st
        st["pipeline_seen"] = True
        if self.marks_mode:
            if stage not in st["marked_stages"] and st.get("current_stage") in (UNMARKED, AFTER, TRAILING):
                self._enter(stage, ts)
                self.emit("stage", "进入 %s(缺结束标记)" % stage, ts)
            return
        if stage == st.get("current_stage"):
            st["stage_pending"] = None
            return
        pending = st.get("stage_pending")
        if pending and pending[0] == stage:
            return  # 同一阶段的后续信号(归属戳)不重置起点
        st["stage_pending"] = [stage, ts]

    def attribution(self, stage: str, ts: Any) -> None:
        """Claude 的归属戳:后续轮里又见管线归属 = 中途插话,退回管线;换戳才算信号。"""
        st = self.st
        st["pipeline_seen"] = True
        if not self.marks_mode and st.get("current_stage") == TRAILING:
            self._enter(stage, ts)
            self.emit("stage", "回到 %s" % stage, ts)
        if stage != st.get("last_attr"):
            st["last_attr"] = stage
            self.signal(stage, ts)

    def confirm(self, ts: Any) -> None:
        st = self.st
        pending = st.get("stage_pending")
        if not pending or not ts:
            return
        t0, t1 = iso_seconds(pending[1]), iso_seconds(ts)
        if t0 is not None and t1 is not None and t1 - t0 >= MIN_SPAN_S:
            if st.get("current_stage") != pending[0] and not (
                    is_pipeline_stage(pending[0]) and not is_pipeline_stage(st.get("current_stage"))):
                st["current_workflow"] = None
            self._enter(pending[0], pending[1])
            st["stage_pending"] = None
            self.emit("stage", "进入 %s" % pending[0], pending[1])

    def mark(self, stage: str, ts: Any) -> None:
        """真跑成了的 mark-stage(权威,不等 90 秒)。ecat-refine 是开始;其余是完成水位:
        execute 及之后收尾进收尾段,更早的收尾进「未标记」。"""
        st = self.st
        st["pipeline_seen"] = True
        st["stage_pending"] = None
        if stage not in st["marked_stages"]:
            st["marked_stages"].append(stage)
        if stage in START_MARK_STAGES:
            if stage != st.get("current_stage"):
                self._enter(stage, ts)
                self.emit("stage", "进入 %s" % stage, ts)
            return
        self.emit("stage", "%s 收尾" % stage, ts)
        st["unmarked_after"] = stage
        st["current_workflow"] = None
        hist = st.get("stage_history") or []
        if hist and hist[-1].get("stage") != stage and hist[-1].get("stage") in (SESSION, SETUP, UNMARKED):
            hist[-1]["stage"] = stage     # mark 是完成水位:前面那段就是这个阶段
        elif not hist:
            hist.append({"stage": stage, "start_ts": None, "tools_at_start": 0})
        self._enter(AFTER if stage in DONE_STAGES else UNMARKED, ts)

    def human(self, text: Any, ts: Any, command: bool = False) -> None:
        """人工输入。有 mark:管线收尾后的第一条(不论内容)开后续轮;没有 mark:管线阶段里、
        不是斜杠命令、也不是「继续」类的输入开后续轮(之后再见管线归属戳就退回)。"""
        st = self.st
        current = st.get("current_stage")
        if self.marks_mode:
            if current == AFTER:
                self._enter(TRAILING, ts)
                self.emit("stage", "进入后续轮", ts)
        elif not command and st.get("pipeline_seen") and is_pipeline_stage(current) and \
                not is_resume_request(text):
            self._enter(TRAILING, ts)
            st["stage_pending"] = None
            self.emit("stage", "进入后续轮", ts)

    def workflow(self, name: str, ts: Any) -> None:
        """管线阶段里(含还在 90 秒挂起期的)发起的编排是子段,外层阶段不变;否则是顶层段。"""
        st = self.st
        pending = st.get("stage_pending") or [None]
        current = st.get("current_stage")
        if is_pipeline_stage(current) or current == UNMARKED or is_pipeline_stage(pending[0]):
            st["current_workflow"] = name
        else:
            self._enter("wf:" + name, ts)
        self.emit("stage", "启动 %s" % name, ts)


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
