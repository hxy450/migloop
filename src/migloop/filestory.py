"""文件编年史引擎 + 生成链闭包 —— 返修链路的地基。

一句话:给每个文件写一本"编年史"(它什么时候被谁写成什么样、谁看过它、哪段
历史是空白),再从被修文件的版本出发把生成 DAG 离线算全。全部输入来自会话
实录,零磁盘、零推断;信息不在场就明确标"未知",不猜。

三层裁定(与用户逐条对齐,见 PR #95 讨论与 0723 复盘):

1. 观测即锚 —— Read/干净 cat 的结果就是该文件那一刻的真实快照。内容失联
   (脚本落盘/edit-miss)不再一票断死:下一张快照处重锚,段间续命;快照与
   已知状态不符 = 抓到实录外改动,记断点、立 ``__outband__`` 版本,链照走。
2. diff 是档位不是有无 —— native(edit 原生)/true(前态已知)/creation(整篇
   新增)/interval(观测封口,单笔可归属)/collapsed(多笔夹一起,归属糊)/
   unknown(信息不在场)。每笔写都有可点开的 diff 或明确的"为什么没有"。
3. 闭包与披露分离 —— 找全用**累积读边**(agent 在这笔写之前读过的一切,
   因为上下文是累积的,这是唯一因果诚实的完备判据);树先离线算完,每个
   agent 被拉入几次到此已知;然后按"被拉入的出现"切区间做披露归属:
   每条相关读恰好展示一次,后续出现只留「沿用 N 项」指针。渐进式披露是
   视觉行为,不是计算行为 —— 渲染层没有资格丢节点。
"""

from __future__ import annotations

import difflib
import heapq
from dataclasses import dataclass, field
from typing import Any

from migloop.audit import agent_is_fixer

#: 非 agent 的版本作者:外部输入(没人写过,链的天然叶子)与实录外改动
EXTERNAL = "__external__"
OUTBAND = "__outband__"

#: 出现的身份:(agent, ts, seq) —— 一笔写恰好一个出现,可排序可哈希
OccKey = tuple[str, str, int]
#: 版本节点的身份:(path, v)
VerKey = tuple[str, int]


@dataclass(frozen=True)
class Ev:
    """归一化事件。收集层(adapter/shellparse)负责把五花八门的原始记录
    翻译成这六种;引擎只认这个形状。"""

    ts: str
    seq: int
    kind: str                 # wfull | edit | wopaque | wderived | delete | read
    path: str
    agent: str
    content: str | None = None      # wfull 的全文;read 携带时=观测快照
    old: str | None = None          # edit
    new: str | None = None
    replace_all: bool = False
    src: str | None = None          # wderived 的来源文件
    start: int | None = None        # read 的行区间(命令自带才有,不编造)
    n: int | None = None
    full: bool = False              # read: 快照是否全文(只有全文才能当锚)
    dep: bool = False               # 依赖读(cp 源/< 输入):内容未进上下文
    aver: int | None = None         # 产出它的 agent 版本号(效应序号),收集层回填
    via: str = "tool"               # 来路:tool | shell | script(字面量推断)
    #: read: 从 stdout 对账出来的"看见了哪几行"((行号, 原文)…);grep -n / head 前缀
    seen: tuple[tuple[int, str], ...] | None = None
    stage: str | None = None        # 管线阶段(记录归属戳):版本文件据此知道每版写在哪个阶段


@dataclass
class Version:
    v: int
    ts: str
    seq: int
    by: str
    source: str               # full | delta | derived | opaque | delete | outband | external
    content: str | None       # None = 此刻内容未知(可能被后续观测封口)
    diff: str | None
    diff_kind: str            # creation | true | native | interval | collapsed | delete | external | unknown
    sealed: bool = False      # opaque 被观测封口
    by_ver: int | None = None  # 写者的 agent 版本号(观测/外部版本无)
    via: str = "tool"         # 写者来路;观测/外部 = observe
    stage: str | None = None  # 写这一版时的管线阶段(修复方判定:execute 之后即修复)


@dataclass
class ReadRec:
    ts: str
    seq: int
    by: str
    version: int              # 绑定的版本号(读那一刻编年史里它是第几版)
    start: int | None
    n: int | None
    certain: bool             # False = 状态未知时的就近绑定
    dep: bool = False
    seen: tuple[tuple[int, str], ...] | None = None   # 看见的行(行号, 原文)


@dataclass
class Break:
    ts: str
    seq: int
    path: str
    kind: str                 # edit-miss | outband-change
    detail: str


