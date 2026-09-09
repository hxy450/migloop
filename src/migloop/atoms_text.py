"""两原子的紧凑文本渲染 —— 给模型看的那一面。

页面吃 JSON,模型吃这里的文本:一行一条读/写/版本,路径相对工程根,标签用中文短词。
主会话 454 条读的 JSON 有 146KB,渲成文本 10KB —— 信息量本来就这么大,别把 JSON 的
字段名和绝对路径当信息。所有数字都来自 atoms.* 的同一份结果,不另算。
"""

from __future__ import annotations

from typing import Any

from migloop import atoms, time_scope

_EXT_LABEL = {"__external__": "外部输入", "__outband__": "实录外修改"}


def rel(path: str, root: str) -> str:
    r = root.replace("\\", "/").rstrip("/")
    p = path.replace("\\", "/")
    if r and p.startswith(r + "/"):
        return p[len(r) + 1:]
    return p


#: 正文类记录在时间线上的叫法
_TEXT_KINDS = {"say": "说", "think": "想", "instruction": "指令", "inject": "注入技能", "system": "系统提示",
               "notify": "通知", "interrupt": "打断"}


def _who(ledger: atoms.Ledger, by: str, ver: int | None) -> str:
    if by in _EXT_LABEL:
        return _EXT_LABEL[by]
    owner = ledger.agents.get(by)
    address = f" (id={by})" if owner else ""
    if owner and ver is not None and ver > owner.n_versions:
        return atoms.agent_label(ledger, by) + f" 收尾后(喂养槽 {ver}，未形成版本；action 查原文)" + address
    return atoms.agent_label(ledger, by) + (f" v{ver}" if ver is not None else "") + address


def _core(seq: Any, loc: int | str | None) -> str:
    """引用主体 #转录标识:n@L行[/块]:标识在前,是坐标的一部分,截不掉(放后缀时模型抄的时候丢了七成)。
    #n 给 action 展开用,是本次建账的句柄,账本重建后会漂;标识 + 行 + 块是转录里的位置,不漂,核验按它。"""
    if isinstance(loc, str) and "·" in loc:
        pos, tag = loc.split("·", 1)
        return f"#{tag}:{seq}@L{pos}"
    return f"#{seq}@L{loc}" if loc else f"#{seq}"


def _ref(seq: Any, t: str | None, line: int | str | None = None) -> str:
    """动作引用 (#转录标识:n@L行 T+h:mm);T+ 给跨 agent 对先后用。"""
    core = _core(seq, line)
    return f"({core} {t})" if t else f"({core})"


def _short(path: str, root: str) -> str:
    """工程内相对根;工程外(安卓源码、技能库)只留最后三段 —— 一条读记录曾 150 字,110 字是绝对路径。"""
    r = rel(path, root)
    if root and r != path:
        return r
    parts = path.replace("\\", "/").split("/")
    return path if len(parts) <= 4 else "…/" + "/".join(parts[-3:])


def _read_span(r: dict[str, Any]) -> str:
    """一条读到底读了多少:全文快照 / 行段 / 命中 N 行(grep、head 前缀从 stdout 对账出来的)/ 范围未知。
    0723 复跑教训:slice6-risk 对 AppFormInfoManager.ets 只 grep 过方法名,读者列表却标「全文」,
    调查 agent 据此判「读全了仍写错」—— 不是全文的不许冒充全文。"""
    if r.get("start") is not None and r.get("n") is not None and not r.get("full"):
        return f"{r['start']}-{r['start'] + r['n'] - 1}行"
    seen_n = r.get("seen_n") or len(r.get("seen") or ())
    if seen_n:
        return f"命中 {seen_n} 行"
    return "全文" if r.get("full") else "范围未知"


def _read_tags(r: dict[str, Any]) -> str:
    t = []
    if r.get("stale"):
        t.append(f"▲旧版 v{r['v']}/{r['latest_v']}")
    span = _read_span(r)
    if span != "全文":
        t.append(span)
    if r.get("dep"):
        t.append("依赖读")
    if r.get("self_written"):
        t.append("同 agent 也写过")
    if r.get("via") == "script":
        t.append("脚本读")
    elif r.get("via") == "inject":
        t.append("注入")
    elif r.get("via") == "stdout":
        t.append("命令输出推出")
    if r.get("certain") is False:
        t.append("版本就近绑定(不确定)")
    if r.get("observation_uncertain"):
        t.append("读写窗口重叠,观测时刻未确认")
    if r.get("availability_basis") in ("input", "dependency"):
        t.append("工具输入/依赖线索,不是返回读回")
    proof = r.get("proof")
    if isinstance(proof, dict) and proof.get("execution") != "confirmed":
        t.append("读取执行依据未核")
    elif isinstance(proof, dict) and not r.get("dep") and proof.get("delivery") != "content":
        t.append("正文交付未核")
    return f" [{' '.join(t)}]" if t else ""


def _clip(text: str, cap: int) -> str:
    text = text or ""
    return text if len(text) <= cap else text[:cap] + f"…(截断,共 {len(text)} 字)"


def _hops(ledger: atoms.Ledger, node: tuple[str, str, int]) -> str:
    """「上游 N/M 跳」:N 累计口径(写之前读过的一切),M 窗口口径(上一效应之后读的);每次 agent↔文件转换算一跳,派发算一跳。"""
    dm, dw = ledger.depth_max.get(node), ledger.depth_win.get(node)
    return f" · 上游 {dm}/{dw} 跳" if dm is not None else ""


def _scan_note(ledger: atoms.Ledger, agent: str | None = None, seq: int | None = None) -> list[str]:
    gaps = [g for g in ledger.scan_gaps if (agent is None or g["agent"] == agent)
            and (seq is None or g["seq"] == seq)]
    if not gaps:
        return []
    return [f"⚠ 提及索引不完备: {len(gaps)} 条记录达到扫描/收集上限,"
            f"{sum(g['chars'] for g in gaps)} 字符未扫描、{sum(g['mentions'] for g in gaps)} 条提及未收集。"
            "未扫描区域可能涉及任何文件;零命中不证明没出现。index(kind=scan) 列原文指针,action 可按 part/offset/find 翻页。"]


def render_index(ledger: atoms.Ledger, kind: str | None = None, query: str | None = None,
                 root: str = "", limit: int = 300) -> str:
    """目录。kind: agent | ets | spec | src | other | None(全部);query 子串过滤。"""
    if kind == "time":
        return render_time_scope(time_scope.overview(ledger), expanded=True, query=query, limit=limit)
    q = (query or "").lower()
    out: list[str] = _scan_note(ledger)
    if kind == "scan":
        gaps = [g for g in ledger.scan_gaps if not q or q in g["agent"].lower() or q == str(g["seq"])]
        out.append(f"# 扫描缺口 {len(gaps)} 条(不是文件覆盖率)")
        for g in gaps[:limit]:
            out.append(f"- {_core(g['seq'], ledger.locs.get(g['seq']))} agent={g['agent']} "
                       f"未扫 {g['chars']} 字符,未收 {g['mentions']} 条提及;来源={','.join(g['sources']) or '提及数量上限'} "
                       f"→ action(id={g['agent']}, seq={g['seq']}, part=input/output, find=…)")
        if len(gaps) > limit:
            out.append(f"还有 {len(gaps) - limit} 条,增大 limit={len(gaps)} 或 query=agent id / 动作号。")
        return "\n".join(out)
    idx = atoms.ledger_index(ledger)
    if kind in (None, "agent"):
        ags = [a for a in idx["agents"]
               if not q or q in str(a["label"]).lower() or q in a["id"].lower()
               or q in str(a.get("kind") or "").lower() or q in a["session"]]
        out.append(f"## agent ({len(ags)})")
        for a in ags[:limit]:
            parent = (f" 派发自 {atoms.agent_label(ledger, a['parent'])}@v{a['parent_ver']}"
                      if a.get("parent") else "")
            stage = f" | 阶段 {a['stage']}" if a.get("stage") else ""
            unres = f" · 未解析读写 {a['n_unresolved']}" if a.get("n_unresolved") else ""
            out.append(f"- {a['label']} | id={a['id']} | {a.get('kind') or 'agent'} | 会话 {a['session']}"
                       f" | {a['n_versions']} 版 · 读 {a['n_reads']}{unres}{stage}{parent}")
        if len(ags) > limit:
            out.append(f"  …还有 {len(ags) - limit} 个,用 query 缩小(pod730 有 221 个 agent,不带 query 一次就是 3 万字)")
    if kind != "agent":
        fs = [f for f in idx["files"] if (kind is None or f["kind"] == kind)
              and (not q or q in f["path"].lower())]
        out.append(f"## 文件 ({len(fs)})")
        for f in fs[:limit]:
            if f["has_writer"]:
                tag = f"{f['n_versions']} 版"
            elif not f["n_versions"] and not f["n_reads"] and not f.get("n_touches") and f.get("n_mentions"):
                tag = "只被提到(命令里出现,无读写记录)"
            elif not f["n_versions"] and f.get("n_touches"):
                tag = "只被脚本碰过(方向不明)"
            else:
                tag = f"{f['n_versions']} 版 · 只被读过(外部输入)"
            touch = f" · 碰过 {f['n_touches']}" if f.get("n_touches") else ""
            if f.get("n_unknown"):
                touch += f" · {f['n_unknown']} 版内容未知(按词查文件查不到这些版)"
            if f.get("n_mentions_unrecorded"):
                touch += f" · {f['n_mentions_unrecorded']} 条命令提到它但没入账(file 末尾列)"
            hops = _hops(ledger, ("f", f["path"], f["n_versions"])) if f["n_versions"] else ""
            out.append(f"- {rel(f['path'], root)} | {f['kind']} | {tag} · 读 {f['n_reads']}{touch}{hops}")
        if len(fs) > limit:
            out.append(f"  …还有 {len(fs) - limit} 个,用 query/kind 缩小")
    return "\n".join(out)


