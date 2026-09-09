"""两组对账:报告里的引用有没有落在模型真正看到过的返回里(依据覆盖),以及它打开了多少东西(打开深度)。
只读现有 run 的 transcript.jsonl / result.json / metrics.json,不跑模型、不建账。

原始组:引用 = <转录>.jsonl:行号 / toolu_id;看到过 = Read 返回的行号(cat -n 样式)、Grep / Bash 返回里出现的 文件:行号、返回正文里出现的 toolu_id。
工具组:引用 = #标识:n@L行[/块] / path@vN;看到过 = 这段坐标原样出现在某次工具返回里(渲染器打印的就是这个格式)。
"用法: python basis_check.py <runs 根目录> <label>..."""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any

_TOOL_REF = re.compile(r"#(?:[\w-]+:)?\d+@L\d+(?:/\d+)?(?:·[\w-]+)?")
_FILE_AT = re.compile(r"[\w./-]+\.[A-Za-z0-9]+@v\d+")
_RAW_LINE = re.compile(r"([\w-]+\.jsonl):(\d+)")
_TUID = re.compile(r"\btoolu_[A-Za-z0-9]{8,}\b")
_CATN = re.compile(r"^\s*(\d+)(?:→|\t| \|)", re.M)


def _text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(str(x.get("text") or "") for x in c if isinstance(x, dict))
    return ""


def _unwrap(txt: str) -> str:
    if txt.lstrip().startswith('{"result"'):
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict) and isinstance(obj.get("result"), str):
                return obj["result"]
        except json.JSONDecodeError:
            pass
    return txt


