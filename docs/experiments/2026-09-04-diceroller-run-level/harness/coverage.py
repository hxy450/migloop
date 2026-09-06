"""机械覆盖率:不经模型,按子串对账。两级:
① 段覆盖:报告有没有提到账本里的每一个修复段(文件 × 修复方);修复方名(desc / 账本 label)或 id 前 8 位任一出现,且文件名出现,算命中。
② 版本覆盖:每个被修文件的每个修复版本,有没有被报告里某条「问题」的「覆盖版本: v..」列到 —— 段是容器,问题才是单位,
   一个段里几件事就得几条问题,漏掉的版本直接点名。
用法: python coverage.py <status-<sid>.json> <label> [<label> ...]"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

EXP = os.path.dirname(os.path.abspath(__file__))
_VTOK = re.compile(r"v(\d+)(?:\s*[-–~]\s*v?(\d+))?")


def segments(status: dict) -> list[dict]:
    segs = []
    for c in status.get("chains") or []:
        for f in c.get("fixers_all") or []:
            fid = str(f.get("id") or "")
            short = fid[6:14] if fid.startswith("agent-") else fid.split(":")[-1][:8]
            segs.append({"file": str(c["file"]), "desc": str(f.get("desc") or ""), "id": fid, "short": short,
                         "label": str(f.get("label") or ""), "fvers": f.get("fvers") or [], "at": f.get("at")})
    return segs


def hit(seg: dict, text: str) -> bool:
    if seg["file"] not in text:
        return False
    keys = [k for k in (seg["desc"], seg["label"], seg["short"]) if k and not k.startswith("主会话")]
    return any(k in text for k in keys)


def _expand(tok: re.Match) -> set[int]:
    a = int(tok.group(1))
    b = int(tok.group(2)) if tok.group(2) else a
    return set(range(min(a, b), max(a, b) + 1))


def covered_versions(text: str) -> dict[str, set[int]]:
    """按「段:」切块,块里的文件名 + 所有「覆盖版本」行里的 v 号 → {文件名: 版本集}。"""
    out: dict[str, set[int]] = {}
    blocks = re.split(r"(?m)^\s*-?\s*段[::]", text)[1:]
    for b in blocks:
        head = b.split("\n", 1)[0]
        m = re.search(r"([\w.\-]+\.(?:ets|ts|js|json5|json|cpp|h))", head)
        if not m:
            continue
        fname = m.group(1).rsplit("/", 1)[-1]
        vs = out.setdefault(fname, set())
        for line in b.splitlines():
            if "覆盖版本" in line:
                for tok in _VTOK.finditer(line.split("覆盖版本", 1)[1]):
                    vs |= _expand(tok)
    return out


def main() -> None:
    status = json.load(open(sys.argv[1], encoding="utf-8"))
    segs = segments(status)
    want: dict[str, set[int]] = {}
    for s in segs:
        want.setdefault(s["file"], set()).update(s["fvers"])
    print(f"账本修复段 {len(segs)} 个,修复版本 {sum(len(v) for v in want.values())} 个:")
    for s in segs:
        print(f"  {s['file']:<18} {s['desc'][:30]:<30} id={s['short']} 文件版本={s['fvers']} @{str(s['at'])[11:19]}")
    for label in sys.argv[2:]:
        for res in sorted(glob.glob(os.path.join(EXP, "runs", label, "chain00-RUN", "rep*", "result.json"))):
            text = str(json.load(open(res, encoding="utf-8")).get("result") or "")
            hits = [s for s in segs if hit(s, text)]
            rep = os.path.basename(os.path.dirname(res))
            n_problems = len(re.findall(r"(?m)^\s*-?\s*问题\s*\d+", text))
            print(f"\n[{label}/{rep}] 段命中 {len(hits)}/{len(segs)} · 问题条数 {n_problems} · 报告 {len(text)} 字")
            for s in segs:
                if s not in hits:
                    print(f"   漏段: {s['file']} · {s['desc'][:30]} ({s['short']})")
            got = covered_versions(text)
            for fname, vs in sorted(want.items()):
                miss = sorted(vs - got.get(fname, set()))
                extra = sorted(got.get(fname, set()) - vs)
                mark = "OK" if not miss else "漏版本 " + ",".join(f"v{v}" for v in miss)
                print(f"   {fname:<18} 版本覆盖 {len(vs) - len(miss)}/{len(vs)}  {mark}"
                      + (f"  (报告多列了 {','.join(f'v{v}' for v in extra)})" if extra else ""))


if __name__ == "__main__":
    main()
