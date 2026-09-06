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


def _who(ledger: atoms.Ledger, by: str, ver: int | None) -> str:
    if by in _EXT_LABEL:
        return _EXT_LABEL[by]
    return atoms.agent_label(ledger, by) + (f" v{ver}" if ver is not None else "")


def _read_tags(r: dict[str, Any]) -> str:
    t = []
    if r.get("stale"):
        t.append(f"▲旧版 v{r['v']}/{r['latest_v']}")
    if r.get("start") is not None and r.get("n") is not None and not r.get("full"):
        t.append(f"{r['start']}-{r['start'] + r['n'] - 1}行")
    if r.get("dep"):
        t.append("依赖读")
    if r.get("self_written"):
        t.append("写前读")
    if r.get("via") == "script":
        t.append("脚本读")
    if r.get("certain") is False:
        t.append("版本就近绑定(不确定)")
    return f" [{' '.join(t)}]" if t else ""


def _clip(text: str, cap: int) -> str:
    text = text or ""
    return text if len(text) <= cap else text[:cap] + f"…(截断,共 {len(text)} 字)"


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
            out.append(f"- {a['label']} | id={a['id']} | {a.get('kind') or 'agent'} | 会话 {a['session']}"
                       f" | {a['n_versions']} 版 · 读 {a['n_reads']}{parent}")
        if len(ags) > limit:
            out.append(f"  …还有 {len(ags) - limit} 个,用 query 缩小")
    if kind != "agent":
        fs = [f for f in idx["files"] if (kind is None or f["kind"] == kind)
              and (not q or q in f["path"].lower())]
        out.append(f"## 文件 ({len(fs)})")
        for f in fs[:limit]:
            tag = f"{f['n_versions']} 版" + ("" if f["has_writer"] else " · 只被读过(外部输入)")
            out.append(f"- {rel(f['path'], root)} | {f['kind']} | {tag} · 读 {f['n_reads']}")
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


def render_file(ledger: atoms.Ledger, hint: str, v: int | None = None, root: str = "",
                content: bool = False, diff: bool = False,
                start: int | None = None, n: int | None = None) -> str:
    fa = atoms.file_atom(ledger, hint, v, with_diff=diff, with_content=content)
    if fa is None:
        return f"账本里没有该文件: {hint}"
    anchor = fa["v"]
    vv_anchor = fa["versions"][anchor - 1] if fa["versions"] else None
    out = [f"# 文件 {rel(fa['path'], root)} @v{anchor}  (共 {fa['n_versions']} 版)"]
    out.append(f"完整路径: {fa['path']}")
    if vv_anchor is not None:
        out.append("这一版内容: " + ("可复原" if vv_anchor["content_known"]
                                  else "无法复原 —— " + _unknown_reason(vv_anchor)))
    for b in fa["breaks"]:
        out.append(f"⚠ 断点 {b['kind']} @ {b['ts'][:19]}: {b['detail']}")
    out.append("## 写者脊柱(≤ 这一版)")
    for vv in fa["versions"]:
        extra = []
        if vv["via"] == "script":
            extra.append("脚本落盘(字面量推断)")
        elif vv["via"] == "shell":
            extra.append("shell")
        if vv["sealed"]:
            extra.append("观测封口")
        if vv["lines"] is not None:
            extra.append(f"{vv['lines']} 行")
        if not vv["content_known"]:
            extra.append("内容未知")
        mark = " ◀" if vv["v"] == anchor else ""
        out.append(f"- v{vv['v']} ← {_who(ledger, vv['by'], vv['by_ver'])} | {vv['ts'][5:19]} | "
                   f"{vv['diff_kind']}" + (" · " + " · ".join(extra) if extra else "") + mark)
        if diff and vv.get("diff"):
            out.append("```diff\n" + _clip(vv["diff"], 6000) + "\n```")
    readers = [r for r in fa["readers"] if r["v"] == anchor]
    out.append(f"## 读了 @v{anchor} 的 agent(下游,{len(readers)})")
    for r in readers:
        span = (f"{r['start']}-{r['start'] + r['n'] - 1}行" if r["start"] is not None and r["n"] is not None
                else "全文")
        flags = ("" if r["certain"] else " · 版本就近绑定(不确定)") + (" · 依赖读" if r["dep"] else "")
        out.append(f"- {_who(ledger, r['by'], r['at'])} | {r['ts'][5:19]} | {span}{flags}")
    if content:
        if fa["content"] is None:
            out.append("## 内容: 无法复原")
        else:
            lines = fa["content"].replace("\n", "\n", 1).split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            lo = max(start or 1, 1)
            hi = min(lo + n - 1, len(lines)) if (start and n) else len(lines)
            out.append(f"## 内容 @v{anchor}(第 {lo}-{hi} 行 / 共 {len(lines)} 行)")
            width = len(str(hi))
            out.append("```")
            for i in range(lo - 1, hi):
                out.append(f"{i + 1:>{width}} | {lines[i]}")
            out.append("```")
    return "\n".join(out)