def render_time_scope(scope: dict[str, Any], expanded: bool = False,
                      query: str | None = None, limit: int = 80) -> str:
    """The same bounded metadata is supplied to HTTP; no inferred validation events."""
    roots = scope["roots"]
    latest = scope.get("latest_known_pool_time") or "未知"
    anchor = scope.get("anchor") or {}
    out = [f"全池时间边界: {len(roots)} 个会话分组 · 最晚已记录活动 {latest}（不是验证成功证明）。"]
    if anchor.get("time"):
        later = scope.get("later_sessions") or []
        other = scope.get("other_later_sessions")
        out.append(f"当前查询锚点 {anchor['time']}；之后仍有 {len(later)} 个会话的活动"
                   + (f"（其他会话 {len(other)} 个）" if other is not None else "")
                   + "。早期窗口没构建 ≠ 后续全池没构建；是否包含本次补丁仍需核验。")
        window = scope.get("search_window")
        if window:
            out.append(f"后续窗口查法: search(q=检索词, since_ts=\"{window['since_ts']}\", "
                       f"until_ts=\"{window['until_ts']}\")；这是后续证据，不是生成前输入。")
    if expanded:
        q = (query or "").lower()
        selected = [r for r in roots if not q or q in str(r.get("session") or "").lower()
                    or q in str(r.get("root_agent") or "").lower()]
        for r in selected[:max(0, limit)]:
            vr = r.get("root_versions") or {}
            versions = f" v{vr['first']}–v{vr['last']}" if vr.get("count") else " 无已编号效应版本"
            out.append(f"- 会话 {r.get('session') or '未记录'} · root={r.get('root_agent') or '缺失或歧义'}{versions}"
                       f" · {r.get('observed_start') or '未知'} → {r.get('observed_end') or '未知'}"
                       f" · {r['agent_count']} agents / {r['action_count']} actions")
        if len(selected) > max(0, limit):
            out.append(f"另 {len(selected) - max(0, limit)} 个分组未展开；index(kind=time, limit={len(selected)})。")
        out.append(scope["scope"])
    else:
        out.append("index(kind=time) 展开各会话与主代理版本范围；只覆盖已提供记录，不保证池外、子代理记录齐全。")
    if scope.get("reversed_intervals") or any(scope.get("unknown_timestamps", {}).values()):
        out.append("部分动作时刻缺失/无法排序；零计数不是不存在的证明。")
    return "\n".join(out)


def _unknown_reason(vv: dict[str, Any]) -> str:
    if vv["by"] == "__external__":
        return "外部输入,读取时没带全文快照"
    if vv["by"] == "__outband__":
        return "实录外修改,观测没带全文快照"
    if vv["diff_kind"] == "delete":
        return "该版为删除,内容为空"
    if vv["source"] in ("opaque", "derived"):
        return "脚本/shell 落盘后未被全文读到"
    if vv["source"] == "delta":
        return "edit 作用在未知状态上(盲写)"
    return "覆盖前未被观测"


def _collapse_spine(ledger: atoms.Ledger, rows: list[dict[str, Any]], anchor: int,
                    lines: dict[int, Any]) -> list[dict[str, Any]]:
    """同一写者、同一来路、内容已知与否一致的连续 ≥3 版折成一行;锚点版永远单列。折行 = {"_run": 文本}。"""
    if len(rows) <= 8:
        return rows
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(rows):
        j = i
        key = (rows[i]["by"], rows[i]["via"], rows[i].get("source"), rows[i]["content_known"], rows[i]["diff_kind"])
        while (j + 1 < len(rows) and rows[j + 1]["v"] != anchor and rows[j]["v"] != anchor
               and (rows[j + 1]["by"], rows[j + 1]["via"], rows[j + 1].get("source"), rows[j + 1]["content_known"],
                    rows[j + 1]["diff_kind"]) == key):
            j += 1
        if j - i + 1 >= 3:
            a, b = rows[i], rows[j]
            bv = f"v{a['by_ver']}–v{b['by_ver']}" if a.get("by_ver") is not None and b.get("by_ver") is not None else ""
            ln = (f" · {a['lines']}→{b['lines']} 行" if a.get("lines") is not None and b.get("lines") is not None else "")
            ptr = ""
            if a.get("seq") is not None and b.get("seq") is not None:
                ptr = f" ({_core(a['seq'], lines.get(a['seq']))} … {_core(b['seq'], lines.get(b['seq']))})"
            who = f"{atoms.agent_label(ledger, a['by']) or a['by']} {bv}".strip()
            out.append({"_run": f"- v{a['v']}–v{b['v']} ← {who} | {a['ts'][5:16]}–{b['ts'][11:16]} | {a['diff_kind']} ×{j - i + 1}"
                                f"({j - i + 1} 版){ln}{'' if a['content_known'] else ' · 内容未知'}{ptr}"})
        else:
            out.extend(rows[i:j + 1])
        i = j + 1
    return out



def _evidence_label(vv: dict[str, Any]) -> str:
    """每一版凭什么:工具写/Edit 是「报告成功」(工具说成功,内容是请求的正文);heredoc / ast / cp / 黑盒是「推导」
    (满足执行条件才有这个变换);快照、首见、实录外是「观测」。证据强弱按断言,不按来路一刀切。"""
    src, via, known = vv.get("source"), vv.get("via"), bool(vv.get("content_known"))
    proof = vv.get("proof") or {}
    if src in ("full", "delta", "derived", "opaque", "delete") and proof.get("execution") != "confirmed":
        return "历史操作执行依据未核 · " + str(src)
    if src == "full":
        return "工具写·报告成功" if via == "tool" else ("推导·heredoc 全文" if via == "shell" else "推导·受支持脚本全文")
    if src == "delta":
        return "Edit·报告成功" if via == "tool" else "推导·ast 读改写"
    if src == "derived":
        return "推导·派生自已知源" if known and not vv.get("sealed") else "推导·派生源未知"
    if src == "opaque":
        return "推导·黑盒写"
    if src == "outband":
        return "观测·当前内容,写者未知" if vv.get("state_gap") else "观测·内容变了无写者"
    if src == "external":
        return "观测·首次读到" if known else "首见·内容未进上下文"
    if src == "generated":
        return "推导·脚本字面量含正文"
    if src == "delete":
        return "删除·报告成功"
    return str(src or "")


_MENTION_CLS = {"change": "改动类", "body": "正文提到", "out": "输出里", "readonly": "只读检查", "other": "其他",
                "dispatch": "派发词", "message": "消息", "content": "写入内容", "text": "正文"}
#: 默认折叠的分档:只读检查(噪声)、别的文件写入内容里的清单、说/想/收件正文(量大;search 按词能找)
_MENTION_FOLD = ("readonly", "content", "text")