@dataclass
class FileStory:
    path: str
    versions: list[Version] = field(default_factory=list)
    reads: list[ReadRec] = field(default_factory=list)
    breaks: list[Break] = field(default_factory=list)


def _udiff(a: str | None, b: str | None) -> str | None:
    if b is None:
        return None
    lines = difflib.unified_diff(
        (a or "").splitlines(), b.splitlines(), lineterm="")
    return "\n".join(lines) or None


def _same(a: str, b: str) -> bool:
    # 快照常带/缺末尾换行,不构成"内容不同"
    return a.rstrip("\n") == b.rstrip("\n")


class _State:
    """单文件的构建期状态(不出货)。"""

    __slots__ = ("content", "interval_base", "pending")

    def __init__(self) -> None:
        self.content: str | None = None      # 当前已知内容;None=未知
        self.interval_base: str | None = None  # 上一个已知状态(区间 diff 的基)
        self.pending: list[int] = []          # 未封口的 opaque 版本下标


def build_stories(events: list[Ev]) -> dict[str, FileStory]:
    """事件(全局时间序)→ 每文件编年史。跨文件按同一时间轴处理,
    wderived(cp)因此能查到源文件"那一刻"的状态。"""
    stories: dict[str, FileStory] = {}
    states: dict[str, _State] = {}

    def story(path: str) -> tuple[FileStory, _State]:
        if path not in stories:
            stories[path] = FileStory(path)
            states[path] = _State()
        return stories[path], states[path]

    def add_version(st: FileStory, e: Ev, by: str, source: str,
                    content: str | None, diff: str | None, diff_kind: str) -> Version:
        own = by == e.agent
        v = Version(v=len(st.versions) + 1, ts=e.ts, seq=e.seq, by=by,
                    source=source, content=content, diff=diff, diff_kind=diff_kind,
                    by_ver=e.aver if own else None, via=e.via if own else "observe",
                    stage=e.stage if own else None)
        st.versions.append(v)
        return v

    def write_known(st: FileStory, s: _State, e: Ev, content: str, source: str) -> None:
        if s.content is not None:
            diff, kind = _udiff(s.content, content), "true"
        elif not st.versions:
            diff, kind = _udiff(None, content), "creation"
        else:
            diff, kind = None, "unknown"      # 前态永失:覆盖前没被看过
        add_version(st, e, e.agent, source, content, diff, kind)
        s.content = content
        s.interval_base = content
        s.pending = []                        # 未封口的到此永久失封(如实留白)

    def write_unknown(st: FileStory, s: _State, e: Ev, source: str) -> None:
        if s.content is not None:
            s.interval_base = s.content
        v = add_version(st, e, e.agent, source, None, None, "unknown")
        s.content = None
        s.pending.append(v.v - 1)

    for e in sorted(events, key=lambda x: (x.ts, x.seq)):
        st, s = story(e.path)
        if e.kind == "wfull":
            write_known(st, s, e, e.content or "", "full")
        elif e.kind == "wderived":
            # cp/mv = 对源的依赖读(内容未进上下文) + 对目标的写。依赖读落进
            # 源的编年史,闭包经它流过 cp,边标 dep。
            src_st, src_s = story(e.src or "")
            if not src_st.versions:
                add_version(src_st, e, EXTERNAL, "external", None, None, "external")
            src_st.reads.append(ReadRec(e.ts, e.seq, e.agent,
                                        len(src_st.versions), None, None,
                                        src_s.content is not None, dep=True))
            if src_s.content is not None:
                write_known(st, s, e, src_s.content, "derived")
            else:
                write_unknown(st, s, e, "derived")
        elif e.kind == "wopaque":
            write_unknown(st, s, e, "opaque")
        elif e.kind == "delete":
            # 终态为空是确定的:之后若再被观测到内容,就是有人重建(outband 接榫)
            add_version(st, e, e.agent, "delete", "",
                        _udiff(s.content, "") if s.content else None, "delete")
            s.content = ""
            s.interval_base = ""
            s.pending = []
        elif e.kind == "edit":
            old, new = e.old or "", e.new or ""
            native = _udiff(old, new)
            if s.content is not None and old and old in s.content:
                applied = (s.content.replace(old, new) if e.replace_all
                           else s.content.replace(old, new, 1))
                add_version(st, e, e.agent, "delta", applied, native, "native")
                s.content = applied
                s.interval_base = applied
            else:
                if s.content is not None:
                    st.breaks.append(Break(e.ts, e.seq, e.path, "edit-miss",
                                           f"old_string 不在已知内容中: {old[:60]!r}"))
                    s.interval_base = s.content
                # 盲写:发生过、diff 原生可看,但之后状态未知
                add_version(st, e, e.agent, "delta", None, native, "native")
                s.content = None
        elif e.kind == "read":
            self_read_version: int
            certain = True
            if e.content is not None and e.full:
                snap = e.content
                if s.content is not None:
                    if _same(s.content, snap):
                        self_read_version = len(st.versions)
                    else:
                        st.breaks.append(Break(e.ts, e.seq, e.path, "outband-change",
                                               "观测与已知状态不符 —— 实录外修改"))
                        add_version(st, e, OUTBAND, "outband", snap,
                                    _udiff(s.content, snap), "true")
                        s.content = snap
                        s.interval_base = snap
                        self_read_version = len(st.versions)
                elif s.pending:
                    idx = s.pending[-1]
                    ver = st.versions[idx]
                    ver.content = snap
                    ver.sealed = True
                    ver.diff = _udiff(s.interval_base, snap)
                    ver.diff_kind = "interval" if len(s.pending) == 1 else "collapsed"
                    s.pending = []
                    s.content = snap
                    s.interval_base = snap
                    self_read_version = len(st.versions)
                elif st.versions:
                    # 盲写/miss 之后的重锚:实录外的状态由观测揭示
                    add_version(st, e, OUTBAND, "outband", snap,
                                _udiff(s.interval_base, snap),
                                "true" if s.interval_base is not None else "unknown")
                    s.content = snap
                    s.interval_base = snap
                    self_read_version = len(st.versions)
                else:
                    # 外部输入:首见即读 —— 链的天然叶子
                    add_version(st, e, EXTERNAL, "external", snap, None, "external")
                    s.content = snap
                    s.interval_base = snap
                    self_read_version = 1
            else:
                if s.content is not None:
                    self_read_version = len(st.versions)
                elif st.versions:
                    self_read_version = len(st.versions)
                    certain = False
                else:
                    add_version(st, e, EXTERNAL, "external", None, None, "external")
                    self_read_version = 1
                    certain = False
            st.reads.append(ReadRec(e.ts, e.seq, e.agent, self_read_version,
                                    e.start, e.n, certain, e.dep, seen=e.seen))
        else:
            raise ValueError(f"未知事件类型: {e.kind}")
    return stories


