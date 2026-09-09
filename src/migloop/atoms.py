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

import bisect
import difflib
import hashlib
import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import cache
from typing import Any

from migloop.evidence import FileProof, proof_payload

from migloop.filestory import (
    EXTERNAL,
    OUTBAND,
    Ev,
    FileStory,
    Touch,
    build_stories,
    find_story_path,
    line_origins,
    ts_norm,
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
    observation_uncertain: bool = False  # 调用窗口与写入重叠,快照取得时刻无法确定

    @property
    def proof(self) -> FileProof | None:
        return self.ev.proof


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
    done_ts: str | None = None  # 结果返回时刻:读的内容这一刻才进上下文,喂的版本按它算(评审反例:写之后才返回的读)
    blk: int = 0               # 原始 content 数组的块下标;混合 think/text/tool_use 也不碰撞


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
class Mention:
    """一条命令提到了这个路径(命令行 / heredoc 体 / 跑的脚本正文里出现),不论账本有没有解出读写。"""
    ts: str
    seq: int
    by: str
    by_ver: int
    token: str
    ctx: str
    ambiguous: bool = False     # 只给了文件名,池里同名文件不止一个
    stage: str | None = None
    where: str = "in"           # in = 命令行;body = heredoc / 脚本正文;out = 工具输出
    cls: str = "other"          # change / readonly / body / out / other:分档只决定默认折不折,不影响可达


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
    #: 动作号 → "行号·转录标识"(渲染用):#n 是本次建账的句柄,账本重建后会漂;@L行·标识不漂,核验按它
    locs: dict[int, str] = field(default_factory=dict)
    #: (转录标识, 行号, 块号) → 动作号:报告里的引用反查,#n 漂了也能对回去
    by_loc: dict[tuple[str, int, int], int] = field(default_factory=dict)
    #: 撞了键的位置(理论上不该有):核验时报歧义,不能 first-wins
    loc_ambiguous: set[tuple[str, int, int]] = field(default_factory=set)
    line_blocks: dict[tuple[str, int], set[int]] = field(default_factory=dict)
    scan_gaps: list[dict[str, Any]] = field(default_factory=list)
    #: 转录标识 → 转录路径;旧格式短标识(8 位 / 带名字)→ 新标识,不唯一的记 None(报歧义,不猜)
    tag_paths: dict[str, str] = field(default_factory=dict)
    legacy_tags: dict[str, str | None] = field(default_factory=dict)
    #: (path, 读事件 seq) → 读它那次调用的动作号:文件原子的读者行带展开指针
    read_act: dict[tuple[str, int], int] = field(default_factory=dict)
    #: 上游最长链(建账时 DP 一遍算完):键 ("f", path, v) / ("a", agent, k),值 = 到池外为止最多经过几次
    #: agent↔文件转换(派发也算一跳)。depth_max 按累计读(写之前读过的一切都是前驱,诚实上界),depth_win 只按窗口读
    depth_max: dict[tuple[str, str, int], int] = field(default_factory=dict)
    depth_win: dict[tuple[str, str, int], int] = field(default_factory=dict)
    #: 提到它的命令:路径 → 按时间排的 Mention。等于原始转录按文件名 grep 的结果,解析器放弃的也在
    mentions: dict[str, list[Mention]] = field(default_factory=dict)
    #: 动作号 → 它提到的文件(反向索引:search 命中行、agent 槽里的「可能碰了」用)
    mention_seq: dict[int, list[str]] = field(default_factory=dict)
    #: 全池有写能力的命令 (ts, seq, agent),按时刻排:断点窗口里「谁可能改的」按它数,不解析脚本
    write_cmds: list[tuple[str, int, str]] = field(default_factory=list)
    #: A tag shared by distinct source paths is ambiguous at every line, not just overlapping lines.
    tag_conflicts: dict[str, list[str]] = field(default_factory=dict)
    #: 建账完成时冻结;查询期间源文件的 mtime / 内容变化不能改写这本内存账本的身份。
    _identity: str | None = field(default=None, init=False, repr=False)


LEDGER_CODE_VERSION = "atoms-2026-09-09-file-evidence5"


@cache
def _builder_fingerprint() -> str:
    """构建器代码内容摘要,进程内一次;换机器或换行格式不改变它。"""
    h = hashlib.sha256()
    for name in ("atoms.py", "atoms_collect.py", "filestory.py", "filestory_collect.py", "shellparse.py", "audit.py", "evidence.py"):
        h.update(name.encode("ascii"))
        path = os.path.join(os.path.dirname(__file__), name)
        with open(path, "rb") as fh:
            h.update(fh.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def ledger_identity(ledger: Ledger) -> str:
    """冻结的建账摘要:构建器 + 转录内容 + 实际节点/动作映射,不使用活源 mtime。

    build_ledger 完成时调用一次;直接构造的 Ledger 首次调用时冻结。逐文件 / 逐条流式摘要,
    不保存第二份账本,不重放历史。后续修改源文件需要重新建账才能得到新身份。
    """
    if ledger._identity is not None:
        return ledger._identity
    h = hashlib.sha256(_builder_fingerprint().encode("ascii"))

    def add(value: Any) -> None:
        h.update(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii"))
        h.update(b"\n")

    def digest(text: str | None) -> str | None:
        return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest() if text is not None else None

    sources = [(tag, source) for tag, path in ledger.tag_paths.items()
               for source in ledger.tag_conflicts.get(tag, [path])]
    for tag, path in sorted(sources):
        source = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    source.update(chunk)
            signature = source.hexdigest()
        except OSError:
            signature = "missing"
        add(["source", tag, os.path.basename(path), signature])
    for aid, agent in sorted(ledger.agents.items()):
        add(["agent", aid, agent.session, agent.name, agent.parent, agent.parent_ver,
             digest(agent.prompt), digest(agent.result)])
        for act in agent.actions:
            add(["action", act.seq, act.ver, act.at, act.ts, act.done_ts, act.kind, act.tool, act.ok,
                 act.tuid, act.blk, ledger.locs.get(act.seq), act.detail])
            for ref in act.files:
                add(["ref", ref.op, ref.path, ref.v, ref.certain, ref.ev.dep, ref.ev.conditional,
                     ref.ev.start, ref.ev.n, ref.ev.full, ref.ev.seen, digest(ref.ev.content),
                     ref.ev.use_ts, ref.ev.done_ts, ref.observation_uncertain, proof_payload(ref.proof)])
    for path, story in sorted(ledger.stories.items()):
        add(["file", path])
        for ver in story.versions:
            add(["version", ver.v, ver.ts, ver.seq, ver.by, ver.by_ver, ver.act_seq, ver.source, ver.via,
                 ver.conditional, ver.state_gap, digest(ver.content), digest(ver.partial), digest(ver.diff), proof_payload(ver.proof)])
    ledger._identity = f"{LEDGER_CODE_VERSION}:{len(ledger.tag_paths)}:{h.hexdigest()[:24]}"
    return ledger._identity


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
    effects: list[tuple[str, int]] = []
    for act in a.actions:
        if act.kind in EFFECTS and act.ok:
            n += 1
            act.ver = n
            act.at = n
            effects.append((act.ts, act.seq))
        else:
            act.ver = None
            act.at = n + 1
    # 输入喂的版本按完成时刻算:结果返回之前发生的效应不可能用到它
    # (评审反例:00:00 发起 Read、00:10 Write、00:20 才返回 —— 那次读不是 v1 的输入)
    for act in a.actions:
        if act.ver is None and act.done_ts and act.done_ts > act.ts:
            act.at = 1 + sum(1 for ts_, seq_ in effects if (ts_, seq_) < (act.done_ts, act.seq))
        for ref in act.files:
            ref.ev = replace(ref.ev, aver=act.ver)


def event_id(ledger: Ledger, agent_id: str, seq: int) -> str | None:
    """事件的稳定身份:会话 + 转录文件名 + tool_use_id(没有 id 的记录用转录行号/原始块号)。
    动作号 #n 只是本次建账的句柄,解析器多认出一条读它就变;这个不变。"""
    a = resolve_agent(ledger, agent_id)
    act = next((x for x in a.actions if x.seq == seq), None) if a else None
    if a is None or act is None:
        return None
    stem = os.path.splitext(os.path.basename(act.src[0]))[0] if act.src else a.id
    tail = (act.tuid if act.tuid else
            f"message:{act.detail['source_event_id']}" if act.detail.get("source_event_id") else
            f"L{act.src[1] + 1}/{act.blk}" if act.src else f"seq{act.seq}")
    return f"{a.session}:{stem}:{tail}"


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
    for a in agents.values():
        for act in a.actions:
            # 必须先进入重建引擎,不能 build_stories 后才补一条展示用虚线。
            candidates = (set(act.detail.get("conditional") or []) | set(act.detail.get("touched") or [])
                          | set(act.detail.get("effect_candidates") or []))
            for p in candidates:
                events.append(Ev(act.ts, act.seq, "candidate", p, a.id, stage=act.stage,
                                 use_ts=act.ts, done_ts=act.done_ts))
                if act.done_ts and act.done_ts != act.ts:
                    events.append(Ev(act.done_ts, act.seq, "candidate", p, a.id, stage=act.stage,
                                     use_ts=act.ts, done_ts=act.done_ts))
    stories = build_stories(events)
    _sweep_phantoms(stories)
    index: dict[tuple[str, int], int] = {}
    certain: dict[tuple[str, int], bool] = {}
    observation_uncertain: dict[tuple[str, int], bool] = {}
    for path, st in stories.items():
        for ver in st.versions:
            index[(path, ver.seq)] = ver.v
        for r in st.reads:
            index[(path, r.seq)] = r.version
            certain[(path, r.seq)] = r.certain
            observation_uncertain[(path, r.seq)] = r.observation_uncertain
    feeds: dict[tuple[str, int], int] = {}
    act_seq: dict[tuple[str, int], int] = {}
    read_act: dict[tuple[str, int], int] = {}
    lines: dict[int, int] = {}
    locs: dict[int, str] = {}
    by_loc: dict[tuple[str, int, int], int] = {}
    loc_ambiguous: set[tuple[str, int, int]] = set()
    line_blocks: dict[tuple[str, int], set[int]] = {}
    for a in agents.values():
        for act in a.actions:
            if act.src is not None:
                line_blocks.setdefault((transcript_tag(act.src[0]), act.src[1] + 1), set()).add(act.blk)
    for a in agents.values():
        for act in a.actions:
            if act.src is not None:
                lines[act.seq] = act.src[1] + 1
                tag = transcript_tag(act.src[0])
                block_needed = act.blk or len(line_blocks[(tag, act.src[1] + 1)]) > 1
                locs[act.seq] = f"{act.src[1] + 1}{'/' + str(act.blk) if block_needed else ''}·{tag}"
                key = (tag, act.src[1] + 1, act.blk)
                if key in by_loc and by_loc[key] != act.seq:
                    loc_ambiguous.add(key)                    # 撞键:核验时报歧义,不自动认第一个
                else:
                    by_loc[key] = act.seq
            for ref in act.files:
                ref.v = index.get((ref.path, ref.ev.seq))
                if ref.op == "read":
                    feeds[(ref.path, ref.ev.seq)] = act.at
                    ref.certain = certain.get((ref.path, ref.ev.seq), False)
                    ref.observation_uncertain = observation_uncertain.get((ref.path, ref.ev.seq), False)
                    read_act[(ref.path, ref.ev.seq)] = act.seq
                else:
                    act_seq[(ref.path, ref.ev.seq)] = act.seq
            # 脚本碰过但方向不明的路径:不立版本,挂到文件原子上(没写过的文件也进目录),指针指回这次调用
            for p in act.detail.get("touched") or []:
                if p in (act.detail.get("conditional") or []):
                    continue  # same candidate compatibility alias; retain the more precise reason below
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                        str(act.detail.get("unresolved") or "方向不明"), act.stage))
            for p in (set(act.detail.get("effect_candidates") or []) - set(act.detail.get("touched") or [])
                      - set(act.detail.get("conditional") or [])):
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                        "语法识别的可能效应,执行未知", act.stage))
            # 条件分支里的效应:不进正式状态(评审反例:false && 写 A,文件没变,账本却多出一版和一次「实录外修改」),记候选
            for p in act.detail.get("conditional") or []:
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                        "条件分支,是否执行未知(候选写)", act.stage))
            for p in act.detail.get("conditional_reads") or []:
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.at,
                                        "条件分支,读取未获证实(不是已见输入)", act.stage))
            for candidate in act.detail.get("read_candidates") or []:
                if candidate["path"] in (act.detail.get("conditional_reads") or []):
                    continue
                st = stories.setdefault(candidate["path"], FileStory(candidate["path"]))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.at,
                                        "输出定位线索,读取执行未获证实(非确定正文读)", act.stage))
            # 存在性守卫里探过的路径:文件当时可能不存在,只留指针
            for p in act.detail.get("probed") or []:
                st = stories.setdefault(p, FileStory(p))
                st.touches.append(Touch(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                        "存在性探测,内容未进上下文", act.stage))
            for p in act.detail.get("script_mentions") or []:
                stories.setdefault(p, FileStory(p))  # Navigation only: no version, author, read or state barrier.
    _sweep_phantoms(stories)  # New mention/probe-only paths must not reintroduce basename ghosts.
    # 目录级线索:建了目录 / --out 指到目录 / 脚本正文写着这个目录 的运行,该目录下首见即外部的文件挂
    # 「可能由此次运行生成」—— 只看首见之前的运行(生成后几小时才被读是常态),最近的 3 次,不立版本不猜
    runs_by_dir: dict[str, list[tuple[str, str, Action]]] = {}
    for a in agents.values():
        for act in a.actions:
            for d in act.detail.get("out_dirs") or []:
                runs_by_dir.setdefault(d.rstrip("/") + "/", []).append((act.ts, a.id, act))
    # 覆盖面过大的目录不算线索:工程根(ROOT = Path("/…/aippt_0723"))曾让全工程的文件都挂到 api-inventory 的脚本上
    n_all = max(len(stories), 1)
    runs_by_dir = {p: r for p, r in runs_by_dir.items()
                   if not ((cnt := sum(1 for path in stories if path.startswith(p))) >= 50 and cnt >= n_all * 0.25)}
    if runs_by_dir:
        batches: dict[tuple[int, ...], list[FileStory]] = {}
        for path, st in stories.items():
            if not (st.versions and st.versions[0].source == "external"):
                continue
            cands: dict[int, tuple[str, str, Action, int]] = {}
            for prefix, runs in runs_by_dir.items():
                if not path.startswith(prefix):
                    continue
                for ts_, aid_, act_ in runs:
                    if ts_ <= st.versions[0].ts and (act_.seq not in cands or len(prefix) > cands[act_.seq][3]):
                        cands[act_.seq] = (ts_, aid_, act_, len(prefix))
            # 前缀最长的运行最像生成者;同样长的取最早那次(之后的是补丁);最多留 3 个候选
            recent = [r[:3] for r in sorted(cands.values(), key=lambda x: (-x[3], x[0]))[:3]]
            for _ts, aid, act in recent:
                st.touches.append(Touch(act.ts, act.seq, aid, act.ver if act.ver is not None else act.at,
                                        "可能由此次运行生成(目录级线索)", act.stage))
            # 候选只导航不入账:跑过一个可能输出到这个目录的脚本,不证明这个文件是它生成的
            # (评审反例:--out-dir 跑完输出「nothing changed」,文件仍被记成它生成)。作者仍是外部输入,
            # 候选运行号留在 gen_runs,file() 摆出来让人判;0723 那 102 份页面 spec 由此是「外部输入 + 候选运行」
            v0 = st.versions[0]
            v0.gen_runs = tuple(a.seq for _t, _a, a in recent)
            batches.setdefault(v0.gen_runs, []).append(st)
        for sts in batches.values():
            for st in sts:
                st.versions[0].batch = len(sts)
    # 渲染器写出的文件:正文以字面量出现在脚本调用参数里 —— 按文件名挂成首版的部分内容,写者 = 跑脚本的 agent
    partials: dict[str, list[tuple[str, str, Action, str]]] = {}
    for a in agents.values():
        for act in a.actions:
            for name, text in act.detail.get("partials") or []:
                partials.setdefault(name, []).append((act.ts, a.id, act, text))
    for path, st in stories.items():
        if not st.versions:
            continue
        v0 = st.versions[0]
        if v0.content is not None or v0.source not in ("external", "generated"):
            continue
        pcands = [c for c in partials.get(path.rsplit("/", 1)[-1], []) if c[0] <= v0.ts]
        if not pcands:
            continue
        _pts, paid, pact, ptext = pcands[-1]
        v0.partial = ptext
        if v0.source == "external":
            v0.by, v0.by_ver, v0.source, v0.via, v0.act_seq = paid, pact.at, "generated", "script-run", pact.seq
            v0.gen_runs = (pact.seq,)
        st.touches.append(Touch(pact.ts, pact.seq, paid, pact.at, "脚本字面量里给了正文(部分内容)", pact.stage))
    for path, st in stories.items():
        for ver in st.versions:
            if ver.source != "generated":
                ver.act_seq = act_seq.get((path, ver.seq))
        st.touches.sort(key=lambda t: (t.ts, t.seq))
    t0 = min((act.ts for a in agents.values() for act in a.actions if act.ts), default="")
    dmax, dwin = _upstream_depths(stories, agents)
    mentions = _command_mentions(stories, agents)
    mention_seq: dict[int, list[str]] = {}
    for path, lst in mentions.items():
        for m in lst:
            mention_seq.setdefault(m.seq, []).append(path)
    tag_paths: dict[str, str] = {}
    tag_sources: dict[str, dict[str, str]] = {}
    legacy: dict[str, str | None] = {}
    for a in agents.values():
        for act in a.actions:
            if act.src is None:
                continue
            tag = transcript_tag(act.src[0])
            tag_paths.setdefault(tag, act.src[0])
            source_key = os.path.normcase(os.path.abspath(act.src[0]))
            tag_sources.setdefault(tag, {}).setdefault(source_key, act.src[0])
            stem = os.path.splitext(os.path.basename(act.src[0]))[0]
            old = stem[6:14] if stem.startswith("agent-") else stem[:8]
            if old != tag:
                legacy[old] = None if (old in legacy and legacy[old] != tag) else tag
    ledger = Ledger(stories, agents, feeds, t0, lines=lines, read_act=read_act, depth_max=dmax, depth_win=dwin,
                  mentions=mentions, mention_seq=mention_seq, write_cmds=_write_capable_cmds(agents),
                  locs=locs, by_loc=by_loc, loc_ambiguous=loc_ambiguous, line_blocks=line_blocks,
                  tag_paths=tag_paths, legacy_tags=legacy,
                  tag_conflicts={tag: sorted(paths.values()) for tag, paths in tag_sources.items() if len(paths) > 1},
                  scan_gaps=[{"agent": a.id, "seq": act.seq,
                              "chars": act.detail.get("mentions_scan_truncated", 0),
                              "mentions": act.detail.get("mentions_truncated", 0),
                              "sources": act.detail.get("mentions_scan_sources", [])}
                             for a in agents.values() for act in a.actions
                              if act.detail.get("mentions_scan_truncated") or act.detail.get("mentions_truncated")])
    ledger_identity(ledger)
    return ledger


