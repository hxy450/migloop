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

import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any

from migloop.filestory import (
    EXTERNAL,
    OUTBAND,
    Ev,
    FileStory,
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


def _head(text: str | None) -> str:
    return _WS.sub(" ", text or "").strip()[:120]


def _link_dispatches(agents: dict[str, AgentRec]) -> None:
    """父的 dispatch 动作 ↔ 子 AgentRec:先按派发词开头对齐,退而按 id 前缀
    (CC 子代理 id = 'a' + name + '-' + hash)。连上后把名片抄给子,子 id 回写父动作。"""
    orphans = [c for c in agents.values() if c.parent is None and not c.id.startswith("__main__")]
    for a in agents.values():
        for act in a.actions:
            if act.kind != "dispatch" or not act.ok:
                continue
            name = str(act.detail.get("name") or "")
            want = _head(act.detail.get("prompt"))
            hit = next((c for c in orphans if c.parent is None and want
                        and _head(c.prompt) == want), None)
            if hit is None and name:
                hit = next((c for c in orphans if c.parent is None
                            and c.id.startswith(f"agent-a{name}-")), None)
            if hit is None:
                continue
            hit.parent, hit.parent_ver = a.id, act.ver
            hit.name = hit.name or (name or None)
            hit.kind = hit.kind or act.detail.get("subagent_type")
            hit.description = hit.description or act.detail.get("description")
            hit.model = hit.model or act.detail.get("model")
            act.detail["child"] = hit.id


def build_ledger(agents: dict[str, AgentRec]) -> Ledger:
    for a in agents.values():
        _number(a)
    _link_dispatches(agents)
    events = [ref.ev for a in agents.values() for act in a.actions for ref in act.files]
    stories = build_stories(events)
    index: dict[tuple[str, int], int] = {}
    certain: dict[tuple[str, int], bool] = {}
    for path, st in stories.items():
        for ver in st.versions:
            index[(path, ver.seq)] = ver.v
        for r in st.reads:
            index[(path, r.seq)] = r.version
            certain[(path, r.seq)] = r.certain
    feeds: dict[tuple[str, int], int] = {}
    for a in agents.values():
        for act in a.actions:
            for ref in act.files:
                ref.v = index.get((ref.path, ref.ev.seq))
                if ref.op == "read":
                    feeds[(ref.path, ref.ev.seq)] = act.at
                    ref.certain = certain.get((ref.path, ref.ev.seq), True)
    return Ledger(stories, agents, feeds)


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


def action_raw(ledger: Ledger, agent_id: str, seq: int) -> dict[str, Any] | None:
    """按指针展开一次工具调用的完整 input / output(原始记录,不经任何摘要)。"""
    a = ledger.agents.get(agent_id) or ledger.agents.get(f"agent-{agent_id}")
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
    if isinstance(res_rec, dict):
        tur = res_rec.get("toolUseResult")
    return {"seq": act.seq, "ts": act.ts, "tool": act.tool, "kind": act.kind, "ok": act.ok,
            "ver": act.ver, "at": act.at, "input": inp, "output": out,
            "tool_use_result": tur, "src": {"path": path, "use_line": use_idx, "result_line": res_idx}}


def blame(ledger: Ledger, hint: str, v: int | None = None,
          start: int | None = None, n: int | None = None) -> dict[str, Any] | None:
    """逐行归属:文件@v 的每一行是谁在哪一版写的(逐行签名,确定性)。
    内容未知的版本如实报 known=False、不给行;窗口 start/n 只裁输出,汇总仍按全文。"""
    path = find_story_path(ledger.stories, hint)
    if path is None:
        return None
    st = ledger.stories[path]
    if not st.versions:
        return {"path": path, "v": 0, "n_versions": 0, "known": False, "n_lines": 0,
                "lines": [], "summary": [], "unknown": 0}
    anchor = min(max(v or len(st.versions), 1), len(st.versions))
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
            "v": ver.v, "ts": ver.ts, "by": ver.by,
            "by_name": _agent_label(ledger.agents, ver.by),
            "by_ver": ver.by_ver, "via": ver.via, "source": ver.source,
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
                "v": r.version, "at": ledger.feeds.get((path, r.seq)),
                "start": r.start, "n": r.n, "dep": r.dep, "certain": r.certain,
                "seen": [list(x) for x in r.seen] if r.seen else None}
               for r in st.reads]
    return {
        "path": path, "v": vers[-1].v if vers else 0, "n_versions": len(st.versions),
        "versions": out, "readers": readers,
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
            "n_reads": len(st.reads),
        })
    agents = []
    for a in ledger.agents.values():
        agents.append({
            "id": a.id, "label": _agent_label(ledger.agents, a.id) or a.id,
            "kind": a.kind, "session": a.session, "parent": a.parent,
            "parent_ver": a.parent_ver, "n_versions": a.n_versions,
            "n_reads": sum(1 for act in a.actions for ref in act.files if ref.op == "read"),
            "first_ts": a.actions[0].ts if a.actions else "",
        })
    agents.sort(key=lambda x: (x["session"], x["first_ts"]))
    return {"files": files, "agents": agents}