# ═══════════════ 闭包:找全 + 披露归属 ═══════════════


@dataclass
class Dag:
    """生成链 DAG。闭包收敛后不可变;渲染层只做折叠/展开,没有资格丢节点。"""

    root: str
    version_nodes: dict[VerKey, Version] = field(default_factory=dict)
    occurrences: dict[OccKey, VerKey] = field(default_factory=dict)   # 出现 → 它产出的版本
    edges: list[tuple[VerKey, OccKey, str]] = field(default_factory=list)  # 版本 →(读)→ 出现
    produced: list[tuple[OccKey, VerKey]] = field(default_factory=list)    # 出现 →(写)→ 版本
    owned_reads: dict[OccKey, list[tuple[str, int, str]]] = field(default_factory=dict)
    inherited: dict[OccKey, tuple[int, OccKey | None]] = field(default_factory=dict)


def build_generation_dag(
    stories: dict[str, FileStory],
    root_path: str,
    root_versions: list[int] | None = None,
) -> Dag:
    """从被修文件的版本出发,按累积读边把生成 DAG 离线算全。

    - 找全用累积规则:出现 W 的入边 = 其 agent 在 W 之前的**全部**读取
      (上下文是累积的;回合切分只属于披露层,不参与找全)。
    - 出现入树的唯一途径:它产出的版本被闭包内的读边指到。
    - 时间沿每条边严格递减 → 无环、必停,与遍历顺序无关。
    - 收敛后做披露归属:agent 的被拉入出现 W1<…<Wk,读取按
      (t_{W(i-1)}, t_{Wi}] 归属 Wi —— 每条相关读恰好展示一次;
      Wi 另携带 (沿用条数, 上一次出现) 指针。
    """
    # agent → 全部读取(带路径),时间序
    agent_reads: dict[str, list[tuple[str, ReadRec]]] = {}
    for path, st in stories.items():
        for r in st.reads:
            agent_reads.setdefault(r.by, []).append((path, r))
    for lst in agent_reads.values():
        lst.sort(key=lambda pr: (pr[1].ts, pr[1].seq))

    dag = Dag(root=root_path)
    root_story = stories.get(root_path)
    if root_story is None or not root_story.versions:
        return dag

    picks = root_versions or [v.v for v in root_story.versions]
    heap: list[VerKey] = []
    for v in picks:
        if 1 <= v <= len(root_story.versions):
            key = (root_path, v)
            if key not in dag.version_nodes:
                dag.version_nodes[key] = root_story.versions[v - 1]
                heapq.heappush(heap, key)

    edge_seen: set[tuple[VerKey, OccKey, str]] = set()
    while heap:
        vid = heapq.heappop(heap)
        ver = dag.version_nodes[vid]
        if ver.by in (EXTERNAL, OUTBAND):
            continue                                  # 天然叶子
        occ: OccKey = (ver.by, ver.ts, ver.seq)
        if occ in dag.occurrences:
            continue
        dag.occurrences[occ] = vid
        dag.produced.append((occ, vid))
        for path, r in agent_reads.get(ver.by, []):
            if (r.ts, r.seq) > (ver.ts, ver.seq):
                break                                  # 时间序列表,后面的都晚于这笔写
            tgt: VerKey = (path, r.version)
            kind = "dep" if r.dep else "content"
            edge = (tgt, occ, kind)
            if edge in edge_seen:
                continue
            edge_seen.add(edge)
            dag.edges.append(edge)
            if tgt not in dag.version_nodes:
                dag.version_nodes[tgt] = stories[path].versions[r.version - 1]
                heapq.heappush(heap, tgt)

    # -- 披露归属(闭包收敛后才有资格算:出现集到此已知) --
    by_agent: dict[str, list[OccKey]] = {}
    for occ in dag.occurrences:
        by_agent.setdefault(occ[0], []).append(occ)
    for agent, occs in by_agent.items():
        occs.sort(key=lambda o: (o[1], o[2]))
        reads = agent_reads.get(agent, [])
        prev_key: tuple[str, int] | None = None
        prev_occ: OccKey | None = None
        inherited_total = 0
        for occ in occs:
            cut = (occ[1], occ[2])
            owned = [(p, r.version, r.ts) for p, r in reads
                     if (prev_key is None or (r.ts, r.seq) > prev_key)
                     and (r.ts, r.seq) <= cut]
            dag.owned_reads[occ] = owned
            dag.inherited[occ] = (inherited_total, prev_occ)
            inherited_total += len(owned)
            prev_key = cut
            prev_occ = occ
    dag.edges.sort()
    dag.produced.sort()
    return dag


