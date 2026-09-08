"""两原子的紧凑文本渲染 —— 给模型看的那一面。

页面吃 JSON,模型吃这里的文本:一行一条读/写/版本,路径相对工程根,标签用中文短词。
主会话 454 条读的 JSON 有 146KB,渲成文本 10KB —— 信息量本来就这么大,别把 JSON 的
字段名和绝对路径当信息。所有数字都来自 atoms.* 的同一份结果,不另算。
"""

from __future__ import annotations

from typing import Any

from migloop import atoms

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
    return atoms.agent_label(ledger, by) + (f" v{ver}" if ver is not None else "")


def _ref(seq: Any, t: str | None, line: int | str | None = None) -> str:
    """动作引用 (#n@L行·转录标识 T+h:mm):#n 给 action 展开用,是本次建账的句柄,账本重建后会漂;@L行·标识是转录里的位置,
    不漂,报告不经工具也能回查、核验按它;T+ 给跨 agent 对先后用。"""
    core = f"#{seq}@L{line}" if line else f"#{seq}"
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
        t.append("写前读")
    if r.get("via") == "script":
        t.append("脚本读")
    elif r.get("via") == "inject":
        t.append("注入")
    elif r.get("via") == "stdout":
        t.append("命令输出推出")
    if r.get("certain") is False:
        t.append("版本就近绑定(不确定)")
    return f" [{' '.join(t)}]" if t else ""


def _clip(text: str, cap: int) -> str:
    text = text or ""
    return text if len(text) <= cap else text[:cap] + f"…(截断,共 {len(text)} 字)"


def _hops(ledger: atoms.Ledger, node: tuple[str, str, int]) -> str:
    """「上游 N/M 跳」:N 累计口径(写之前读过的一切),M 窗口口径(上一效应之后读的);每次 agent↔文件转换算一跳,派发算一跳。"""
    dm, dw = ledger.depth_max.get(node), ledger.depth_win.get(node)
    return f" · 上游 {dm}/{dw} 跳" if dm is not None else ""


def render_index(ledger: atoms.Ledger, kind: str | None = None, query: str | None = None,
                 root: str = "", limit: int = 300) -> str:
    """目录。kind: agent | ets | spec | src | other | None(全部);query 子串过滤。"""
    idx = atoms.ledger_index(ledger)
    q = (query or "").lower()
    out: list[str] = []
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
                ptr = f" (#{a['seq']}@L{lines.get(a['seq'], '?')} … #{b['seq']}@L{lines.get(b['seq'], '?')})"
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
    if src == "full":
        return "工具写·报告成功" if via == "tool" else ("推导·heredoc 全文" if via == "shell" else "推导·脚本字面量全文")
    if src == "delta":
        return "Edit·报告成功" if via == "tool" else "推导·ast 读改写"
    if src == "derived":
        return "推导·派生自已知源" if known and not vv.get("sealed") else "推导·派生源未知"
    if src == "opaque":
        return "推导·黑盒写"
    if src == "outband":
        return "观测·内容变了无写者"
    if src == "external":
        return "观测·首次读到" if known else "首见·内容未进上下文"
    if src == "generated":
        return "推导·脚本字面量含正文"
    if src == "delete":
        return "删除·报告成功"
    return str(src or "")


_MENTION_CLS = {"change": "改动类", "body": "正文提到", "out": "输出里", "readonly": "只读检查", "other": "其他"}


