"""引用核验(机械):两组报告里的坐标能不能核回原文。只证明「位置存在、原文匹配」,不证明结论成立。

工具组坐标:#n@L行·转录标识(按 (标识, 行) 反查账本 by_loc;老格式 #n@L行 要求账本 lines[n] == L)、path@vN(该文件版本数 ≥ N)。
原始组坐标:<转录文件>.jsonl:行号(池子里有这个文件且行数 ≥ 行号)、toolu_… id(在池子任一转录里出现)。
用法: python cite_check.py <sid> <result.json>...   → 每份一行 JSON:{total, valid, invalid, drifted, samples}
也可 import:check_report(ledger, pool, text) -> dict;summary_line(tag, r) -> str。评委脚本把 summary_line 拼进提示词。"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any

_TOOL_REF = re.compile(r"#(?:([\w-]+):)?(\d+)@L(\d+)(?:/(\d+))?(?:·([\w-]+))?")
_FILE_AT = re.compile(r"([\w./-]+\.[A-Za-z0-9]+)@v(\d+)")
_RAW_LINE = re.compile(r"([\w-]+\.jsonl):(\d+)")
_TUID = re.compile(r"\btoolu_[A-Za-z0-9]{8,}\b")
_TUID_DEF = re.compile(r'"id":\s*"(toolu_[A-Za-z0-9]{8,})"')      # 只认 tool_use 块里定义的 id,正文里提到的不算


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
                            ids.update(_TUID_DEF.findall(line))
                except OSError:
                    continue
            self._ids = ids
        return tuid in self._ids


def check_report(ledger: Any, pool: Pool, text: str) -> dict[str, Any]:
    total = valid = drifted = 0
    bad: list[str] = []
    untagged = 0
    for m in _TOOL_REF.finditer(text):
        total += 1
        if ledger is None:
            bad.append(m.group(0))
            continue
        from migloop import atoms
        tag = m.group(1) or m.group(5)
        hit, status = atoms.resolve_ref(ledger, int(m.group(2)), int(m.group(3)), int(m.group(4) or 0), tag)
        if hit is not None:
            valid += 1
            if status == "drifted":
                drifted += 1                          # #n 漂了,位置对得上:仍可核
        else:
            if status == "untagged":
                untagged += 1
            bad.append(m.group(0) + ("(歧义)" if status == "ambiguous" else "(无标识)" if status == "untagged" else ""))
    if ledger is not None:
        from migloop import filestory
        for m in _FILE_AT.finditer(text):
            k = filestory.find_story_path(ledger.stories, m.group(1))
            total += 1
            if k and 1 <= int(m.group(2)) <= len(ledger.stories[k].versions):
                valid += 1
            else:
                bad.append(m.group(0))
    for m in _RAW_LINE.finditer(text):
        total += 1
        name = m.group(1)
        hit_name = next((n for n in pool.files if n == name or n.startswith(name.rsplit(".", 1)[0])), None)
        if hit_name and 1 <= int(m.group(2)) <= pool.lines(hit_name):
            valid += 1
        else:
            bad.append(m.group(0))
    for tuid in set(_TUID.findall(text)):
        total += 1
        if pool.has_id(tuid):
            valid += 1
        else:
            bad.append(tuid)
    return {"total": total, "valid": valid, "invalid": len(bad), "drifted": drifted, "untagged": untagged, "samples": bad[:8]}


def summary_line(tag: str, r: dict[str, Any]) -> str:
    if not r["total"]:
        return f"{tag}:没有可机械核验的坐标"
    s = f"{tag}:{r['total']} 条坐标,位置可核 {r['valid']},无效 {r['invalid']}"
    if r.get("drifted"):
        s += f"(其中 {r['drifted']} 条动作号漂了但位置对得上)"
    if r.get("untagged"):
        s += f"(无效里 {r['untagged']} 条没带转录标识,核不回去)"
    if r["samples"]:
        s += ";无效例:" + ", ".join(r["samples"][:5])
    return s


def pool_for(sid: str) -> tuple[Any, Pool]:
    from migloop import service
    path = service.locate_session(sid)
    ledger = service.session_ledger(path)
    trace = service.extract_trace(path)
    cwd = str((trace.get("meta") or {}).get("cwd") or "")
    return ledger, Pool([*service.prior_roots(service._fmt_of(trace), path, cwd), path])


def main() -> None:
    sid, files = sys.argv[1], sys.argv[2:]
    ledger, pool = pool_for(sid)
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        text = str(data.get("result") or data.get("report") or "")
        print(json.dumps({"file": f, **check_report(ledger, pool, text)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
