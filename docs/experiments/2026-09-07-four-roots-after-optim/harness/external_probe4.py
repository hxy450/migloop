"""a) 幽灵路径计数:只有外部版本、且同名文件在账本里另有真实写者的 story,按形状分;
b) 主会话前 45 分钟的 system 记录(stop_hook_summary 等)内容,看 hook 有没有产出 spec 文件。"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

RAW = "C:/Users/hongy/.claude/projects/-Users-chenjiamin-arkTs-arkts-pilot-project-aippt-version-aippt-0723"
p = service.locate_session("ff019d8a")
led = service.session_ledger(p)
ROOT = "/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723/"

real: dict[str, list[str]] = collections.defaultdict(list)
for path, st in led.stories.items():
    if any(v.source != "external" for v in st.versions):
        real[path.rsplit("/", 1)[-1]].append(path)
shape: collections.Counter[str] = collections.Counter()
phantom = 0
ext_only_total = 0
for path, st in led.stories.items():
    if not st.versions or any(v.source != "external" for v in st.versions):
        continue
    ext_only_total += 1
    base = path.rsplit("/", 1)[-1]
    if base not in real or path in real[base]:
        continue
    rel = path[len(ROOT):] if path.startswith(ROOT) else path
    if re.search(r"(entry/src/main/ets/pages/).*\1", rel):
        k = "路径段重复拼接"
    elif rel == base:
        k = "只有文件名(相对根目录)"
    elif rel.startswith("spec/baseline/ui/") and base.endswith(".ets"):
        k = "工程文件名拼到 spec/baseline/ui 下"
    elif rel.startswith("entry/src/main/ets/") and rel.count("/") == 4:
        k = "文件名直接拼到 entry/src/main/ets 下"
    elif rel.startswith("pages/") or rel.startswith("components/"):
        k = "相对 ets 目录的短路径"
    elif "/entry/src/main/ets/app/src/main/java/" in path:
        k = "安卓源码路径拼到 ets 下"
    elif not path.startswith(ROOT):
        k = "工程外同名(安卓侧等,合理)"
    else:
        k = "其它同名"
    shape[k] += 1
    phantom += k not in ("工程外同名(安卓侧等,合理)", "其它同名")
print(f"只有外部版本的 story {ext_only_total} 条;其中同名文件另有真实写者的,按形状:")
for k, v in shape.most_common():
    print(f"  {k:<28} {v}")
print(f"  可判为幽灵路径(解析层拼错)的: {phantom}")

print("\n=== 主会话前 45 分钟的 system 记录")
t0 = datetime.fromisoformat(led.t0.replace("Z", "+00:00")).timestamp()
n = 0
for line in open(os.path.join(RAW, "9b3105a2-85ec-4889-9786-b3c220f06754.jsonl"), encoding="utf-8"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") != "system":
        continue
    t = datetime.fromisoformat(str(d.get("timestamp")).replace("Z", "+00:00")).timestamp()
    if t - t0 > 45 * 60:
        break
    n += 1
    if n <= 8:
        body = json.dumps({k: v for k, v in d.items() if k not in ("uuid", "parentUuid", "sessionId", "version", "cwd", "gitBranch", "userType")}, ensure_ascii=False)
        print(f"  T+{int((t - t0) // 60):>2} {d.get('subtype')}: {body[:260]}")
print(f"  共 {n} 条")
