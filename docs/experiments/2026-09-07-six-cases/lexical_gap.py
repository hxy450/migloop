"""完备性差集检验(评审 K):对一个文件,拿文件名 grep 整份转录的每一行(tool_use / tool_result / 正文都算),
和账本词法层(该文件的读、写、碰过、提及)按「转录 + 行号」逐条对:转录里提到它、账本却没有任何入口的行 = 差集。
差集为零才算「相对转录完备」。用法: python lexical_gap.py <sid> <文件名或路径>..."""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter


def main() -> None:
    from migloop import atoms, filestory, service
    sid, hints = sys.argv[1], sys.argv[2:]
    path = service.locate_session(sid)
    ledger = service.session_ledger(path)
    trace = service.extract_trace(path)
    cwd = str((trace.get("meta") or {}).get("cwd") or "")
    roots = [*service.prior_roots(service._fmt_of(trace), path, cwd), path]
    files: list[str] = []
    for r in roots:
        files.append(r)
        files += glob.glob(os.path.join(os.path.splitext(r)[0], "subagents", "*.jsonl"))
    for hint in hints:
        p = filestory.find_story_path(ledger.stories, hint)
        if p is None:
            print(hint, "账本里没有")
            continue
        base = p.rsplit("/", 1)[-1]
        st = ledger.stories[p]
        # 账本对这个文件的全部入口:按 (转录标识, 行号)
        covered: set[tuple[str, int]] = set()
        seqs: set[int] = set()
        seqs.update(v.act_seq for v in st.versions if v.act_seq is not None)
        seqs.update(s for (pp, _rs), s in ledger.read_act.items() if pp == p)
        seqs.update(t.seq for t in st.touches)
        seqs.update(m.seq for m in ledger.mentions.get(p, []))
        # 按动作自己的 tool_use 行与 tool_result 行精确配对(Action.src),不用邻行冒充(评审反例:没入口的
        # file-history-snapshot 紧挨着 Write 就被算成覆盖)
        by_seq = {a.seq: a for ag in ledger.agents.values() for a in ag.actions}
        for s in seqs:
            a = by_seq.get(s)
            if a is not None and a.src:
                tag = atoms.transcript_tag(a.src[0])
                covered.add((tag, a.src[1] + 1))
                if a.src[2] is not None:
                    covered.add((tag, a.src[2] + 1))
        # 转录里提到它的行
        hit_lines: list[tuple[str, int, str]] = []
        for f in files:
            tag = atoms.transcript_tag(f)
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
                    if base in line:
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        m = rec.get("message") or {}
                        role = str(rec.get("type") or m.get("role") or "?")
                        blocks = m.get("content") if isinstance(m, dict) else None
                        kinds = Counter((str(b.get("type") or "text") if isinstance(b, dict) else "text") for b in (blocks if isinstance(blocks, list) else [{}]))
                        hit_lines.append((tag, i, f"{role}:{'/'.join(sorted(kinds))}"))
        missing2 = [(t, i, k) for t, i, k in hit_lines if (t, i) not in covered]
        kinds = Counter(k for _t, _i, k in missing2)
        print(f"== {base}: 转录里提到它 {len(hit_lines)} 行;账本入口覆盖 {len(hit_lines) - len(missing2)};差集 {len(missing2)}")
        print("   差集按记录种类:", dict(kinds.most_common(8)))
        for t, i, k in missing2[:10]:
            print(f"   {t}:L{i} {k}")


if __name__ == "__main__":
    main()
