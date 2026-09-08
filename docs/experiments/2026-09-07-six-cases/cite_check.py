"""引用核验(机械):两组报告里的坐标能不能核回原文。只证明「位置存在、原文匹配」,不证明结论成立。

工具组坐标:#n@L行(账本动作号 + 转录行号,要求账本 lines[n] == L)、path@vN(账本里该文件版本数 ≥ N)。
原始组坐标:<转录文件>.jsonl:行号(池子里有这个文件且行数 ≥ 行号)、toolu_… id(在池子任一转录里出现)。
用法: python cite_check.py <sid> <report.json 或 result.json>...   → 每份一行 JSON:{total, valid, invalid, samples}
也可 import:check_report(ledger, pool_dir, text) -> dict。评委脚本把这一行拼进提示词。"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any

_TOOL_REF = re.compile(r"#(\d+)@L(\d+)")
_FILE_AT = re.compile(r"([\w./-]+\.[A-Za-z0-9]+)@v(\d+)")
_RAW_LINE = re.compile(r"([\w-]+\.jsonl):(\d+)")
_TUID = re.compile(r"\btoolu_[A-Za-z0-9]{8,}\b")


def _line_count(path: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


class Pool:
    """池子里的转录:名字 → 路径;tool_use id 集合按需加载。"""

    def __init__(self, roots: list[str]) -> None:
        self.files: dict[str, str] = {}
        for r in roots:
            self.files[os.path.basename(r)] = r
            sub = os.path.splitext(r)[0] + "/subagents"
            for fn in glob.glob(os.path.join(sub, "*.jsonl")):
                self.files[os.path.basename(fn)] = fn
        self._lines: dict[str, int] = {}
        self._ids: set[str] | None = None

    def lines(self, name: str) -> int:
        if name not in self._lines:
            self._lines[name] = _line_count(self.files.get(name, ""))
        return self._lines[name]

    def has_id(self, tuid: str) -> bool:
        if self._ids is None:
            ids: set[str] = set()
            for p in self.files.values():
                try:
                    with open(p, encoding="utf-8", errors="ignore") as fh:
                        for line in fh:
                            ids.update(_TUID.findall(line))
                except OSError:
                    continue
            self._ids = ids
        return tuid in self._ids


def check_report(ledger: Any, pool: Pool, text: str) -> dict[str, Any]:
    total = valid = 0
    bad: list[str] = []
    for m in _TOOL_REF.finditer(text):
        total += 1
        if ledger is not None and ledger.lines.get(int(m.group(1))) == int(m.group(2)):
            valid += 1
        else:
            bad.append(m.group(0))
    if ledger is not None:
        from migloop import filestory
        for m in _FILE_AT.finditer(text):
            k = filestory.find_story_path(ledger.stories, m.group(1))
            total += 1
            if k and len(ledger.stories[k].versions) >= int(m.group(2)):
                valid += 1
            else:
                bad.append(m.group(0))
    for m in _RAW_LINE.finditer(text):
        total += 1
        name = m.group(1)
        hit = next((n for n in pool.files if n == name or n.startswith(name.rsplit(".", 1)[0])), None)
        if hit and pool.lines(hit) >= int(m.group(2)):
            valid += 1
        else:
            bad.append(m.group(0))
    for tuid in set(_TUID.findall(text)):
        total += 1
        if pool.has_id(tuid):
            valid += 1
        else:
            bad.append(tuid)
    return {"total": total, "valid": valid, "invalid": len(bad), "samples": bad[:8]}


def summary_line(tag: str, r: dict[str, Any]) -> str:
    if not r["total"]:
        return f"{tag}:没有可机械核验的坐标"
    s = f"{tag}:{r['total']} 条坐标,可核 {r['valid']},无效 {r['invalid']}"
    if r["samples"]:
        s += "(无效例:" + ", ".join(r["samples"][:5]) + ")"
    return s


def main() -> None:
    from migloop import service
    sid, files = sys.argv[1], sys.argv[2:]
    path = service.locate_session(sid)
    ledger = service.session_ledger(path)
    trace = service.extract_trace(path)
    cwd = str((trace.get("meta") or {}).get("cwd") or "")
    pool = Pool([*service.prior_roots(service._fmt_of(trace), path, cwd), path])
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        text = str(data.get("result") or data.get("report") or "")
        print(json.dumps({"file": f, **check_report(ledger, pool, text)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
