"""两原子基座:版本文件 × 版本 agent。

底层只有一本账:build_stories 的文件编年史 + 每个 agent 的动作时间线。两原子是
账上的两个查询,互相以 (path, v) / (agent, ver) 引用,不靠时间戳比较:

- 版本文件 file(path, v):≤v 的全部写者,每版带 (agent, agent 版本, 来路, diff),
  以及尽可能复原的该版内容(None = 诚实未知)。
- 版本 agent agent(id, ver):每个对外效应(写/删/派发/发消息)+1 版;读、收件箱等
  输入归到它们喂养的下一版。ver 之后的活动与这一版的归因无因果,截掉。

收集层(atoms_collect)只负责把实录翻译成 AgentRec + 事件;这里做编号、派发边
连接、版本回填与两个查询。
"""

from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from migloop.filestory import (
    EXTERNAL,
    OUTBAND,
    Ev,
    FileStory,
    Touch,
    build_stories,
    find_story_path,
    line_origins,
)

#: 让 agent 版本 +1 的动作
EFFECTS = frozenset({"write", "delete", "dispatch", "message"})
_WS = re.compile(r"\s+")


@dataclass
class FileRef:
    op: str                    # read | write | delete
    path: str
    ev: Ev                     # 落进编年史的事件;v 在 build 后回填
    v: int | None = None
    certain: bool = True       # 读:版本是实锤还是状态未知时的就近绑定(build 后回填)


@dataclass
class Action:
    ts: str
    seq: int
    tool: str
    kind: str                  # read|write|delete|dispatch|message|inbox|skill|compact|other
    ok: bool | None = True     # None = 没等到结果
    ver: int | None = None     # 效应序号 = agent 版本号(失败的效应不占号)
    at: int = 0                # 该动作喂养的版本号(效应 = 自身;其余 = 之前效应数 + 1)
    files: list[FileRef] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    #: 原始记录指针 (转录路径, tool_use 所在行, tool_result 所在行):账本是实录的索引,
    #: 任何动作都能按需展开完整 input/output,不存内容不占内存,信息不丢
    src: tuple[str, int, int] | None = None
    tuid: str | None = None
    stage: str | None = None   # 管线阶段:记录的归属戳(attributionSkill);子 agent 无戳时继承派发时阶段


@dataclass
class AgentRec:
    id: str
    session: str
    name: str | None = None
    kind: str | None = None            # subagent_type
    description: str | None = None
    model: str | None = None
    parent: str | None = None
    parent_ver: int | None = None      # 父 agent 派发它时所处的版本
    prompt: str | None = None          # 派发指令全文
    result: str | None = None          # 收尾输出(最后一段正文)
    stage: str | None = None           # 子 agent 的阶段(自己记录的戳,否则派发时父的阶段);主会话横跨全程,无
    actions: list[Action] = field(default_factory=list)

    @property
    def n_versions(self) -> int:
        return sum(1 for a in self.actions if a.ver is not None)


@dataclass
class Ledger:
    stories: dict[str, FileStory]
    agents: dict[str, AgentRec]
    #: (path, 读事件 seq) → 这条读喂养的 agent 版本;文件原子列读者(下游)时用
    feeds: dict[tuple[str, int], int] = field(default_factory=dict)
    #: 池子里最早一条动作的时刻(迁移开始)—— T+ 相对时刻的零点
    t0: str = ""
    #: execute 阶段结束时刻(run 级 stage-marks 给的;用户口径:之后的写全是修复)。None = 没有 marks,
    #: 修复方退回按阶段名判。由调用方(routes / server)在建账后填,账本自己不读 marks
    fix_after: str | None = None
    #: 动作号 → 转录行号(1 起):报告里的 #n 旁边带 @L,不经工具也能回查
    lines: dict[int, int] = field(default_factory=dict)
    #: (path, 读事件 seq) → 读它那次调用的动作号:文件原子的读者行带展开指针
    read_act: dict[tuple[str, int], int] = field(default_factory=dict)


def resolve_agent(ledger: Ledger, hint: str) -> AgentRec | None:
    """id、不带 agent- 前缀的 id、唯一的名字、唯一的 id 后缀都认 —— 模型用「conv-aboutus」这种名字调过好几次落空。"""
    a = ledger.agents.get(hint) or ledger.agents.get(f"agent-{hint}")
    if a is not None:
        return a
    by_name = [x for x in ledger.agents.values() if x.name == hint]
    if len(by_name) == 1:
        return by_name[0]
    by_tail = [x for k, x in ledger.agents.items() if len(hint) >= 8 and k.endswith(hint)]
    return by_tail[0] if len(by_tail) == 1 else None


def _number(a: AgentRec) -> None:
    a.actions.sort(key=lambda x: (x.ts, x.seq))
    n = 0
    for act in a.actions:
        if act.kind in EFFECTS and act.ok:
            n += 1
            act.ver = n
            act.at = n
        else:
            act.ver = None
            act.at = n + 1
        for ref in act.files:
            ref.ev = replace(ref.ev, aver=act.ver)


