"""真实工程文件的 v1 是「外部输入」、v2 才是池内全文写入的有多少;v1 外部是谁、用什么动作「读」出来的。"""
from __future__ import annotations

import collections
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

p = service.locate_session("ff019d8a")
led = service.session_ledger(p)
ROOT = "/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723/"
n = 0
tools: collections.Counter[str] = collections.Counter()
ex = []
for path, st in led.stories.items():
    if not path.startswith(ROOT + "entry/src/main/ets/") or len(st.versions) < 2:
        continue
    v1, v2 = st.versions[0], st.versions[1]
    if v1.source == "external" and v2.source in ("full", "delta"):
        n += 1
        r0 = next((r for r in st.reads if r.version == 1), None)
        who = led.agents.get(r0.by) if r0 else None
        act = next((a for a in who.actions if a.seq == r0.seq), None) if who else None
        key = f"{act.tool}/{act.detail.get('unresolved') or ('字面量' if act.tool == 'Bash' else '')}" if act else "无读记录"
        tools[key] += 1
        if len(ex) < 4 and act:
            ex.append(f"{path[len(ROOT):]}: v1 外部 {v1.ts[5:16]} ← {who.name} #{act.seq} {act.tool}: {str(act.detail.get('cmd') or act.detail.get('path') or '')[:140]!r}; v2 {v2.source} by {led.agents[v2.by].name if v2.by in led.agents else v2.by}")
print(f"entry/src/main/ets 下 v1 外部、v2 池内写入的真实文件: {n} 个")
print("v1 是怎么被「看见」的:", dict(tools))
for e in ex:
    print("  " + e)
