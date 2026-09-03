"""迁移轨迹自动审计 —— 告警规则的唯一聚集地。

migloop 的血缘/阶段/skill 数据是证据库(不做归属推断,只记实际发生),
这里在其上跑规则,产出 findings;呈现在报告页「02 风险点」段。
规则与未来的 sentinel(live 流上的实时检测)共享:审计是事后全景。

== 开发者添加一条审计规则的四步 ==
1. 写 ``_check_<name>(trace) -> list[dict]``,用 ``_finding()`` 构造结果;
   level 取 error(要人处理)/warn(建议核查)/info(供了解)。
2. 把函数挂进 ``build_audit`` 的 findings 列表,规则名加进 ``checked``。
3. 在 tests/web/test_insight1_audit.py 钉死触发与不触发两个方向 ——
   字段名写错规则会静默失效,正向用例必须有。
4. 用真会话回测定级(参考 no-source-write 的 AntennaPod 定级记录),
   误报比漏报伤害大:一页红的报告没人再看第二眼。

可用的证据面:trace["tools"](每条带 stage/brief/ok/skill),
trace["stages"],trace["agents"](aborted/type),trace["lineage"]
(agents 读写边/specs.read_by/files.writers)。

口径与 build_summary 同一立场:客户能看懂的话,不出现取证词汇。
"""

from __future__ import annotations

from typing import Any

#: a2h 管线的阶段顺序约定 —— pipeline-gap 规则的基准。
#: 只对「实际出现过的名字」内部找洞:名单不全时最多规则不触发,不会误报。
DEFAULT_PIPELINE: tuple[str, ...] = (
    "a2h-run", "a2h-spec", "a2h-plan", "a2h-execute", "a2h-verify",
)

#: 返工热点最多列几个文件 —— 再多前端也读不过来,完整名单在血缘视图里。
_REWORK_TOP = 5


def _finding(rule: str, level: str, title: str, detail: str,
             agents: list[str] | None = None,
             paths: list[str] | None = None,
             anchor: dict[str, Any] | None = None) -> dict[str, Any]:
    """anchor = 证据定位,报告页「02 风险点」的点击跳转吃它:
    {"stage": 阶段键} 跳到 06 对应阶段卡;再带 {"ts": ISO 时刻} 则
    顺便把该卡时间轴放大到出事时刻附近。"""
    return {
        "rule": rule,
        "level": level,          # error / warn / info
        "title": title,
        "detail": detail,
        "agents": agents or [],
        "paths": paths or [],
        "anchor": anchor or {},
    }


def _lineage_agents(trace: dict[str, Any]) -> list[dict[str, Any]]:
    lin = trace.get("lineage") or {}
    rows = lin.get("agents") or []
    return [a for a in rows if isinstance(a, dict)]