def rel_time(ts: str | None, t0: str | None) -> str:
    """相对迁移开始的时刻 T+h:mm(池子里最早一条动作为零点,跨天小时累加);解析不了给空串。
    跨 agent 对先后靠它:动作号只在单个 agent 内有序。"""
    if not ts or not t0:
        return ""
    try:
        a = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(t0).replace("Z", "+00:00"))
    except ValueError:
        return ""
    mins = int((a - b).total_seconds() // 60)
    sign = "-" if mins < 0 else "+"
    mins = abs(mins)
    return f"T{sign}{mins // 60}:{mins % 60:02d}"


def _head(text: str | None) -> str:
    return _WS.sub(" ", text or "").strip()[:120]


def _link_dispatches(agents: dict[str, AgentRec]) -> None:
    """父的 dispatch 动作 ↔ 子 AgentRec:收集器给了实锤的边(CC 的 toolUseResult.agentId、codex 的 task_path)
    直接用;没有的先按派发词全文、再按开头对齐,最后退到 id 前缀(CC 子代理 id = 'a' + name + '-' + hash)。
    连上后把名片抄给子,子 id 回写父动作。"""
    def adopt(parent: AgentRec, act: Action, child: AgentRec) -> None:
        child.parent, child.parent_ver = parent.id, act.ver
        if child.stage is None:
            child.stage = act.stage
        child.name = child.name or (act.detail.get("name") or None)
        child.kind = child.kind or act.detail.get("subagent_type")
        child.description = child.description or act.detail.get("description")
        child.model = child.model or act.detail.get("model")
        act.detail["child"] = child.id

    for a in agents.values():
        for act in a.actions:
            child = agents.get(str(act.detail.get("child") or "")) if act.kind == "dispatch" else None
            if child is not None and child.parent_ver is None:
                adopt(a, act, child)
    orphans = [c for c in agents.values() if c.parent is None and not c.id.startswith("__main__")]
    for a in agents.values():
        for act in a.actions:
            if act.kind != "dispatch" or not act.ok or agents.get(str(act.detail.get("child") or "")):
                continue
            name = str(act.detail.get("name") or "")
            full = _WS.sub(" ", str(act.detail.get("prompt") or "")).strip()
            want = _head(act.detail.get("prompt"))
            hit = next((c for c in orphans if c.parent is None and full
                        and _WS.sub(" ", str(c.prompt or "")).strip() == full), None)
            if hit is None:
                hit = next((c for c in orphans if c.parent is None and want
                            and _head(c.prompt) == want), None)
            if hit is None and name:
                hit = next((c for c in orphans if c.parent is None
                            and c.id.startswith(f"agent-a{name}-")), None)
            if hit is not None:
                adopt(a, act, hit)


def _fill_stages(agents: dict[str, AgentRec]) -> None:
    """阶段下沉到每笔动作与事件:子 agent 自己的记录没有归属戳时整个生命周期继承派发时的阶段;
    主会话逐笔按记录的戳。版本文件由此知道每一版写在哪个阶段(修复方判定:execute 之后即修复)。"""
    changed = True
    while changed:   # 沿派发边传到底:子的子在链接时父动作还没有阶段,这里补齐
        changed = False
        for a in agents.values():
            for act in a.actions:
                if act.stage is None and a.stage:
                    act.stage = a.stage
                    changed = True
                child = (agents.get(str(act.detail.get("child") or ""))
                         if act.kind == "dispatch" else None)
                if child is not None and child.stage is None and act.stage:
                    child.stage = act.stage
                    changed = True
    for a in agents.values():
        for act in a.actions:
            if act.stage:
                for ref in act.files:
                    ref.ev = replace(ref.ev, stage=act.stage)


#: 不算实锤的读的来路:脚本字面量推断、stdout 反证 —— 只有它们支撑的路径可能是拼错的
_NONAUTH = frozenset({"script", "stdout"})


def _sweep_phantoms(stories: dict[str, FileStory]) -> None:
    """脚本字面量按当时的 cwd 拼出来的路径(只有文件名 / 拼到别的目录下 / 路径段重复):0723 有 327 条。
    判据:所有版本都是外部输入、所有读都来自脚本字面量,且同名文件另有真凭实据(工具读写过)。
    这种 story 删掉,指针改挂到同名真文件上(唯一就说对上了,多个就都挂并说路径未定);
    含正则元字符的直接丢。只有碰过、没有版本的幽灵一样处理。"""
    auth: dict[str, list[str]] = {}
    for path, st in stories.items():
        if any(v.source != "external" for v in st.versions) or any(r.via not in _NONAUTH for r in st.reads):
            auth.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    for path in list(stories):
        st = stories[path]
        if any(v.source != "external" for v in st.versions) or any(r.via not in _NONAUTH for r in st.reads):
            continue
        cands = [p for p in auth.get(path.rsplit("/", 1)[-1], []) if p != path]
        regexy = bool(re.search(r"[\[\]()+\\]|\.\*", path))
        if not cands and not regexy:
            continue
        reason = "脚本字面量或命令输出里提到(路径按文件名对上)" if len(cands) == 1 else "脚本字面量或命令输出里提到(同名多个,路径未定)"
        moved = ([Touch(r.ts, r.seq, r.by, None, reason) for r in st.reads]
                 + [Touch(t.ts, t.seq, t.by, t.by_ver, f"{reason};原记 {t.reason}", t.stage) for t in st.touches])
        del stories[path]
        for p in cands:
            stories[p].touches.extend(moved)


def build_ledger(agents: dict[str, AgentRec]) -> Ledger:
    for a in agents.values():
        _number(a)
    _link_dispatches(agents)
    _fill_stages(agents)
    events = [ref.ev for a in agents.values() for act in a.actions for ref in act.files]
    stories = build_stories(events)
    _sweep_phantoms(stories)
    index: dict[tuple[str, int], int] = {}
    certain: dict[tuple[str, int], bool] = {}
    for path, st in stories.items():
        for ver in st.versions:
            index[(path, ver.seq)] = ver.v
        for r in st.reads:
            index[(path, r.seq)] = r.version
            certain[(path, r.seq)] = r.certain
    feeds: dict[tuple[str, int], int] = {}
    act_seq: dict[tuple[str, int], int] = {}
    read_act: dict[tuple[str, int], int] = {}
    lines: dict[int, int] = {}
    for a in agents.values():
        for act in a.actions:
            if act.src is not None:
                lines[act.seq] = act.src[1] + 1
            for ref in act.files:
                ref.v = index.get((ref.path, ref.ev.seq))
                if ref.op == "read":
                    feeds[(ref.path, ref.ev.seq)] = act.at
                    ref.certain = certain.get((ref.path, ref.ev.seq), True)
                    read_act[(ref.path, ref.ev.seq)] = act.seq
                else:
                    act_seq[(ref.path, ref.ev.seq)] = act.seq
            # 脚本碰过但方向不明的路径:不立版本,挂到文件原子上(没写过的文件也进目录),指针指回这次调用
            for p in act.detail.get("touched") or []:
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                        str(act.detail.get("unresolved") or "方向不明"), act.stage))
            # 存在性守卫里探过的路径:文件当时可能不存在,只留指针
            for p in act.detail.get("probed") or []:
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                        "存在性探测,内容未进上下文", act.stage))
    # 目录级线索:建了目录 / --out 指到目录 / 脚本正文写着这个目录 的运行,该目录下首见即外部的文件挂
    # 「可能由此次运行生成」—— 只看首见之前的运行(生成后几小时才被读是常态),最近的 3 次,不立版本不猜
    runs_by_dir: dict[str, list[tuple[str, str, Action]]] = {}
    for a in agents.values():
        for act in a.actions:
            for d in act.detail.get("out_dirs") or []:
                runs_by_dir.setdefault(d.rstrip("/") + "/", []).append((act.ts, a.id, act))
    if runs_by_dir:
        for path, st in stories.items():
            if not (st.versions and st.versions[0].source == "external"):
                continue
            cands = {r[2].seq: r for prefix, runs in runs_by_dir.items() if path.startswith(prefix)
                     for r in runs if r[0] <= st.versions[0].ts}
            # 嵌套目录(spec/baseline 与 spec/baseline/ui)各自的运行合在一起,只留最近的 3 次
            for _ts, aid, act in sorted(cands.values(), key=lambda x: x[0])[-3:]:
                st.touches.append(Touch(act.ts, act.seq, aid, act.ver if act.ver is not None else act.at,
                                        "可能由此次运行生成(目录级线索,不立版本)", act.stage))
    for path, st in stories.items():
        for ver in st.versions:
            ver.act_seq = act_seq.get((path, ver.seq))
        st.touches.sort(key=lambda t: (t.ts, t.seq))
    t0 = min((act.ts for a in agents.values() for act in a.actions if act.ts), default="")
    return Ledger(stories, agents, feeds, t0, lines=lines, read_act=read_act)


