"""service(会话定位 / 账本缓存 / 返修链载荷 / 两原子端点)与 serve(stdlib HTTP)—— legacy/mcp-2026-09-02 口径。

夹具是一个最小的 CC 会话:主会话无戳写 A → execute 派发子 agent conv(子写 A)→ visual-verify 派发子 agent fix
(子改 A),正好出一条返修链。22d88c0e 的修复方判定在血缘层按 agent 的阶段(主会话不算修复方,
「主会话 verify 期亲手改也算」是 09-02 下午之后的口径),所以修复方是子 agent。
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
CONV = "agent-aconv-abc123"
FIX = "agent-afix-abc123"


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
        *_call("2026-01-01T00:01:00Z", "t2", "Agent",
               {"name": "fix", "subagent_type": "worker", "description": "修 A", "prompt": "修 A"},
               stage="arkts-visual-verify"),
    ])
    # 血缘层(提取层)靠 subagents/agent-<id>.meta.json 发现子 agent、靠记录上的 agentId / attributionSkill 认身份与阶段;
    # 22d88c0e 的修复方判定走血缘层的 agent 级阶段,少了就没有修复方
    def _sub(aid: str, stage: str, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**r, "agentId": aid, "isSidechain": True, "attributionSkill": f"x:{stage}"} for r in recs]

    sub_dir = proj / SID / "subagents"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / f"{CONV}.meta.json").write_text(
        json.dumps({"agentType": "worker", "description": "转换 A", "toolUseId": "t1"}), encoding="utf-8")
    (sub_dir / f"{FIX}.meta.json").write_text(
        json.dumps({"agentType": "worker", "description": "修 A", "toolUseId": "t2"}), encoding="utf-8")
    _write_jsonl(str(sub_dir / f"{CONV}.jsonl"), _sub(CONV[6:], "a2h-execute", [
        _rec("2026-01-01T00:00:20Z", "user", [{"type": "text", "text": "转 A"}]),
        *_call("2026-01-01T00:00:30Z", "c1", "Write", {"file_path": "/proj/entry/A.ets", "content": "b\n"}),
    ]))
    _write_jsonl(str(sub_dir / f"{FIX}.jsonl"), _sub(FIX[6:], "arkts-visual-verify", [
        _rec("2026-01-01T00:01:10Z", "user", [{"type": "text", "text": "修 A"}]),
        *_call("2026-01-01T00:01:20Z", "f1", "Edit",
               {"file_path": "/proj/entry/A.ets", "old_string": "b", "new_string": "c"}),
    ]))
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
    assert MAIN_ID in led.agents and CONV in led.agents and FIX in led.agents
    assert service.session_ledger(path) is led                     # (mtime, size) 没变就命中缓存
    payload = service.fixchain_payload(path)
    assert "t0" in payload and payload["cross"] is None
    assert [c["fixer"]["id"] for c in payload["chains"]] == [FIX]
    assert payload["chains"][0]["fixer"]["stage"] == "arkts-visual-verify"
    assert payload["chains"][0]["generator"]["id"] == CONV
    assert service.session_cwd(path) == CWD


def test_pages_and_atoms(session: tuple[str, dict[str, str]]) -> None:
    path, _ = session
    html = service.report_html(path)
    assert "__TRACE_JSON__" not in html and "返修" in html
    served = service.report_trace(path)
    assert "urls" not in served                                    # 有服务端:页面上留返修链路入口
    assert "findings" in served["audit"]
    static = service.report_trace(path, static=True)
    assert static["urls"] == {"fixchain": None}                    # 导出 HTML:入口藏起来
    light = service.fixchain_light(path)
    assert light["sid8"] == "abcdef12" and light["project"] == "proj"
    assert [f["id"] for f in light["fixes"]] == ["/proj/entry/A.ets"]   # 首屏列表从链缓存来
    assert [f["id"] for f in light["fixers"]] == [FIX]
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
    assert "修 A" in service.atom_text(path, "agent", {"id": FIX})          # 派发词全文归子 agent 原子
    assert "-b" in service.atom_text(path, "diff", {"path": "A.ets", "v": "3"})
    assert "A.ets" in service.atom_text(path, "blame", {"path": "A.ets", "v": "3"})
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