def render_file(ledger: atoms.Ledger, hint: str, v: int | None = None, root: str = "",
                content: bool = False, diff: bool = False,
                start: int | None = None, n: int | None = None, readers: bool = False,
                v_from: int | None = None, v_to: int | None = None, diff_chars: int | None = None,
                m_from: int = 1, m_n: int = 40, m_all: bool = False) -> str:
    """默认只给写者脊柱与碰过:单根往上追看的是写者。读者是下游,归并阶段才用(指南漏条款波及了哪些页),
    默认一行计数,readers=True 展开;按词找读者用 search(file=)。"""
    from .atom_queries import file_data
    fa = file_data(ledger, hint, v, diff=diff, content=content)
    if fa is None:
        return "\n".join([f"账本里没有该文件: {hint}", *_scan_note(ledger)])
    anchor = fa["v"]
    vv_anchor = fa["versions"][anchor - 1] if fa["versions"] else None
    lines = ledger.locs
    out = [f"# 文件 {rel(fa['path'], root)} @v{anchor}  (共 {fa['n_versions']} 版)"]
    out.append(f"完整路径: {fa['path']}")
    out.append(render_time_scope(fa["time_scope"]))
    out += _scan_note(ledger)
    if vv_anchor is not None:
        out.append("这一版内容: " + ("可复原" if vv_anchor["content_known"]
                                  else ("部分已知(脚本字面量里的正文,不是全文;content=1 看)" if fa.get("partial_known")
                                        else "无法复原 —— " + _unknown_reason(vv_anchor)))
                   + _hops(ledger, ("f", fa["path"], anchor)) + "(累计/窗口口径;每次 agent↔文件转换算一跳,派发算一跳)")
    for b in fa["breaks"]:
        out.append(f"⚠ 断点 {b['kind']} @ {b['ts'][:19]}: {b['detail']}")
    # v 是查询锚点;v_from/v_to 仅选择锚点以内的 diff 窗口,不能偷偷换锚点。
    log = diff and (v is None or v_from is not None or v_to is not None)
    from .atom_queries import validate_file_window
    try:
        validate_file_window(anchor, v_from, v_to)
    except ValueError as exc:
        return str(exc)
    lo_v = max(v_from or 1, 1)
    hi_v = min(v_to or (lo_v + 39), anchor) if log else anchor
    if log:
        out.append(f"## 写者脊柱 + 每版完整 diff(v{lo_v}–v{hi_v} / 共 {anchor} 版;创建版只给行数,content=1 看全文;"
                   "一页 40 版,v_from / v_to 翻页" + (f";每版截 {diff_chars} 字" if diff_chars else "") + ")")
    elif diff:
        out.append("## 写者脊柱(≤ 这一版)—— 只给第 v 版的 diff(同 diff(path, v));区间日志用 file(path, v, diff=1, v_from=…, v_to=…)")
    else:
        out.append("## 写者脊柱(≤ 这一版)—— (#n@L 行) 是写它那次调用的动作号与转录行号,action 展开"
                   + (";同一写者连续几版折成一行,file(path, v=某版) 单看;diff=1 加 v_from/v_to 给区间改动" if len(fa["versions"]) > 8 else ""))
    rows = [r for r in fa["versions"] if lo_v <= r["v"] <= hi_v] if log else fa["versions"]
    for vv in (rows if log else _collapse_spine(ledger, rows, anchor, lines)):
        if vv.get("_run"):
            out.append(vv["_run"])
            continue
        extra = [_evidence_label(vv)]
        if vv.get("source") == "generated":
            # 不是 agent 读源码写的,是脚本一次跑出来的:归因到这里就该问「这批是怎么生成的」而不是「谁写错了」
            runs = ", ".join(f"#{s}" for s in vv.get("gen_runs") or [])
            batch = f"同批 {vv.get('batch')} 个;" if vv.get("batch") else ""
            extra.append(f"批量生成(脚本跑出来的,{batch}候选运行 {runs})")
        elif vv.get("source") == "external" and vv.get("gen_runs"):
            # 候选只导航不入账:跑过可能输出到这个目录的脚本,作者仍是外部输入,候选运行号摆出来让人判
            runs = ", ".join(f"#{s}" for s in vv["gen_runs"])
            batch = f";同批 {vv.get('batch')} 个" if vv.get("batch") else ""
            extra.append(f"候选生成运行 {runs}(目录级线索,未证实{batch})")
        if vv.get("conditional"):
            extra.append("条件分支,是否执行未知")
        if vv.get("win_mentions"):
            extra.append(f"窗口内提及 {vv['win_mentions']} 条(改动类 {vv['win_change']}),见末尾提及节")
        if vv.get("win_writes") and vv.get("win_since") and (not vv["content_known"] or vv.get("source") == "outband"
                                                               or vv.get("sealed")):
            # 内容未知 / 实录外修改 / 封口的版本:谁可能改的按时间圈,只给数和查法,不自动铺(一小时窗口几十条,一万字)
            extra.append(f"窗口内有写能力的命令 {vv['win_writes']} 条(全池,不含写它自己的那条):"
                         f"search(q='', kind=write, since_ts={vv['win_since']}, until_ts={vv['ts']})")
        if vv["sealed"]:
            extra.append("观测封口")
        if vv["lines"] is not None:
            extra.append(f"{vv['lines']} 行")
        if vv.get("partial_known"):
            extra.append("部分已知(脚本字面量)")
        elif not vv["content_known"]:
            extra.append("内容未知")
        mark = " ◀" if vv["v"] == anchor else ""
        ptr = " " + _ref(vv["seq"], None, lines.get(vv["seq"])) if vv.get("seq") is not None else ""
        out.append(f"- v{vv['v']} ← {_who(ledger, vv['by'], vv['by_ver'])} | {vv['ts'][5:16]} {vv.get('t') or ''} | "
                   f"{vv['diff_kind']}" + (" · " + " · ".join(extra) if extra else "") + ptr + mark)
        if diff and vv.get("diff") and (log or vv["v"] == anchor):
            if vv.get("diff_kind") == "creation":
                out.append(f"  (整篇 {vv.get('lines')} 行,创建版不铺;file(path, v={vv['v']}, content=1) 看)")
            elif not log:
                out.append("```diff\n" + _clip(vv["diff"], 6000) + "\n```")
            else:
                out.append("```diff\n" + (_clip(vv["diff"], diff_chars) if diff_chars else vv["diff"]) + "\n```")
        elif log and not vv.get("content_known"):
            out.append("  (内容未知,没有 diff;action 展开那次调用看命令)")
    if log and hi_v < anchor:
        out.append(f"…v{hi_v + 1}–v{anchor} 还有 {anchor - hi_v} 版:file(path, v={anchor}, diff=1, v_from={hi_v + 1}) 续页")
    rlist = [r for r in fa["readers"] if r["v"] == anchor]
    if not readers:
        out.append(f"## 读者 {len(rlist)} 个(下游;readers=1 展开;按词找用 search(file=))")
    else:
        out.append(f"## 读了 @v{anchor} 的 agent(下游,{len(rlist)})—— action 展开能看到它读到的原文")
        for r in rlist:
            span = _read_span(r)
            flags = ("" if r["certain"] else " · 版本就近绑定(不确定)") + (" · 依赖读" if r["dep"] else "")
            flags += " · 注入" if r.get("via") == "inject" else ""
            ptr = " " + _ref(r["seq"], None, lines.get(r["seq"])) if r.get("seq") is not None else ""
            out.append(f"- {_who(ledger, r['by'], r['at'])} | {r['ts'][5:16]} {r.get('t') or ''} | {span}{flags}{ptr}")
    if fa.get("touches"):
        # 脚本碰过它但账本判不出读写:不立版本,只给指针 —— 展开 action 看原文,别当它没被改过
        out.append(f"## 碰过它、方向不明的调用({len(fa['touches'])}) —— 不立版本;action(id, n) 展开看是读是写")
        for t in fa["touches"]:
            out.append(f"- {_who(ledger, t['by'], t['by_ver'])} | {t['ts'][5:16]} {t.get('t') or ''} | {t['reason']}"
                       f" | action{_ref(t['seq'], None, lines.get(t['seq']))}")
    if fa.get("mentions"):
        # 原始转录按文件名 grep 会跳出来的命令,这里一条不少:解析器放弃的、当成无关的、写在 heredoc 正文里的、输出里点名的都在。
        # 已入账的折成计数;没记到的按分档逐条列(改动类 / 正文提到 / 输出里 / 其他),只读检查默认折叠(m_all=1 铺);
        # 一页 m_n 条,m_from 翻页 —— 底层一条不丢,没返回的不算看过
        ms = fa["mentions"]
        miss = [m for m in ms if m["effect"] is None]
        kinds: dict[str, int] = {}
        for m in ms:
            if m["effect"]:
                k = "写" if str(m["effect"]).startswith("写") else str(m["effect"])
                kinds[k] = kinds.get(k, 0) + 1
        done = "、".join(f"{k} {n} 次" for k, n in kinds.items())
        listed = [m for m in miss if m_all or m.get("cls") not in _MENTION_FOLD]
        folded = len(miss) - len(listed)
        fold_by: dict[str, int] = {}
        for m in miss:
            if m.get("cls") in _MENTION_FOLD:
                k = _MENTION_CLS.get(str(m.get("cls")), "其他")
                fold_by[k] = fold_by.get(k, 0) + 1
        out.append(f"## 提到它的命令({len(ms)},其中 {len(miss)} 条账本没记到读写)—— 命令行 / heredoc 体 / 跑的脚本正文 / "
                   "工具输出里出现这个路径;版本无法复原或实录外修改时先看这里,action 展开命令原文自己判")
        if done:
            out.append(f"已入账的 {len(ms) - len(miss)} 条({done})脊柱与读者里已有,不再铺")
        if folded:
            out.append("折叠 " + "、".join(f"{k} {n} 条" for k, n in fold_by.items())
                       + "(只读检查 = cat / grep / wc / ls;写入内容 = 别的文件正文里列了它;正文 = 说 / 想 / 收件;m_all=1 铺)")
        lo = max(m_from, 1)
        page = listed[lo - 1:lo - 1 + max(m_n, 0)]
        hi = lo - 1 + len(page)
        if listed and m_n <= 0:
            out.append(f"候选仅计数,未展开 {len(listed)} 条;需要时 file(path, v={anchor}, m_n=40, m_from=1) 查看。"
                       "没有展开不等于没有候选,也不能据此断言无人读写。")
        elif listed:
            out.append(f"第 {lo}–{hi} 条 / 共 {len(listed)} 条"
                       + (f";剩余 {len(listed) - hi}:file(path, m_from={hi + 1})" if hi < len(listed) else ""))
        for m in page:
            amb = " · 只给了文件名,同名不止一个" if m.get("ambiguous") else ""
            win = f"v{m['win']} 窗口" if m.get("win") else "最新版之后"
            out.append(f"- {win} | {_who(ledger, m['by'], m['by_ver'])} | {m['ts'][5:16]} {m.get('t') or ''} | "
                       f"[{_MENTION_CLS.get(str(m.get('cls')), '其他')}]{amb} | …{m['ctx']}… | "
                       f"action{_ref(m['seq'], None, lines.get(m['seq']))}")
    if content:
        if fa["content"] is None and fa.get("partial"):
            out.append("## 内容(部分,脚本字面量里的正文;行号不是文件行号)")
            out.append("```\n" + _clip(str(fa["partial"]), 6000) + "\n```")
        elif fa["content"] is None:
            out.append("## 内容: 无法复原")
        else:
            body = fa["content"].replace("\n", "\n", 1).split("\n")
            if body and body[-1] == "":
                body.pop()
            lo = max(start or 1, 1)
            hi = min(lo + n - 1, len(body)) if (start and n) else len(body)
            out.append(f"## 内容 @v{anchor}(第 {lo}-{hi} 行 / 共 {len(body)} 行)")
            width = len(str(hi))
            out.append("```")
            for i in range(lo - 1, hi):
                out.append(f"{i + 1:>{width}} | {body[i]}")
            out.append("```")
    return "\n".join(out)


def _seen_suffix(r: dict[str, Any]) -> str:
    """命中读默认只留行号(看原文用 seen=True 或 action 展开)。行号必须露出来:复跑教训,第 615 行不在摘要里,
    调查员就没去展开 #4641。"""
    seen = r.get("seen") or []
    if not seen:
        return ""
    if all(not ln for ln, _t in seen):
        return f" [看见 {len(seen)} 行,行号未知]"      # 循环 + echo 分隔切出来的段落
    nums = ", ".join(str(ln) for ln, _t in seen[:20])
    return f" [行号 {nums}{'…' if len(seen) > 20 else ''}]"


def _vtag(r: dict[str, Any]) -> str:
    return f"@v{r['v']}" if r.get("v") is not None else "(图片,不立版本)"


def _possible_suffix(ledger: atoms.Ledger, a: dict[str, Any], root: str) -> str:
    """解不出效应的命令直接带「可能碰了 A.ets@v3」(当时的版本按时刻就近),不用经 action 才看到。"""
    if a.get("files"):
        return ""
    paths = [p for p in ledger.mention_seq.get(a["seq"], []) if atoms.mention_effect(ledger, p, a["seq"]) is None]
    if not paths:
        return ""
    items = [f"{rel(p, root)}@v{atoms.version_at(ledger, p, a['ts'])}" for p in paths[:3]]
    return " · 可能碰了 " + ", ".join(items) + (f" …共 {len(paths)}" if len(paths) > 3 else "")


