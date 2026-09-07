"""cases.json → 一页 HTML:六根,每根两份报告并排 + 评委按环结论 + 费用。用法: python render_cases_html.py cases.json out.html"""
from __future__ import annotations

import html
import json
import re
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
out_path = sys.argv[2]


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def report(text: str) -> str:
    """报告正文:环 N 行加标签,判定词上色,坐标弱化。"""
    lines = []
    for ln in text.split("\n"):
        e = esc(ln)
        e = re.sub(r"(判定[::]\s*)(传递|错[^,,。;;\s]*|缺[^,,。;;\s]*)", lambda m: m.group(1) + f'<b class="v v-{ "pass" if m.group(2).startswith("传递") else "err" if m.group(2).startswith("错") else "gap" }">{m.group(2)}</b>', e)
        e = re.sub(r"(#\d+@L\d+|@v\d+|:\d+(?:-\d+)?)", r'<span class="coord">\1</span>', e)
        m = re.match(r"^(环\s*\d+[A-Za-z']?)\s*(.*)$", e)
        if m:
            lines.append(f'<p class="link"><span class="ln">{m.group(1)}</span>{m.group(2)}</p>')
        elif re.match(r"^(故障进入点|修复侧多看到的|无法确认|置信|遗留|文件)[::]", ln):
            k, _, rest = e.partition(":") if ":" in e[:8] else e.partition(":")
            lines.append(f'<p class="tail"><span class="k">{k}</span>{rest}</p>')
        elif ln.strip():
            lines.append(f"<p>{e}</p>")
    return "\n".join(lines)


def money(x: object) -> str:
    return f"{float(x):.2f}" if x is not None else "—"


rows = []
sections = []
for i, c in enumerate(data, 1):
    t, r, j = c["tools"], c["raw"], c["judge"]
    pref = {"treat": "工具", "control": "原始", "tie": "平"}.get((j or {}).get("preferred") or "", "—")
    act = {"treat": "工具", "control": "原始", "tie": "平"}.get((j or {}).get("actionable") or "", "—")
    same = "是" if (j or {}).get("same_entry") else "否" if j else "—"
    rows.append(f"""<tr>
      <td><a href="#c{i}">{esc(c['name'])}</a><div class="why">{esc(c['why'])}</div></td>
      <td class="num">{money(t and t['cost'])}<div class="sub">{t and t['turns']} 轮 · {t and t['calls']} 调用 · {t and (t['chars'] or 0) // 1000} 千字</div></td>
      <td class="num">{money(r and r['cost'])}<div class="sub">{r and r['turns']} 轮 · {r and r['calls']} 调用 · {r and (r['chars'] or 0) // 1000} 千字</div></td>
      <td>{esc((j or {}).get('links', ('—', '—'))[0])} / {esc((j or {}).get('links', ('—', '—'))[1])}</td>
      <td>{same}</td>
      <td><span class="pill pill-{'t' if pref == '工具' else 'r' if pref == '原始' else 'n'}">{pref}</span></td>
      <td><span class="pill pill-{'t' if act == '工具' else 'r' if act == '原始' else 'n'}">{act}</span></td>
    </tr>""")
    jbox = ""
    if j:
        conf = "".join(f"<li>{esc(x)}</li>" for x in j["conflicts"][:6])
        jbox = f"""<div class="judge">
        <div class="jhead">评委按环比 · 共同环 {esc(j['shared'])} 个,判定一致 {esc(j['agree'])} · 进入点同环 {same} · 坐标可核 工具 {esc(j['checkable'][0])} / 原始 {esc(j['checkable'][1])} · 一致性 工具 {esc(j['consistency'][0])} / 原始 {esc(j['consistency'][1])} · 更可信 <b>{pref}</b> · 对改流程更有用 <b>{act}</b></div>
        <p><span class="k">进入点</span>{esc(j['entry_note'])}</p>
        <p><span class="k">理由</span>{esc(j['reason'])}</p>
        {('<p class="k">事实冲突</p><ul>' + conf + '</ul>') if conf else ''}
      </div>"""
    sections.append(f"""<section class="case" id="c{i}">
      <header class="chead">
        <h2>{esc(c['name'])}</h2>
        <p class="why">{esc(c['why'])}</p>
      </header>
      <div class="cols">
        <article class="pane tools">
          <div class="phead"><span class="tag tag-t">工具组</span><span class="meta">${money(t and t['cost'])} · {t and t['turns']} 轮 · {t and t['calls']} 次调用 · 返回 {t and (t['chars'] or 0) // 1000} 千字 · {t and round((t['wall'] or 0) / 60, 1)} 分</span></div>
          <div class="body">{report(t['text']) if t else '<p class="muted">缺</p>'}</div>
        </article>
        <article class="pane raw">
          <div class="phead"><span class="tag tag-r">原始转录组</span><span class="meta">${money(r and r['cost'])} · {r and r['turns']} 轮 · {r and r['calls']} 次调用 · 返回 {r and (r['chars'] or 0) // 1000} 千字 · {r and round((r['wall'] or 0) / 60, 1)} 分</span></div>
          <div class="body">{report(r['text']) if r else '<p class="muted">缺</p>'}</div>
        </article>
      </div>
      {jbox}
    </section>""")