def render_file(ledger: atoms.Ledger, hint: str, v: int | None = None, root: str = "",
                content: bool = False, diff: bool = False,
                start: int | None = None, n: int | None = None, readers: bool = False,
                v_from: int | None = None, v_to: int | None = None, diff_chars: int | None = None,
                m_from: int = 1, m_n: int = 40, m_all: bool = False) -> str:
    """默认只给写者脊柱与碰过:单根往上追看的是写者。读者是下游,归并阶段才用(指南漏条款波及了哪些页),
    默认一行计数,readers=True 展开;按词找读者用 search(file=)。"""
    fa = atoms.file_atom(ledger, hint, v, with_diff=diff, with_content=content)
    if fa is None:
        return f"账本里没有该文件: {hint}"
    anchor = fa["v"]
    vv_anchor = fa["versions"][anchor - 1] if fa["versions"] else None
    lines = ledger.locs
    out = [f"# 文件 {rel(fa['path'], root)} @v{anchor}  (共 {fa['n_versions']} 版)"]
    out.append(f"完整路径: {fa['path']}")
    if vv_anchor is not None:
        out.append("这一版内容: " + ("可复原" if vv_anchor["content_known"]
                                  else ("部分已知(脚本字面量里的正文,不是全文;content=1 看)" if fa.get("partial_known")
                                        else "无法复原 —— " + _unknown_reason(vv_anchor)))
                   + _hops(ledger, ("f", fa["path"], anchor)) + "(累计/窗口口径;每次 agent↔文件转换算一跳,派发算一跳)")
    for b in fa["breaks"]:
        out.append(f"⚠ 断点 {b['kind']} @ {b['ts'][:19]}: {b['detail']}")
    # file 以索引为主:改动正文只在 diff=1 时给。带 v = 只给第 v 版整段;不带 v = 改动日志,一页最多 40 版
    log = diff and v is None
    lo_v = max(v_from or 1, 1)
    hi_v = min(v_to or (lo_v + 39), anchor) if log else anchor
    if log:
        out.append(f"## 写者脊柱 + 每版完整 diff(v{lo_v}–v{hi_v} / 共 {anchor} 版;创建版只给行数,content=1 看全文;"
                   "一页 40 版,v_from / v_to 翻页" + (f";每版截 {diff_chars} 字" if diff_chars else "") + ")")
    elif diff:
        out.append("## 写者脊柱(≤ 这一版)—— 只给第 v 版的 diff(同 diff(path, v));全部版本的改动日志用 file(path, diff=1) 不带 v")
    else:
        out.append("## 写者脊柱(≤ 这一版)—— (#n@L 行) 是写它那次调用的动作号与转录行号,action 展开"
                   + (";同一写者连续几版折成一行,file(path, v=某版) 单看;diff=1 不带 v 给每版改动" if len(fa["versions"]) > 8 else ""))
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
        out.append(f"…v{hi_v + 1}–v{anchor} 还有 {anchor - hi_v} 版:file(path, diff=1, v_from={hi_v + 1}) 续页")
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
        listed = [m for m in miss if m_all or m.get("cls") != "readonly"]
        folded = len(miss) - len(listed)
        out.append(f"## 提到它的命令({len(ms)},其中 {len(miss)} 条账本没记到读写)—— 命令行 / heredoc 体 / 跑的脚本正文 / "
                   "工具输出里出现这个路径;版本无法复原或实录外修改时先看这里,action 展开命令原文自己判")
        if done:
            out.append(f"已入账的 {len(ms) - len(miss)} 条({done})脊柱与读者里已有,不再铺")
        if folded:
            out.append(f"只读检查 {folded} 条折叠(cat / grep / wc / ls …;m_all=1 铺)")
        lo = max(m_from, 1)
        page = listed[lo - 1:lo - 1 + max(m_n, 1)]
        hi = lo - 1 + len(page)
        if listed:
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
                 reads: bool = True, seen: bool = False, until: int | None = None) -> str:
    """默认是索引:头部、派发词全文、收件索引行、逐版效应、读记录按调用合行(安卓路径缩短、看见的行只留行号)、
    正文索引行、收尾。0723 复盘:agent 整段 1.27 万字里三分之二是读清单和看见的行,报告每根只引 6 个文件名和
    6 次「看见」;信息不删,只是不默认铺开 —— seen=True 铺原文,reads=False 只给每版读的条数。
    曾试过默认折叠非目标版本的窗口(变体 B):调查员改用逐窗口查询,总字符没省,还把 AboutUsPage 那条链
    误判成「漏读」—— 整段仍给,只是压短。"""
    ag = atoms.agent_atom(ledger, agent_id, v, since=since)
    if ag is None:
        return f"账本里没有该 agent: {agent_id}"
    if until is not None:
        # 从一条命令进来只想看它之前的输入:槽截到 #until,之后的囊余不算这一版的依据
        for key in ("reads", "actions", "inbox"):
            ag[key] = [r for r in ag[key] if r.get("seq") is None or r["seq"] <= until]
    anchor = ag["v"]
    big_note = ""
    if reads and since is None and ag["n_versions"] > 25:
        # pod730 一个 closer 52 版,整段 1.8 万字里读清单占大头:大 agent 不带窗口只给每版读的条数
        reads = False
        big_note = "(超过 25 版且没带 since 窗口:读只给条数;reads=1 全铺,或 agent(id, v, since=v-1) 看一版的窗口)"
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
    if ag.get("t0"):
        out.append(f"时刻: 动作号旁的 T+h:mm 相对迁移开始 {ag['t0']}(池子里最早一条动作),跨 agent 对先后用它;"
                   "@L 是转录行号")
    if ag["parent"]:
        out.append(f"派发自: {ag['parent']['name'] or ag['parent']['id']} @v{ag['parent']['ver']}"
                   f"  (id={ag['parent']['id']})")
        if ag.get("kind"):
            # 它的类型定义(技能 / agent 说明)由 harness 放进系统提示,转录里没有:conv-mine 的「固有尺寸交
            # icon-sizing 自愈」在它全部记录里找不到来源,就是这一层;search 到不了,别把零命中当「杜撰」
            out.append(f"定义: 类型 {ag['kind']} 的说明来自系统提示,不在转录里 —— 它写的东西若在其记录里找不到来源,多半出自这里")
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
    piece = text[offset:offset + cap]
    end = offset + len(piece)
    if offset == 0 and end == total:
        return piece, note.rstrip(";")
    rest = total - end
    note += f"第 {offset + 1}-{end} 字 / 共 {total} 字" + (f";剩余 {rest} 字,offset={end} 继续" if rest else "")
    return piece, note


