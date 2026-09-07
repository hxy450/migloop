"""一个会话为什么 0 条链:根目录、阶段戳、fix_after、根下文件的版本分布。用法: python diag_session.py <jsonl>"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import filestory, service  # noqa: E402

p = sys.argv[1]
data = service.extract_trace(p)
meta = data.get("meta") or {}
print("meta cwd:", meta.get("cwd"), "| session_id:", str(meta.get("session_id"))[:8], "| fmt:", service._fmt_of(data))
led = service.session_ledger(p)
print("fix_after:", led.fix_after, "| agents:", len(led.agents), "| stories:", len(led.stories))
stages = Counter(act.stage for a in led.agents.values() for act in a.actions)
print("stages:", stages.most_common(8))
root = str(meta.get("cwd") or "")
under = {path: st for path, st in led.stories.items() if filestory.is_project_code(path, root or None)}
print("root 下代码文件:", len(under))
multi = sorted(((len(st.versions), path) for path, st in under.items() if len(st.versions) > 1), reverse=True)[:10]
for n, path in multi:
    st = led.stories[path]
    print(f"  {n} 版  {path.rsplit('/', 1)[-1]}  写者 {sorted({str(v.by)[:22] for v in st.versions})} 阶段 {sorted({str(v.stage) for v in st.versions})}")
proj = root.replace("\\", "/")
marks = os.path.join(root, ".migbot", "metrics") if root else ""
print("stage-marks 目录:", marks, os.path.isdir(marks) if marks else None)
if marks and os.path.isdir(marks):
    for run in os.listdir(marks)[:5]:
        f = os.path.join(marks, run, "facts", "stage-marks.json")
        print("  ", run, os.path.exists(f))