# ═══════════════ 逐行签名:每一行现在是谁写的(链的行级归属地基) ═══════════════


def line_owners(story: FileStory) -> list[list[str | None]]:
    """每个版本的逐行作者。确定性计算:相邻**已知**内容做序列比对,equal 块
    沿承原作者,新增/替换行归本版作者;内容未知的版本 → 整版 None(不猜);
    未知后的重锚版本,与上一个已知版本比对接续 —— 断点处丢失的只是断点段
    自己的归属,历史不清零。"""
    owners_per_version: list[list[str | None]] = []
    prev_content: str | None = None
    prev_owners: list[str | None] = []
    for ver in story.versions:
        if ver.content is None:
            owners_per_version.append([])
            prev_content = None
            continue
        cur_lines = ver.content.splitlines()
        if prev_content is None:
            # 首版 = 全归作者;断点后的重锚版 = 行归属未知(不猜)
            cur: list[str | None] = ([ver.by] * len(cur_lines)
                                     if not owners_per_version
                                     else [None] * len(cur_lines))
            owners_per_version.append(cur)
            prev_content, prev_owners = ver.content, cur
            continue
        sm = difflib.SequenceMatcher(None, prev_content.splitlines(),
                                     cur_lines, autojunk=False)
        cur = [ver.by] * len(cur_lines)
        for tag, i1, _i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(j2 - j1):
                    cur[j1 + k] = prev_owners[i1 + k]
        owners_per_version.append(cur)
        prev_content, prev_owners = ver.content, cur
    return owners_per_version