def render_agent(ledger: atoms.Ledger, agent_id: str, v: int | None = None,
                 root: str = "", full_text: bool = True, since: int | None = None,
                 reads: bool | None = None, seen: bool = False, until: int | None = None) -> str:
    """默认是索引:头部、派发词全文、收件索引行、逐版效应、读记录按调用合行(安卓路径缩短、看见的行只留行号)、
    正文索引行、收尾。0723 复盘:agent 整段 1.27 万字里三分之二是读清单和看见的行,报告每根只引 6 个文件名和
    6 次「看见」;信息不删,只是不默认铺开 —— seen=True 铺原文,reads=False 只给每版读的条数。
    曾试过默认折叠非目标版本的窗口(变体 B):调查员改用逐窗口查询,总字符没省,还把 AboutUsPage 那条链
    误判成「漏读」—— 整段仍给,只是压短。"""
    from .atom_queries import agent_data
    try:
        ag = agent_data(ledger, agent_id, v, since=since, until=until)
    except ValueError as exc:
        return f"⛔ until 时间截止无法核验，未打开 agent: {exc}"
    if ag is None:
        return f"账本里没有该 agent: {agent_id}"
    anchor = ag["v"]
    big_note = ""
    if reads is None and since is None and ag["n_versions"] > 25:
        # pod730 一个 closer 52 版,整段 1.8 万字里读清单占大头:大 agent 不带窗口只给每版读的条数
        reads = False
        big_note = "(超过 25 版且没带 since 窗口:读只给条数;reads=1 全铺,或 agent(id, v, since=v-1) 看一版的窗口)"
    elif reads is None:
        reads = True
    lines = ledger.locs
    out = [f"# agent {ag['label']}  id={ag['id']}  v{anchor} / 共 {ag['n_versions']} 版"
           + (f"  窗口 v{since + 1}–v{anchor}(只给喂养这段版本的动作)" if since is not None else "")
           + _hops(ledger, ("a", ag["id"], anchor))
           + (f"  截到 #{until} 为止(之后的输入不算这一版的依据)" if until is not None else "")]
    ident = [ag.get("kind") or "agent", f"会话 {ag['session']}"]
    if ag.get("model"):
        ident.append(ag["model"])
    if ag.get("description"):
        ident.append(ag["description"])
    out.append("身份: " + " · ".join(ident))
    out.append(render_time_scope(ag.get("time_scope") or time_scope.for_atom(ledger, "agent", ag, until=until)))
    input_scope = ag.get("input_scope") or {}
    omitted = input_scope.get("omitted_prior") or {}
    if any(omitted.values()):
        out.append("早期输入索引(本窗口未展开，不等于没有): "
                   + " · ".join(f"{key} {count}" for key, count in omitted.items() if count))
        for r in input_scope.get("prior_read_preview") or []:
            out.append(f"  早期读 {_short(r['path'], root)}{_vtag(r)}{_read_tags(r)} → 喂 v{r['at']} "
                       + _ref(r["seq"], None, lines.get(r["seq"])))
        remaining = input_scope.get("prior_read_remaining") or 0
        query = input_scope.get("prior_query")
        if query:
            out.append((f"  另有 {remaining} 条早期读；" if remaining else "  ")
                       + f"展开 agent({query['id']}, v={query['v']}, reads=True)；"
                       + "早期记录是否相关由调查判断，未继承本次 until 截止。")
    cutoff = ag.get("cutoff")
    if cutoff:
        out.append("截止输入边界: " + cutoff["use_ts"] + "；发起序号在前不等于结果已返回。")
        for kind in ("deferred_reads", "deferred_effects"):
            rows = cutoff.get(kind) or []
            if rows:
                out.append(("截止时未确认可用的读取" if kind == "deferred_reads" else "截止时未确认完成的效应")
                           + f" {len(rows)} 条，不计为当时已知输入/完成输出。")
                for r in rows:
                    out.append(f"  {_core(r.get('seq'), ledger.locs.get(r.get('seq')))} "
                               + str(r.get("path") or r.get("tool") or "") + " · " + str(r.get("reason") or "需核时刻")
                               + "；action 可核原文（可能含截止后结果）。")
        if any((cutoff.get("excluded") or {}).values()):
            out.append("窗口外索引项另计: " + str(cutoff["excluded"]) + "；去掉 until 可查，不是没有发生。")
    out += _scan_note(ledger, ag["id"])
    if ag.get("t0"):
        out.append(f"时刻: 动作号旁的 T+h:mm 相对迁移开始 {ag['t0']}(池子里最早一条动作),跨 agent 对先后用它;"
                   "@L 是转录行号")
    if ag["parent"]:
        out.append(f"派发自: {ag['parent']['name'] or ag['parent']['id']} @v{ag['parent']['ver']}"
                   f"  (id={ag['parent']['id']})")
        if ag.get("kind"):
            # 它的类型定义(技能 / agent 说明)由 harness 放进系统提示,转录里没有:conv-mine 的「固有尺寸交
            # icon-sizing 自愈」在它全部记录里找不到来源,就是这一层;search 到不了,别把零命中当「杜撰」
            out.append(f"定义: 类型 {ag['kind']} 不证明具体输入;转录中的系统/注入文本可展开核对,未记录的说明仍未知。")
    if ag["prompt"] and since is not None:
        out.append(f"## 派发指令: 见 agent({ag['id']}, v=1)(窗口查询不重印,{len(ag['prompt'])} 字)")
    elif ag["prompt"]:
        out.append("## 派发指令(全文)\n" + (_clip(ag["prompt"], 12000) if full_text else _clip(ag["prompt"], 600)))
    inbox = [m for m in ag["inbox"] if not (ag["prompt"] and m["text"] == ag["prompt"])]
    if inbox:
        out.append(f"## 收件箱({len(inbox)}) —— 一行一条,action 展开全文")
        for m in inbox:
            late = " (锚点之后)" if m["after_anchor"] else ""
            out.append(f"- 喂 v{m['at']}{late} · 来自 {m['from']}" + (f" · {m['summary']}" if m.get("summary") else "")
                       + f" · {_clip(' '.join(str(m.get('text') or '').split()), 160)} "
                       + _ref(m.get("seq"), None, lines.get(m.get("seq") or -1)))
    by_ver: dict[int, dict[str, list[Any]]] = {}
    for a in ag["actions"]:
        k = a["ver"] if a["ver"] is not None else a["at"]
        slot = by_ver.setdefault(k, {"eff": [], "inp": []})
        slot["eff" if a["ver"] is not None else "inp"].append(a)
    reads_by_at: dict[int, list[dict[str, Any]]] = {}
    for r in ag["reads"]:
        if r.get("via") == "inject":
            continue          # 注入行已经点名了这份技能,SKILL.md 的读边留给 file() 的读者用
        reads_by_at.setdefault(r["at"], []).append(r)
    out.append("## 逐版时间线(每个对外效应 +1 版;读归到它喂养的下一版;(#n@L 行) 是动作号与转录行号,"
               "action(id, n) 可展开该次调用的完整输入输出;同一次调用读的文件合在一行)" + big_note)
    for k in sorted(by_ver):
        slot = by_ver[k]
        late = k > anchor
        head = f"### v{k}" if k <= ag["n_versions"] else "### 收尾后"
        stg = next((a.get("stage") for a in slot["eff"] if a.get("stage")), None)
        if stg:
            head += f" · 阶段 {stg}"
        if late:
            head += " (锚点之后,非因果)"
        out.append(head)
        for a in slot["eff"]:
            d = a["detail"]
            tag = " " + _ref(a["seq"], a.get("t"), lines.get(a["seq"]))
            if a.get("completion_state") in ("pending", "unknown"):
                out.append(f"- 已发起 {a['tool']}{tag} · 截止时" + ("尚未返回" if a["completion_state"] == "pending" else "完成情况未知")
                           + "；不作为已完成写入/派发，action 可核原文。")
                continue
            if a["kind"] == "dispatch":
                out.append(f"- 派发 {d.get('name') or d.get('description') or '子agent'}"
                           + (f"  (子 agent id={d['child']})" if d.get("child") else "") + tag)
            elif a["kind"] == "message":
                out.append(f"- 发消息 → {d.get('to')}: {_clip(d.get('text') or '', 300)}{tag}")
            else:
                fs = [f for f in a["files"] if f["op"] != "read"]
                if fs:
                    out.append("- " + ", ".join(
                        ("删 " if f["op"] == "delete" else "写 ") + f"{rel(f['path'], root)}@v{f['v']}"
                        + ("(脚本落盘)" if f["via"] == "script" else "(shell)" if f["via"] == "shell" else "")
                        for f in fs) + (f"  ← {d['cmd']}" if d.get("cmd") else "") + tag)
                else:
                    out.append(f"- {a['tool']}" + ("" if a["ok"] else "(失败)")
                               + (f": {d['cmd']}" if d.get("cmd") else "") + tag)
        rs = reads_by_at.get(k, [])
        if rs and not reads:
            out.append(f"  读 {len(rs)} 条(reads=True 展开)")
        elif rs:
            groups: dict[int, list[dict[str, Any]]] = {}
            for r in rs:
                groups.setdefault(r["seq"], []).append(r)
            for seq, grp in groups.items():
                ref = _ref(seq, grp[0].get("t"), lines.get(seq))
                if len(grp) == 1:
                    r = grp[0]
                    out.append(f"  读 {_short(r['path'], root)}{_vtag(r)}{_read_tags(r)}{_seen_suffix(r)} {ref}")
                else:
                    items = [f"{r['path'].rsplit('/', 1)[-1]}{_vtag(r)}{_read_tags(r)}{_seen_suffix(r)}" for r in grp[:12]]
                    more = f" …共 {len(grp)} 个" if len(grp) > 12 else ""
                    out.append(f"  读 {len(grp)} 个文件 {ref}: " + ", ".join(items) + more)
                if seen:
                    for r in grp:
                        sl = r.get("seen") or []
                        for ln, t in sl[:3]:
                            out.append(f"      看见 {ln if ln else '(行号未知)'}: {_clip(str(t).strip(), 160)}")
                        if len(sl) > 3:
                            out.append(f"      …共 {len(sl)} 行;action(#{r['seq']}) 展开原文")
        others = [a for a in slot["inp"] if a["kind"] not in ("read", "inbox")]
        injects = [a for a in others if a["kind"] == "inject"]
        if len(injects) > 3:
            # 被灌 17 份技能就是 17 行,与本链有关的多半只有一份:折成一行点名,action 展开各份
            names = ", ".join(str(a["detail"].get("skill") or "?") for a in injects)
            first = injects[0]
            out.append(f"  注入技能 {len(injects)} 份: {names} "
                       + _ref(first["seq"], first.get("t"), lines.get(first["seq"])))
            others = [a for a in others if a["kind"] != "inject"]
        for a in others:
            d = a["detail"]
            ref = _ref(a["seq"], a.get("t"), lines.get(a["seq"]))
            if a.get("completion_state") in ("pending", "unknown"):
                out.append(f"  已发起 {a['tool']} {ref} · 截止时" + ("尚未返回" if a["completion_state"] == "pending" else "完成情况未知")
                           + "；不作为已返回输入，action 可核原文。")
                continue
            if a["kind"] in _TEXT_KINDS:
                out.append(f"  {_TEXT_KINDS[a['kind']]}: {_clip(d.get('skill') or d.get('text') or '', 120)} {ref}")
                continue
            desc = d.get("cmd") or d.get("pattern") or d.get("skill") or d.get("url") or ""
            poss = _possible_suffix(ledger, a, root)
            if d.get("unresolved"):
                # 解析不了的读写不许静默:调查员据此知道该展开哪次 action 看原文
                out.append(f"  ⚠ 未解析读写({d['unresolved']}) {a['tool']}: {_clip(desc, 120)} {ref}{poss}")
                continue
            out.append(f"  {a['tool']}" + ("" if a["ok"] else "(失败)") + (f": {desc}" if desc else "") + " " + ref + poss)
        inboxes = [a for a in slot["inp"] if a["kind"] == "inbox"]
        if inboxes:
            out.append(f"  收件 {len(inboxes)} 条(见上)")
    # 收尾是最后一版之后的事:问第 v 版(v 不是最后一版)时不给,按版本切;给也只给索引行,全文 action 展开
    if ag["result"] and ag["result"]["text"] and (v is None or anchor >= ag["n_versions"]):
        says = [a for a in ag["actions"] if a["kind"] == "say"]
        ref = " " + _ref(says[-1]["seq"], says[-1].get("t"), lines.get(says[-1]["seq"])) if says else ""
        par = ag.get("parent") or {}
        # 收尾全文在父会话那条派发调用的结果里,子自己的 say 往往只是最后一句
        where = (f"action({par['id']}, {par['seq']}) 展开全文(父会话派发调用的结果)" if par.get("seq")
                 else "action 展开全文")
        out.append(f"## 收尾输出(锚点之后,非因果证据){ref} —— {where}\n"
                   + _clip(" ".join(str(ag["result"]["text"]).split()), 300))
    return "\n".join(out)


