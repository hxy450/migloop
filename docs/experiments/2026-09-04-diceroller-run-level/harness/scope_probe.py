"""链范围探针:把 build_fix_chains 的 ets_only 关掉,看多出来哪些非 .ets 的链,按"工程代码/配置"还是"产物/文档"分类。
用法: python scope_probe.py <sid>"""
from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/src")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from migbot.insight import atoms, filestory, routes  # noqa: E402

SID = sys.argv[1]
_NOISE_DIR = re.compile(r"(^|/)(spec|docs|\.claude|\.agents|\.ecat|\.migbot|build|oh_modules|\.hvigor|\.git|node_modules)(/|$)")
_NOISE_EXT = (".log", ".bat", ".md", ".patch", ".sh", ".py", ".txt", ".yaml", ".yml", ".out", ".err")
_CODE_EXT = (".ets", ".ts", ".js", ".json5", ".cpp", ".h", ".c")


def classify(rel: str) -> str:
    r = rel.replace("\\", "/")
    if _NOISE_DIR.search(r) or r.endswith(_NOISE_EXT):
        return "噪音(产物/文档/脚本)"
    if r.endswith(_CODE_EXT):
        return "代码/配置"
    if "/resources/" in r and r.endswith(".json"):
        return "资源 json"
    if "/resources/" in r:
        return "资源媒体"
    return "其它"


async def main() -> None:
    orig = filestory.build_fix_chains

    def wide(stories, meta, fixer, ets_only=True, **kw):
        return orig(stories, meta, fixer, ets_only=False, **kw)

    filestory.build_fix_chains = wide          # routes 在函数内 import 模块、按属性取,补丁生效
    routes._FIXCHAIN_DATA_CACHE.clear()
    ledger = await routes.get_ledger(SID)
    payload = await routes.get_fixchain(SID)
    cwd = await routes.get_session_cwd(SID)
    chains = payload["chains"]
    ets = [c for c in chains if str(c["file_abs"]).endswith(".ets")]
    other = [c for c in chains if not str(c["file_abs"]).endswith(".ets")]
    print(f"sid {SID}: 全部 {len(chains)} 条 = .ets {len(ets)} + 非 .ets {len(other)}  (fix_after={ledger.fix_after})")
    buckets: dict[str, list] = {}
    for c in other:
        rel = os.path.relpath(c["file_abs"], cwd) if cwd and str(c["file_abs"]).startswith(cwd) else c["file_abs"]
        buckets.setdefault(classify(rel), []).append((rel, c))
    for k in sorted(buckets):
        rows = buckets[k]
        print(f"\n## {k}: {len(rows)}")
        for rel, c in rows if k != "噪音(产物/文档/脚本)" else rows[:6]:
            st = ledger.stories[c["file_abs"]]
            v1 = st.versions[0].source if st.versions else "?"
            segs = " · ".join(f"{f['desc'][:22]} {filestory_vr(f.get('fvers') or [])}@{atoms.rel_time(f.get('at'), payload.get('t0'))}"
                              for f in c.get("fixers_all") or [])
            gen = (c.get("generator") or {}).get("desc")
            print(f"  {rel:<60} {c['kind']:<8} v1={v1:<9} 生成方={str(gen)[:20]:<20} | {segs}")
        if k == "噪音(产物/文档/脚本)" and len(rows) > 6:
            print(f"  … 共 {len(rows)} 条")


def filestory_vr(vs: list[int]) -> str:
    from migbot.insight.atoms_text import _vrange
    return _vrange(vs)


asyncio.run(main())