# ═══════════════ 两个查询 ═══════════════

def _agent_label(agents: dict[str, AgentRec], aid: str) -> str | None:
    a = agents.get(aid)
    if a is not None and (a.name or a.description):
        return a.name or a.description
    if aid.startswith("__main__"):
        # 池子里不止一个主会话(多轮迁移)时带上会话号,树上两个"主会话"才分得开
        mains = [k for k in agents if k.startswith("__main__")]
        return "主会话" if len(mains) <= 1 else "主会话·" + aid.split(":", 1)[-1][:8]
    return None


def agent_label(ledger: Ledger, aid: str) -> str:
    """给人/模型看的 agent 名:名片 → 主会话 → 去前缀的短 id。"""
    lab = _agent_label(ledger.agents, aid)
    if lab:
        return lab
    return aid[6:] if aid.startswith("agent-") else aid


def _text_of(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "\n".join(str(x.get("text", "")) for x in raw if isinstance(x, dict))
    return ""


def build_evidence(ledger: Ledger) -> list[dict[str, Any]]:
    """池子里跑过的构建命令(hvigor / ohpm),按时间排:{sid8, agent, ts, stage, cmd}。
    报告页「执行阶段未见构建」要看整个 run,不只主线一个 root —— 构建可以发生在后起的 build 会话里。"""
    from migloop.audit import BUILD_MARKERS

    out: list[dict[str, Any]] = []
    for a in ledger.agents.values():
        for act in a.actions:
            if act.tool not in ("Bash", "PowerShell", "exec"):
                continue
            cmd = str(act.detail.get("cmd") or "")
            if any(m in cmd.lower() for m in BUILD_MARKERS):
                out.append({"sid8": a.session, "agent": a.id, "ts": act.ts, "stage": act.stage, "cmd": cmd[:200]})
    out.sort(key=lambda r: str(r["ts"]))
    return out


def action_raw(ledger: Ledger, agent_id: str, seq: int) -> dict[str, Any] | None:
    """按指针展开一次工具调用的完整 input / output(原始记录,不经任何摘要)。"""
    a = resolve_agent(ledger, agent_id)
    if a is None:
        return None
    act = next((x for x in a.actions if x.seq == seq), None)
    if act is None or act.src is None:
        return None
    path, use_idx, res_idx = act.src
    want = {use_idx, res_idx}
    recs: dict[int, Any] = {}
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh):
            if i in want:
                try:
                    recs[i] = json.loads(line)
                except Exception:
                    recs[i] = None
            if i >= max(want):
                break
    inp: Any = None
    out = ""
    tur: Any = None
    use_rec, res_rec = recs.get(use_idx), recs.get(res_idx)
    for b in ((use_rec or {}).get("message") or {}).get("content") or []:
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") == act.tuid:
            inp = b.get("input")
    for b in ((res_rec or {}).get("message") or {}).get("content") or []:
        if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") == act.tuid:
            out = _text_of(b.get("content"))
    if act.tuid is None and isinstance(use_rec, dict):
        # 正文 / thinking / 指令 / 收件 / 注入:记录本身就是原文
        want_type = "thinking" if act.kind == "think" else "text"
        blocks = (use_rec.get("message") or {}).get("content")
        texts = ([str(b.get(want_type) or "") for b in blocks if isinstance(b, dict) and b.get("type") == want_type]
                 if isinstance(blocks, list) else [str(blocks or "")])
        inp = "\n".join(t for t in texts if t.strip())
    # codex rollout:调用与结果都在 payload 里,按 call_id 对上
    for rec, is_use in ((use_rec, True), (res_rec, False)):
        pl = rec.get("payload") if isinstance(rec, dict) and isinstance(rec.get("payload"), dict) else None
        if pl is None or str(pl.get("call_id")) != str(act.tuid):
            continue
        if is_use and inp is None:
            inp = pl.get("arguments") if pl.get("arguments") is not None else pl.get("input")
        if not is_use and not out:
            out = _text_of(pl.get("output"))
    if isinstance(res_rec, dict):
        tur = res_rec.get("toolUseResult")
    return {"seq": act.seq, "ts": act.ts, "tool": act.tool, "kind": act.kind, "ok": act.ok,
            "ver": act.ver, "at": act.at, "input": inp, "output": out,
            "tool_use_result": tur, "src": {"path": path, "use_line": use_idx, "result_line": res_idx}}