def _window(text: str, cap: int, offset: int = 0, find: str = "") -> tuple[str, str]:
    """长原文取一段:find 给了就跳到关键词前 200 字;截断处明说剩多少、offset 多少继续 —— 静默前缀截断会让人
    误以为看到了全文(DiceRoller think #4218 有 9.8 万字,决策句在 2 万字之后)。"""
    total = len(text)
    note = ""
    if find:
        pos = text.lower().find(find.lower(), max(offset, 0))
        if pos < 0:
            note = f"「{find}」在第 {offset} 字之后未命中;"
        else:
            offset = max(0, pos - 200)
    offset = max(0, min(offset, total))
    if offset == total and total > 0:
        return "", note + f"已到末尾(EOF)，共 {total} 字；本页为空，offset=0 可回到开头"
    piece = text[offset:offset + cap]
    end = offset + len(piece)
    if offset == 0 and end == total:
        return piece, note.rstrip(";")
    rest = total - end
    note += f"第 {offset + 1}-{end} 字 / 共 {total} 字" + (f";剩余 {rest} 字,offset={end} 继续" if rest else "")
    return piece, note


def render_repair_manifest(ledger: atoms.Ledger, payload: dict[str, Any], hint: str,
                           root: str = "") -> str:
    """Expose the fixed ledger denominator; do not equate accounted rows with true causes."""
    from . import coverage as repair_coverage

    doc = repair_coverage.manifest(ledger, payload, hint)
    out = ["## 版本与候选对账清单（记录内范围，不等于真实缺陷总数）"]
    if doc.get("errors"):
        return "\n".join(out + ["清单无法确定: " + "; ".join(str(x) for x in doc["errors"])])
    from .guidance import verdict_version
    compact = verdict_version() == "2"
    out.append(f"共 {len(doc['items'])} 个返修阶段记录版本 + {len(doc['candidates'])} 个待核候选。"
               + ("有具体判断的项写coverage.reviewed，其余系统标未调查；清单凭据见末尾。" if compact else
                  "每项须在 coverage 单独交代;repair.before/after 区间不能代替中间项。"))
    out.append("可标 explained / unresolved / out_of_scope / not_repair。"
               + ("out_of_scope=有依据的题外判断；没调查的直接留在系统补集，仍留在分母；" if compact else
                  "out_of_scope=本题未调查，仍留在分母；")
               +
               "not_repair=有依据认为非修复，不能仅因为不在题目内。阶段后新增不自动是生成错误，写了理由不等于理由已证实。")
    excluded = (doc.get("candidate_scope") or {}).get("excluded_nonexecution") or {}
    if excluded:
        out.append("未列入执行候选的纯文本记录: " + ", ".join(f"{kind}={count}" for kind, count in sorted(excluded.items()))
                   + "。仍可通过提及/search/action 查原文;不证明其中自述的外部修改没有发生。")
    for item in doc["items"]:
        node = f"file:{rel(str(doc['file']), root)}@v{item['v']}"
        event = item.get("event") or {}
        change = item.get("change") or {}
        out.append(f"- {node} · {item.get('source')} · 内容{'已观测/可复原' if item.get('content_known') else '未知'}"
                   + (f" · {event['ref']}" if event.get("ref") else " · 原始调用指针未知"))
        snippet = str(change.get("text") or "变化细节未知")
        cue = snippet.replace("\n", " ⏎ ")
        out.append("  变化线索（不是归因）: " + cue[:450]
                   + (" …（摘录已截断，完整变化请用 diff/action）" if len(cue) > 450 or change.get("truncated") else ""))
    if doc["candidates"]:
        scope = doc.get("candidate_scope") or {}
        out.append("### 待核候选（不是已确认修复，不新增作者或版本）")
        out.append("来源为修复参与者窗口内的方向不明触碰及精确路径提及；窗口: " + str(scope.get("window_scope")))
        out.append("同一动作仅列一次；用 action 核对 input/output 的真实目标和效应。已核明未影响目标/只读可记 not_repair；"
                   + ("本题不调查留系统补集，调查后证据不足记 unresolved，确认修复后关联 defect。" if compact else
                      "本题不调查记 out_of_scope，调查后证据不足记 unresolved，确认修复后关联 defect。") +
                   "未立正式版本不等于未写入：脚本执行及输出也可作为效应证据，须说明证据强度。")
        for item in doc["candidates"]:
            out.append(f"- {item['id']} · {item['ref'] or '原始调用指针未知'} · agent:{item['agent']} · {item['ts']}")
            out.append("  线索（不是事实）: " + str(item.get("reason") or "效应待核") + " · " + str(item.get("ctx") or ""))
    out.append("此清单不覆盖索引之外的真实写入,也不证明一个版本内每个语义修改均已解释;已交代不等于已查清,候选不等于修复。")
    if compact:
        from .coverage_receipt import receipt
        import json
        out.append("MIGLOOP_COVERAGE_RECEIPT " + json.dumps(receipt(doc), ensure_ascii=False, separators=(",", ":")))
    return "\n".join(out)