def render_action(ledger: atoms.Ledger, agent_id: str, seq: int, max_chars: int = 20000,
                  offset: int = 0, find: str = "") -> str:
    """一次工具调用的原始输入输出 —— 账本是实录的索引,这里按指针展开原文,不经摘要。
    offset / find 只作用于输出(长 think / 长结果);输入仍取前 max_chars/3。"""
    import json

    raw = atoms.action_raw(ledger, agent_id, seq)
    if raw is None:
        return f"没有这个动作: {agent_id} #{seq}(或它没有原始记录指针)"
    head = (f"# 动作 #{raw['seq']} · {raw['tool']} · {raw['ts'][:19]} · "
            + ("成功" if raw["ok"] else "失败" if raw["ok"] is False else "无结果")
            + (f" · 效应 v{raw['ver']}" if raw["ver"] is not None else f" · 喂 v{raw['at']}"))
    inp = raw["input"]
    inp_text = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False, indent=1)
    if raw["output"]:
        in_piece, in_note = _clip(inp_text, max_chars // 3), ""
        piece, note = _window(raw["output"], max_chars, offset, find)
    else:
        # think / say / 派发词:正文在输入侧,输出为空 —— offset / find 作用在这一侧
        in_piece, in_note = _window(inp_text, max_chars, offset, find)
        piece, note = "(空)", ""
    out = [head]
    eid = atoms.event_id(ledger, agent_id, seq)
    if eid:
        out.append(f"事件 id {eid}(会话:转录:tool_use_id;解析升级也不变,#n 只是本次建账的句柄)")
    links = atoms.action_links(ledger, agent_id, seq)
    if links:
        out.append(f"发自 {links['label']} (id={links['agent']}) v{links['ver']}"
                   + ("(这次调用就是这一版的效应)" if links["is_effect"] else "(喂这一版)")
                   + f" → agent({links['agent']}, v={links['ver']})")
        if links["files"]:
            out.append("## 账本记到的读写 → file(path, v)")
            for f in links["files"]:
                op = "读" if f["op"] == "read" else "删" if f["op"] == "delete" else "写"
                out.append(f"- {op} {f['path']}@v{f['v']} → file({f['path']}, v={f['v']})")
        if links["possible"]:
            out.append("## 命令里提到、账本没记到读写的文件(可能碰到;「当时」按时刻就近)→ file(path, v)")
            for p in links["possible"]:
                amb = " · 只给了文件名,同名不止一个" if p["ambiguous"] else ""
                out.append(f"- {p['path']} 当时@v{p['v']}{amb} | …{p['ctx']}… → file({p['path']}, v={max(p['v'], 1)})")
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
    if changed:
        return _render_blame_changed(ledger, bl, root)
    out = [f"# 逐行归属 {rel(bl['path'], root)} @v{bl['v']}  (共 {bl['n_versions']} 版)"]
    if not bl["known"]:
        out.append("这一版内容未知,无法逐行归属(见 file 的复原原因)。")
        return "\n".join(out)
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
    out = [head, f"v{bl['v']} 替换/删除了 v{bl['prev_v']} 的 {len(bl['lines'])} 行,新增 {bl['added']} 行"
                 f"(前一版共 {bl['n_lines']} 行;新增行没有原作者,要问 v{bl['prev_v']} 的写者当时为什么没写)"]
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
        return head + "\n(无 diff 正文:" + _unknown_reason(vv) + ")"
    return head + "\n```diff\n" + _clip(vv["diff"], 20000) + "\n```"


def render_chains(payload: dict[str, Any], root: str = "", file: str | None = None) -> str:
    """file 给了只回目标文件那条链(文件名 / 相对路径 / 绝对路径都行):调查一条链不必把全部链读一遍。"""
    chains = payload.get("chains") or []
    touched = payload.get("touched") or []
    total = len(chains)
    if file:
        want = file.replace("\\", "/").lstrip("/")
        chains = [c for c in chains if any(_same_file(p, want) for p in (c.get("file_abs"), c.get("file")) if p)]
        # 「碰过」附录也只列这个文件:0723 上全列是 54 个文件 6.5K 字,每根调查从第二次调用起就一直背着
        touched = [t for t in touched if _same_file(t["path"], want)]
        if not chains and not touched:
            return f"# 返修链(0/{total},只看 {want})\n没有匹配的链;不带 file 看全部,或先用 index 确认路径。"
        out = [f"# 返修链({len(chains)}/{total},只看 {want})"]
        if not chains:
            out.append("没有匹配的链(下面只有脚本碰过的记录);不带 file 看全部,或先用 index 确认路径。")
    else:
        out = [f"# 返修链({total})"]
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


def _render_pool_search(ledger: atoms.Ledger, q: str, until_ts: str, since_ts: str | None, root: str) -> str:
    res = atoms.search_pool(ledger, q, until_ts, since_ts)
    win = f"{since_ts} ~ {until_ts}" if since_ts else f"≤ {until_ts}"
    out = [f"# search 「{q}」 全池 {win}  文件 {len(res['files'])} 个 · agent {len(res['agents'])} 个",
           f"范围: 这一刻之前 {res['n_agents']} 个 agent 的全部记录 + {res['n_files']} 个文件到这一刻为止的已知内容"
           + (f";内容未知 {res['unknown_versions']} 版查不了" if res["unknown_versions"] else "")
           + " —— 这个范围内的零命中才可以写成「那一刻之前没人见过」,引用时把这一行抄上"]
    if res["files"]:
        out.append("## 文件里(每个文件只报首次出现)")
        for r in res["files"][:30]:
            ref = " " + _ref(r["seq"], r.get("t"), r.get("line")) if r.get("seq") else ""
            out.append(f"- {rel(r['path'], root)}@v{r['v']} ← {_who(ledger, r['by'], r['by_ver'])}{ref} · 命中 {r['n']} 行"
                       f"  → search(q, file=) 看逐版;file(path, v={r['v']}) 看写者")
            if r.get("snip"):
                out.append(f"    {'第 ' + str(r['ln']) + ' 行: ' if r.get('ln') else ''}{r['snip']}")
        if len(res["files"]) > 30:
            out.append(f"  …还有 {len(res['files']) - 30} 个文件")
    if res["agents"]:
        out.append("## agent 的记录里(每个 agent 只报最早一条)")
        for a in res["agents"][:30]:
            h = a["first"]
            where = ", ".join(rel(p, root) for p in (h.get("targets") or [])[:2])
            out.append(f"- {a['label']} · 命中 {a['n']} 条 · 最早 {_SEARCH_KIND.get(h['kind'], h['kind'])}"
                       + (f" {where}" if where else "") + " " + _ref(h["seq"], h.get("t"), h.get("line"))
                       + f"  → search(q, agent={a['agent']}, until_ts=…) 看全部")
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
                  kind: str | None = None) -> str:
    """带起点的按词查找。agent=:只看它喂养第 v 版及之前的记录(或 since_ts/until_ts 时间区间);
    file=:只看它到第 v 版为止的内容和读者。没有起点不搜 —— 「提到过」不等于「上游」,每一跳都要有账本里的边。
    kind=write:时间窗口里全池有写能力的命令(断点窗口候选),q 可空。"""
    if kind == "write":
        return _render_window_writes(ledger, q, since_ts, until_ts, root)
    if not agent and not file:
        if not until_ts:
            return ("search 要么带起点(agent= 或 file=),要么全池但只允许带时间上限:search(q, until_ts=…)。"
                    "全池查只用来核否定(「那一刻之前没人见过 X」),找上游仍要顺 agent / file 的边走。")
        return _render_pool_search(ledger, q, until_ts, since_ts, root)
    if agent:
        res = atoms.search_agent(ledger, agent, q, v, since, after, since_ts, until_ts)
        if res is None:
            return f"账本里没有该 agent: {agent}"
        scope = (f"时间区间 {since_ts or '…'} ~ {until_ts or '…'}" if (since_ts or until_ts)
                 else f"≤ v{res['v']}" + (f"(窗口 v{since + 1}–v{res['v']})" if since is not None else ""))
        out = [f"# search 「{q}」 in agent {res['label']}  {scope}  命中 {len(res['hits'])} 条记录",
               "范围: 只有这个 agent 的记录(派发词 / 读到的内容 / 写入 / 命令 / 说 / 想 / 收件 / 注入);别的 agent 和文件内容不在内。"
               "零命中只能写「它在这个范围内没见过」;要写「那一刻之前没人见过」用 search(q, until_ts=那一刻) 全池查"]
        groups: dict[str, list[dict[str, Any]]] = {}
        for h in res["hits"]:
            groups.setdefault(h["kind"], []).append(h)
        for kind, hs in groups.items():
            out.append(f"## {_SEARCH_KIND.get(kind, kind)}({len(hs)})")
            for h in hs[:20]:
                where = ""
                if h["kind"] in ("read", "write", "delete") and h.get("target"):
                    where = f" {rel(h['target'], root)}@v{h.get('target_v')}"
                elif h.get("targets"):
                    where = " " + ", ".join(rel(p, root) for p in h["targets"][:3])
                if h.get("possible"):
                    where += " · 可能碰到 " + ", ".join(rel(p, root) for p in h["possible"][:3])
                fed = "" if h["seq"] is None else (f" 效应 v{h['ver']}" if h["ver"] is not None else f" 喂 v{h['at']}")
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
            out.append("(范围内没有命中 —— 只证明这个 agent 在这个范围内没见过这个词;不证明别的 agent 或别的版本没见过,"
                       "别写成「全实录只有…」)")
        return "\n".join(out)
    res2 = atoms.search_file(ledger, str(file), q, v)
    if res2 is None:
        return f"账本里没有该文件: {file}"
    out = [f"# search 「{q}」 in file {rel(res2['path'], root)}  ≤ v{res2['v']}(共 {res2['n_versions']} 版)",
           f"范围: 该文件 ≤v{res2['v']} 的已知内容与读者读到的行"
           + (f";内容未知 {res2['unknown']} 版查不了" if res2.get("unknown") else "")
           + " —— 别的文件不在内,要查「那一刻之前谁写过 / 见过」用 search(q, until_ts=那一刻)"]
    if res2["first"] is None:
        out.append("这些版本的已知内容里没有这个词(内容未知的版本查不了)")
    else:
        out.append(f"首次出现: v{res2['first']}")
    rows = res2["versions"]
    i = 0
    while i < len(rows):
        row = rows[i]
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
            ref = " " + _ref(r["seq"], r.get("t"), r.get("line")) if r.get("seq") else ""
            out.append(f"- {_who(ledger, r['by'], r['at'])} 读 @v{r['v']}{ref} · 命中 {r['n']} 行")
            for ln, snip in r["snips"]:
                out.append(f"    {'第 ' + str(ln) + ' 行: ' if ln else '(行号未知) '}{snip}")
    return "\n".join(out)