def blame(ledger: Ledger, hint: str, v: int | None = None,
          start: int | None = None, n: int | None = None,
          changed: bool = False) -> dict[str, Any] | None:
    """逐行归属:文件@v 的每一行是谁在哪一版写的(逐行签名,确定性)。
    内容未知的版本如实报 known=False、不给行;窗口 start/n 只裁输出,汇总仍按全文。
    changed=True 时把 v 当修复版:只给它替换/删除掉的前一版那些行及其原作者(见 _blame_changed)。"""
    path = find_story_path(ledger.stories, hint)
    if path is None:
        return None
    st = ledger.stories[path]
    if not st.versions:
        return {"path": path, "v": 0, "n_versions": 0, "known": False, "n_lines": 0,
                "lines": [], "summary": [], "unknown": 0}
    anchor = min(max(v or len(st.versions), 1), len(st.versions))
    if changed:
        return _blame_changed(ledger, path, st, anchor)
    ver = st.versions[anchor - 1]
    rows = line_origins(st)[anchor - 1]
    text = ver.content.splitlines() if ver.content is not None else []
    known = ver.content is not None
    lo = max(start or 1, 1)
    hi = min(lo + n - 1, len(text)) if (start and n) else len(text)
    lines = []
    for i in range(lo - 1, hi):
        o = rows[i] if i < len(rows) else None
        lines.append({"ln": i + 1, "owner": o[0] if o else None,
                      "owner_name": _agent_label(ledger.agents, o[0]) if o else None,
                      "since_v": o[1] if o else None, "text": text[i]})
    counts: dict[str, int] = {}
    unknown = 0
    for o in rows:
        if o is None:
            unknown += 1
        else:
            counts[o[0]] = counts.get(o[0], 0) + 1
    summary = [{"owner": k, "owner_name": _agent_label(ledger.agents, k), "n": c}
               for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {"path": path, "v": anchor, "n_versions": len(st.versions), "known": known,
            "n_lines": len(text), "lines": lines, "summary": summary, "unknown": unknown}


def _blame_changed(ledger: Ledger, path: str, st: FileStory, anchor: int) -> dict[str, Any]:
    """修复版 v 替换/删除了前一版的哪些行、各是谁引入的 —— 归因第 4 步要的就是这几行。
    0723 调查基线里 agent 三次整文件 blame(32K/28K/12K 字符)都只为找它们;这里按 v-1 与 v 的
    行级 diff 直接挑出旧侧的 replace/delete 行,归属取自 v-1 的逐行签名,新增侧只给行数。"""
    base: dict[str, Any] = {"path": path, "v": anchor, "n_versions": len(st.versions), "changed": True,
                            "prev_v": anchor - 1 if anchor > 1 else None, "known": False,
                            "n_lines": 0, "lines": [], "added": 0, "summary": [], "unknown": 0, "note": ""}
    if anchor < 2:
        base["note"] = "创建版,没有前一版可比"
        return base
    prev, ver = st.versions[anchor - 2], st.versions[anchor - 1]
    if prev.content is None or ver.content is None:
        base["note"] = "前一版或本版内容未知,无法定位被替换行(见 file 的复原原因)"
        return base
    old, new = prev.content.splitlines(), ver.content.splitlines()
    rows = line_origins(st)[anchor - 2]
    lines: list[dict[str, Any]] = []
    added = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            for i in range(i1, i2):
                o = rows[i] if i < len(rows) else None
                lines.append({"ln": i + 1, "owner": o[0] if o else None,
                              "owner_name": _agent_label(ledger.agents, o[0]) if o else None,
                              "since_v": o[1] if o else None, "text": old[i]})
        if tag in ("replace", "insert"):
            added += j2 - j1
    counts: dict[str, int] = {}
    unknown = 0
    for x in lines:
        if x["owner"] is None:
            unknown += 1
        else:
            counts[x["owner"]] = counts.get(x["owner"], 0) + 1
    base.update(known=True, n_lines=len(old), lines=lines, added=added, unknown=unknown,
                summary=[{"owner": k, "owner_name": _agent_label(ledger.agents, k), "n": c}
                         for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))])
    return base