def render_action(ledger: atoms.Ledger, agent_id: str, seq: int, max_chars: int = 20000,
                  offset: int = 0, find: str = "", part: str | None = None,
                  m_n: int = 40, m_from: int = 1) -> str:
    """一次工具调用的原始输入输出 —— 账本是实录的索引,这里按指针展开原文,不经摘要。
    part=input/output 可选择翻页侧;不指定时共享正文预算,offset/find仍定位输出侧。"""
    import json

    raw = atoms.action_raw(ledger, agent_id, seq)
    if raw is None:
        return f"没有这个动作: {agent_id} #{seq}(或它没有原始记录指针)"
    links = atoms.action_links(ledger, agent_id, seq)
    if links.get("ver") is not None:
        version_note = f"效应 v{links['ver']}" if raw["ver"] is not None else f"喂 v{links['ver']}"
    else:
        tail = "收尾后" if links.get("after_last_effect") and links.get("n_versions") else "未形成效应版本"
        version_note = f"{tail}(喂养槽 {raw['at']};已记录 {links.get('n_versions', 0)} 个效应版本,无可导航版本)"
    head = (f"# 动作 #{raw['seq']} · {raw['tool']} · {raw['ts'][:19]} · "
            + ("成功" if raw["ok"] else "失败" if raw["ok"] is False else "无结果")
            + " · " + version_note)
    inp = raw["input"]
    inp_text = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False, indent=1)
    if part not in (None, "input", "output"):
        return "part 只能是 input 或 output"
    if max_chars < 1:
        return "max_chars 必须大于 0"
    if part == "input":
        in_piece, in_note = _window(inp_text, max_chars, offset, find)
        piece, note = "(未展开;part=output 查看)", ""
    elif part == "output":
        in_piece, in_note = "(未展开;part=input 查看)", ""
        piece, note = _window(raw["output"], max_chars, offset, find)
    elif raw["output"]:
        # A short stdout must not force an otherwise-fitting script behind a 1/3 preview.
        # Both displayed bodies share the cap; details remain available per side.
        in_cap = min(len(inp_text), max(max_chars // 2, max_chars - len(raw["output"])))
        in_piece, in_note = _window(inp_text, in_cap)
        piece, note = _window(raw["output"], max_chars - len(in_piece), offset, find)
    else:
        # think / say / 派发词:正文在输入侧,输出为空 —— offset / find 作用在这一侧
        in_piece, in_note = _window(inp_text, max_chars, offset, find)
        piece, note = "(空)", ""
    out = [head]
    if in_note:
        in_note += ";part=input 单独展开/翻页"
    if note:
        note += ";part=output 单独展开/翻页"
    owner = atoms.resolve_agent(ledger, agent_id)
    out += _scan_note(ledger, owner.id if owner else agent_id, seq)
    loc = ledger.locs.get(seq)
    out.append("原文引用: " + (_core(seq, loc) if loc else "未知(未记录转录定位,不能拼造引用)"))
    eid = atoms.event_id(ledger, agent_id, seq)
    if eid:
        out.append(f"事件 id {eid}(会话:转录:原始事件ID或行/块;用于事件识别,不是上行的原文引用)")
    if raw.get("claim_note"):
        out.append("证据类别: " + str(raw["claim_note"]) + (f" · 来源 {raw['sender']}" if raw.get("sender") else ""))
    if links:
        if links["ver"] is not None:
            out.append(f"发自 {links['label']} (id={links['agent']}) v{links['ver']}"
                       + ("(这次调用就是这一版的效应)" if links["is_effect"] else "(喂这一版)")
                       + f" → agent({links['agent']}, v={links['ver']})")
        else:
            out.append(f"发自 {links['label']} (id={links['agent']}) · {version_note}")
        if links["files"]:
            out.append("## 账本记到的读写 → file(path, v)")
            for f in links["files"]:
                op = "读" if f["op"] == "read" else "删" if f["op"] == "delete" else "写"
                flags = _read_tags(f) if f["op"] == "read" else ""
                out.append(f"- {op} {f['path']}@v{f['v']}{flags} → file({f['path']}, v={f['v']})")
        if links["possible"]:
            total = len(links["possible"])
            size, start = max(0, min(int(m_n), 200)), max(1, int(m_from))
            page = links["possible"][start - 1:start - 1 + size]
            query = f"action(id={agent_id}, seq={seq}, m_n=40, m_from="
            out.append(f"## 命令里提到、账本没记到读写的文件({total} 条候选;不是确定读写)")
            if not size:
                out.append(f"候选仅计数,未展开 {total} 条;需要时 {query}1) 查看。未展开不等于没有候选。")
            elif start > total:
                out.append(f"m_from={start} 超出 {total} 条候选;从 {query}1) 查看。")
            else:
                out.append(f"候选第 {start}-{start + len(page) - 1} / {total} 条;「当时」仅按时刻就近 → file(path, v)")
            for p in page:
                amb = " · 只给了文件名,同名不止一个" if p["ambiguous"] else ""
                out.append(f"- {p['path']} 当时@v{p['v']}{amb} | …{p['ctx']}… → file({p['path']}, v={max(p['v'], 1)})")
            if size and start - 1 + len(page) < total:
                out.append(f"还有 {total - start + 1 - len(page)} 条候选未展开;{query}{start + len(page)}) 继续。")
    out += ["## 输入" + (f"({in_note})" if in_note else ""), "```", in_piece, "```",
            "## 输出" + (f"({note})" if note else ""), "```", piece, "```"]
    tur = raw.get("tool_use_result")
    if isinstance(tur, dict) and isinstance(tur.get("file"), dict):
        f = tur["file"]
        out.append(f"(toolUseResult.file: {f.get('filePath')} 第 {f.get('startLine')} 行起 "
                   f"{f.get('numLines')} / {f.get('totalLines')} 行)")
    return "\n".join(out)


def render_blame(ledger: atoms.Ledger, hint: str, v: int | None = None,
                 start: int | None = None, n: int | None = None, root: str = "",
                 changed: bool = False) -> str:
    bl = atoms.blame(ledger, hint, v, start, n, changed=changed)
    if bl is None:
        return f"账本里没有该文件: {hint}"
    from .blame_recovery import render
    recovery = "\n" + render(bl["recovery"], root) if bl.get("recovery") else ""
    if changed:
        return _render_blame_changed(ledger, bl, root) + recovery
    out = [f"# 逐行归属 {rel(bl['path'], root)} @v{bl['v']}  (共 {bl['n_versions']} 版)"]
    if not bl["known"]:
        out.append("这一版内容未知,无法逐行归属(见 file 的复原原因)。")
        return "\n".join(out) + recovery
    out.append("## 汇总")
    for s in bl["summary"]:
        out.append(f"- {atoms.agent_label(ledger, s['owner'])} (id={s['owner']}): {s['n']} 行")
    if bl["unknown"]:
        out.append(f"- 归属未知(断点后): {bl['unknown']} 行")
    if bl["lines"]:
        out.append(f"## 逐行(第 {bl['lines'][0]['ln']}-{bl['lines'][-1]['ln']} 行 / 共 {bl['n_lines']} 行)")
        width = len(str(bl["lines"][-1]["ln"]))
        out.append("```")
        for x in bl["lines"]:
            who = f"{x['owner_name'] or x['owner']}@v{x['since_v']}" if x["owner"] else "?"
            if x.get("inferred"):
                who += " 跨断点同文推定"
            out.append(f"{x['ln']:>{width}} | {who:<28} | {x['text']}")
        out.append("```")
    return "\n".join(out)


def _render_blame_changed(ledger: atoms.Ledger, bl: dict[str, Any], root: str) -> str:
    """修复版替换/删除了哪些行、谁引入的 —— 只给这几行,不给整文件。"""
    head = f"# 被替换行归属 {rel(bl['path'], root)} @v{bl['v']}  (共 {bl['n_versions']} 版)"
    if not bl["known"]:
        return head + "\n" + str(bl.get("note") or "无法定位被替换行")
    out = [head, f"可观测端点文本比较：v{bl['v']} 替换/删除了 v{bl['prev_v']} 的 {len(bl['lines'])} 行,新增 {bl['added']} 行"
                 f"(前一版共 {bl['n_lines']} 行;新增行没有对应的旧行原作者)"]
    if bl.get("comparison_note"):
        out.append(str(bl["comparison_note"]))
    if bl["summary"]:
        out.append("## 被替换行的原作者")
        for s in bl["summary"]:
            out.append(f"- {atoms.agent_label(ledger, s['owner'])} (id={s['owner']}): {s['n']} 行")
    if bl["unknown"]:
        out.append(f"- 归属未知(断点后): {bl['unknown']} 行")
    if bl["lines"]:
        out.append(f"## 逐行(v{bl['prev_v']} 的行号)")
        width = len(str(bl["lines"][-1]["ln"]))
        out.append("```")
        for x in bl["lines"]:
            who = f"{x['owner_name'] or x['owner']}@v{x['since_v']}" if x["owner"] else "?"
            if x.get("inferred"):
                who += " 跨断点同文推定"
            out.append(f"{x['ln']:>{width}} | {who:<28} | {x['text']}")
        out.append("```")
    return "\n".join(out)


def render_diff(ledger: atoms.Ledger, hint: str, v: int, root: str = "") -> str:
    fa = atoms.file_atom(ledger, hint, v, with_diff=True, with_content=False)
    if fa is None or not fa["versions"]:
        return f"账本里没有该文件/版本: {hint}@v{v}"
    vv = fa["versions"][-1]
    head = f"# diff {rel(fa['path'], root)} @v{vv['v']} ← {_who(ledger, vv['by'], vv['by_ver'])} · {vv['diff_kind']}"
    if not vv.get("diff"):
        if vv.get("content_known"):
            bl = atoms.blame(ledger, hint, v, changed=True)
            if bl and bl["known"]:
                if not bl["lines"] and bl["added"] == 0:
                    return head + "\n可观测端点文本相同：净新增 0 行、净删除/替换 0 行，无非空 diff 正文。\n" + str(bl["comparison_note"])
                return (head + f"\n未保存 diff 正文；端点比较净新增 {bl['added']} 行、净删除/替换 {len(bl['lines'])} 行。\n"
                        + str(bl["comparison_note"]))
            return head + "\n本版内容可见；" + str((bl or {}).get("note") or "前一版无法比较") + "。无 diff 正文不等于没有变化。"
        return head + "\n(无 diff 正文:" + _unknown_reason(vv) + ")"
    return head + "\n```diff\n" + _clip(vv["diff"], 20000) + "\n```"


def render_chains(payload: dict[str, Any], root: str = "", file: str | None = None,
                  identity: str | None = None) -> str:
    """file 给了只回目标文件那条链(文件名 / 相对路径 / 绝对路径都行):调查一条链不必把全部链读一遍。
    identity 给了写在首行:结论块的 ledger 字段照抄它。"""
    head = [f"账本身份: {identity}"] if identity else []
    chains = payload.get("chains") or []
    touched = payload.get("touched") or []
    total = len(chains)
    if file:
        want = file.replace("\\", "/").lstrip("/")
        chains = [c for c in chains if any(_same_file(p, want) for p in (c.get("file_abs"), c.get("file")) if p)]
        # 「碰过」附录也只列这个文件:0723 上全列是 54 个文件 6.5K 字,每根调查从第二次调用起就一直背着
        touched = [t for t in touched if _same_file(t["path"], want)]
        if not chains and not touched:
            return "\n".join([*head, f"# 返修链(0/{total},只看 {want})",
                              "没有匹配的链;不带 file 看全部,或先用 index 确认路径。"])
        out = [*head, f"# 返修链({len(chains)}/{total},只看 {want})"]
        if not chains:
            out.append("没有匹配的链(下面只有脚本碰过的记录);不带 file 看全部,或先用 index 确认路径。")
    else:
        out = [*head, f"# 返修链({total})"]
    cross = payload.get("cross") or {}
    if cross.get("priors"):
        out.append(f"前序会话: {', '.join(cross['priors'])} · 跨会话链 {cross.get('n_cross', 0)}")
    for c in chains:
        g, fx = c.get("generator") or {}, c.get("fixer") or {}
        if c.get("kind") == "created":
            gen_txt = "生成期未产出 · 修复期新建(问:为什么生成期没有它)"
        elif c.get("kind") == "template":
            gen_txt = "生成期未改 · 模板/外部原样(问:为什么生成期没改它)"
        else:
            gen_txt = f"生成方 {g.get('desc')}({g.get('stage')}) id={g.get('id')}"
        line = (f"- {rel(str(c.get('file_abs') or c.get('file')), root)} | {gen_txt}"
                f" | 修复方 {fx.get('desc')}({fx.get('stage')}) id={fx.get('id')}")
        t0 = str(payload.get("t0") or "")
        if c.get("fix_at"):
            f_t = atoms.rel_time(c.get("fix_at"), t0) or str(c.get("fix_at"))[5:16]
            if c.get("gen_at"):
                g_t = atoms.rel_time(c.get("gen_at"), t0) or str(c.get("gen_at"))[5:16]
                line += f" | 生成于 {g_t} · 修复于 {f_t}"
            else:                       # created / template 链没有生成侧时刻
                line += f" | 修复于 {f_t}"
            if c.get("hops"):
                line += f" | 上游 {c['hops'][0]}/{c['hops'][1]} 跳"
        g_parent = g.get("parent")
        if g_parent and c.get("gen_at") and c.get("fix_at"):
            # 生成方的派发者在生成→修复这段说过什么、决定过什么,是转换器自己的记录里没有的一层;区间摆到眼前
            line += (f" | 派发者 {g.get('parent_name') or g_parent}:生成→修复之间它说过什么用 "
                     f'search(q, agent="{g_parent}", since_ts="{c["gen_at"]}", until_ts="{c["fix_at"]}")')
        if c.get("gen_session"):
            line += f" | 生成于会话 {c['gen_session']}"
        if c.get("fix_session"):
            line += f" | 修复于前序会话 {c['fix_session']}(回合内返修)"
        out.append(line)
        if c.get("lines"):
            frm = "、".join(f"{x.get('desc')}({x.get('n')}行, id={x.get('id')})" for x in c["lines"].get("from") or [])
            other = c["lines"].get("other")
            out.append(f"  被修 {c['lines']['touched']} 行 · 原作者 {frm}" + (f" · 其它 {other}" if other else ""))
        elif c.get("blame_broken"):
            out.append(f"  行级归属: {c['blame_broken']}")
        fixers = [ff for ff in c.get("fixers_all") or [] if ff.get("fvers")]
        if fixers:
            # 一个文件常被几拨修复方分段改(Index.ets:视觉修 → ID 注入 → ECAT),每段一个原因;按先后列出各段
            parts = [f"{ff.get('desc')} 文件{_vrange(ff['fvers'])}"
                     + (f" @{atoms.rel_time(ff.get('at'), t0) or str(ff.get('at'))[5:16]}" if ff.get("at") else "")
                     for ff in fixers]
            out.append("  修复方(按先后): " + " · ".join(parts))
        for ff in c.get("fixers_all") or []:
            if ff.get("basis"):
                # 修复方写第一笔修复之前读的单:这是「凭什么改」的直接指针,比它的收尾摘要有信息
                items = ", ".join(f"{b['file']}" for b in ff["basis"][:6]) + (" …" if len(ff["basis"]) > 6 else "")
                ref = _ref(ff["basis"][0]["seq"], None, ff["basis"][0].get("line"))
                other = f" · 窗口内另 {ff['basis_other']} 张单与本文件无关" if ff.get("basis_other") else ""
                out.append(f"  依据({ff.get('desc')}): 写第一笔修复前读了 {items} {ref}{other}")
                # 单的来历:修复方读到的那一版是谁写的、那人写单前看的是哪一类证据(真机 dump / 截图 …)。
                # 这不是差集 —— 生成方可能读过同一版;真差集在下面「修复方读了而生成方没读」
                saw = []
                for b in ff["basis"][:4]:
                    if b.get("writer"):
                        ev = "、".join(f"{k} {n}" for k, n in (b.get("evidence") or {}).items()) or "来源未记"
                        saw.append(f"{b['file']}@v{b.get('v')} ← {b.get('writer_name') or b['writer']} {b.get('writer_how') or '写'}"
                                   + (f"(#{b['writer_seq']})" if b.get("writer_seq") else "") + f",此前看了 {ev}")
                if saw:
                    out.append("  依据单的来历: " + " · ".join(saw))
            gap = ff.get("read_gap")
            if gap:
                parts = []
                for kind, paths in gap.items():
                    counts: dict[str, int] = {}
                    for p in paths:
                        counts[p.rsplit("/", 1)[-1]] = counts.get(p.rsplit("/", 1)[-1], 0) + 1
                    names = ", ".join(f"{nm} ×{n}" if n > 1 else nm for nm, n in list(counts.items())[:3])
                    parts.append(f"{kind} {names}" + (f" …共 {len(counts)}" if len(counts) > 3 else ""))
                mixed = "(窗口内混有别的文件的读,看类型别看单个文件)" if ff.get("basis_other") else ""
                out.append("  修复方读了而生成方没读: " + " · ".join(parts) + mixed)
            elif ff.get("note"):
                out.append(f"  修因({ff.get('desc')}): {_clip(ff['note'], 200)}")
    if touched:
        # 链是「确定的写」算出来的;脚本碰过但方向不明的工程文件不在链里,指针摆在这里,别让它隐身。
        # 0723 有 83 次(vv-static-B 一张数据表就碰了 24 个 .ets),按文件归组,agent id 单列一张对照表
        t0 = str(payload.get("t0") or "")
        by_path: dict[str, list[dict[str, Any]]] = {}
        for t in touched:
            by_path.setdefault(str(t["path"]), []).append(t)
        out.append(f"## 修复期被脚本碰过、方向不明的工程文件({len(by_path)} 个文件,{len(touched)} 次)"
                   " —— 不在链里;action(agent id, #n) 展开看是不是写")
        ids: dict[str, str] = {}
        for path, ts in by_path.items():
            parts = []
            for t in ts:
                name = str(t.get("by_name") or t["by"])
                ids.setdefault(name, str(t["by"]))
                when = atoms.rel_time(t.get("ts"), t0) or str(t.get("ts") or "")[5:16]
                parts.append(f"{name} v{t.get('by_ver')} #{t['seq']} {when} {t.get('reason')}")
            out.append(f"- {rel(path, root)} | {len(ts)} 次 | " + " · ".join(parts))
        out.append("  agent id: " + ", ".join(f"{n} = {i}" for n, i in ids.items()))
    return "\n".join(out)


def _same_file(p: object, want: str) -> bool:
    """文件名 / 相对路径 / 绝对路径都能对上 want。"""
    s = str(p).replace("\\", "/")
    return s == want or s.endswith("/" + want)


def _vrange(vs: list[int]) -> str:
    """[5,6,7,12,14,15] → v5-7,v12,v14-15。"""
    runs: list[tuple[int, int]] = []
    for v in sorted(vs):
        if runs and v == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], v)
        else:
            runs.append((v, v))
    return ",".join(f"v{a}" if a == b else f"v{a}-{b}" for a, b in runs)