def render_agent(ledger: atoms.Ledger, agent_id: str, v: int | None = None,
                 root: str = "", full_text: bool = True) -> str:
    ag = atoms.agent_atom(ledger, agent_id, v)
    if ag is None:
        return f"账本里没有该 agent: {agent_id}"
    anchor = ag["v"]
    out = [f"# agent {ag['label']}  id={ag['id']}  v{anchor} / 共 {ag['n_versions']} 版"]
    ident = [ag.get("kind") or "agent", f"会话 {ag['session']}"]
    if ag.get("model"):
        ident.append(ag["model"])
    if ag.get("description"):
        ident.append(ag["description"])
    out.append("身份: " + " · ".join(ident))
    if ag["parent"]:
        out.append(f"派发自: {ag['parent']['name'] or ag['parent']['id']} @v{ag['parent']['ver']}"
                   f"  (id={ag['parent']['id']})")
    if ag["prompt"]:
        out.append("## 派发指令(全文)\n" + (_clip(ag["prompt"], 12000) if full_text else _clip(ag["prompt"], 600)))
    inbox = [m for m in ag["inbox"] if not (ag["prompt"] and m["text"] == ag["prompt"])]
    if inbox:
        out.append(f"## 收件箱({len(inbox)})")
        for m in inbox:
            late = " (锚点之后)" if m["after_anchor"] else ""
            out.append(f"- 喂 v{m['at']}{late} · 来自 {m['from']}" + (f" · {m['summary']}" if m.get("summary") else "")
                       + "\n  " + _clip(m["text"] or "", 1500).replace("\n", "\n  "))
    # 逐版:效应 + 喂它的输入
    by_ver: dict[int, dict[str, list[Any]]] = {}
    for a in ag["actions"]:
        k = a["ver"] if a["ver"] is not None else a["at"]
        slot = by_ver.setdefault(k, {"eff": [], "inp": []})
        slot["eff" if a["ver"] is not None else "inp"].append(a)
    reads_by_at: dict[int, list[dict[str, Any]]] = {}
    for r in ag["reads"]:
        reads_by_at.setdefault(r["at"], []).append(r)
    out.append("## 逐版时间线(每个对外效应 +1 版;读归到它喂养的下一版;(#n) 是动作号,"
               "action(id, n) 可展开该次调用的完整输入输出)")
    for k in sorted(by_ver):
        slot = by_ver[k]
        late = k > anchor
        head = f"### v{k}" if k <= ag["n_versions"] else "### 收尾后"
        if late:
            head += " (锚点之后,非因果)"
        out.append(head)
        for a in slot["eff"]:
            d = a["detail"]
            tag = f" (#{a['seq']})"
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
        for r in reads_by_at.get(k, []):
            out.append(f"  读 {rel(r['path'], root)}@v{r['v']}{_read_tags(r)} (#{r['seq']})")
            # 看见的行全给(每行截 200 字):复跑实测,只给前 8 行时调查员没去展开 #4641,
            # 关键的第 615 行就漏了 —— 这里省的 token 远不如漏证据贵
            for ln, t in (r.get("seen") or [])[:60]:
                out.append(f"      看见 {ln}: {_clip(t.strip(), 200)}")
            if r.get("seen") and len(r["seen"]) > 60:
                out.append(f"      …看见的共 {len(r['seen'])} 行,action(#{r['seq']}) 可展开原文")
        others = [a for a in slot["inp"] if a["kind"] not in ("read", "inbox")]
        for a in others:
            d = a["detail"]
            desc = d.get("cmd") or d.get("pattern") or d.get("skill") or d.get("url") or ""
            out.append(f"  {a['tool']}" + ("" if a["ok"] else "(失败)") + (f": {desc}" if desc else "")
                       + f" (#{a['seq']})")
        inboxes = [a for a in slot["inp"] if a["kind"] == "inbox"]
        if inboxes:
            out.append(f"  收件 {len(inboxes)} 条(见上)")
    if ag["result"] and ag["result"]["text"]:
        out.append("## 收尾输出(锚点之后,非因果证据)\n" + _clip(ag["result"]["text"], 4000))
    return "\n".join(out)


