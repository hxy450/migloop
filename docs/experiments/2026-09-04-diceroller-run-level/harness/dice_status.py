"""DiceRoller 现状体检:fix_after、修复期被写的全部文件(是否成链 / 为什么不成链)、sessions 文本。"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, "C:/Users/hongy/projects/migbot-elite/.claude/worktrees/filestory/src")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from migbot.insight import atoms, atoms_text, routes  # noqa: E402
from migbot.insight.filestory import _is_test_path, ts_norm  # noqa: E402

SID = sys.argv[1] if len(sys.argv) > 1 else "49d451b1"
HERE = os.path.dirname(os.path.abspath(__file__))


async def main() -> None:
    ledger = await routes.get_ledger(SID)
    payload = await routes.get_fixchain(SID)
    cwd = await routes.get_session_cwd(SID)
    fa = ledger.fix_after
    print("sid:", SID, "cwd:", cwd)
    print("fix_after:", fa, "t0:", ledger.t0)
    chains = {c["file_abs"]: c for c in payload.get("chains") or []}
    print("chains:", len(chains), {k.rsplit("/", 1)[-1]: c.get("kind") for k, c in chains.items()})
    rows = []
    for path, st in sorted(ledger.stories.items()):
        vs = [v for v in (getattr(st, "versions", []) or [])
              if v.source not in ("external", "outband")]          # 只看记录在案的写
        fix_vs = [v for v in vs if fa and ts_norm(v.ts) >= ts_norm(fa)]
        if not fix_vs or not (cwd and path.startswith(cwd)):
            continue
        gen_vs = [v for v in vs if v not in fix_vs]
        rel = os.path.relpath(path, cwd) if cwd and path.startswith(cwd) else path
        why = ""
        if path in chains:
            why = "链:" + str(chains[path].get("kind"))
        elif not path.endswith(".ets"):
            why = "非 .ets"
        elif _is_test_path(path):
            why = "测试路径(仅修复期新建)" if not gen_vs else "测试路径但有生成版?"
        else:
            why = "?? 有 .ets 修复写却不成链"
        agents = sorted({str(v.by) for v in fix_vs})
        stages = sorted({str(v.stage) for v in fix_vs})
        srcs = sorted({str(v.source) for v in fix_vs})
        rows.append((rel, len(gen_vs), len(fix_vs), agents, stages + srcs, why))
    print(f"\n修复期被写文件 {len(rows)} 个 (gen版数 / fix版数 / 修复方 / 阶段 / 判定):")
    for rel, ng, nf, agents, stages, why in rows:
        print(f"  {rel:<70} g{ng:<3} f{nf:<3} {','.join(a[:12] for a in agents)[:60]:<60} {','.join(stages)[:28]:<28} {why}")
    text = atoms_text.render_chains(payload, root=cwd)
    out = os.path.join(HERE, f"sessions-{SID}.txt")
    open(out, "w", encoding="utf-8").write(text)
    print("\nsessions text chars:", len(text), "->", out)
    json.dump({"sid": SID, "cwd": cwd, "fix_after": fa, "t0": ledger.t0,
               "chains": [{"file": c["file"], "file_abs": c["file_abs"], "kind": c.get("kind"),
                           "fix_versions": c.get("fix_versions"),
                           "fixer": (c.get("fixer") or {}).get("desc"), "gen": (c.get("generator") or {}).get("desc"),
                           "gen_id": (c.get("generator") or {}).get("id"),
                           "fixers_all": [{k: f.get(k) for k in ("id", "desc", "stage", "fvers", "at")}
                                          | {"label": atoms.agent_label(ledger, str(f.get("id")))}
                                          for f in c.get("fixers_all") or []]}
                          for c in payload.get("chains") or []]},
              open(os.path.join(HERE, f"status-{SID}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


asyncio.run(main())