_SEARCH_KIND = {"prompt": "派发词", "read": "读", "write": "写", "delete": "删", "say": "说", "think": "想",
                "inbox": "收件", "instruction": "指令", "inject": "注入技能", "system": "系统提示", "notify": "通知",
                "interrupt": "打断", "dispatch": "派发", "message": "发消息", "other": "命令", "skill": "技能",
                "compact": "压缩摘要"}

_SEARCH_MATCH = "匹配方式: 不区分大小写的字面子串；不支持正则/OR，| 也是普通字符。多个词请分次查。"


def _next_hint(h: dict[str, Any], root: str) -> str:
    """每条命中带下一跳:模型只能顺着账本里的边走,跳不出去。"""
    if h["kind"] == "prompt":
        return "→ agent(派发者, since=派发时的版本) 看它凭什么这么派"
    if h["kind"] == "read" and h.get("target"):
        return f"→ file({rel(h['target'], root)}, v={h.get('target_v')}) 看这一版是谁写的;action(#{h['seq']}) 看它读到的原文"
    if h["kind"] in ("write", "delete") and h.get("target"):
        return f"→ diff({rel(h['target'], root)}, v={h.get('target_v')}) / blame 看这几行的归属"
    if h["kind"] == "inbox":
        return "→ agent(来信的 agent) 看它凭什么这么说"
    return f"→ action(#{h['seq']}) 展开原文"


def _navigation_hit(ledger: atoms.Ledger, hits: list[dict[str, Any]] | None,
                    kind: str, key: str, v: Any, seq: Any, field: str) -> None:
    """Expose only a displayed hit's exact existing target; not a historical relation."""
    if hits is None or not isinstance(v, int) or isinstance(v, bool) or v < 1:
        return
    if kind == "file":
        story = ledger.stories.get(key)
        if story is None or v > len(story.versions):
            return
    elif kind == "agent":
        owner = ledger.agents.get(key)
        if owner is None or v > owner.n_versions:
            return
    else:
        return
    hits.append({"kind": kind, "key": key, "v": v, "seq": seq, "field": field})


def _render_pool_search(ledger: atoms.Ledger, q: str, until_ts: str, since_ts: str | None, root: str,
                        navigation_hits: list[dict[str, Any]] | None = None) -> str:
    res = atoms.search_pool(ledger, q, until_ts, since_ts)
    win = f"{since_ts} ~ {until_ts}" if since_ts else f"≤ {until_ts}"
    out = [f"# search 「{q}」 全池 {win}  文件 {len(res['files'])} 个 · agent {len(res['agents'])} 个",
           f"范围: 这一刻之前 {res['n_agents']} 个 agent 的全部记录 + {res['n_files']} 个文件到这一刻为止的已知内容"
           + (f";内容未知 {res['unknown_versions']} 版查不了" if res["unknown_versions"] else "")
           + " —— 零命中只支持「此范围内未检索到」,不证明此前无人见过或要求不存在;引用时把范围抄上"]
    if res["files"]:
        out.append("## 文件里(每个文件只报首次出现)")
        for r in res["files"][:30]:
            _navigation_hit(ledger, navigation_hits, "file", r["path"], r["v"], r.get("seq"), "content")
            ref = " " + _ref(r["seq"], r.get("t"), r.get("line")) if r.get("seq") else ""
            out.append(f"- {rel(r['path'], root)}@v{r['v']} ← {_who(ledger, r['by'], r['by_ver'])}{ref} · 命中 {r['n']} 行"
                       f"  → search(q, file=) 看逐版;file(path, v={r['v']}) 看写者")
            if r.get("snip"):
                out.append(f"    {'第 ' + str(r['ln']) + ' 行: ' if r.get('ln') else ''}{r['snip']}")
        if len(res["files"]) > 30:
            out.append(f"  …还有 {len(res['files']) - 30} 个文件")
    if res["agents"]:
        out.append("## agent 的记录里（每种来源展示最早一条；数量包含未展开命中）")
        out.append("来源按记录形态分，不判断内容真假；工具输出也可能含转述，仍须 action 核原文和上下文。")
        source_labels = {"tool_output": "工具返回", "tool_input": "工具输入", "statement": "消息/自述",
                         "instruction": "指令/注入", "other": "其他记录"}
        for a in res["agents"][:30]:
            out.append(f"- {a['label']} · 命中 {a['n']} 条 · agent={a['agent']}"
                       + "；search(q, agent=此id, 同一 since_ts/until_ts) 展开")
            for group in a["sources"]:
                h = group["first"]
                _navigation_hit(ledger, navigation_hits, "agent", a["agent"],
                                h.get("ver") if h.get("ver") is not None else h.get("at"), h.get("seq"), h["field"])
                where = ", ".join(rel(p, root) for p in (h.get("targets") or [])[:2])
                out.append(f"  [{source_labels[group['source']]} {group['n']} 条] 最早 {h.get('tool') or h['kind']}"
                           + (f" {where}" if where else "") + " " + _ref(h["seq"], h.get("t"), h.get("line"))
                           + f" → action(id={a['agent']}, seq={h['seq']})")
                for ln, snip in h["snips"][:1]:
                    out.append(f"    {'第 ' + str(ln) + ' 行: ' if ln else ''}{snip}")
        if len(res["agents"]) > 30:
            out.append(f"  …还有 {len(res['agents']) - 30} 个 agent")
    if not res["files"] and not res["agents"]:
        out.append("零命中(范围见上一行;内容未知的版本不在内)")
    return "\n".join(out)