tot_t = sum(float(c["tools"]["cost"] or 0) for c in data if c["tools"])
tot_r = sum(float(c["raw"]["cost"] or 0) for c in data if c["raw"])
pref_counts = {"treat": 0, "control": 0, "tie": 0}
for c in data:
    if c["judge"]:
        pref_counts[c["judge"]["preferred"]] = pref_counts.get(c["judge"]["preferred"], 0) + 1

page = f"""<title>六根返修链对照</title>
<style>
:root {{
  --paper: #f2f3f5; --ink: #1c2126; --ink-2: #5b6470; --rule: #d6dae0; --pane: #ffffff;
  --tools: #0f6e63; --tools-soft: #e3f1ee; --raw: #9a4a21; --raw-soft: #f6e8df;
  --judge: #7a5c00; --judge-soft: #f7f0d8; --pass: #2f6b3a; --err: #a33a2a; --gap: #7a5c00;
  --coord: #6b7280; --mono: Consolas, "Cascadia Mono", "SF Mono", Menlo, monospace;
  --sans: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --paper: #15181c; --ink: #e6e8eb; --ink-2: #a3abb5; --rule: #2e343b; --pane: #1c2126;
  --tools: #4fb3a6; --tools-soft: #12302c; --raw: #d98a5a; --raw-soft: #33241a;
  --judge: #d9b44a; --judge-soft: #2d2711; --pass: #7fc48f; --err: #e08a7c; --gap: #d9b44a; --coord: #8b95a1;
}} }}
:root[data-theme="dark"] {{
  --paper: #15181c; --ink: #e6e8eb; --ink-2: #a3abb5; --rule: #2e343b; --pane: #1c2126;
  --tools: #4fb3a6; --tools-soft: #12302c; --raw: #d98a5a; --raw-soft: #33241a;
  --judge: #d9b44a; --judge-soft: #2d2711; --pass: #7fc48f; --err: #e08a7c; --gap: #d9b44a; --coord: #8b95a1;
}}
body {{ background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.6; margin: 0; }}
.wrap {{ max-width: 1440px; margin: 0 auto; padding: 32px 28px 80px; }}
h1 {{ font-size: 28px; margin: 0 0 6px; letter-spacing: -0.01em; text-wrap: balance; }}
.lede {{ color: var(--ink-2); max-width: 70ch; margin: 0 0 24px; }}
.lede b {{ color: var(--ink); }}
table.sum {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; margin-bottom: 40px; }}
table.sum th {{ text-align: left; font-weight: 600; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-2); padding: 8px 10px; border-bottom: 1px solid var(--rule); }}
table.sum td {{ padding: 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
table.sum td.num {{ font-family: var(--mono); font-size: 14px; }}
table.sum .sub, .why {{ color: var(--ink-2); font-size: 12px; }}
table.sum a {{ color: var(--ink); text-decoration: none; font-weight: 600; }}
.pill {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
.pill-t {{ background: var(--tools-soft); color: var(--tools); }}
.pill-r {{ background: var(--raw-soft); color: var(--raw); }}
.pill-n {{ background: var(--rule); color: var(--ink-2); }}
.case {{ margin: 0 0 56px; }}
.chead {{ display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; border-top: 2px solid var(--ink); padding-top: 12px; }}
.chead h2 {{ font-size: 20px; margin: 0; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }}
@media (max-width: 980px) {{ .cols {{ grid-template-columns: 1fr; }} }}
.pane {{ background: var(--pane); border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }}
.pane.tools {{ border-top: 3px solid var(--tools); }}
.pane.raw {{ border-top: 3px solid var(--raw); }}
.phead {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--rule); flex-wrap: wrap; }}
.tag {{ font-weight: 700; font-size: 13px; }}
.tag-t {{ color: var(--tools); }} .tag-r {{ color: var(--raw); }}
.meta {{ font-family: var(--mono); font-size: 12px; color: var(--ink-2); }}
.body {{ padding: 12px 14px 16px; max-width: 100%; overflow-x: auto; }}
.body p {{ margin: 0 0 8px; overflow-wrap: anywhere; }}
.body .link {{ padding-left: 3.6em; text-indent: -3.6em; }}
.body .ln {{ display: inline-block; width: 3.4em; text-indent: 0; font-family: var(--mono); font-weight: 700; color: var(--ink-2); }}
.body .tail {{ margin-top: 10px; border-top: 1px dashed var(--rule); padding-top: 8px; }}
.k {{ display: inline-block; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-2); margin-right: 8px; font-weight: 600; }}
.coord {{ font-family: var(--mono); font-size: 12px; color: var(--coord); }}
.v {{ padding: 0 5px; border-radius: 3px; }}
.v-pass {{ color: var(--pass); background: color-mix(in srgb, var(--pass) 12%, transparent); }}
.v-err {{ color: var(--err); background: color-mix(in srgb, var(--err) 12%, transparent); }}
.v-gap {{ color: var(--gap); background: color-mix(in srgb, var(--gap) 14%, transparent); }}
.judge {{ margin-top: 14px; background: var(--judge-soft); border-left: 3px solid var(--judge); padding: 10px 14px; border-radius: 0 6px 6px 0; }}
.judge p {{ margin: 6px 0; }}
.jhead {{ font-family: var(--mono); font-size: 12px; color: var(--ink-2); }}
.judge ul {{ margin: 4px 0 0 18px; padding: 0; }}
.muted {{ color: var(--ink-2); }}
.note {{ color: var(--ink-2); font-size: 12px; margin-top: 40px; border-top: 1px solid var(--rule); padding-top: 12px; }}
</style>
<div class="wrap">
  <h1>六根返修链对照</h1>
  <p class="lede">同题同模型(claude-opus-5),工具组只拿账本工具、原始组只拿转录目录,两组都只给文件名。评委(opus)按环盲比。
  这一轮工具组用的是今天为止全部改动后的工具;原始组报告沿用 09-07 那次。合计费用 工具 <b>${tot_t:.2f}</b> · 原始 <b>${tot_r:.2f}</b>;更可信 工具 <b>{pref_counts['treat']}</b> : 原始 <b>{pref_counts['control']}</b> : 平 {pref_counts['tie']}。</p>
  <table class="sum">
    <thead><tr><th>根(挑选口径)</th><th>工具 $</th><th>原始 $</th><th>环数 工具/原始</th><th>进入点同环</th><th>更可信</th><th>更可行动</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  {''.join(sections)}
  <p class="note">判定色:<span class="v v-pass">传递</span> 照上游做的 · <span class="v v-err">错</span> 有好的输入没用或用错 · <span class="v v-gap">缺</span> 输入里本来就没有。坐标 #n@L行 = 账本动作号 + 转录行号;原始组坐标是转录文件行号与时间戳。产物在 migloop 仓 docs/experiments/2026-09-07-six-cases。</p>
</div>
"""
open(out_path, "w", encoding="utf-8").write(page)
print("ok", out_path, len(page))