def _versions_at(st: FileStory, ts: str) -> int:
    return sum(1 for ver in st.versions if ver.ts <= ts)


def agent_atom(ledger: Ledger, agent_id: str, v: int | None = None) -> dict[str, Any] | None:
    """版本 agent:≤ver 的全部动作(读绑文件版本、写产出版本)、派发指令、收件箱、
    父/子边、收尾输出。v=None = 整个生命周期(锚之后的动作打 after_anchor)。"""
    a = ledger.agents.get(agent_id) or ledger.agents.get(f"agent-{agent_id}")
    if a is None:
        return None
    n = a.n_versions
    anchor = n if v is None else max(0, min(v, n))
    written = {ref.path for act in a.actions for ref in act.files if ref.op != "read"}
    effect_ts = {act.ver: act.ts for act in a.actions if act.ver is not None}

    def keep(act: Action) -> bool:
        if v is None:
            return True
        return act.ver <= anchor if act.ver is not None else act.at <= anchor

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
        row: dict[str, Any] = {"seq": act.seq, "ts": act.ts, "tool": act.tool, "kind": act.kind,
                               "ok": act.ok, "ver": act.ver, "at": act.at, "files": [],
                               "detail": detail, "expandable": act.src is not None}
        for ref in act.files:
            row["files"].append({"op": ref.op, "path": ref.path, "v": ref.v, "via": ref.ev.via})
            if ref.op == "read":
                st = ledger.stories.get(ref.path)
                anchor_ts = effect_ts.get(act.at) or act.ts
                latest = _versions_at(st, anchor_ts) if st else None
                reads.append({
                    "seq": act.seq, "ts": ref.ev.ts, "path": ref.path, "v": ref.v, "via": ref.ev.via,
                    "seen": [list(x) for x in ref.ev.seen] if ref.ev.seen else None,
                    "start": ref.ev.start, "n": ref.ev.n, "full": ref.ev.full, "dep": ref.ev.dep,
                    "certain": ref.certain,
                    "at": act.at, "after_anchor": act.at > anchor,
                    "self_written": ref.path in written,
                    "latest_v": latest,
                    "stale": bool(latest is not None and ref.v is not None and ref.v < latest),
                })
            else:
                writes.append({"ts": ref.ev.ts, "path": ref.path, "v": ref.v, "op": ref.op,
                               "ver": act.ver, "via": ref.ev.via})
        timeline.append(row)
    parent = None
    if a.parent:
        parent = {"id": a.parent, "ver": a.parent_ver,
                  "name": _agent_label(ledger.agents, a.parent)}
    children = [{"id": act.detail.get("child"), "name": act.detail.get("name"), "ver": act.ver}
                for act in acts if act.kind == "dispatch" and act.ok]
    inbox = [{"ts": act.ts, "from": act.detail.get("from"), "summary": act.detail.get("summary"),
              "text": act.detail.get("text"), "at": act.at, "after_anchor": act.at > anchor}
             for act in acts if act.kind == "inbox"]
    return {
        "id": a.id, "session": a.session, "name": a.name, "kind": a.kind,
        "description": a.description, "model": a.model,
        "label": _agent_label(ledger.agents, a.id) or a.id,
        "parent": parent, "prompt": a.prompt, "inbox": inbox, "children": children,
        "n_versions": n, "v": anchor,
        "reads": reads, "writes": writes, "actions": timeline,
        "result": {"text": a.result, "after_anchor": True} if a.result else None,
    }
