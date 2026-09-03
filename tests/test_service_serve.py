"""service(会话定位 / 账本缓存 / 返修链载荷 / 两原子端点)与 serve(stdlib HTTP)—— 行为契约。

夹具是一个最小的 CC 会话:主会话无戳写 A → execute 派发子 agent(子写 A)→ visual-verify 亲手改 A,
正好出一条返修链(修复方 = 主会话的 verify 阶段)。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from migloop import serve, service
from migloop.mcp_server import GUIDE

CWD = "/proj"
SID = "abcdef12-0000-0000-0000-000000000000"
MAIN_ID = "__main__:abcdef12"


def _rec(ts: str, role: str, blocks: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"timestamp": ts, "cwd": CWD, "type": role, "sessionId": SID,
                         "message": {"role": role, "content": blocks}}
    r.update(extra)
    return r


def _call(ts: str, tid: str, name: str, inp: dict[str, Any], stage: str | None = None,
          ) -> list[dict[str, Any]]:
    ts2 = ts[:-3] + f"{int(ts[-3:-1]) + 1:02d}Z"
    extra = {"attributionSkill": f"x:{stage}"} if stage else {}
    return [_rec(ts, "assistant", [{"type": "tool_use", "id": tid, "name": name, "input": inp}], **extra),
            _rec(ts2, "user", [{"type": "tool_result", "tool_use_id": tid, "is_error": False,
                                "content": [{"type": "text", "text": "ok"}]}], **extra)]


def _write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def session(tmp_path: Any) -> tuple[str, dict[str, str]]:
    """discover 认的是 <root>/<project>/<sid>.jsonl;子 agent 在 <root>/<project>/<sid>/subagents/。"""
    proj = tmp_path / "claude" / "C--proj"
    main_path = str(proj / f"{SID}.jsonl")
    _write_jsonl(main_path, [
        *_call("2026-01-01T00:00:00Z", "t0", "Write", {"file_path": "/proj/entry/A.ets", "content": "a\n"}),
        *_call("2026-01-01T00:00:10Z", "t1", "Agent",
               {"name": "conv", "subagent_type": "worker", "description": "转换 A", "prompt": "转 A"},
               stage="a2h-execute"),
        *_call("2026-01-01T00:01:00Z", "t2", "Edit",
               {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"},
               stage="arkts-visual-verify"),
    ])
    _write_jsonl(str(proj / SID / "subagents" / "agent-aconv-abc123.jsonl"), [
        _rec("2026-01-01T00:00:20Z", "user", [{"type": "text", "text": "转 A"}]),
        *_call("2026-01-01T00:00:30Z", "c1", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}),
    ])
    for empty in ("codex", "deveco"):
        (tmp_path / empty).mkdir()
    roots = {"claude": str(tmp_path / "claude"), "codex": str(tmp_path / "codex"),
             "deveco": str(tmp_path / "deveco")}
    return main_path, roots


def test_locate_session_by_path_prefix_and_project(session: tuple[str, dict[str, str]]) -> None:
    path, roots = session
    assert service.locate_session(path, roots) == os.path.abspath(path)
    assert service.locate_session("abcdef12", roots) == os.path.abspath(path)
    assert service.locate_session("c--proj", roots) == os.path.abspath(path)   # 项目名片段,不分大小写
    with pytest.raises(service.SessionLookupError):
        service.locate_session("nosuch", roots)


def test_ledger_and_fixchain_from_service(session: tuple[str, dict[str, str]]) -> None:
    path, _ = session
    led = service.session_ledger(path)
    assert MAIN_ID in led.agents and "agent-aconv-abc123" in led.agents
    assert service.session_ledger(path) is led                     # (mtime, size) 没变就命中缓存
    payload = service.fixchain_payload(path)
    assert payload["t0"] and payload["cross"] is None
    assert [c["fixer"]["id"] for c in payload["chains"]] == [MAIN_ID]
    assert payload["chains"][0]["fixer"]["stage"] == "arkts-visual-verify"
    assert payload["chains"][0]["generator"]["id"] == "agent-aconv-abc123"
    assert service.session_cwd(path) == CWD


def test_pages_and_atoms(session: tuple[str, dict[str, str]]) -> None:
    path, _ = session
    html = service.report_html(path)
    assert "__TRACE_JSON__" not in html and "返修" in html
    served = service.report_trace(path)
    assert "urls" not in served                                    # 有服务端:页面上留返修链路入口
    assert any(f.get("chain") for f in served["audit"]["findings"])  # 返修追溯卡吃的是账本的链
    static = service.report_trace(path, static=True)
    assert static["urls"] == {"fixchain": None}                    # 导出 HTML:入口藏起来
    assert "findings" in service.report_trace(path, static=True, with_chains=False)["audit"]
    light = service.fixchain_light(path)
    assert light["sid8"] == "abcdef12" and light["project"] == "proj"
    assert [f["id"] for f in light["fixes"]] == ["/proj/entry/A.ets"]   # 首屏列表从链缓存来
    assert "__FIXCHAIN_JSON__" not in service.fixchain_html(path)

    idx = service.atom_json(path, "index", {})
    assert [f["path"] for f in idx["files"]] == ["/proj/entry/A.ets"]
    f = service.atom_json(path, "file", {"path": "A.ets", "diff": "0"})
    assert f and len(f["versions"]) == 3
    assert service.atom_json(path, "action", {"id": MAIN_ID, "seq": "1"})
    with pytest.raises(ValueError):
        service.atom_json(path, "file", {})
    with pytest.raises(ValueError):
        service.atom_json(path, "nosuch", {})

    assert service.atom_text(path, "guide", {}) == GUIDE
    assert "A.ets" in service.atom_text(path, "sessions", {})
    agent_txt = service.atom_text(path, "agent", {"id": MAIN_ID})
    assert "T+0:00" in agent_txt and "arkts-visual-verify" in agent_txt
    assert "-b" in service.atom_text(path, "diff", {"path": "A.ets", "v": "3"})
    assert service.file_diff(path, "A.ets", 3) is not None
    assert service.file_diff(path, "A.ets", 9) is None


def test_mcp_backend_shares_service_caches(session: tuple[str, dict[str, str]]) -> None:
    path, _ = session
    backend = service.McpBackend()
    led = asyncio.run(backend.get_ledger(path))
    assert led is service.session_ledger(path)
    assert asyncio.run(backend.get_session_cwd(path)) == CWD
    assert len(asyncio.run(backend.get_fixchain(path))["chains"]) == 1


def _get(base: str, url: str) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(base + url, timeout=30) as resp:
            return resp.status, resp.read(), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.geturl()


def test_serve_routes(session: tuple[str, dict[str, str]]) -> None:
    path, roots = session
    srv = serve.make_server("abcdef12", "127.0.0.1", 0, roots)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        st, body, final = _get(base, "/")
        assert st == 200 and final.endswith("/api/insight1/report/abcdef12")   # 302 → 报告页
        assert "返修" in body.decode("utf-8")
        st, body, _ = _get(base, "/api/insight1/fixchain/abcdef12")
        assert st == 200 and '"sid8": "abcdef12"' in body.decode("utf-8")
        st, body, _ = _get(base, "/api/insight1/fixchain-data/abcdef12")
        assert st == 200 and len(json.loads(body)["chains"]) == 1
        st, body, _ = _get(base, "/api/insight1/atom/abcdef12/text/guide")
        assert st == 200 and body.decode("utf-8") == GUIDE
        st, body, _ = _get(base, "/api/insight1/atom/abcdef12/index")
        assert st == 200 and json.loads(body)["files"]
        st, body, _ = _get(base, "/api/insight1/atom/abcdef12/file?path=A.ets&v=3&content=1")
        assert st == 200 and json.loads(body)["versions"]
        st, body, _ = _get(base, "/api/insight1/filediff/abcdef12?file=A.ets&v=3")
        assert st == 200
        st, body, _ = _get(base, "/api/insight1/atom/abcdef12/file")
        assert st == 400 and "参数错误" in json.loads(body)["error"]
        st, body, _ = _get(base, "/api/insight1/atom/nosuch/index")
        assert st == 404 and "找不到会话" in json.loads(body)["error"]
        st, body, _ = _get(base, "/nope")
        assert st == 404 and json.loads(body)["error"] == "no such route"
    finally:
        srv.shutdown()
        srv.server_close()
