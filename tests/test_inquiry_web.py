"""The old session URL mounts the new application, not a second query engine."""

import http.client
import json
import threading
from pathlib import Path

from migloop import serve, service
from migloop.inquiry.engine import Engine
from migloop.inquiry.store import Store
from migloop.inquiry.web import dispatch_http
from tests import test_service_serve

SID = test_service_serve.SID
session = test_service_serve.session


def test_session_tree_uses_same_http_and_kernel(session, tmp_path, monkeypatch):
    path, roots = session
    monkeypatch.setenv("MIGLOOP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        service,
        "session_ledger",
        lambda *_: (_ for _ in ()).throw(AssertionError("old ledger used")),
    )
    monkeypatch.setattr(service, "prior_roots", lambda *_: [])
    database = service.inquiry_database(path)
    server = serve.make_server(SID, roots=roots)
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}
    )
    worker.start()

    def call(route, data=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            conn.request(
                "POST" if data is not None else "GET",
                route,
                body=json.dumps(data).encode() if data is not None else None,
                headers={"Origin": origin} if origin else {},
            )
            res = conn.getresponse()
            return res.status, res.read().decode(), res.getheader("Content-Type")
        finally:
            conn.close()

    try:
        prefix = f"/api/insight1/inquiry/{SID}"
        page = call(f"/api/insight1/fixchain/{SID}")
        assert page[0] == 200 and prefix + "/tree.js" in page[1]
        assert "__INQUIRY_CONFIG__" not in page[1]
        assert call(prefix + "/tree.js")[2].startswith("text/javascript")
        query = {
            "op": "file",
            "key": "/proj/entry/A.ets",
            "at": "2026-01-01T00:02:00Z",
            "view": "neighbors",
        }
        status, body, _ = call(prefix + "/api/query", query)
        assert status == 200
        assert json.loads(body) == json.loads(
            dispatch_http(database, "/api/query", query)[1]
        )
        assert json.loads(call(prefix + "/api/trace")[1]) == []
        assert (
            call(prefix + "/api/report", {"document": "{}"}, "https://foreign.example")[
                0
            ]
            == 403
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)
    assert not worker.is_alive()


def test_snapshot_reuse_does_not_parse_sources_or_rebuild_after_queries(
    session, tmp_path, monkeypatch
):
    from migloop.inquiry import store as module

    path, _ = session
    monkeypatch.setenv("MIGLOOP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(service, "prior_roots", lambda *_: [])
    first = service.inquiry_database(path)
    store = Store(first)
    Engine(store).query({"op": "file", "key": "A.ets", "at": "2026-01-01T00:02:00Z"})
    store.close()
    descriptor = module.describe_source
    monkeypatch.setattr(
        module,
        "describe_source",
        lambda *_: (_ for _ in ()).throw(AssertionError("warm index parsed source")),
    )
    assert service.inquiry_database(path) == first
    monkeypatch.setattr(module, "describe_source", descriptor)
    source = Path(path)
    source.write_bytes(source.read_bytes() + b"\n")
    second = service.inquiry_database(path)
    assert second != first and Path(first).is_file()


def test_frozen_anchor_index_does_not_import_other_roots(tmp_path, monkeypatch):
    from tests.test_frozen_anchor import anchored, root

    pool = tmp_path / "pool"
    early = root(pool, "early111", "2026-01-01T00:00:00Z")
    anchor = root(pool, "anchor22", "2026-01-01T01:00:00Z")
    root(pool, "future33", "2026-01-01T02:00:00Z")
    anchored(monkeypatch, pool, anchor, [early, anchor])
    monkeypatch.setenv("MIGLOOP_CACHE_DIR", str(tmp_path / "cache"))
    first = service.inquiry_database(str(early))
    assert first == service.inquiry_database(str(anchor))
    store = Store(first)
    assert {r["name"] for r in store.rows("SELECT name FROM sources")} == {
        early.name,
        anchor.name,
    }
    store.close()