def line_origins(story: FileStory) -> list[list[tuple[str, int] | None]]:
    """line_owners 的加强版:每行 (作者, 引入版本)。同一套确定性规则 —— equal 块沿承,
    新增/替换行归本版;内容未知的版本整版空;断点后重锚版整版 None。"""
    per_version: list[list[tuple[str, int] | None]] = []
    prev_content: str | None = None
    prev: list[tuple[str, int] | None] = []
    for ver in story.versions:
        if ver.content is None:
            per_version.append([])
            prev_content = None
            continue
        cur_lines = ver.content.splitlines()
        if prev_content is None:
            cur: list[tuple[str, int] | None] = ([(ver.by, ver.v)] * len(cur_lines)
                                                 if not per_version
                                                 else [None] * len(cur_lines))
            per_version.append(cur)
            prev_content, prev = ver.content, cur
            continue
        sm = difflib.SequenceMatcher(None, prev_content.splitlines(), cur_lines, autojunk=False)
        cur = [(ver.by, ver.v)] * len(cur_lines)
        for tag, i1, _i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(j2 - j1):
                    cur[j1 + k] = prev[i1 + k]
        per_version.append(cur)
        prev_content, prev = ver.content, cur
    return per_version


def fixed_line_origins(story: FileStory, fix_vs: list[int],
                       ) -> tuple[int, dict[str, int], dict[str, int], str | None]:
    """修复版本动了哪些行、那些行原来是谁写的。

    返回 (touched 行数, {原作者: 行数}, 无原作者行的分类计数, 断链原因|None)。
    判据:每个修复版本与其前一版已知内容比对,被替换/删除的**前版行**的作者
    计入 origins;归不出原作者的行如实分类 —— unknown(断点后逐行归属未知)/
    self(修复方改自己写的行)/insert(纯新增);任一端内容未知则该笔整体无法
    行级归因(计入断链原因)。"""
    owners = line_owners(story)
    touched = 0
    origins: dict[str, int] = {}
    other: dict[str, int] = {}
    broken: str | None = None

    def bump(key: str, n: int = 1) -> None:
        other[key] = other.get(key, 0) + n

    for v in fix_vs:
        idx = v - 1
        cur = story.versions[idx]
        prev = story.versions[idx - 1] if idx >= 1 else None
        if cur.content is None or prev is None or prev.content is None:
            broken = ("no-baseline" if prev is None or prev.content is None
                      else "content-unknown")
            continue
        prev_owned = owners[idx - 1]
        sm = difflib.SequenceMatcher(None, prev.content.splitlines(),
                                     cur.content.splitlines(), autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("replace", "delete"):
                for k in range(i1, i2):
                    touched += 1
                    o = prev_owned[k] if k < len(prev_owned) else None
                    if o is None:
                        bump("unknown")
                    elif o == cur.by:
                        bump("self")
                    else:
                        origins[o] = origins.get(o, 0) + 1
            elif tag == "insert":
                touched += j2 - j1  # 纯新增行:动了文件,但没有"原作者"
                bump("insert", j2 - j1)
    return touched, origins, other, broken


def build_fix_chains(
    stories: dict[str, FileStory],
    agent_meta: dict[str, dict[str, Any]],
    is_fixer: dict[str, bool],
    ets_only: bool = True,
    *,
    session_of: dict[str, str] | None = None,
    fix_sessions: set[str] | None = None,
) -> list[dict[str, Any]]:
    """返修链 —— 全部从编年史算,旧 blame/crosschain 退役。

    链根 = 修复方写过版本的 .ets 文件(用户裁定:被修文件只认鸿蒙代码)。
    生成方 = 被修行的原作者(逐行签名,确定性);行级不可得时退回该文件的
    全部非修复写手并标注原因。diff = 修复版本的引擎真 diff 档位。
    agent_meta/is_fixer 来自血缘层(desc/stage/派发词),按引擎 agent id 松配
    ("agent-<id>" ↔ "<id>","__main__:*" 互认)。
    fix_sessions:跨会话池里只有这些会话(sid8)的写才可能是修复 —— 修复方只认当前会话,
    前序生成轮里 execute 之后的写一律生成侧(老口径);None = 不限。session_of 由账本给
    (agent id → sid8)。"""
    def meta_of(eng_agent: str) -> dict[str, Any]:
        key = eng_agent[6:] if eng_agent.startswith("agent-") else eng_agent
        if key in agent_meta:
            return agent_meta[key]
        if eng_agent.startswith("__main__"):
            for k, v in agent_meta.items():
                if k.startswith("__main__"):
                    return v
            return {"desc": "主会话(编排/直接写盘)", "stage": None}
        return {"desc": eng_agent, "stage": None}

    def fixer_of(eng_agent: str) -> bool:
        key = eng_agent[6:] if eng_agent.startswith("agent-") else eng_agent
        return bool(is_fixer.get(key))

    def fixer_of_ver(ver: Version) -> bool:
        if (fix_sessions is not None and session_of is not None
                and session_of.get(ver.by) not in fix_sessions):
            return False
        # 账本自带的阶段优先(主会话逐笔、子 agent 继承派发时阶段):正式口径 execute 之后全是修复,
        # 主会话在 verify 阶段亲手改的也算;没有归属戳(codex / 旧记录)退回血缘层的 agent 级判定
        if ver.stage:
            return agent_is_fixer({"stage": ver.stage})
        return fixer_of(ver.by)

    def meta_at(eng_agent: str, ver: Version | None) -> dict[str, Any]:
        """名片带上这一版所在的阶段:主会话横跨全程,按版本给;子 agent 血缘层没给时用账本的。"""
        m = meta_of(eng_agent)
        if ver is None or not ver.stage:
            return m
        if eng_agent.startswith("__main__"):
            return {**m, "stage": ver.stage, "desc": "主会话(编排/直接写盘) · " + ver.stage}
        return m if m.get("stage") else {**m, "stage": ver.stage}

    chains: list[dict[str, Any]] = []
    for path, st in sorted(stories.items()):
        if ets_only and not path.endswith(".ets"):
            continue
        fix_vs = [v.v for v in st.versions
                  if v.by not in (EXTERNAL, OUTBAND) and fixer_of_ver(v)]
        gen_vs = [v.v for v in st.versions
                  if v.by not in (EXTERNAL, OUTBAND) and not fixer_of_ver(v)]
        if not fix_vs or not gen_vs:
            continue
        touched, origins, other, broken = fixed_line_origins(st, fix_vs)
        gen_agents: list[str] = []
        for v in gen_vs:                                  # 首写者(创建者)在前
            by = st.versions[v - 1].by
            if by not in gen_agents:
                gen_agents.append(by)
        fix_agents = sorted({st.versions[v - 1].by for v in fix_vs})
        gen_ids: list[str]
        if origins:
            from_rows: list[dict[str, Any]] = [
                {"id": k, "desc": str(meta_of(k).get("desc") or k)[:40], "n": n}
                for k, n in sorted(origins.items(), key=lambda kv: -kv[1])]
            lines: dict[str, Any] | None = {"touched": touched, "from": from_rows,
                                            "other": other or None}
            gen_ids = [str(r["id"]) for r in from_rows]
        else:
            lines = None
            gen_ids = gen_agents
            if broken is None and touched:
                # 行都动了但归不出原作者:如实报分类,别让页面空白
                names = {"unknown": "断点后归属未知", "self": "修复方改自己的行",
                         "insert": "纯新增"}
                broken = "、".join(f"{names[k]} {n} 行"
                                   for k, n in other.items())
        gid, fid = gen_ids[0], fix_agents[0]
        # 主会话横跨全程:名片按它在这个文件上第一笔生成 / 第一笔修复所在的阶段给
        first_gen: dict[str, Version] = {}
        for v in gen_vs:
            first_gen.setdefault(st.versions[v - 1].by, st.versions[v - 1])
        first_fix: dict[str, Version] = {}
        for v in fix_vs:
            first_fix.setdefault(st.versions[v - 1].by, st.versions[v - 1])
        gm, fm = meta_at(gid, first_gen.get(gid)), meta_at(fid, first_fix.get(fid))

        # vers = 修复方写修复版本时自己的 agent 版本号:主会话只有这几笔是修复,页面按版本号着色
        fix_vers: dict[str, set[int]] = {}
        for v in fix_vs:
            ver = st.versions[v - 1]
            if ver.by_ver is not None:
                fix_vers.setdefault(ver.by, set()).add(ver.by_ver)

        chains.append({
            "file": path.rsplit("/", 1)[-1],
            "file_abs": path,
            # 时刻:生成方在这个文件上第一笔生成 / 修复方第一笔修复(T+ 换算在文本层与页面做)
            "gen_at": first_gen[gid].ts if gid in first_gen else None,
            "fix_at": first_fix[fid].ts if fid in first_fix else None,
            "generator": {"id": gid, "desc": str(gm.get("desc") or gid)[:40],
                          "stage": gm.get("stage"),
                          "prompt": str(gm.get("prompt") or "")[:200]},
            "generators": [{"id": g, "desc": str(meta_at(g, first_gen.get(g)).get("desc") or g)[:40],
                            "stage": meta_at(g, first_gen.get(g)).get("stage"),
                            "prompt": str(meta_of(g).get("prompt") or "")[:200]}
                           for g in gen_ids],
            "fixer": {"id": fid, "desc": str(fm.get("desc") or fid)[:40],
                      "stage": fm.get("stage"),
                      "note": str(fm.get("note") or "")[:280]},
            "fixers_all": [{"id": f, "desc": str(meta_at(f, first_fix.get(f)).get("desc") or f)[:40],
                            "stage": meta_at(f, first_fix.get(f)).get("stage"),
                            "note": str(meta_of(f).get("note") or "")[:280],
                            "vers": sorted(fix_vers.get(f, set()))}
                           for f in fix_agents],
            "lines": lines,
            "blame_broken": broken if lines is None else None,
            "fix_versions": fix_vs,
            "breaks": [{"ts": b.ts, "kind": b.kind} for b in st.breaks],
            "diff": [],   # 页面吃 /fileversions + /filediff,不再内嵌摘要
        })
    return chains


def chain_entry_lists(chains: list[dict[str, Any]],
                      ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """链页首屏入口(被修文件 / 修复方)直接从链来 —— 与「02 风险点」返修追溯卡、fixchain-data
    同一口径,不再另从血缘层算一遍。修复方按首次出现排序,同一 id 只留一张卡。"""
    fixes = [{"id": str(c.get("file_abs") or c.get("file")), "label": str(c.get("file"))}
             for c in chains]
    fixers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in chains:
        for f in c.get("fixers_all") or []:
            fid = str(f.get("id"))
            if fid in seen:
                continue
            seen.add(fid)
            fixers.append({"id": fid, "label": str(f.get("desc") or fid)[:60]})
    return fixes, fixers


# ═══════════════ Web 载荷(瘦身序列化;内容与 diff 正文留在服务端按需取) ═══════════════


def find_story_path(stories: dict[str, FileStory], hint: str) -> str | None:
    """按后缀匹配把页面上的相对路径解析到 story 键;多命中取最长版本史。"""
    h = hint.replace("\\", "/").lstrip("/")
    cands = [p for p in stories if p.endswith("/" + h) or p == h]
    if not cands:
        return None
    return max(cands, key=lambda p: len(stories[p].versions))


def _occ_id(occ: OccKey) -> list[Any]:
    return [occ[0], occ[1], occ[2]]


def dag_payload(stories: dict[str, FileStory], hint: str,
                root_versions: list[int] | None = None) -> dict[str, Any] | None:
    """生成链 DAG 的页面载荷,列式紧凑编码(0723 实测 5.7MB → 列式后 <1MB):

    - versions 行按 vcols 列出,行下标即版本节点 id(vi)
    - occurrences 行按 ocols 列出,行下标即出现 id(oi);owned/produced 用 vi,
      inherited_prev 用 oi(-1=无)
    - edges = [vi, oi, dep01]
    内容与 diff 正文不进载荷,按需走 diff_payload。
    """
    root = find_story_path(stories, hint)
    if root is None:
        return None
    dag = build_generation_dag(stories, root, root_versions)
    vkeys = sorted(dag.version_nodes)
    vindex = {k: i for i, k in enumerate(vkeys)}
    versions = []
    for p_, v_ in vkeys:
        ver = dag.version_nodes[(p_, v_)]
        versions.append([p_, v_, ver.by, ver.ts, ver.source, ver.diff_kind,
                         1 if ver.diff is not None else 0, 1 if ver.sealed else 0,
                         (ver.content.count("\n") + 1) if ver.content else None])
    # 写前必读判定:读它的 agent 自己也写过同一文件 → 过程性读取(编辑目标
    # 的先读/读回),不是信息输入。闭包保持全的,标出来交给展示层裁量。
    writers_of: dict[str, set[str]] = {}
    for p_w, st_w in stories.items():
        for ver_w in st_w.versions:
            if ver_w.by not in (EXTERNAL, OUTBAND):
                writers_of.setdefault(p_w, set()).add(ver_w.by)
    okeys = sorted(dag.occurrences)
    oindex = {k: i for i, k in enumerate(okeys)}
    occurrences = []
    for occ in okeys:
        vid = dag.occurrences[occ]
        owned_keys = [(p_, v_) for p_, v_, _ts in dag.owned_reads.get(occ, [])
                      if (p_, v_) in vindex]
        owned = [vindex[k] for k in owned_keys]
        owned_self = [1 if occ[0] in writers_of.get(p_, ()) else 0
                      for p_, _v in owned_keys]
        n_inh, prev = dag.inherited.get(occ, (0, None))
        occurrences.append([occ[0], occ[1], occ[2], vindex[vid], owned,
                            n_inh, oindex[prev] if prev is not None else -1,
                            owned_self])
    edges = [[vindex[vid], oindex[occ], 1 if kind == "dep" else 0]
             for vid, occ, kind in dag.edges
             if vid in vindex and occ in oindex]
    return {"root": root,
            "root_versions": root_versions or [v.v for v in stories[root].versions],
            "vcols": ["path", "v", "by", "ts", "source", "diff_kind",
                      "has_diff", "sealed", "lines"],
            "versions": versions,
            "ocols": ["agent", "ts", "seq", "produced_vi", "owned_vi",
                      "inherited_n", "inherited_prev_oi", "owned_self01"],
            "occurrences": occurrences,
            "edges": edges,
            "breaks": [{"path": root, "ts": b.ts, "kind": b.kind, "detail": b.detail}
                       for b in stories[root].breaks]}


def diff_payload(stories: dict[str, FileStory], hint: str,
                 v: int) -> dict[str, Any] | None:
    """单个版本的 diff 正文(点开写节点看的那份)。"""
    path = find_story_path(stories, hint)
    if path is None:
        return None
    st = stories[path]
    if not (1 <= v <= len(st.versions)):
        return None
    ver = st.versions[v - 1]
    return {"path": path, "v": v, "by": ver.by, "ts": ver.ts,
            "source": ver.source, "diff_kind": ver.diff_kind,
            "sealed": ver.sealed, "diff": ver.diff}


def _agent_matches(by: str, hint: str) -> bool:
    if by == hint or by == f"agent-{hint}" or f"agent-{by}" == hint:
        return True
    return by.startswith("__main__") and hint.startswith("__main__")


def agent_story_payload(stories: dict[str, FileStory],
                        hint: str) -> dict[str, Any] | None:
    """一个 agent 的全局写入史 —— fixer 河流与 agent 抽屉的供数。

    每笔写 = 一次出现;两组披露的全局版:新读 = 上一笔写之后到本笔写之间
    该 agent 的读取(绑版本),沿用 = 更早读过的累计数。写完之后还有读取的
    (读回自查),挂在末尾哨兵出现上,不丢。"""
    writes: list[tuple[str, int, str, int]] = []
    reads: list[tuple[str, int, str, int, bool, int | None, int | None]] = []
    canon: str | None = None
    wrote_paths: set[str] = set()
    for path, st in stories.items():
        for ver in st.versions:
            if _agent_matches(ver.by, hint):
                canon = canon or ver.by
                writes.append((ver.ts, ver.seq, path, ver.v))
                wrote_paths.add(path)
        for r in st.reads:
            if _agent_matches(r.by, hint):
                canon = canon or r.by
                reads.append((r.ts, r.seq, path, r.version, bool(r.dep),
                              r.start, r.n))
    if canon is None:
        return None
    writes.sort()
    reads.sort()

    def read_row(rp: str, rv: int, dep: bool,
                 start: int | None, n: int | None) -> list[Any]:
        # [path, v, 依赖标, 写前必读标, 起始行, 行数]。行段是"源码没读完全"
        # 这类定性的原始证据(None = 全文或未知);写前必读 = 读自己也写过的文件
        return [rp, rv, 1 if dep else 0, 1 if rp in wrote_paths else 0,
                start, n]

    occurrences: list[dict[str, Any]] = []
    ri = 0
    seen_reads = 0
    for ts, _seq, path, v in writes:
        news: list[list[Any]] = []
        while ri < len(reads) and (reads[ri][0], reads[ri][1]) <= (ts, _seq):
            _rts, _rseq, rp, rv, dep, rs, rn = reads[ri]
            news.append(read_row(rp, rv, dep, rs, rn))
            ri += 1
        occurrences.append({"ts": ts, "path": path, "v": v, "news": news,
                            "inherited_n": seen_reads})
        seen_reads += len(news)
    if ri < len(reads):
        tail = [read_row(rp, rv, dep, rs, rn)
                for _rts, _rseq, rp, rv, dep, rs, rn in reads[ri:]]
        occurrences.append({"ts": reads[ri][0], "path": None, "v": None,
                            "news": tail, "inherited_n": seen_reads})
    return {"agent": canon, "occurrences": occurrences,
            "n_writes": len(writes), "n_reads": len(reads)}