def _check_blind_write(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """盲写:execute 角色的子代理写了代码,却没读任何 spec / 安卓源码。

    主线合成条目(__main__:*)不参与 —— 主线上下文横跨全程,单阶段切片里
    「没读」不代表无据。
    """
    out = []
    for a in _lineage_agents(trace):
        if str(a.get("agent_id", "")).startswith("__main__"):
            continue
        if a.get("role") != "execute" or not a.get("n_ets"):
            continue
        no_spec = not a.get("n_spec_read") and not a.get("shared_reads")
        no_android = not a.get("lines_android")
        # 工程内读取也算依据:修复/组装类代理(closer/fixer)的输入是编译报错
        # 与现有工程代码,不读 spec 很正常 —— AntennaPod 真数据回测,不加这条
        # 会把全部收尾代理误打成盲写
        no_proj = not a.get("n_proj")
        if no_spec and no_android and no_proj:
            out.append(_finding(
                "blind-write", "error",
                "无依据写码",
                f"代理 {a.get('desc') or a.get('agent_id')} 写了 "
                f"{a.get('n_ets')} 个代码文件,但没有读过任何规格或源码 —— 产物可信度存疑。",
                agents=[str(a.get("agent_id"))],
                paths=[str(p) for p in (a.get("writes_ets") or [])[:5]],
            ))
    return out


def _check_missing_inputs(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """输入缺失聚合:写码代理没读 spec / 没读安卓源码。

    与 blind-write 去重:三类输入全零的代理已按「盲写」单独报,不再计入。
    定级依据 AntennaPod 真数据(168 个写码代理):
    - 未读 spec(18 个)= warn。a2h 是 spec 驱动流程,execute 代理不读
      规格就写码是异常,值得点名。
    - 未读安卓源码(19 个)= info。converter 吃 spec 产码、不回读源码
      是流程设计,只作提示,免得把报告淹了。
    """
    no_spec: list[str] = []
    no_src: list[str] = []
    for a in _lineage_agents(trace):
        if str(a.get("agent_id", "")).startswith("__main__"):
            continue
        if a.get("role") != "execute" or not a.get("n_ets"):
            continue
        blind = (not a.get("n_spec_read") and not a.get("shared_reads")
                 and not a.get("lines_android") and not a.get("n_proj"))
        if blind:
            continue
        name = str(a.get("desc") or a.get("agent_id"))
        if not a.get("n_spec_read") and not a.get("shared_reads"):
            no_spec.append(name)
        if not a.get("lines_android"):
            no_src.append(name)
    out = []
    if no_spec:
        shown = "、".join(no_spec[:3])
        more = f" 等 {len(no_spec)} 个" if len(no_spec) > 3 else ""
        out.append(_finding(
            "no-spec-write", "warn",
            "写码未读规格",
            f"{shown}{more}代理写了代码但没读过任何规格页 —— 依据可能只来自派发说明,建议抽查产物。",
            agents=no_spec,
        ))
    if no_src:
        shown = "、".join(no_src[:3])
        more = f" 等 {len(no_src)} 个" if len(no_src) > 3 else ""
        out.append(_finding(
            "no-source-write", "info",
            "写码未读安卓源码",
            f"{shown}{more}代理产码时没有回读安卓源码 —— 规格驱动流程下属常见,列出供了解。",
            agents=no_src,
        ))
    return out


def _check_spec_orphan(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """spec 覆盖缺口:已经开始产码了,还有实质 spec 分页从没被任何代理读过。

    门槛「已有代码产出」是防进行中误报:spec 刚写完、还没进实现阶段时,
    全部 spec 都暂时无人读,这不是缺口。
    """
    lin = trace.get("lineage") or {}
    has_ets = any(f.get("kind") == "ets" for f in lin.get("files") or [])
    if not has_ets:
        return []
    orphans = [s["path"] for s in lin.get("specs") or []
               if s.get("kind") in ("page", "feature", "base") and not s.get("read_by")]
    if not orphans:
        return []
    shown = orphans[:_REWORK_TOP]
    more = f" 等 {len(orphans)} 页" if len(orphans) > len(shown) else ""
    return [_finding(
        "spec-orphan", "warn",
        "规格页无人读取",
        f"已开始产出代码,但 {'、'.join(shown)}{more}从未被任何代理读过 —— 对应需求可能整页遗漏。",
        paths=orphans,
    )]


def _check_aborted_agents(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """异常收尾:中断/断连的代理,产物多半作废、通常还要补跑一次。

    按阶段聚合(先例:script-fail 拆条)—— AntennaPod 有 15 个,逐个出卡
    会刷屏;每阶段一条,点名前几个并汇总浪费的 token 量。
    首屏「白烧 OUTPUT」指标卡已撤,这里是该信息的唯一出口。"""
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for a in trace.get("agents") or []:
        # 主会话快照的"异常收尾"是快照截断的假象,由 agent-snapshot 规则单独点名
        if not a.get("aborted") or a.get("snapshot_of_main"):
            continue
        by_stage.setdefault(str(a.get("stage") or "?"), []).append(a)
    out = []
    for st, rows in sorted(by_stage.items(), key=lambda kv: -len(kv[1])):
        tok = sum(a.get("output_tokens") or 0 for a in rows)
        names = "、".join(str(a.get("desc") or a.get("agent_id"))[:24] for a in rows[:3])
        more = f" 等 {len(rows)} 个" if len(rows) > 3 else ""
        out.append(_finding(
            "aborted-agent", "warn",
            f"代理异常收尾 · {st}",
            f"{names}{more}因中断/连接问题未正常结束,共浪费约 {tok} token 的产出 —— "
            "需要人工确认或补跑。",
            agents=[str(a.get("agent_id")) for a in rows],
            anchor={"stage": st, "ts": rows[0].get("start_ts")},
        ))
    return out


def _check_snapshot_agents(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """子代理记录是主会话快照:上传上来的转录 uuid 全部落在主会话里(adapter 标 snapshot_of_main)。

    这是会话上传侧的问题(migbot-runtime-src#46),不是迁移本身的问题;但这些"代理"的工具、
    token、收尾状态全是主会话的影子,甘特里表现为从会话开头铺到派发时刻、末端异常收尾的长条。
    只点名不剔除 —— 分析页忠实呈现上传内容,遮掉就没人修;归因去重在两原子账本做。
    判据是 uuid 集合包含,零误报,定 error:要运行时的人处理。
    """
    rows = [a for a in trace.get("agents") or [] if a.get("snapshot_of_main")]
    if not rows:
        return []
    by_stage: dict[str, int] = {}
    for a in rows:
        st = str(a.get("stage") or "?")
        by_stage[st] = by_stage.get(st, 0) + 1
    ranked = sorted(by_stage.items(), key=lambda kv: -kv[1])
    stages_txt = "、".join(f"{st} {n} 个" for st, n in ranked)
    names = "、".join(f"{a.get('type') or '?'}·{str(a.get('agent_id'))[:8]}" for a in rows[:3])
    more = f" 等 {len(rows)} 个" if len(rows) > 3 else ""
    return [_finding(
        "agent-snapshot", "error",
        f"子代理记录是主会话快照 · {len(rows)} 个",
        f"{names}{more}上传上来的转录与主会话完全重合(记录 uuid 全部落在主会话里),"
        "不是这些代理自己的轨迹 —— 它们的工具、token、收尾状态都不可信,甘特里表现为从会话开头"
        f"铺到派发时刻、末端异常收尾的长条(分布:{stages_txt})。这是会话上传侧的问题,"
        "需要运行时修复(migbot-runtime-src#46);迁移产物本身不受影响。",
        agents=[str(a.get("agent_id")) for a in rows],
        anchor={"stage": ranked[0][0]},
    )]


def _check_pipeline_gap(trace: dict[str, Any],
                        pipeline: tuple[str, ...]) -> list[dict[str, Any]]:
    """流程跳步:管线约定顺序里,后面的阶段出现了、前面的却从没出现。"""
    seen = {s.get("stage") for s in trace.get("stages") or []}
    hit_idx = [i for i, name in enumerate(pipeline) if name in seen]
    if not hit_idx:
        return []
    missing = [pipeline[i] for i in range(max(hit_idx)) if pipeline[i] not in seen]
    if not missing:
        return []
    return [_finding(
        "pipeline-gap", "error",
        "管线阶段缺失",
        f"已进行到 {pipeline[max(hit_idx)]},但之前的 {'、'.join(missing)} 阶段没有出现过 —— 流程跳步。",
        paths=missing,
    )]


# 经验规则的命令词表 —— 按管线演进随时补充,大小写不敏感子串匹配
_BUILD_MARKERS = ("hvigor", "assemblehap", "ohpm ")
_EMULATOR_MARKERS = ("emulator", "hdc ", "simulator", "phone-", "x86emu")


def _tools_of_stage(trace: dict[str, Any], stage_key: str) -> list[dict[str, Any]]:
    return [t for t in trace.get("tools") or [] if t.get("stage") == stage_key]


def _check_skill_failures(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Skill 调用失败/找不到 —— 管线的一环没接上,后续都在错误前提上跑。"""
    out = []
    for t in trace.get("tools") or []:
        if t.get("name") == "Skill" and t.get("ok") is False:
            when = str(t.get("ts") or "")[11:16]
            out.append(_finding(
                "skill-fail", "error",
                "Skill 调用失败",
                f"阶段 {t.get('stage') or '?'} 调用 Skill「{t.get('brief') or '?'}」失败"
                f"{f'(发生于 {when})' if when else ''} —— 可能是技能未安装/名字不对,该环节的产出不可信。",
                paths=[str(t.get("brief") or "")],
                anchor={"stage": t.get("stage"), "ts": t.get("ts")},
            ))
    return out


def _check_script_failures(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """脚本执行失败聚类:少量失败是正常迭代,集中失败说明环境或工具链有问题。
    定级:≥5 次 warn,否则 info。"""
    fails: dict[str, int] = {}
    first_ts: dict[str, str] = {}
    for t in trace.get("tools") or []:
        if t.get("name") == "Bash" and t.get("ok") is False:
            st = str(t.get("stage") or "?")
            fails[st] = fails.get(st, 0) + 1
            first_ts.setdefault(st, str(t.get("ts") or ""))
    if not fails:
        return []
    # 按阶段各出一条 —— 聚合成一条时「查看现场」只能跳一个阶段,点击语义
    # 对不上;拆开后每张卡跳自己的阶段、对自己的首次失败时刻。
    out = []
    for st, n in sorted(fails.items(), key=lambda kv: -kv[1]):
        when = str(first_ts.get(st) or "")[11:16]
        out.append(_finding(
            "script-fail", "warn" if n >= 5 else "info",
            f"脚本执行失败 · {st}",
            f"{st} 阶段 {n} 次脚本失败{f'(首次 {when})' if when else ''}"
            " —— 集中出现时先查环境与工具链,再看失败输出。",
            anchor={"stage": st, "ts": first_ts.get(st)},
        ))
    return out


def _check_execute_build(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """execute 阶段没跑过构建 —— 产出的代码从未被编译器检验过。

    只看主线命令(子代理内部的编译不进主线 transcript);主线门禁编译是
    a2h 流程的硬要求,词表见 _BUILD_MARKERS。"""
    ex_stages = [s for s in trace.get("stages") or [] if "execute" in str(s.get("stage") or "")]
    if not ex_stages:
        return []
    for st in ex_stages:
        for t in _tools_of_stage(trace, str(st.get("stage"))):
            if t.get("name") == "Bash" and any(
                    m in str(t.get("brief") or "").lower() for m in _BUILD_MARKERS):
                return []
    return [_finding(
        "execute-no-build", "error",
        "执行阶段未见构建",
        "execute 阶段的主线命令里没有出现过构建(hvigor/ohpm)—— 产出的代码可能从未编译验证。",
        anchor={"stage": str(ex_stages[0].get("stage"))},
    )]


def _check_spec_analyzer(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """spec 阶段的两条派发纪律:该起 Android 分析代理;spec 该由子代理写。

    门槛:spec 之后已出现别的阶段(spec 已收尾)才评 —— 阶段进行中
    analyzer 可能还没起,评早了是误报。"""
    stage_seq = [str(s.get("stage") or "") for s in trace.get("stages") or []]
    spec_idx = [i for i, name in enumerate(stage_seq)
                if "spec" in name and name != "setup"]
    if not spec_idx or max(spec_idx) == len(stage_seq) - 1:
        return []
    spec_stages = {stage_seq[i] for i in spec_idx}
    out = []
    spec_agents = [a for a in _lineage_agents(trace)
                   if str(a.get("stage")) in spec_stages
                   and not str(a.get("agent_id", "")).startswith("__main__")]
    if not any("analyzer" in str(a.get("type") or "").lower() for a in spec_agents):
        out.append(_finding(
            "spec-no-analyzer", "warn",
            "spec 阶段未起分析代理",
            "spec 阶段没有出现 Android 分析类子代理(analyzer)—— 源码理解可能只靠主线粗读。",
            anchor={"stage": sorted(spec_stages)[0]},
        ))
    if spec_agents and not any(a.get("n_spec_w") for a in spec_agents):
        out.append(_finding(
            "spec-main-write", "warn",
            "规格由主线直写",
            "spec 阶段有子代理但规格全部由主线直写 —— 与「子代理分工写 spec」的派发纪律不符。",
            anchor={"stage": sorted(spec_stages)[0]},
        ))
    return out


#: verify 深检的词表(依赖多,按环节分拆)
_INSTALL_MARKERS = ("hdc install", "install-hap", "bm install")
_SCREENSHOT_MARKERS = ("snapshot", "screencap", "screenshot", "uitest")


def _check_verify_emulator(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """verify 依赖链三层检:起设备 → 装包 → 截图取证。

    层层递进:设备都没起时装包/截图必然也无,只报最上层一条,免得刷屏。
    词表见 _EMULATOR_MARKERS / _INSTALL_MARKERS / _SCREENSHOT_MARKERS。"""
    vf_stages = [s for s in trace.get("stages") or [] if "verify" in str(s.get("stage") or "")]
    if not vf_stages:
        return []

    def _hit(markers: tuple[str, ...]) -> bool:
        for st in vf_stages:
            for t in _tools_of_stage(trace, str(st.get("stage"))):
                if t.get("name") == "Bash" and any(
                        m in str(t.get("brief") or "").lower() for m in markers):
                    return True
        return False

    if not _hit(_EMULATOR_MARKERS):
        return [_finding(
            "verify-no-emulator", "warn",
            "验证阶段未见模拟器",
            "verify 阶段的命令里没有出现模拟器/设备(emulator/hdc)—— 验证可能只做了静态检查,没有真机行为核验。",
            anchor={"stage": str(vf_stages[0].get("stage"))},
        )]
    out = []
    if not _hit(_INSTALL_MARKERS):
        out.append(_finding(
            "verify-no-install", "warn",
            "验证阶段未见装包",
            "起了模拟器/设备,但没有出现安装命令(hdc install/bm install)—— 跑的可能是旧包或根本没上真机。",
            anchor={"stage": str(vf_stages[0].get("stage"))},
        ))
    if not _hit(_SCREENSHOT_MARKERS):
        out.append(_finding(
            "verify-no-screenshot", "info",
            "验证阶段未见截图取证",
            "没有出现截图/快照命令 —— 行为核验缺少可回看的证据,列出供了解。",
            anchor={"stage": str(vf_stages[0].get("stage"))},
        ))
    return out


#: 规范阶段序 —— 跨会话通用的迁移阶段刻度。纯修复轮会话里没有 execute
#: 阶段(整场只有 verify),所以分界线不能用时间戳,只能用这张序表比较。
_CANON_STAGE_ORDER = {
    "setup": 0,
    "mig-arch": 1, "a2h-arch-scaffold": 1,
    "a2h-spec": 2,
    "a2h-plan": 3,
    "a2h-execute": 4,
    "a2h-verify": 5, "arkts-visual-verify": 5,
    "a2h-retrospect": 6,
}
#: 分界线:execute 之后(序 > 4)全部是修复
_GEN_LAST_ORDER = _CANON_STAGE_ORDER["a2h-execute"]
#: workflow 自定义阶段名的词根兜底(dynamic workflow 不走 skill 词表)
_FIX_STAGE_WORDS = ("verify", "fix", "repair", "retrospect")


def stage_order(stage: str | None) -> int | None:
    """阶段 → 规范序。认不出返回 None(保守当生成侧,不凭空造修复关系)。"""
    s = str(stage or "").strip().lower()
    if not s:
        return None
    if s in _CANON_STAGE_ORDER:
        return _CANON_STAGE_ORDER[s]
    if any(w in s for w in _FIX_STAGE_WORDS):
        return _GEN_LAST_ORDER + 1
    return None


def agent_is_fixer(a: dict[str, Any]) -> bool:
    """修复方判定 —— 口径只此一处:唯一用武之地是账本的 filestory.build_fix_chains(逐笔版本的
    阶段)与它的血缘层兜底映射;「02 风险点」返修追溯卡、链页首屏、迁移全程轮间连接都吃它算的链。

    正式口径:**a2h-execute 结束就是修复开始的标志,之后所有的都是修复**。
    判据是规范阶段序 > execute,不是 per-agent 的类型/描述关键词:
    - execute 内部的收尾(group closer 修 build error)算生成侧 —— 把一组
      产出收尾到可编译属于"生成完成",返修是交付之后别人回来改。它作为
      行级原作者的身份由 blame 保留,链上信息不丢。
    - 阶段认不出时保守归生成侧:宁可少一条链,不可凭空造修复关系。
    """
    return (stage_order(a.get("stage")) or 0) > _GEN_LAST_ORDER


def check_fix_chains(chains: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """返修追溯 —— 链由两原子账本算(filestory.build_fix_chains,逐笔版本按阶段判修复方),
    这里只把它包成「02 风险点」的一张卡:点名文件与生成方、跨会话计数、跳转链页。
    修复/生成的划分只在账本那一层;不再从血缘层另算一遍,免得两处口径漂移。
    """
    if not chains:
        return []
    shown = " · ".join(
        f"{str(c.get('file') or '').rsplit('/', 1)[-1]}"
        f"(生成:{str((c.get('generator') or {}).get('desc') or '')[:24]})"
        for c in chains[:5])
    more = f" 等 {len(chains)} 个文件" if len(chains) > 5 else ""
    cross = sum(1 for c in chains if c.get("gen_session") or c.get("fix_session"))
    stage = next((str((c.get("generator") or {}).get("stage"))
                  for c in chains if (c.get("generator") or {}).get("stage")), None)
    finding = _finding(
        "verify-fix-traceback", "info",
        "返修追溯",
        f"修复轮改写了 {len(chains)} 个生成产物:{shown}{more}"
        + (f"(其中 {cross} 条跨会话)" if cross else "")
        + " —— 点开链路看生成方依据(spec 页/派发指令)与修复方说明;逐行归属与 diff 在链页。",
        paths=[str(c.get("file_abs") or c.get("file")) for c in chains],
        anchor={"stage": stage} if stage else None,
    )
    finding["chain"] = [
        {"file": c.get("file"), "file_abs": c.get("file_abs"),
         "generator": c.get("generator"), "fixer": c.get("fixer"), "lines": c.get("lines"),
         "gen_session": c.get("gen_session"), "fix_session": c.get("fix_session")}
        for c in chains[:40]]
    return [finding]


def _check_rework(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """返工热点:同一代码文件被多个代理先后重写。少量属并行组装的正常现象,
    集中出现说明派发切分有重叠 —— 给信息级提示,完整名单在血缘视图。"""
    lin = trace.get("lineage") or {}
    hot = [(f["path"], f.get("writers") or []) for f in lin.get("files") or []
           if f.get("kind") == "ets" and len(f.get("writers") or []) >= 2]
    if not hot:
        return []
    hot.sort(key=lambda kv: -len(kv[1]))
    shown = [f"{p}({len(w)} 人)" for p, w in hot[:_REWORK_TOP]]
    more = f" 等 {len(hot)} 个文件" if len(hot) > _REWORK_TOP else ""
    return [_finding(
        "rework", "info",
        "多代理重写同一文件",
        f"{'、'.join(shown)}{more}被多个代理先后写过 —— 若非有意组装,说明任务切分有重叠。",
        paths=[p for p, _ in hot],
    )]


_LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}


def build_audit(trace: dict[str, Any],
                pipeline: tuple[str, ...] = DEFAULT_PIPELINE,
                fix_chains: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """跑全部规则,findings 按严重度排序。纯函数,不 I/O。
    fix_chains = 两原子账本算好的返修链(filestory.build_fix_chains);不传(摘要端点、进行中的
    会话)就没有返修追溯卡 —— 这里不再从血缘层另算。"""
    # 启用集 = 用户点名的六条经验检测。其余规则(管线跳步/盲写/输入缺失/
    # spec 覆盖缺口/异常收尾/返工)代码与测试保留但暂不启用 —— 风险点面板
    # 不放自由发挥的东西,逐条评审后再回来。pipeline 参数供未启用的
    # _check_pipeline_gap 复用,签名不动。
    findings = [
        *_check_skill_failures(trace),
        *_check_script_failures(trace),
        *_check_execute_build(trace),
        *_check_spec_analyzer(trace),
        *_check_verify_emulator(trace),
        *_check_aborted_agents(trace),
        *_check_snapshot_agents(trace),
        *check_fix_chains(fix_chains or []),
    ]
    findings.sort(key=lambda f: _LEVEL_ORDER.get(f["level"], 9))
    counts = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["level"]] = counts.get(f["level"], 0) + 1
    return {
        "findings": findings,
        "counts": counts,
        "checked": ["skill-fail", "script-fail", "execute-no-build",
                    "spec-no-analyzer", "spec-main-write", "verify-no-emulator",
                    "verify-no-install", "verify-no-screenshot", "aborted-agent",
                    "agent-snapshot", "verify-fix-traceback"],
    }