def calls(transcript: str) -> list[dict[str, Any]]:
    order: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for line in open(transcript, encoding="utf-8", errors="ignore"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = r.get("message") if isinstance(r.get("message"), dict) else {}
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if r.get("type") == "assistant" and b.get("type") == "tool_use":
                rec = {"tool": str(b.get("name") or "").replace("mcp__migloop__", ""), "input": b.get("input") or {}, "out": ""}
                by_id[str(b.get("id"))] = rec
                order.append(rec)
            elif r.get("type") == "user" and b.get("type") == "tool_result":
                rec = by_id.get(str(b.get("tool_use_id")))
                if rec is not None:
                    rec["out"] = _unwrap(_text(b.get("content")))
    return order


def raw_seen(cs: list[dict[str, Any]]) -> tuple[set[tuple[str, int]], set[str], dict[str, Any]]:
    """原始组看到过的 (转录名, 行号) 与 toolu_id;顺带打开深度。"""
    lines: set[tuple[str, int]] = set()
    tuids: set[str] = set()
    files: set[str] = set()
    read_bytes = 0
    n_read = n_grep = n_bash = n_glob = 0
    for c in cs:
        t, inp, out = c["tool"], c["input"], c["out"]
        if t == "Read":
            n_read += 1
            fn = os.path.basename(str(inp.get("file_path") or ""))
            files.add(fn)
            read_bytes += len(out)
            for m in _CATN.finditer(out):
                lines.add((fn, int(m.group(1))))
        elif t in ("Grep", "Bash", "Glob"):
            if t == "Grep":
                n_grep += 1
            elif t == "Bash":
                n_bash += 1
            else:
                n_glob += 1
            for m in _RAW_LINE.finditer(out):
                lines.add((m.group(1), int(m.group(2))))
                files.add(m.group(1))
        for m in _TUID.finditer(out):
            tuids.add(m.group(0))
    return lines, tuids, {"Read": n_read, "Grep": n_grep, "Bash": n_bash, "Glob": n_glob,
                          "files_touched": len(files), "read_chars": read_bytes}


def tools_seen(cs: list[dict[str, Any]]) -> tuple[set[str], set[str], dict[str, Any]]:
    refs: set[str] = set()
    fileats: set[str] = set()
    opens = {"file_v": 0, "file_whole": 0, "agent_v": 0, "agent_whole": 0, "content_or_diff": 0, "search": 0, "action": 0, "blame": 0}
    for c in cs:
        t, inp, out = c["tool"], c["input"], c["out"]
        for m in _TOOL_REF.finditer(out):
            refs.add(m.group(0))
        for m in _FILE_AT.finditer(out):
            fileats.add(m.group(0))
        if t == "file":
            opens["file_v" if inp.get("v") is not None else "file_whole"] += 1
            if inp.get("content") or inp.get("diff"):
                opens["content_or_diff"] += 1
        elif t == "agent":
            opens["agent_v" if inp.get("v") is not None else "agent_whole"] += 1
        elif t == "diff":
            opens["content_or_diff"] += 1
        elif t in ("search", "action", "blame"):
            opens[t] += 1
    return refs, fileats, opens


def _norm_ref(s: str) -> str:
    return s.split("·")[0]      # 旧后缀标识格式:只比 #n@L行 部分


def check_run(run_dir: str, arm: str) -> dict[str, Any]:
    cs = calls(os.path.join(run_dir, "transcript.jsonl"))
    report = str(json.load(open(os.path.join(run_dir, "result.json"), encoding="utf-8")).get("result") or "")
    m = json.load(open(os.path.join(run_dir, "metrics.json"), encoding="utf-8"))
    out: dict[str, Any] = {"run": os.path.relpath(run_dir).replace("\\", "/"), "arm": arm, "cost": m.get("cost_usd"),
                           "turns": m.get("num_turns"), "wall_s": m.get("wall_s"),
                           "tool_chars": (m.get("transcript") or {}).get("tool_chars"), "calls": len(cs)}
    if arm == "raw":
        lines, tuids, depth = raw_seen(cs)
        cited = [(mm.group(1), int(mm.group(2))) for mm in _RAW_LINE.finditer(report)]
        cited_ids = _TUID.findall(report)
        ok = sum(1 for c in cited if c in lines)
        ok_id = sum(1 for t in cited_ids if t in tuids)
        # 宽档:同一次调用的命令 + 返回里同时出现转录名(去掉 .jsonl)和这个行号(独立整数 token)
        blobs = [json.dumps(c["input"], ensure_ascii=False) + "\n" + c["out"] for c in cs]

        def loose(f: str, n: int) -> bool:
            stem = f[:-6] if f.endswith(".jsonl") else f
            pat = re.compile(r"(?<![\d.])" + str(n) + r"(?![\d.])")
            return any(stem in b and pat.search(b) for b in blobs)

        ok_loose = sum(1 for c in cited if c in lines or loose(*c))
        out.update({"cited": len(cited) + len(cited_ids), "grounded": ok + ok_id, "grounded_loose": ok_loose + ok_id,
                    "ungrounded_samples": [f"{f}:{n}" for f, n in cited if (f, n) not in lines and not loose(f, n)][:5], **depth})
    else:
        refs, fileats, depth = tools_seen(cs)
        norm_refs = {_norm_ref(r) for r in refs}
        cited = [mm.group(0) for mm in _TOOL_REF.finditer(report)]
        cited_fa = [mm.group(0) for mm in _FILE_AT.finditer(report)]
        ok = sum(1 for c in cited if c in refs or _norm_ref(c) in norm_refs)
        ok_fa = sum(1 for c in cited_fa if c in fileats or any(f.endswith("/" + c) or f.endswith(c) for f in fileats))
        out.update({"cited": len(cited) + len(cited_fa), "grounded": ok + ok_fa, "grounded_loose": ok + ok_fa,
                    "ungrounded_samples": [c for c in cited if not (c in refs or _norm_ref(c) in norm_refs)][:5], **depth})
    out["grounded_pct"] = round(100 * out["grounded"] / out["cited"]) if out["cited"] else None
    out["loose_pct"] = round(100 * out["grounded_loose"] / out["cited"]) if out["cited"] else None
    return out


def main() -> None:
    root = sys.argv[1]
    rows: list[dict[str, Any]] = []
    for label in sys.argv[2:]:
        arm = "raw" if "raw" in label else "tools"
        for d in sorted(glob.glob(os.path.join(root, label, "chain*", "rep1"))):
            if os.path.isfile(os.path.join(d, "transcript.jsonl")):
                rows.append(check_run(d, arm))
    print("run | arm | cost | turns | wall_s | calls | tool_chars | cited | grounded(严) | % | grounded(宽) | %")
    for r in rows:
        print(f"{r['run']} | {r['arm']} | {r['cost']:.2f} | {r['turns']} | {r['wall_s']} | {r['calls']} | {r['tool_chars']} | "
              f"{r['cited']} | {r['grounded']} | {r['grounded_pct']} | {r['grounded_loose']} | {r['loose_pct']}")
    print("\n两组汇总(同一组题:0723 五根 = cases_raw vs cases_tools6;DiceRoller = cases_raw_dice vs 工具各跑):")
    for arm in ("raw", "tools"):
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        cited = sum(r["cited"] for r in rs)
        print(f"  {arm}: {len(rs)} 根 · 费用 ${sum(r['cost'] for r in rs):.2f} · 墙钟 {sum(r['wall_s'] for r in rs) / 60:.1f} min · "
              f"调用 {sum(r['calls'] for r in rs)} · 返回 {sum(r['tool_chars'] for r in rs)} 字 · 引用 {cited} · "
              f"严 {sum(r['grounded'] for r in rs)} · 宽 {sum(r['grounded_loose'] for r in rs)}")
    print("\n打开深度:")
    for r in rows:
        keys = [k for k in r if k in ("Read", "Grep", "Bash", "Glob", "files_touched", "read_chars", "file_v", "file_whole",
                                      "agent_v", "agent_whole", "content_or_diff", "search", "action", "blame")]
        print(f"  {r['run']}: " + ", ".join(f"{k}={r[k]}" for k in keys) + (f"  未落在看到过的范围里(样例): {r['ungrounded_samples']}" if r["ungrounded_samples"] else ""))
    json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "basis_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