REF_RE = re.compile(r"#(?:([\w-]+):)?(\d+)@L(\d+)(?:/(\d+))?(?:·([\w-]+))?")


def resolve_tag(ledger: Ledger, tag: str) -> tuple[str | None, bool]:
    """报告里的转录标识 → 账本里的标识。精确 → 旧格式迁移(唯一才认)→ 前缀(≥4 位且唯一)。(None, True) = 歧义。"""
    if tag in ledger.tag_conflicts:
        return None, True
    if tag in ledger.tag_paths:
        return tag, False
    if tag in ledger.legacy_tags:
        t = ledger.legacy_tags[tag]
        return (t, False) if t and t not in ledger.tag_conflicts else (None, True)
    if len(tag) >= 4:
        cands = [t for t in ledger.tag_paths if t.startswith(tag)]
        if len(cands) == 1:
            return (None, True) if cands[0] in ledger.tag_conflicts else (cands[0], False)
        if cands:
            return None, True
    return None, False


def resolve_ref(ledger: Ledger, no: int, line: int, blk: int | None, tag: str | None) -> tuple[int | None, str]:
    """一条引用 → (现在的动作号, 状态)。ok / drifted(#n 漂了但位置唯一)/ ambiguous / missing / untagged。
    无标识一律不算可核;多动作记录缺块号也不能借动作号猜。"""
    if line < 1:
        return None, "missing"
    if tag:
        t, amb = resolve_tag(ledger, tag)
        if amb:
            return None, "ambiguous"
        if t is None:
            return None, "missing"
        if blk is None:
            blocks = ledger.line_blocks.get((t, line), set())
            if len(blocks) > 1:
                return None, "ambiguous"       # 缺 /块号不是 #n 漂移,不能偷偷指向第一个调用
            blk = next(iter(blocks), 0)
        key = (t, line, blk)
        if key in ledger.loc_ambiguous:
            return None, "ambiguous"
        hit = ledger.by_loc.get(key)
        if hit is None:
            return None, "missing"
        return hit, ("ok" if hit == no else "drifted")
    return None, "untagged"