def render_action(ledger: atoms.Ledger, agent_id: str, seq: int, max_chars: int = 20000) -> str:
    """一次工具调用的原始输入输出 —— 账本是实录的索引,这里按指针展开原文,不经摘要。"""
    import json

    raw = atoms.action_raw(ledger, agent_id, seq)
    if raw is None:
        return f"没有这个动作: {agent_id} #{seq}(或它没有原始记录指针)"
    head = (f"# 动作 #{raw['seq']} · {raw['tool']} · {raw['ts'][:19]} · "
            + ("成功" if raw["ok"] else "失败" if raw["ok"] is False else "无结果")
            + (f" · 效应 v{raw['ver']}" if raw["ver"] is not None else f" · 喂 v{raw['at']}"))
    inp = raw["input"]
    inp_text = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False, indent=1)
    out = [head, "## 输入", "```", _clip(inp_text, max_chars // 3), "```",
           "## 输出", "```", _clip(raw["output"] or "(空)", max_chars), "```"]
    tur = raw.get("tool_use_result")
    if isinstance(tur, dict) and isinstance(tur.get("file"), dict):
        f = tur["file"]
        out.append(f"(toolUseResult.file: {f.get('filePath')} 第 {f.get('startLine')} 行起 "
                   f"{f.get('numLines')} / {f.get('totalLines')} 行)")
    return "\n".join(out)


def render_blame(ledger: atoms.Ledger, hint: str, v: int | None = None,
                 start: int | None = None, n: int | None = None, root: str = "") -> str:
    bl = atoms.blame(ledger, hint, v, start, n)
    if bl is None:
        return f"账本里没有该文件: {hint}"
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


def render_chains(payload: dict[str, Any], root: str = "") -> str:
    chains = payload.get("chains") or []
    out = [f"# 返修链({len(chains)})"]
    cross = payload.get("cross") or {}
    if cross.get("priors"):
        out.append(f"前序会话: {', '.join(cross['priors'])} · 跨会话链 {cross.get('n_cross', 0)}")
    for c in chains:
        g, fx = c.get("generator") or {}, c.get("fixer") or {}
        line = (f"- {rel(str(c.get('file_abs') or c.get('file')), root)} | 生成方 {g.get('desc')}({g.get('stage')})"
                f" id={g.get('id')} | 修复方 {fx.get('desc')}({fx.get('stage')}) id={fx.get('id')}")
        if c.get("gen_session"):
            line += f" | 生成于会话 {c['gen_session']}"
        out.append(line)
        if c.get("lines"):
            frm = "、".join(f"{x.get('desc')}({x.get('n')}行, id={x.get('id')})" for x in c["lines"].get("from") or [])
            other = c["lines"].get("other")
            out.append(f"  被修 {c['lines']['touched']} 行 · 原作者 {frm}" + (f" · 其它 {other}" if other else ""))
        elif c.get("blame_broken"):
            out.append(f"  行级归属: {c['blame_broken']}")
        for ff in c.get("fixers_all") or []:
            if ff.get("note"):
                out.append(f"  修因({ff.get('desc')}): {_clip(ff['note'], 400)}")
    return "\n".join(out)