def file_atom(ledger: Ledger, hint: str, v: int | None = None,
              with_diff: bool = True, with_content: bool = True) -> dict[str, Any] | None:
    """版本文件:≤v 的写者脊柱(上游)+ 读者(下游)+ 该版内容。v=None 取最新。
    content_known 独立于 with_content:脊柱查询可以不带正文但仍知道能否复原。"""
    path = find_story_path(ledger.stories, hint)
    if path is None:
        return None
    st = ledger.stories[path]
    vers = st.versions if v is None else st.versions[:max(v, 0)]
    out = []
    for ver in vers:
        row: dict[str, Any] = {
            "v": ver.v, "ts": ver.ts, "t": rel_time(ver.ts, ledger.t0), "by": ver.by,
            "by_name": _agent_label(ledger.agents, ver.by),
            "by_ver": ver.by_ver, "seq": ver.act_seq, "via": ver.via, "source": ver.source,
            "diff_kind": ver.diff_kind, "sealed": ver.sealed,
            "lines": (ver.content.count("\n") + 1) if ver.content else None,
            "has_diff": ver.diff is not None,
            "content_known": ver.content is not None,
        }
        if with_diff:
            row["diff"] = ver.diff
        out.append(row)
    content = vers[-1].content if vers else None
    readers = [{"by": r.by, "by_name": _agent_label(ledger.agents, r.by), "ts": r.ts,
                "t": rel_time(r.ts, ledger.t0), "seq": ledger.read_act.get((path, r.seq)), "via": r.via,
                "v": r.version, "at": ledger.feeds.get((path, r.seq)),
                "start": r.start, "n": r.n, "dep": r.dep, "certain": r.certain,
                "seen": [list(x) for x in r.seen] if r.seen else None,
                "seen_n": len(r.seen or ()), "full": r.full}
               for r in st.reads]
    touches = [{"by": t.by, "by_name": _agent_label(ledger.agents, t.by), "by_ver": t.by_ver,
                "ts": t.ts, "t": rel_time(t.ts, ledger.t0), "seq": t.seq, "reason": t.reason}
               for t in st.touches]
    return {
        "path": path, "v": vers[-1].v if vers else 0, "n_versions": len(st.versions),
        "versions": out, "readers": readers, "touches": touches, "t0": ledger.t0,
        "content": content if with_content else None, "content_known": content is not None,
        "breaks": [{"ts": b.ts, "kind": b.kind, "detail": b.detail} for b in st.breaks],
    }


