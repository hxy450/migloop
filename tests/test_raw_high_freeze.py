"""Offline contract for the separately requested matched raw-high experiment."""

import json
import runpy
from pathlib import Path

import pytest


def test_raw_high_freeze(tmp_path, monkeypatch):
    driver = Path(__file__).resolve().parents[1] / "docs/experiments/inquiry-20260911/raw-high.py"
    module = runpy.run_path(str(driver))
    iteration, base, raw = module["ITER"], module["BASE"], module["RAW"]
    old, match, prior, out = (tmp_path / n for n in ("old", "match", "prior", "out"))
    (old / "private").mkdir(parents=True)
    (old / "tasks").mkdir()
    prior.mkdir()
    match.mkdir()
    cli = tmp_path / "fake-cli"
    cli.write_text("not executed", encoding="utf-8")
    cases = []
    config = {"model_reasoning_effort": "high", "mcp_servers": {"inquiry": {"args": []}}, "web_search": "disabled"}
    for number in (1, 2):
        cid = f"F10-{number:02d}"
        cases.append({"id": cid, "file": f"{cid}.ets", "pool": str(tmp_path / "pool"), "prompt": f"tasks/{cid}.md"})
        directory = match / cid
        directory.mkdir()
        task = f"Unchanged task {cid}\n"
        (old / f"tasks/{cid}.md").write_text(task, encoding="utf-8")
        if number == 1:
            (prior / "raw-prompt.md").write_text(task, encoding="utf-8")
        (directory / "prompt.md").write_text(task + module["MARKER"] + "tool-only GUIDE", encoding="utf-8")
        base.save(directory / "settings.json", config)
        base.save(directory / "manifest.json", {"model": "gpt-5.6-luna", "effort": "high"})
    matched = {"cases": cases, "pools": {str(tmp_path / "pool"): {}}}
    base.save(match / "manifest.json", matched)
    for name in ("scoring-core.json", "reference-units.json"):
        base.save(old / "private" / name, {"frozen": True})
    monkeypatch.setitem(iteration, "verify", lambda path: matched)
    monkeypatch.setitem(iteration, "BASELINE", old)
    monkeypatch.setitem(iteration, "PRIOR", prior)
    monkeypatch.setattr(raw, "command", lambda *_: [str(cli)])
    module["prepare_raw_high"](out, match)
    manifest = module["verify_raw_high"](out)
    actual = json.loads((out / "runtime-settings.json").read_text(encoding="utf-8"))
    assert actual == {**config, "mcp_servers": {}}
    assert manifest["repetitions"] == 1 and manifest["timeout_seconds"] == 1800
    for case in cases:
        assert (out / case["prompt"]).read_text(encoding="utf-8") == (old / case["prompt"]).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="New experiment directory"):
        module["prepare_raw_high"](out, match)
    before = (out / "tasks/F10-02.md").read_bytes()
    (out / "tasks/F10-02.md").write_bytes(before + b"changed")
    with pytest.raises(ValueError, match="artifact drift"):
        module["verify_raw_high"](out)
    # The original launcher refuses an existing output directory before any CLI call.
    with pytest.raises(ValueError, match="Run directory must be new"):
        raw.launch(tmp_path / "pool", out, "never sent", actual, 1)