def transcript_tag(path: str) -> str:
    """转录文件的标识:Codex rollout 取末尾完整 UUID/hex;Claude 主会话仍取前 8 位;子代理取末尾整段 hex(agent-aconv-apploaddlg-8ea392b08bb155da →
    8ea392b08bb155da)—— 截 8 位会撞(0723 有 17 个短标识各对两个文件)、带名字的会有非 hex 字符。引用 (#n@L行·标识) 里的那一截。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem.lower().startswith("rollout-"):
        # Codex prepends a timestamp; the stable session UUID is at the end.
        uuid = re.search(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$", stem, re.I)
        if uuid:
            return uuid.group(1).lower()
        hexadecimal = re.search(r"-([0-9a-f]{16,})$", stem, re.I)
        if hexadecimal:
            return hexadecimal.group(1).lower()
        return "rollout-" + hashlib.sha256(stem.encode("utf-8")).hexdigest()[:24]
    if stem.startswith("agent-"):
        m = re.search(r"([0-9a-f]+)$", stem)
        if m and len(m.group(1)) >= 4:
            return m.group(1)
        return re.sub(r"[^\w-]", "", stem[6:]) or stem
    return stem[:8]


def _write_capable_cmds(agents: dict[str, AgentRec]) -> list[tuple[str, int, str]]:
    """全池里可能写文件的命令:解出了写、分析器标了写能力、或压根没解出来的 Bash / PowerShell / exec,按时刻排。
    「实录外修改」的窗口里谁可能改的,按它数,不解析脚本(评审:不追脚本黑盒,靠时间圈候选)。"""
    rows: list[tuple[str, int, str]] = []
    for a in agents.values():
        for act in a.actions:
            if act.tool not in ("Bash", "PowerShell", "exec"):
                continue
            if (act.detail.get("write_capable") or act.detail.get("unresolved") or act.detail.get("conditional")
                    or any(ref.op != "read" for ref in act.files)
                    or any(len(m) > 4 and m[4] == "change" for m in act.detail.get("mentions") or [])):
                rows.append((act.ts, act.seq, a.id))
    rows.sort()
    return rows


def version_at(ledger: Ledger, path: str, ts: str) -> int:
    """那一刻文件在第几版(时刻 ≤ ts 的最后一版;0 = 还没有版本)。"""
    st = ledger.stories.get(path)
    return _versions_at(st, ts) if st else 0


def search_window_writes(ledger: Ledger, since_ts: str | None, until_ts: str | None,
                         q: str = "", cap: int = 60, *, q_any: list[str] | None = None) -> dict[str, Any]:
    """时间窗口 (since_ts, until_ts] 里全池有写能力的命令,q 过滤命令文本。只按时间圈,不解析脚本。"""
    from . import search_terms
    terms = search_terms.normalize(q, q_any)
    by_seq = {act.seq: (a, act) for a in ledger.agents.values() for act in a.actions}
    ql = (q or "").lower()
    rows: list[dict[str, Any]] = []
    n = 0
    missing_input = 0
    unknown_times = 0
    for ts, seq, aid in ledger.write_cmds:
        if terms and not search_terms.valid_time(ts):
            unknown_times += 1
            continue
        key = ts_norm(ts) if terms else ts
        if (since_ts and key <= (ts_norm(since_ts) if terms else since_ts)) \
                or (until_ts and key > (ts_norm(until_ts) if terms else until_ts)):
            continue
        _a, act = by_seq[seq]
        cmd = str(act.detail.get("cmd") or act.detail.get("args") or "")
        if terms:
            original_input = None
            if act.src is not None:
                path, use, _ = act.src
                try:
                    lines = _transcript_lines(path)
                    if type(use) is int and use >= 0:
                        record = json.loads(lines[use])
                        if isinstance(record, dict):
                            original_input = _record_texts(record, act).get("input")
                except (OSError, IndexError, ValueError, TypeError):
                    pass
            if original_input is None:
                missing_input += 1
                continue
            cmd = original_input
        matched = search_terms.scan(cmd, terms) if terms else None
        if (terms and matched is None) or (not terms and ql and ql not in cmd.lower()):
            continue
        n += 1
        if not terms and len(rows) >= cap:
            continue
        effects = ", ".join(f"写 {f.path.rsplit('/', 1)[-1]}@v{f.v}" for f in act.files if f.op != "read")
        rows.append({"ts": ts, "t": rel_time(ts, ledger.t0), "seq": seq, "by": aid,
                     "by_ver": act.ver if act.ver is not None else act.at, "cmd": cmd[:160],
                     "effects": effects, "unresolved": act.detail.get("unresolved")})
        if terms:
            rows[-1].update(matched or {})
            rows[-1].update(record_key=("action", aid, seq, "input"), agent=aid, field="input",
                            kind=act.kind, tool=act.tool, at=act.at, ver=act.ver,
                            line=ledger.locs.get(seq), action_ok=act.ok)
    result = {"rows": rows, "n": n, "n_agents": len(ledger.agents)}
    if terms:
        result["unknown_inputs"] = missing_input
        result["unknown_times"] = unknown_times
    return result


def _command_mentions(stories: dict[str, FileStory], agents: dict[str, AgentRec]) -> dict[str, list[Mention]]:
    """每条命令里长得像路径的词对到账本里的文件:带目录的按后缀对,只有文件名的对所有同名文件(标 ambiguous)。"""
    by_base: dict[str, list[str]] = {}
    for path in stories:
        by_base.setdefault(path.rsplit("/", 1)[-1].lower(), []).append(path)
    known_dirs = {p.rsplit("/", 1)[0] for p in stories if "/" in p}
    out: dict[str, list[Mention]] = {}
    for a in agents.values():
        for act in a.actions:
            for item in act.detail.get("mentions") or []:
                tok, ctx = str(item[0]), str(item[1])
                absp = str(item[2]) if len(item) > 2 and item[2] else None
                low = tok.lower()
                cands = by_base.get(low.rsplit("/", 1)[-1], [])
                if "/" in low:
                    cands = [p for p in cands if p.lower() == low or p.lower().endswith("/" + low)]
                if not cands and absp and absp not in stories and absp.rsplit("/", 1)[0] in known_dirs:
                    # 只被提到、从没读写过的文件也要有入口;只在目录已知时建,输出里的垃圾路径不进目录
                    stories[absp] = FileStory(absp)
                    by_base.setdefault(absp.rsplit("/", 1)[-1].lower(), []).append(absp)
                    cands = [absp]
                where = str(item[3]) if len(item) > 3 else "in"
                cls = str(item[4]) if len(item) > 4 else "other"
                for p in cands:
                    out.setdefault(p, []).append(Mention(act.ts, act.seq, a.id, act.ver if act.ver is not None else act.at,
                                                         str(tok), str(ctx), ambiguous="/" not in low and len(cands) > 1,
                                                         stage=act.stage, where=where, cls=cls))
    for lst in out.values():
        lst.sort(key=lambda m: (m.ts, m.seq))
    return out


def mention_effect(ledger: Ledger, path: str, seq: int) -> str | None:
    """这条命令对这个文件,账本记到了什么:写@vN / 读 / 碰过(方向不明) / None = 没记到。"""
    st = ledger.stories.get(path)
    if st is None:
        return None
    for ver in st.versions:
        if ver.act_seq == seq:
            return f"写@v{ver.v}"
    for r in st.reads:
        if ledger.read_act.get((path, r.seq)) == seq:
            return "读"
    if any(t.seq == seq for t in st.touches):
        return "碰过(方向不明)"
    return None


_LEAF_SOURCES = frozenset({"external", "generated", "outband"})
_Node = tuple[str, str, int]


def _upstream_depths(stories: dict[str, FileStory],
                     agents: dict[str, AgentRec]) -> tuple[dict[tuple[str, str, int], int], dict[tuple[str, str, int], int]]:
    """上游最长链:每个节点到池外为止最多经过几次 agent↔文件转换(派发算一跳)。边全部指向更早的时刻,
    按时间序扫一遍就是 DP:depth = 1 + max(前驱);没有前驱(池外输入 / 批量生成 / 实录外)= 0。
    0723 全账本 5570 个节点 0.1 秒。累计口径下主会话跑了几百轮,每根都是二三百跳,它量的是管线深度;
    窗口口径量的是最近一轮手里的东西,两个都存,读的人自己选。"""
    items: list[tuple[str, int, _Node, list[_Node], list[_Node]]] = []   # (ts, 先后, 节点, 累计前驱, 窗口前驱)
    for aid, a in agents.items():
        effects = {act.ver: act for act in a.actions if act.ver is not None}
        reads_by_at: dict[int, list[_Node]] = {}
        for act in a.actions:
            for ref in act.files:
                if ref.op == "read" and ref.v:
                    reads_by_at.setdefault(act.at, []).append(("f", ref.path, ref.v))
        parent: list[_Node] = [("a", a.parent, a.parent_ver)] if a.parent and a.parent_ver else []
        for k, act in effects.items():
            cum = [n for at, ns in reads_by_at.items() if at <= k for n in ns] + parent
            win = list(reads_by_at.get(k, [])) + parent
            items.append((act.ts, 0, ("a", aid, k), cum, win))
    for path, st in stories.items():
        for ver in st.versions:
            pred: list[_Node] = ([("a", ver.by, ver.by_ver)]
                                if ver.source not in _LEAF_SOURCES and ver.by in agents and ver.by_ver else [])
            items.append((ver.ts, 1, ("f", path, ver.v), pred, pred))
    items.sort(key=lambda x: (x[0], x[1]))
    dmax: dict[_Node, int] = {}
    dwin: dict[_Node, int] = {}
    for _ts, _o, node, cum, win in items:
        best = max((dmax[p] for p in cum if p in dmax), default=-1)
        dmax[node] = best + 1 if best >= 0 else 0
        bw = max((dwin[p] for p in win if p in dwin), default=-1)
        dwin[node] = bw + 1 if bw >= 0 else 0
    return dmax, dwin


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
    if isinstance(raw, dict) and raw.get("type") in (None, "text", "input_text", "output_text"):
        return raw["text"] if isinstance(raw.get("text"), str) else ""
    if isinstance(raw, list):
        return "\n".join(text for x in raw if (text := _text_of(x)))
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
        payload = use_rec.get("payload")
        if isinstance(payload, dict) and payload.get("type") in ("message", "agent_message"):
            inp = _text_of(payload.get("content"))
        elif isinstance(payload, dict) and act.detail.get("source_event_type") == "base_instructions":
            base = payload.get("base_instructions")
            inp = str(base.get("text") or "") if isinstance(base, dict) else ""
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
            "source_event_id": act.detail.get("source_event_id"), "sender": act.detail.get("from"),
            "recipient": act.detail.get("recipient"), "claim_note": act.detail.get("claim_note"),
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
                      "since_v": o[1] if o else None, "inferred": bool(o and len(o) == 3), "text": text[i]})
    counts: dict[str, int] = {}
    unknown = 0
    for o in rows:
        if o is None:
            unknown += 1
        else:
            counts[o[0]] = counts.get(o[0], 0) + 1
    summary = [{"owner": k, "owner_name": _agent_label(ledger.agents, k), "n": c}
               for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    result = {"path": path, "v": anchor, "n_versions": len(st.versions), "known": known,
              "n_lines": len(text), "lines": lines, "summary": summary, "unknown": unknown}
    if not known:
        from .blame_recovery import build
        result["recovery"] = build(ledger, path, anchor)
    return result


def _blame_changed(ledger: Ledger, path: str, st: FileStory, anchor: int) -> dict[str, Any]:
    """修复版 v 替换/删除了前一版的哪些行、各是谁引入的 —— 归因第 4 步要的就是这几行。
    0723 调查基线里 agent 三次整文件 blame(32K/28K/12K 字符)都只为找它们;这里按 v-1 与 v 的
    行级 diff 直接挑出旧侧的 replace/delete 行,归属取自 v-1 的逐行签名,新增侧只给行数。"""
    base: dict[str, Any] = {"path": path, "v": anchor, "n_versions": len(st.versions), "changed": True,
                            "prev_v": anchor - 1 if anchor > 1 else None, "known": False,
                            "n_lines": None, "lines": [], "added": None, "removed": None,
                            "summary": [], "unknown": None, "note": "",
                            "comparison_basis": "unavailable", "comparison_note": ""}
    if anchor < 2:
        from .blame_recovery import build
        base["note"] = "无前版记录，无法比较；首个记录版本不是必然新建文件"
        base["recovery"] = build(ledger, path, anchor)
        return base
    prev, ver = st.versions[anchor - 2], st.versions[anchor - 1]
    if prev.content is None or ver.content is None:
        from .blame_recovery import build
        base["note"] = "前一版或本版内容未知,无法定位被替换行(见 file 的复原原因)"
        base["recovery"] = build(ledger, path, anchor)
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
                              "since_v": o[1] if o else None, "inferred": bool(o and len(o) == 3),
                              "text": old[i]})
        if tag in ("replace", "insert"):
            added += j2 - j1
    counts: dict[str, int] = {}
    unknown = 0
    for x in lines:
        if x["owner"] is None:
            unknown += 1
        else:
            counts[x["owner"]] = counts.get(x["owner"], 0) + 1
    observed = (prev.sealed or ver.sealed or prev.state_gap or ver.state_gap
                or prev.source == "outband" or ver.source == "outband" or ver.diff_kind in ("interval", "collapsed"))
    comparison_note = "计数只表示可观测文本端点的行级净差异，不证明业务行为无回归。"
    if observed:
        comparison_note += " 至少一个端点来自后续观测封口或区间重锚；0增0删不证明黑盒调用没有改写，期间经过仍未知。"
    base.update(known=True, n_lines=len(old), lines=lines, added=added, removed=len(lines), unknown=unknown,
                comparison_basis="observed_endpoints" if observed else "adjacent_version_text",
                comparison_note=comparison_note,
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
            "gen_runs": list(ver.gen_runs), "batch": ver.batch,
            "diff_kind": ver.diff_kind, "sealed": ver.sealed, "conditional": ver.conditional,
            "state_gap": ver.state_gap,
            "proof": proof_payload(ver.proof),
            "lines": len(ver.content.splitlines()) if ver.content else None,   # 末尾换行不算一行
            "has_diff": ver.diff is not None,
            "content_known": ver.content is not None,
            "partial_known": ver.content is None and ver.partial is not None,
        }
        if with_diff:
            row["diff"] = ver.diff
        out.append(row)
    content = vers[-1].content if vers else None
    partial = vers[-1].partial if (vers and content is None) else None
    readers = [{"by": r.by, "by_name": _agent_label(ledger.agents, r.by), "ts": r.ts,
                "t": rel_time(r.ts, ledger.t0), "seq": ledger.read_act.get((path, r.seq)), "via": r.via,
                "v": r.version, "at": ledger.feeds.get((path, r.seq)),
                "start": r.start, "n": r.n, "dep": r.dep, "certain": r.certain,
                "use_ts": r.use_ts, "done_ts": r.ts, "observation_uncertain": r.observation_uncertain,
                "seen": [list(x) for x in r.seen] if r.seen else None,
                "seen_n": len(r.seen or ()), "full": r.full, "proof": proof_payload(r.proof)}
               for r in st.reads]
    for reader in readers:
        # A read after the final effect is a real observation but its feeding
        # slot is not an existing agent version. Keep both facts distinct.
        owner = ledger.agents.get(reader["by"])
        slot = reader["at"]
        reader["feeding_slot"] = slot
        reader["agent_v"] = slot if owner and type(slot) is int and 1 <= slot <= owner.n_versions else None
        reader["after_last_effect"] = bool(owner and type(slot) is int and slot > owner.n_versions)
    touches = [{"by": t.by, "by_name": _agent_label(ledger.agents, t.by), "by_ver": t.by_ver,
                "ts": t.ts, "t": rel_time(t.ts, ledger.t0), "seq": t.seq, "reason": t.reason}
               for t in st.touches]
    vts = [ver.ts for ver in st.versions]

    def _win(ts: str) -> int | None:
        k = bisect.bisect_right(vts, ts)
        return k + 1 if k < len(vts) else None          # 落在第 k+1 版的窗口;最后一版之后 = None

    mentions = [{"by": m.by, "by_name": _agent_label(ledger.agents, m.by), "by_ver": m.by_ver, "ts": m.ts,
                 "t": rel_time(m.ts, ledger.t0), "seq": m.seq, "token": m.token, "ctx": m.ctx,
                 "ambiguous": m.ambiguous, "effect": mention_effect(ledger, path, m.seq),
                 "where": m.where, "cls": m.cls, "win": _win(m.ts)}
                for m in ledger.mentions.get(path, [])]
    # 每版的窗口 = 上一版时刻(不含)到这一版时刻(含):没记到的非只读提及数、全池有写能力的命令数(不含写它自己的那条)
    wts = [t for t, _s, _a in ledger.write_cmds]
    for row in out:
        i = row["v"]
        since, until = (vts[i - 2] if i >= 2 else ""), vts[i - 1]
        row["win_since"] = since
        wm = [m for m in mentions if m["win"] == i and m["effect"] is None]
        row["win_mentions"] = sum(1 for m in wm if m["cls"] != "readonly")
        row["win_change"] = sum(1 for m in wm if m["cls"] in ("change", "body", "out"))
        lo = bisect.bisect_right(wts, since) if since else 0
        hi = bisect.bisect_right(wts, until)
        row["win_writes"] = sum(1 for _t, s, _a in ledger.write_cmds[lo:hi] if s != row["seq"])
    return {
        "path": path, "v": vers[-1].v if vers else 0, "n_versions": len(st.versions),
        "versions": out, "readers": readers, "touches": touches, "mentions": mentions, "t0": ledger.t0,
        "content": content if with_content else None, "content_known": content is not None,
        "partial": partial if with_content else None, "partial_known": partial is not None,
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
            "n_unknown": sum(1 for ver in st.versions if ver.content is None),
            "n_reads": len(st.reads), "n_touches": len(st.touches),
            "n_mentions": len(ledger.mentions.get(path, [])),
            "n_mentions_unrecorded": sum(1 for m in ledger.mentions.get(path, [])
                                         if mention_effect(ledger, path, m.seq) is None),
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


def file_ref_payload(ref: FileRef) -> dict[str, Any]:
    """One evidence contract for action navigation and agent timelines; never erase uncertainty."""
    return {"op": ref.op, "path": ref.path, "v": ref.v, "via": ref.ev.via,
            "certain": ref.certain, "dep": ref.ev.dep, "conditional": ref.ev.conditional,
            "full": ref.ev.full, "start": ref.ev.start, "n": ref.ev.n,
            "seen": [list(x) for x in ref.ev.seen] if ref.ev.seen else None,
            "use_ts": ref.ev.use_ts, "done_ts": ref.ev.done_ts,
            "observation_uncertain": ref.observation_uncertain, "proof": proof_payload(ref.proof)}


def action_links(ledger: Ledger, agent_id: str, seq: int) -> dict[str, Any]:
    """一次调用两头的坐标:发自哪个 agent 的哪一版;账本记到它读写了哪些文件版本;命令里提到但没记到读写的文件
    当时在第几版(按时刻就近)。action 是两个原子之间的枢纽,file 的虚线行和 agent 槽里的命令都经它跳到对面。"""
    a = resolve_agent(ledger, agent_id)
    act = next((x for x in a.actions if x.seq == seq), None) if a else None
    if a is None or act is None:
        return {}
    slot = act.ver if act.ver is not None else act.at
    n = a.n_versions
    ver = slot if type(slot) is int and 1 <= slot <= n else None
    files = [file_ref_payload(f) for f in act.files]
    seen = {f.path for f in act.files}
    possible = []
    for path, lst in ledger.mentions.items():
        if path in seen:
            continue
        for m in lst:
            if m.seq == seq and mention_effect(ledger, path, seq) is None:
                st = ledger.stories.get(path)
                possible.append({"path": path, "v": _versions_at(st, act.ts) if st else 0,
                                 "ambiguous": m.ambiguous, "ctx": m.ctx})
                break
    return {"agent": a.id, "label": agent_label(ledger, a.id), "ver": ver, "agent_v": ver,
            "feeding_slot": act.at, "n_versions": n,
            "after_last_effect": type(slot) is int and slot > n, "is_effect": act.ver is not None,
            "files": files, "possible": possible}


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
            row["files"].append(file_ref_payload(ref))
            # 被作废的探测读(假前身)不列进读记录;图片读没有版本但要列(via=image)
            if ref.op == "read" and (ref.v is not None or ref.ev.via == "image"):
                st = ledger.stories.get(ref.path)
                anchor_ts = effect_ts.get(act.at) or act.ts
                latest = _versions_at(st, anchor_ts) if st else None
                reads.append({
                    **file_ref_payload(ref),
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
            elif ref.op != "read":
                writes.append({"ts": ref.ev.ts, "t": rel_time(ref.ev.ts, ledger.t0),
                               "path": ref.path, "v": ref.v, "op": ref.op,
                               "ver": act.ver, "via": ref.ev.via})
        timeline.append(row)
    parent = None
    if a.parent:
        pa = ledger.agents.get(a.parent)
        pseq = next((act.seq for act in (pa.actions if pa else [])
                     if act.kind == "dispatch" and act.detail.get("child") == a.id), None)
        parent = {"id": a.parent, "ver": a.parent_ver, "seq": pseq,
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

_TRANSCRIPT_CACHE: dict[str, tuple[tuple[int, int], list[str]]] = {}


def _transcript_lines(path: str) -> list[str]:
    """整份转录按行缓存(最多 4 份),键带 (mtime, size):转录追加后重建账本,search 不能还读旧行(评审反例)。"""
    try:
        stt = os.stat(path)
        sig = (stt.st_mtime_ns, stt.st_size)
    except OSError:
        sig = (0, 0)
    hit = _TRANSCRIPT_CACHE.get(path)
    if hit is None or hit[0] != sig:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().split("\n")
        if len(_TRANSCRIPT_CACHE) >= 4 and path not in _TRANSCRIPT_CACHE:
            _TRANSCRIPT_CACHE.pop(next(iter(_TRANSCRIPT_CACHE)))
        _TRANSCRIPT_CACHE[path] = (sig, lines)
        return lines
    return hit[1]


def _record_texts(rec: dict[str, Any], act: Action) -> dict[str, str]:
    """一条记录里可搜的文本,按字段:input(工具输入)/ output(工具输出,Read 的用边车里的全文按行号排)/
    text(正文、指令、收件、注入…)/ thinking。"""
    out: dict[str, str] = {}
    payload = rec.get("payload")
    if isinstance(payload, dict):
        kind = payload.get("type")
        if act.tuid is None and act.detail.get("source_event_type") == "base_instructions":
            base = payload.get("base_instructions")
            return {"text": str(base.get("text") or "") if isinstance(base, dict) else ""}
        if act.tuid is None and kind in ("message", "agent_message"):
            return {"text": _text_of(payload.get("content"))}
        if act.tuid is not None and str(payload.get("call_id")) == str(act.tuid):
            if kind in ("function_call", "custom_tool_call"):
                value = payload.get("arguments") if payload.get("arguments") is not None else payload.get("input")
                if kind == "function_call":
                    # Function arguments are JSON-encoded data, not custom code.
                    # Search decoded values (including paths) like Claude inputs;
                    # action_raw must continue returning the exact original input.
                    try:
                        decoded = json.loads(value) if isinstance(value, str) else value
                    except (ValueError, RecursionError):
                        decoded = None
                    pending, texts = [decoded], []
                    while pending:
                        item = pending.pop()
                        if isinstance(item, str):
                            texts.append(item)
                        elif isinstance(item, dict):
                            pending.extend(reversed(list(item.values())))
                        elif isinstance(item, list):
                            pending.extend(reversed(item))
                    if texts:
                        return {"input": "\n".join(texts)}
                return {"input": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}
            if kind in ("function_call_output", "custom_tool_call_output"):
                return {"output": _text_of(payload.get("output"))}
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
            raw_inp = b.get("input")
            inp: dict[str, Any] = raw_inp if isinstance(raw_inp, dict) else {}
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
                 until_ts: str | None = None, *, q_any: list[str] | None = None) -> dict[str, Any] | None:
    """在一个 agent 的记录里找词,只看喂养第 v 版及之前的(since 给了只看 (since, v]);派发者可改用时间区间
    since_ts / until_ts(由文件时间线上的两个版本给出)。锚点之后的命中只计数(after=True 才列),不混进因果。
    命中的字段按记录种类:工具动作看 input / output,说 / 想看正文,指令 / 收件 / 注入看文本。"""
    from . import search_terms
    terms = search_terms.normalize(q, q_any)
    a = resolve_agent(ledger, agent_id)
    if a is None:
        return None
    ql = q.lower()
    n = a.n_versions
    anchor = n if v is None else max(0, min(v, n))
    hits: list[dict[str, Any]] = []
    excluded = 0
    unknown_times = 0
    prompt_match = search_terms.scan(a.prompt, terms) if terms and a.prompt else None
    if a.prompt and (prompt_match is not None if terms else ql in a.prompt.lower()) and not (since_ts or until_ts):
        snips, cnt = ([], 0) if terms else _snips(a.prompt, ql)
        hits.append({"kind": "prompt", "tool": "prompt", "seq": None, "line": None, "at": 1, "ver": None,
                     "ts": "", "t": "", "field": "text", "target": None, "snips": snips, "n": cnt})
        if terms:
            hits[-1].update(prompt_match or {})
            hits[-1].pop("n")
            hits[-1].pop("snips")
            hits[-1].update(record_key=("prompt", a.id), agent=a.id)
    for act in a.actions:
        if act.src is None:
            continue
        k = act.ver if act.ver is not None else act.at
        if since_ts or until_ts:
            start, end = sorted((ts_norm(act.ts), ts_norm(act.done_ts or act.ts)))
            known_extent = act.done_ts is not None or act.src[1] == act.src[2]
            if terms and not (search_terms.valid_time(act.ts) and search_terms.valid_time(act.done_ts or act.ts)):
                known_extent = False
            if known_extent and ((since_ts and end < ts_norm(since_ts)) or (until_ts and start > ts_norm(until_ts))):
                continue
            in_window = True
        else:
            # 不带 v = 整个生命周期,锚点之后的也算(评审反例:最后一个效应之后说的话搜不到)
            in_window = (since is None or k > since) and (v is None or k <= anchor)
        path, ui, ri = act.src
        lines = _transcript_lines(path)
        idxs = [ui] + ([ri] if ri is not None and ri != ui else [])
        fields: dict[str, str] = {}
        field_times: dict[str, str] = {}
        term_matches: dict[str, dict[str, Any]] = {}
        for i in idxs:
            if i is None or i >= len(lines):
                continue
            try:
                rec = json.loads(lines[i])
            except Exception:
                continue
            for fld, text in _record_texts(rec, act).items():
                field_ts = str(rec.get("timestamp") or (act.done_ts if fld == "output" else act.ts) or act.ts)
                if terms and (since_ts or until_ts):
                    # Missing result time is not the invocation time. Keep a
                    # gap count instead of presenting it inside a precise window.
                    field_ts = str(rec.get("timestamp") or (act.done_ts if fld == "output" else act.ts) or "")
                    if not search_terms.valid_time(field_ts):
                        unknown_times += 1
                        continue
                if ((since_ts and ts_norm(field_ts) < ts_norm(since_ts))
                        or (until_ts and ts_norm(field_ts) > ts_norm(until_ts))):
                    continue
                if act.kind in ("say",) and fld != "text":
                    continue
                if act.kind == "think" and fld != "thinking":
                    continue
                if act.kind in ("inbox", "instruction", "inject", "system", "notify", "interrupt") and fld != "text":
                    continue
                if act.kind not in ("say", "think", "inbox", "instruction", "inject", "system", "notify", "interrupt") \
                        and fld not in ("input", "output"):
                    continue
                matched = search_terms.scan(text, terms) if terms else None
                if matched is not None if terms else ql in text.lower():
                    fields[fld] = text
                    field_times[fld] = field_ts
                    if matched is not None:
                        term_matches[fld] = matched
        if not in_window and not after:
            excluded += bool(fields)
            continue
        for fld, text in fields.items():
            snips, cnt = ([], 0) if terms else _snips(text, ql)
            target = None
            rs = [ref.path for ref in act.files if ref.op == "read"]
            ws = [ref.path for ref in act.files if ref.op != "read"]
            if fld == "output" and rs:
                target = rs[0] if len(rs) == 1 else None
            elif fld == "input" and ws:
                target = ws[0]
            hits.append({"kind": act.kind, "tool": act.tool, "seq": act.seq, "line": ledger.locs.get(act.seq),
                         "at": act.at, "ver": act.ver, "ts": field_times[fld], "t": rel_time(field_times[fld], ledger.t0),
                         "field": fld, "target": target,
                         "sender": act.detail.get("from"), "claim_note": act.detail.get("claim_note"),
                         "source_event_id": act.detail.get("source_event_id"),
                         "targets": rs if fld == "output" else ws,
                         "target_v": next((ref.v for ref in act.files if ref.path == target), None),
                         "possible": ([p for p in ledger.mention_seq.get(act.seq, [])
                                       if mention_effect(ledger, p, act.seq) is None]
                                      if fld == "input" and not ws else []),
                         "after": not in_window, "snips": snips, "n": cnt})
            if terms:
                hits[-1].update(term_matches[fld])
                hits[-1].pop("n")
                hits[-1].pop("snips")
                hits[-1].update(record_key=("action", a.id, act.seq, fld), agent=a.id, action_ok=act.ok)
    result = {"agent": a.id, "label": _agent_label(ledger.agents, a.id) or a.id, "q": q, "v": anchor, "since": since,
              "since_ts": since_ts, "until_ts": until_ts, "hits": hits, "excluded_after": excluded}
    if terms:
        result["unknown_times"] = unknown_times
    return result


def search_file(ledger: Ledger, hint: str, q: str, v: int | None = None, *,
                q_any: list[str] | None = None) -> dict[str, Any] | None:
    """在一个文件到第 v 版为止的内容里找词:哪几版含它(首次出现在第几版、谁写的),哪些读者的读结果里命中过。"""
    from . import search_terms
    terms = search_terms.normalize(q, q_any)
    path = find_story_path(ledger.stories, hint)
    if path is None:
        return None
    st = ledger.stories[path]
    ql = q.lower()
    vers = st.versions if v is None else st.versions[:max(v, 0)]
    rows = []
    for ver in vers:
        body, partial = (ver.content, False) if ver.content is not None else (ver.partial, True)
        matched = search_terms.scan(body, terms) if terms and body is not None else None
        if body is None or (matched is None if terms else ql not in body.lower()):
            continue
        snips = []
        for i, ln in enumerate(body.split("\n") if not terms else [], 1):
            if ql in ln.lower():
                snips.append((0 if partial else i, _WS.sub(" ", ln).strip()[:160]))
        rows.append({"v": ver.v, "by": ver.by, "by_ver": ver.by_ver, "seq": ver.act_seq,
                     "line": ledger.locs.get(ver.act_seq or -1), "t": rel_time(ver.ts, ledger.t0),
                     "snips": snips[:3], "n": len(snips), "partial": partial})
        if terms:
            rows[-1].update(matched or {})
            rows[-1].pop("n")
            rows[-1].pop("snips")
            rows[-1].update(record_key=("file", path, ver.v, "content"), path=path, field="content", kind="file")
    readers = []
    for r in st.reads:
        if not r.seen:
            continue
        if terms:
            if v is not None and r.version is not None and r.version > v:
                continue
            # Observed lines may have gaps. Never concatenate non-adjacent lines
            # into a fictitious multiline literal match or original field slice.
            line_matches = []
            found: set[str] = set()
            for ln, text in r.seen:
                match = search_terms.scan(text, terms)
                if match and set(match["matched_terms"]) - found:
                    line_matches.append((ln, match))
                    found.update(match["matched_terms"])
                if len(found) == len(terms):
                    break  # counts are source fields, not repeated line/term hits
            if not line_matches:
                continue
            matched = {"matched_terms": [term for term in terms if any(term in m["matched_terms"] for _, m in line_matches)],
                       "excerpts": [{**e, "observed_line": ln} for ln, m in line_matches for e in m["excerpts"]]}
            seq = ledger.read_act.get((path, r.seq))
            readers.append({"by": r.by, "agent": r.by, "at": ledger.feeds.get((path, r.seq)),
                            "v": r.version, "seq": seq, "line": ledger.locs.get(seq or -1),
                            "t": rel_time(r.ts, ledger.t0), "field": "output", "kind": "read",
                            "record_key": ("action", r.by, seq, "output") if seq is not None else ("observation", path, r.seq),
                            "read_subset": True, **matched})
            continue
        got = [(ln, _WS.sub(" ", t).strip()[:160]) for ln, t in r.seen if ql in t.lower()]
        if got:
            seq = ledger.read_act.get((path, r.seq))
            readers.append({"by": r.by, "at": ledger.feeds.get((path, r.seq)), "v": r.version,
                            "seq": seq, "line": ledger.locs.get(seq or -1), "t": rel_time(r.ts, ledger.t0),
                            "snips": got[:3], "n": len(got)})
    return {"path": path, "q": q, "v": len(vers), "n_versions": len(st.versions),
            "unknown": sum(1 for ver in vers if ver.content is None),
            "first": rows[0]["v"] if rows else None, "versions": rows, "readers": readers}


def search_pool(ledger: Ledger, q: str, until_ts: str, since_ts: str | None = None, *,
                q_any: list[str] | None = None) -> dict[str, Any]:
    """全池按词查,只允许带时间上限:until_ts 之前所有 agent 的记录 + 所有文件到那一刻为止的已知内容。
    用途是核否定 —— 「生成期没人见过 X」只能引用这种范围的零命中;找上游仍要走 agent / file 的边。"""
    from . import search_terms
    terms = search_terms.normalize(q, q_any)
    if terms:
        return _search_pool_any(ledger, terms, until_ts, since_ts)
    ql = q.lower()
    until_key = ts_norm(until_ts)
    since_key = ts_norm(since_ts) if since_ts else None
    files = []
    unknown = 0
    for path, st in ledger.stories.items():
        for ver in st.versions:
            version_key = ts_norm(ver.ts)
            if version_key > until_key or (since_key and version_key < since_key):
                continue
            body = ver.content if ver.content is not None else ver.partial
            if body is None:
                unknown += 1
                continue
            if ql in body.lower():
                ln, snip = next(((i, _WS.sub(" ", t).strip()[:160]) for i, t in enumerate(body.split("\n"), 1)
                                 if ql in t.lower()), (None, ""))
                files.append({"path": path, "v": ver.v, "by": ver.by, "by_ver": ver.by_ver, "seq": ver.act_seq,
                              "line": ledger.locs.get(ver.act_seq or -1), "t": rel_time(ver.ts, ledger.t0),
                              "ln": None if ver.content is None else ln, "snip": snip,
                              "n": sum(1 for t in body.split("\n") if ql in t.lower()),
                              "partial": ver.content is None})
                break                                          # 每个文件只报首次出现
    agents = []
    for aid in ledger.agents:
        res = search_agent(ledger, aid, q, since_ts=since_ts or ledger.t0 or "0", until_ts=until_ts)
        hits = [h for h in (res or {}).get("hits", []) if h.get("seq") is not None]
        # A call launched first can return last. Earliest output means the
        # matched field's recorded time, not its invocation's sequence number.
        hits.sort(key=lambda hit: (ts_norm(hit.get("ts")), hit["seq"], hit.get("field") or ""))
        if hits:
            h = hits[0]
            # A prompt mentioning a command must not hide that command's actual
            # returned output. Partition by recorded source, never by whether a
            # snippet agrees with a desired answer; preserve every hit in counts.
            groups: dict[str, list[dict[str, Any]]] = {}
            for hit in hits:
                if hit.get("claim_note") or hit["kind"] in ("say", "think", "inbox", "notify", "compact"):
                    source = "statement"
                elif hit["kind"] in ("instruction", "inject", "system", "prompt"):
                    source = "instruction"
                elif hit.get("field") == "output":
                    source = "tool_output"
                elif hit.get("field") == "input":
                    source = "tool_input"
                else:
                    source = "other"
                groups.setdefault(source, []).append(hit)
            sources = [{"source": source, "n": len(groups[source]), "first": groups[source][0]}
                       for source in ("tool_output", "tool_input", "statement", "instruction", "other")
                       if source in groups]
            agents.append({"agent": aid, "label": (res or {}).get("label") or aid,
                           "n": len(hits), "first": h, "sources": sources})
    return {"q": q, "until_ts": until_ts, "since_ts": since_ts, "files": files, "agents": agents,
            "unknown_versions": unknown, "n_agents": len(ledger.agents), "n_files": len(ledger.stories)}


def _search_pool_any(ledger: Ledger, terms: list[str], until_ts: str,
                     since_ts: str | None) -> dict[str, Any]:
    """One pass per source; do not lose later/rare literals to first-union-hit compression."""
    from . import search_terms
    rows: list[dict[str, Any]] = []
    unknown = 0
    partial = 0
    unknown_times = 0
    for path, story in ledger.stories.items():
        for ver in story.versions:
            if not search_terms.valid_time(ver.ts):
                unknown_times += 1
                continue
            stamp = ts_norm(ver.ts)
            if stamp > ts_norm(until_ts) or (since_ts and stamp < ts_norm(since_ts)):
                continue
            body = ver.content if ver.content is not None else ver.partial
            if body is None:
                unknown += 1
                continue
            partial += ver.content is None
            matched = search_terms.scan(body, terms)
            if matched:
                rows.append({"path": path, "v": ver.v, "by": ver.by, "by_ver": ver.by_ver,
                             "seq": ver.act_seq, "line": ledger.locs.get(ver.act_seq or -1),
                             "t": rel_time(ver.ts, ledger.t0), "partial": ver.content is None,
                             "record_key": ("file", path, ver.v, "content"), "field": "content", "kind": "file",
                             **matched})
    for aid in ledger.agents:
        result = search_agent(ledger, aid, "", since_ts=since_ts or ledger.t0 or "0",
                              until_ts=until_ts, q_any=terms)
        unknown_times += (result or {}).get("unknown_times", 0)
        rows.extend(h for h in (result or {}).get("hits", []) if h.get("seq") is not None)
    return {"q_any": terms, "rows": search_terms.unique_rows(rows), "unknown_versions": unknown,
            "partial_versions": partial, "unknown_times": unknown_times,
            "n_agents": len(ledger.agents), "n_files": len(ledger.stories),
            "since_ts": since_ts, "until_ts": until_ts}