_KIND_BY_EXT = {".ets": "ets", ".md": "spec", ".json": "spec", ".json5": "spec",
                ".yaml": "spec", ".yml": "spec", ".java": "src", ".kt": "src",
                ".xml": "src", ".gradle": "src", ".kts": "src"}


def file_kind(path: str) -> str:
    return _KIND_BY_EXT.get(os.path.splitext(path)[1].lower(), "other")


def ledger_index(ledger: Ledger) -> dict[str, Any]:
    """左栏入口用的全量目录:每个文件 / agent 一行,版本行按需再取原子。"""
    files = []
    for path, st in sorted(ledger.stories.items()):
        files.append({
            "path": path, "kind": file_kind(path), "n_versions": len(st.versions),
            "has_writer": any(ver.by not in (EXTERNAL, OUTBAND) for ver in st.versions),
            "n_reads": len(st.reads), "n_touches": len(st.touches),
        })
    agents = []
    for a in ledger.agents.values():
        agents.append({
            "id": a.id, "label": _agent_label(ledger.agents, a.id) or a.id,
            "kind": a.kind, "session": a.session, "parent": a.parent,
            "parent_ver": a.parent_ver, "n_versions": a.n_versions, "stage": a.stage,
            "n_reads": sum(1 for act in a.actions for ref in act.files if ref.op == "read"),
            "n_unresolved": sum(1 for act in a.actions if act.detail.get("unresolved")),
            "first_ts": a.actions[0].ts if a.actions else "",
        })
    agents.sort(key=lambda x: (x["session"], x["first_ts"]))
    return {"files": files, "agents": agents}


def _versions_at(st: FileStory, ts: str) -> int:
    return sum(1 for ver in st.versions if ver.ts <= ts)


def agent_atom(ledger: Ledger, agent_id: str, v: int | None = None,
               since: int | None = None) -> dict[str, Any] | None:
    """版本 agent:≤ver 的全部动作(读绑文件版本、写产出版本)、派发指令、收件箱、
    父/子边、收尾输出。v=None = 整个生命周期(锚之后的动作打 after_anchor)。
    since = 窗口下界:只给喂养 (since, v] 这段版本的动作 —— 主会话动辄几百次调用,
    整个生命周期一次给出会撑爆调查 agent 的上下文,查主会话必须带窗口。"""
    a = resolve_agent(ledger, agent_id)
    if a is None:
        return None
    n = a.n_versions
    anchor = n if v is None else max(0, min(v, n))
    written = {ref.path for act in a.actions for ref in act.files if ref.op != "read"}
    effect_ts = {act.ver: act.ts for act in a.actions if act.ver is not None}

    def keep(act: Action) -> bool:
        k = act.ver if act.ver is not None else act.at
        if since is not None and k <= since:
            return False
        return v is None or k <= anchor

    acts = [act for act in a.actions if keep(act)]
    reads: list[dict[str, Any]] = []
    writes: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    for act in acts:
        # 派发词全文归子 agent 的原子;父的时间线只留名片,否则主会话 113 次派发把
        # 一份 payload 撑到 600KB(实测)
        detail = act.detail
        if act.kind == "dispatch":
            detail = {k: val for k, val in act.detail.items() if k != "prompt"}
        row: dict[str, Any] = {"seq": act.seq, "ts": act.ts, "t": rel_time(act.ts, ledger.t0),
                               "tool": act.tool, "kind": act.kind,
                               "ok": act.ok, "ver": act.ver, "at": act.at, "files": [],
                               "detail": detail, "expandable": act.src is not None,
                               "stage": act.stage}
        for ref in act.files:
            row["files"].append({"op": ref.op, "path": ref.path, "v": ref.v, "via": ref.ev.via})
            if ref.op == "read" and ref.v is not None:      # 被作废的探测读(假前身)不列进读记录
                st = ledger.stories.get(ref.path)
                anchor_ts = effect_ts.get(act.at) or act.ts
                latest = _versions_at(st, anchor_ts) if st else None
                reads.append({
                    "seq": act.seq, "ts": ref.ev.ts, "t": rel_time(ref.ev.ts, ledger.t0),
                    "path": ref.path, "v": ref.v, "via": ref.ev.via,
                    "seen": [list(x) for x in ref.ev.seen] if ref.ev.seen else None,
                    "start": ref.ev.start, "n": ref.ev.n, "full": ref.ev.full, "dep": ref.ev.dep,
                    "certain": ref.certain,
                    "at": act.at, "after_anchor": act.at > anchor,
                    "self_written": ref.path in written,
                    "latest_v": latest,
                    "stale": bool(latest is not None and ref.v is not None and ref.v < latest),
                })
            else:
                writes.append({"ts": ref.ev.ts, "t": rel_time(ref.ev.ts, ledger.t0),
                               "path": ref.path, "v": ref.v, "op": ref.op,
                               "ver": act.ver, "via": ref.ev.via})
        timeline.append(row)
    parent = None
    if a.parent:
        parent = {"id": a.parent, "ver": a.parent_ver,
                  "name": _agent_label(ledger.agents, a.parent)}
    children = [{"id": act.detail.get("child"), "name": act.detail.get("name"), "ver": act.ver}
                for act in acts if act.kind == "dispatch" and act.ok]
    inbox = [{"ts": act.ts, "seq": act.seq, "from": act.detail.get("from"), "summary": act.detail.get("summary"),
              "text": act.detail.get("text"), "at": act.at, "after_anchor": act.at > anchor}
             for act in acts if act.kind == "inbox"]
    return {
        "id": a.id, "session": a.session, "name": a.name, "kind": a.kind,
        "description": a.description, "model": a.model,
        "label": _agent_label(ledger.agents, a.id) or a.id,
        "parent": parent, "prompt": a.prompt, "inbox": inbox, "children": children,
        "n_versions": n, "v": anchor, "since": since, "t0": ledger.t0,
        "reads": reads, "writes": writes, "actions": timeline,
        "result": {"text": a.result, "after_anchor": True} if a.result else None,
    }


