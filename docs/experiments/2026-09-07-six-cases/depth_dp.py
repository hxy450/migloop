"""上游最长链按 DP 一遍算完:节点 = 文件版 (path, v) 与 agent 版 (agent, k),边只往时间更早的方向走,按时间序处理,
depth[节点] = 1 + max(depth[前驱])。四种口径:读边取累计(≤k)或只取窗口(==k)× 派发边计入或不计。
用法: python depth_dp.py <sid>"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

LEAF = ("external", "generated", "outband")


def build(led, window: bool, parent_edge: bool, lineage: bool = False):
    nodes: list[tuple[str, tuple, list]] = []      # (ts, node, preds)
    for aid, a in led.agents.items():
        effects = {act.ver: act for act in a.actions if act.ver is not None}
        reads_by_at: dict[int, list] = {}
        for act in a.actions:
            for ref in act.files:
                if ref.op == "read" and ref.v:
                    reads_by_at.setdefault(act.at, []).append(("f", ref.path, ref.v))
        for k, act in effects.items():
            preds = []
            for at, rs in reads_by_at.items():
                if at == k or (not window and at < k):
                    preds += rs
            if parent_edge and a.parent and a.parent_ver:
                preds.append(("a", a.parent, a.parent_ver))
            nodes.append((act.ts, ("a", aid, k), preds))
    for path, st in led.stories.items():
        for ver in st.versions:
            preds = []
            if ver.source not in LEAF and ver.by in led.agents and ver.by_ver:
                preds.append(("a", ver.by, ver.by_ver))
            if lineage and ver.v > 1:
                preds.append(("f", path, ver.v - 1))      # 同一文件的上一版:修复版 ← 被改的那一版 ← 它的写者
            nodes.append((ver.ts, ("f", path, ver.v), preds))
    nodes.sort(key=lambda x: (x[0], 0 if x[1][0] == "a" else 1))
    depth: dict[tuple, int] = {}
    for _ts, node, preds in nodes:
        best = 0
        for p in preds:
            d = depth.get(p)
            if d is not None and d > best:
                best = d
        depth[node] = best + (1 if node[0] == "a" else 0)     # 跳数 = 经过几个 agent 的手
    return depth, len(nodes), sum(len(n[2]) for n in nodes)


def main(sid: str) -> None:
    p = service.locate_session(sid)
    led = service.session_ledger(p)
    pay = service.fixchain_payload(p)
    t0 = time.time()
    variants = {}
    for window in (False, True):
        for parent in (True, False):
            variants[(window, parent)] = build(led, window, parent)
    variants[("lineage",)] = build(led, True, False, lineage=True)
    print(f"# {sid}: 五种口径 DP 共 {time.time() - t0:.1f}s;节点 {variants[(False, True)][1]},累计读边 {variants[(False, True)][2]},窗口读边 {variants[(True, True)][2]}")
    print("| 根 | 累计读+派发 | 窗口读+派发 | 累计读 | 窗口读 | 窗口读+同文件上一版 |")
    print("|---|---|---|---|---|---|")
    for c in pay["chains"]:
        st = led.stories.get(c["file_abs"])
        fv = (c.get("fix_versions") or [len(st.versions)])[0] if st else None
        if st is None or not fv:
            continue
        node = ("f", c["file_abs"], fv)
        cells = [variants[(w, pe)][0].get(node, 0) for (w, pe) in ((False, True), (True, True), (False, False), (True, False))]
        cells.append(variants[("lineage",)][0].get(node, 0))
        print(f"| {c['file']}@v{fv} | " + " | ".join(str(x) for x in cells) + " |")
    dmax = max(variants[(False, True)][0].values())
    print(f"\n全图最深(累计读+派发): {dmax}")


if __name__ == "__main__":
    main(sys.argv[1])
