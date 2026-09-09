"""Serving delegates session scope to service, without global pre-resolution."""
import sys

import pytest

from migloop import cli, serve


@pytest.mark.parametrize("target", ["ff019d8a", "rollout-abc.jsonl", "/frozen/pool/root.jsonl"])
def test_serve_keeps_raw_alias_for_service_scope(monkeypatch, target):
    calls = []
    monkeypatch.setattr(sys, "argv", ["migloop", target, "--serve", "--host", "127.0.0.1", "--port", "19678"])
    monkeypatch.setattr(cli, "resolve_target", lambda *a, **kw: pytest.fail("must not globally resolve before serving"))
    monkeypatch.setattr(cli.adapters, "detect", lambda *a: pytest.fail("must not read a globally discovered live copy"))
    monkeypatch.setattr(serve, "serve", lambda *a, **kw: calls.append((a, kw)))
    cli.main()
    assert len(calls) == 1
    assert calls[0][0] == (target,)
    assert calls[0][1]["host"] == "127.0.0.1"
    assert calls[0][1]["port"] == 19678
    assert calls[0][1]["open_browser"] is False
