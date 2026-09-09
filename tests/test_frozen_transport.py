"""Both transports use one explicitly selected investigation book across aliases."""
import asyncio
import json
import threading
from urllib.request import urlopen

from migloop import atoms, mcp_server, serve, service
from tests.test_atoms import _call
from tests.test_frozen_anchor import anchored, isolated, root


def test_http_and_mcp_alias_queries_share_scope_and_navigation_state(tmp_path, monkeypatch):
    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z", cwd="/project")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z", cwd="/project/app")
    path = "/project/app/A.ets"
    early.write_text(early.read_text(encoding="utf-8") + "\n".join(json.dumps(row) for row in
        _call("2026-01-01T00:01:00Z", "w", "Write", {"file_path": path, "content": "a"})) + "\n", encoding="utf-8")
    anchor.write_text(anchor.read_text(encoding="utf-8") + "\n".join(json.dumps(row) for row in [
        *_call("2026-01-01T01:01:00Z", "r", "Read", {"file_path": path}, out="1\ta"),
        *_call("2026-01-01T01:02:00Z", "b", "Write", {"file_path": "/project/app/B.ets", "content": "b"}),
    ]) + "\n", encoding="utf-8")
    anchored(monkeypatch, pool, anchor, [anchor, early])
    ledger = service.session_ledger(str(anchor))
    identity = atoms.ledger_identity(ledger)
    mcp = mcp_server.build_server()

    async def investigation():
        first = await mcp.call_tool("sessions", {"sid": "early111", "file": path})
        second = await mcp.call_tool("sessions", {"sid": "anchor22", "file": path})
        assert first[0].text == second[0].text
        assert identity in first[0].text and "固定观察范围" in first[0].text
        file_result = await mcp.call_tool("file", {"sid": "early111", "path": path, "v": 1, "via": "sessions"})
        assert file_result[0].text.startswith("# 文件")
        agent_result = await mcp.call_tool("agent", {"sid": "anchor22", "id": "__main__:anchor22", "v": 1,
                                                    "via": f"file:{path}@v1", "summary_chars": 200})
        assert agent_result[0].text.startswith("# agent")
        assert "每条至多 200" in agent_result[0].text
        return first[0].text

    sessions = asyncio.run(investigation())
    server = serve.make_server("anchor22", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        from urllib.parse import urlencode
        for sid in ("early111", "anchor22"):
            with urlopen(base + f"/api/insight1/atom/{sid}/text/sessions?" + urlencode({"file": path})) as response:
                assert response.read().decode("utf-8") == sessions
            with urlopen(base + f"/api/insight1/fixchain-data/{sid}") as response:
                scope = json.load(response)["observation_scope"]
                assert scope["anchor"] == str(anchor) and scope["roots"] == [str(early), str(anchor)]
            with urlopen(base + f"/api/insight1/fixchain/{sid}") as response:
                html = response.read().decode("utf-8")
                assert '"mode": "frozen_anchor"' in html
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()
