"""合成 Claude Code 转录记录的小工具(测试夹具用)。

从 tests/test_atoms.py 复制(_rec / _use / _res / _call / _read_call / _write_jsonl),那个测试随返修链路
移到了 fuxi-ailabs/a2h-memory 的 fixchain/;会话解析层的冻结池测试还要用这几个造记录的函数。
"""
from __future__ import annotations

import json
import os
from typing import Any

CWD = "/proj"


def _rec(ts: str, role: str, blocks: list[dict[str, Any]] | str, **extra: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"timestamp": ts, "cwd": CWD, "type": role,
                         "message": {"role": role, "content": blocks}}
    r.update(extra)
    return r


def _use(tid: str, name: str, inp: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _res(tid: str, text: str = "ok", is_error: bool = False) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tid, "is_error": is_error,
            "content": [{"type": "text", "text": text}]}


def _call(ts: str, tid: str, name: str, inp: dict[str, Any], out: str = "ok",
          is_error: bool = False, **res_extra: Any) -> list[dict[str, Any]]:
    """一次工具调用 = assistant 的 tool_use + user 的 tool_result(结果时刻 +1s)。"""
    ts2 = ts[:-3] + f"{int(ts[-3:-1]) + 1:02d}Z"
    return [_rec(ts, "assistant", [_use(tid, name, inp)]),
            _rec(ts2, "user", [_res(tid, out, is_error)], **res_extra)]


def _read_call(ts: str, tid: str, path: str, content: str, start: int = 1) -> list[dict[str, Any]]:
    n = content.count("\n") + 1
    return _call(ts, tid, "Read", {"file_path": path}, "…",
                 toolUseResult={"type": "text", "file": {"filePath": path, "content": content,
                                                          "startLine": start, "numLines": n,
                                                          "totalLines": n}})


def _write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