def _render_window_writes(ledger: atoms.Ledger, q: str, since_ts: str | None, until_ts: str | None, root: str) -> str:
    if not since_ts and not until_ts:
        return "search(kind=write) 要带时间窗口:since_ts / until_ts(用文件时间线上两个版本的时刻)"
    res = atoms.search_window_writes(ledger, since_ts, until_ts, q)
    lines = ledger.locs
    out = [f"# 窗口内有写能力的命令 {since_ts or '…'} ~ {until_ts or '…'}  {res['n']} 条" + (f",含「{q}」" if q else ""),
           f"范围: 全池 {res['n_agents']} 个 agent 的 Bash / PowerShell / exec 里,分析器判为可能写文件的(解出了写、标了写能力、"
           "或没解出来的);不解析脚本,只按时间圈 —— 这是「实录外修改 / 内容未知」之前该看的候选,是否真改了要 action 打开自己判"]
    for r in res["rows"]:
        eff = r["effects"] or (f"未解({r['unresolved']})" if r.get("unresolved") else "无")
        out.append(f"- {_who(ledger, r['by'], r['by_ver'])} | {r['ts'][5:16]} {r['t']} | {r['cmd']} | 已解出: {eff}"
                   f" | action{_ref(r['seq'], None, lines.get(r['seq']))}")
    if res["n"] > len(res["rows"]):
        out.append(f"…另有 {res['n'] - len(res['rows'])} 条;缩小时间窗口或加 q 过滤")
    if not res["rows"]:
        out.append("窗口内没有有写能力的命令(范围见上一行)")
    return "\n".join(out)


def render_search(ledger: atoms.Ledger, q: str, agent: str | None = None, v: int | None = None,
                  since: int | None = None, file: str | None = None, after: bool = False,
                  since_ts: str | None = None, until_ts: str | None = None, root: str = "",
                  kind: str | None = None, navigation_hits: list[dict[str, Any]] | None = None) -> str:
    """带起点的按词查找。agent=:只看它喂养第 v 版及之前的记录(或 since_ts/until_ts 时间区间);
    file=:只看它到第 v 版为止的内容和读者。搜索命中可用于调查导航,不证明历史读写或因果关系。
    kind=write:时间窗口里全池有写能力的命令(断点窗口候选),q 可空。"""
    if kind == "write":
        return "\n".join([*_scan_note(ledger), _render_window_writes(ledger, q, since_ts, until_ts, root), _SEARCH_MATCH])
    if not agent and not file:
        if not until_ts:
            return ("search 要么带起点(agent= 或 file=),要么全池但只允许带时间上限:search(q, until_ts=…)。"
                    "全池查可发现上游候选或核限定范围的零命中;搜索跳转不证明历史关系。")
        return "\n".join([*_scan_note(ledger), _render_pool_search(ledger, q, until_ts, since_ts, root, navigation_hits), _SEARCH_MATCH])
    if agent:
        res = atoms.search_agent(ledger, agent, q, v, since, after, since_ts, until_ts)
        if res is None:
            return f"账本里没有该 agent: {agent}"
        scope = (f"时间区间 {since_ts or '…'} ~ {until_ts or '…'}" if (since_ts or until_ts)
                 else f"≤ v{res['v']}" + (f"(窗口 v{since + 1}–v{res['v']})" if since is not None else ""))
        out = [f"# search 「{q}」 in agent {res['label']}  {scope}  命中 {len(res['hits'])} 条记录",
               "范围: 只有这个 agent 的记录(派发词 / 读到的内容 / 写入 / 命令 / 说 / 想 / 收件 / 注入);别的 agent 和文件内容不在内。"
               "零命中只支持「此范围内未检索到」;可用 search(q, until_ts=那一刻) 扩大全池范围,仍不证明无人见过或要求不存在"]
        groups: dict[str, list[dict[str, Any]]] = {}
        owner = atoms.resolve_agent(ledger, agent)
        out.append(_SEARCH_MATCH)
        out += _scan_note(ledger, owner.id if owner else agent)
        for h in res["hits"]:
            groups.setdefault(h["kind"], []).append(h)
        for kind, hs in groups.items():
            out.append(f"## {_SEARCH_KIND.get(kind, kind)}({len(hs)})")
            for h in hs[:20]:
                if owner:
                    _navigation_hit(ledger, navigation_hits, "agent", owner.id,
                                    h.get("ver") if h.get("ver") is not None else h.get("at"), h.get("seq"), h["field"])
                where = ""
                if h["kind"] in ("read", "write", "delete") and h.get("target"):
                    _navigation_hit(ledger, navigation_hits, "file", h["target"], h.get("target_v"), h.get("seq"), h["field"])
                    where = f" {rel(h['target'], root)}@v{h.get('target_v')}"
                elif h.get("targets"):
                    where = " " + ", ".join(rel(p, root) for p in h["targets"][:3])
                if h.get("possible"):
                    where += " · 可能碰到 " + ", ".join(rel(p, root) for p in h["possible"][:3])
                if h.get("claim_note"):
                    where += " · 消息主张(未独立核验)" + (" 来自 " + str(h["sender"]) if h.get("sender") else "")
                fed = "" if h["seq"] is None else (f" 效应 v{h['ver']}" if h["ver"] is not None else f" 喂 v{h['at']}")
                if owner and h["seq"] is not None and h["ver"] is None and h["at"] > owner.n_versions:
                    fed = f" 收尾后(没有形成 v{h['at']}，不能用作节点坐标；该 agent 最后效应为 v{owner.n_versions})"
                late = " (锚点之后)" if h.get("after") else ""
                ref = "" if h["seq"] is None else " " + _ref(h["seq"], h.get("t"), h.get("line"))
                out.append(f"- {_SEARCH_KIND.get(kind, kind)}{where}{fed}{late}{ref} · 命中 {h['n']} 行"
                           f"  {_next_hint(h, root)}")
                for ln, snip in h["snips"]:
                    out.append(f"    {'第 ' + str(ln) + ' 行: ' if ln else ''}{snip}")
            if len(hs) > 20:
                out.append(f"  …还有 {len(hs) - 20} 条")
        if res["excluded_after"]:
            out.append(f"锚点之后另有 {res['excluded_after']} 条命中(非因果;after=True 可看)")
        if not res["hits"]:
            out.append("(范围内没有命中 —— 只说明此范围内未检索到字面子串;不证明这个或别的 agent 没见过相关信息,"
                       "别写成「全实录只有…」)")
        return "\n".join(out)
    res2 = atoms.search_file(ledger, str(file), q, v)
    if res2 is None:
        return "\n".join([f"账本里没有该文件: {file}", *_scan_note(ledger)])
    out = [f"# search 「{q}」 in file {rel(res2['path'], root)}  ≤ v{res2['v']}(共 {res2['n_versions']} 版)",
           f"范围: 该文件 ≤v{res2['v']} 的已知内容与读者读到的行"
           + (f";内容未知 {res2['unknown']} 版查不了" if res2.get("unknown") else "")
           + " —— 别的文件不在内,要查「那一刻之前谁写过 / 见过」用 search(q, until_ts=那一刻)"]
    out += _scan_note(ledger)
    out.append(_SEARCH_MATCH)
    if res2["first"] is None:
        out.append("这些版本的已知内容里没有这个词(内容未知的版本查不了)")
    else:
        out.append(f"首次出现: v{res2['first']}")
    rows = res2["versions"]
    i = 0
    while i < len(rows):
        row = rows[i]
        _navigation_hit(ledger, navigation_hits, "file", res2["path"], row["v"], row.get("seq"), "content")
        ref = " " + _ref(row["seq"], row.get("t"), row.get("line")) if row.get("seq") else ""
        out.append(f"- v{row['v']} ← {_who(ledger, row['by'], row['by_ver'])}{ref} · 命中 {row['n']} 行"
                   + ("(部分内容:脚本字面量)" if row.get("partial") else "")
                   + f"  → blame(v={row['v']}) / agent(写者, since=写它之前的版本)")
        for ln, snip in row["snips"]:
            out.append(f"    {'第 ' + str(ln) + ' 行: ' if ln else '(行号未知) '}{snip}")
        # 命中行没变的后续版本折成一行(HomePage.ets 29 版曾把同两行原样列 29 遍)
        j = i + 1
        while j < len(rows) and [s for _l, s in rows[j]["snips"]] == [s for _l, s in row["snips"]] and rows[j]["n"] == row["n"]:
            j += 1
        if j > i + 1:
            span = f"v{rows[i + 1]['v']}" if j == i + 2 else f"v{rows[i + 1]['v']}–v{rows[j - 1]['v']}"
            out.append(f"- {span} 命中行未变(经 {', '.join(dict.fromkeys(_who(ledger, r['by'], None) for r in rows[i + 1:j]))})")
        i = j
    if res2["readers"]:
        out.append(f"## 读者的读结果里命中过({len(res2['readers'])})")
        for r in res2["readers"]:
            _navigation_hit(ledger, navigation_hits, "agent", r["by"], r["at"], r.get("seq"), "read")
            ref = " " + _ref(r["seq"], r.get("t"), r.get("line")) if r.get("seq") else ""
            out.append(f"- {_who(ledger, r['by'], r['at'])} 读 @v{r['v']}{ref} · 命中 {r['n']} 行")
            for ln, snip in r["snips"]:
                out.append(f"    {'第 ' + str(ln) + ' 行: ' if ln else '(行号未知) '}{snip}")
    return "\n".join(out)
