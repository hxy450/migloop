"""工程内外部输入文件:多少个已经挂上了来源指针(碰过/候选生成),多少个还没有,按目录。"""
from __future__ import annotations

import collections
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

p = service.locate_session("ff019d8a")
led = service.session_ledger(p)
ROOT = "/Users/chenjiamin/arkTs/arkts_pilot_project/aippt_version/aippt_0723/"
DIRS = ("spec/baseline/ui-snapshots", "spec/baseline/ui", "spec/baseline", "entry/src/main/resources", "entry/src",
        "spec/visual-verify", "spec/fix", "docs/autofix-log")
tot: collections.Counter[str] = collections.Counter()
have: collections.Counter[str] = collections.Counter()
reasons: collections.Counter[str] = collections.Counter()
for path, st in led.stories.items():
    if not path.startswith(ROOT) or not st.versions or st.versions[0].source != "external":
        continue
    rel = path[len(ROOT):]
    d = next((x for x in DIRS if rel.startswith(x + "/")), None)
    if not d:
        continue
    tot[d] += 1
    if st.touches:
        have[d] += 1
        for t in st.touches:
            reasons[t.reason.split("(")[0][:14]] += 1
print(f"{'目录':<28}{'外部首版文件':>8}{'有指针':>7}{'无指针':>7}")
for d in DIRS:
    if tot[d]:
        print(f"{d:<28}{tot[d]:>8}{have[d]:>7}{tot[d] - have[d]:>7}")
print("合计", sum(tot.values()), "有指针", sum(have.values()))
print("指针理由:", dict(reasons.most_common(6)))
n_ver = sum(len(st.versions) for st in led.stories.values())
n_ext = sum(1 for st in led.stories.values() for v in st.versions if v.source == "external")
print(f"版本总数 {n_ver},外部输入 {n_ext},story 数 {len(led.stories)}")