# ═══════════════ 带起点的 search ═══════════════

_TRANSCRIPT_CACHE: dict[str, list[str]] = {}


def _transcript_lines(path: str) -> list[str]:
    """整份转录按行缓存(最多 4 份):search 先用子串在原始行上粗筛,命中的才解析 JSON。"""
    lines = _TRANSCRIPT_CACHE.get(path)
    if lines is None:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().split("\n")
        if len(_TRANSCRIPT_CACHE) >= 4:
            _TRANSCRIPT_CACHE.pop(next(iter(_TRANSCRIPT_CACHE)))
        _TRANSCRIPT_CACHE[path] = lines
    return lines


def _record_texts(rec: dict[str, Any], act: Action) -> dict[str, str]:
    """一条记录里可搜的文本,按字段:input(工具输入)/ output(工具输出,Read 的用边车里的全文按行号排)/
    text(正文、指令、收件、注入…)/ thinking。"""
    out: dict[str, str] = {}
    msg = rec.get("message") or {}
    content = msg.get("content")
    blocks = content if isinstance(content, list) else (
        [{"type": "text", "text": content}] if isinstance(content, str) else [])
    texts: list[str] = []
    thinks: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "tool_use" and (act.tuid is None or b.get("id") == act.tuid):
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            # 按行找要用真正的内容字段(content / command / new_string / prompt…),不是整段 JSON
            fields = [str(v) for k, v in inp.items() if isinstance(v, str) and k not in ("file_path", "path", "notebook_path")]
            out["input"] = "\n".join(fields) if fields else json.dumps(b.get("input"), ensure_ascii=False)
        elif t == "tool_result" and (act.tuid is None or b.get("tool_use_id") == act.tuid):
            out["output"] = _text_of(b.get("content"))
        elif t == "text":
            texts.append(str(b.get("text") or ""))
        elif t == "thinking":
            thinks.append(str(b.get("thinking") or ""))
    tur = rec.get("toolUseResult")
    if isinstance(tur, dict) and isinstance(tur.get("file"), dict) and isinstance(tur["file"].get("content"), str):
        start = int(tur["file"].get("startLine") or 1)
        out["output"] = "\n".join(f"{start + i}\t{ln}" for i, ln in enumerate(tur["file"]["content"].split("\n")))
    if texts:
        out["text"] = "\n".join(texts)
    if thinks:
        out["thinking"] = "\n".join(thinks)
    return out


_NUMBERED = re.compile(r"^\s*(\d+)[\t:→|]")


def _snips(text: str, ql: str, cap: int = 3) -> tuple[list[tuple[int | None, str]], int]:
    """命中的行(带行号前缀的取行号)前 cap 条 + 总命中行数。"""
    snips: list[tuple[int | None, str]] = []
    n = 0
    for ln in text.split("\n"):
        if ql not in ln.lower():
            continue
        n += 1
        if len(snips) < cap:
            m = _NUMBERED.match(ln)
            snips.append((int(m.group(1)) if m else None, _WS.sub(" ", ln).strip()[:160]))
    return snips, n


def search_agent(ledger: Ledger, agent_id: str, q: str, v: int | None = None, since: int | None = None,
                 after: bool = False, since_ts: str | None = None,
                 until_ts: str | None = None) -> dict[str, Any] | None:
    """在一个 agent 的记录里找词,只看喂养第 v 版及之前的(since 给了只看 (since, v]);派发者可改用时间区间
    since_ts / until_ts(由文件时间线上的两个版本给出)。锚点之后的命中只计数(after=True 才列),不混进因果。
    命中的字段按记录种类:工具动作看 input / output,说 / 想看正文,指令 / 收件 / 注入看文本。"""
    a = resolve_agent(ledger, agent_id)
    if a is None:
        return None
    ql = q.lower()
    n = a.n_versions
    anchor = n if v is None else max(0, min(v, n))
    hits: list[dict[str, Any]] = []
    excluded = 0
    if a.prompt and ql in a.prompt.lower() and not (since_ts or until_ts):
        snips, cnt = _snips(a.prompt, ql)
        hits.append({"kind": "prompt", "tool": "prompt", "seq": None, "line": None, "at": 1, "ver": None,
                     "ts": "", "t": "", "field": "text", "target": None, "snips": snips, "n": cnt})
    for act in a.actions:
        if act.src is None:
            continue
        k = act.ver if act.ver is not None else act.at
        if since_ts or until_ts:
            if (since_ts and act.ts < since_ts) or (until_ts and act.ts > until_ts):
                continue
            in_window = True
        else:
            in_window = (since is None or k > since) and k <= anchor
        path, ui, ri = act.src
        lines = _transcript_lines(path)
        idxs = [ui] + ([ri] if ri is not None and ri != ui else [])
        if not any(i is not None and i < len(lines) and ql in lines[i].lower() for i in idxs):
            continue
        if not in_window and not after:
            excluded += 1
            continue
        fields: dict[str, str] = {}
        for i in idxs:
            if i is None or i >= len(lines) or ql not in lines[i].lower():
                continue
            try:
                rec = json.loads(lines[i])
            except Exception:
                continue
            for fld, text in _record_texts(rec, act).items():
                if act.kind in ("say",) and fld != "text":
                    continue
                if act.kind == "think" and fld != "thinking":
                    continue
                if act.kind in ("inbox", "instruction", "inject", "system", "notify", "interrupt") and fld != "text":
                    continue
                if act.kind not in ("say", "think", "inbox", "instruction", "inject", "system", "notify", "interrupt") \
                        and fld not in ("input", "output"):
                    continue
                if ql in text.lower():
                    fields[fld] = text
        for fld, text in fields.items():
            snips, cnt = _snips(text, ql)
            target = None
            rs = [ref.path for ref in act.files if ref.op == "read"]
            ws = [ref.path for ref in act.files if ref.op != "read"]
            if fld == "output" and rs:
                target = rs[0] if len(rs) == 1 else None
            elif fld == "input" and ws:
                target = ws[0]
            hits.append({"kind": act.kind, "tool": act.tool, "seq": act.seq, "line": ledger.lines.get(act.seq),
                         "at": act.at, "ver": act.ver, "ts": act.ts, "t": rel_time(act.ts, ledger.t0),
                         "field": fld, "target": target,
                         "targets": rs if fld == "output" else ws,
                         "target_v": next((ref.v for ref in act.files if ref.path == target), None),
                         "after": not in_window, "snips": snips, "n": cnt})
    return {"agent": a.id, "label": _agent_label(ledger.agents, a.id) or a.id, "q": q, "v": anchor, "since": since,
            "since_ts": since_ts, "until_ts": until_ts, "hits": hits, "excluded_after": excluded}


def search_file(ledger: Ledger, hint: str, q: str, v: int | None = None) -> dict[str, Any] | None:
    """在一个文件到第 v 版为止的内容里找词:哪几版含它(首次出现在第几版、谁写的),哪些读者的读结果里命中过。"""
    path = find_story_path(ledger.stories, hint)
    if path is None:
        return None
    st = ledger.stories[path]
    ql = q.lower()
    vers = st.versions if v is None else st.versions[:max(v, 0)]
    rows = []
    for ver in vers:
        if ver.content is None or ql not in ver.content.lower():
            continue
        snips = []
        for i, ln in enumerate(ver.content.split("\n"), 1):
            if ql in ln.lower():
                snips.append((i, _WS.sub(" ", ln).strip()[:160]))
        rows.append({"v": ver.v, "by": ver.by, "by_ver": ver.by_ver, "seq": ver.act_seq,
                     "line": ledger.lines.get(ver.act_seq or -1), "t": rel_time(ver.ts, ledger.t0),
                     "snips": snips[:3], "n": len(snips)})
    readers = []
    for r in st.reads:
        if not r.seen:
            continue
        got = [(ln, _WS.sub(" ", t).strip()[:160]) for ln, t in r.seen if ql in t.lower()]
        if got:
            seq = ledger.read_act.get((path, r.seq))
            readers.append({"by": r.by, "at": ledger.feeds.get((path, r.seq)), "v": r.version,
                            "seq": seq, "line": ledger.lines.get(seq or -1), "t": rel_time(r.ts, ledger.t0),
                            "snips": got[:3], "n": len(got)})
    return {"path": path, "q": q, "v": len(vers), "n_versions": len(st.versions),
            "first": rows[0]["v"] if rows else None, "versions": rows, "readers": readers}
