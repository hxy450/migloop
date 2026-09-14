"""Offline completion adapter guards; no investigator is launched."""

import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from migloop.inquiry import store
from tests.test_inquiry_core import record, result, use

DRIVER = Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/complete_review_tree.py"
spec = importlib.util.spec_from_file_location("complete_tree_test", DRIVER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
PARENT = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def prepared_inputs(tmp_path, monkeypatch):
    review = tmp_path / "review"
    parent = review / "F10-test/inquiry"
    workspace, run = parent / "workspace", parent / "rep1"
    workspace.mkdir(parents=True)
    run.mkdir()
    task = {"file": "A.ets", "pool": str(tmp_path / "pool"),
            "generation_end": "2026-01-01T00:00:01Z", "observation_end": "2026-01-01T00:00:09Z"}
    Path(task["pool"]).mkdir()
    (workspace / "initial-report.md").write_text("MODEL RAW ANSWER", encoding="utf-8")
    (run / "report.md").write_text("MODEL REVIEW DELTA", encoding="utf-8")
    runner.BASE.save(workspace / "investigation.json", task)
    original_source = Path(task["pool"]) / "a.jsonl"
    original_source.write_text("\n".join(json.dumps(row) for row in [
        record(1, use("r", "Bash", command='cd /source && for f in app/input.xml; do cat "$f"; done')),
        record(2, result("r", "<xml>original input</xml>")),
        record(3, use("w", file_path="/source/A.ets", content="generated page")), record(4, result("w")),
    ]) + "\n", encoding="utf-8")
    registration = store.Source(str(original_source), "a.jsonl", "a", "/source")
    with monkeypatch.context() as old_parser:
        old_parser.setattr(store, "literal_path_mentions", lambda *_: [])
        old = store.Store.build(parent.parent / "index.sqlite", [registration])
    old.handle("e", {"ref": old.locate("a.jsonl", 1)})
    with old.db:
        old.db.executemany("INSERT INTO runs VALUES (?,'query','{}','[]','body')", [("q-z",), ("q-a",)])
        old.db.execute("INSERT INTO frames VALUES ('q-z',0,'frame','sha')")
        old.db.execute("INSERT INTO visible VALUES ('q-z',0,1,'recorded')")
    old.close()
    transcript = [{"ordinal": 15, "type": "session_meta", "payload": {"id": PARENT}},
                  {"ordinal": 16, "type": "response_item", "payload": {"role": "assistant",
                   "phase": "final_answer", "content": [{"text": "MODEL REVIEW DELTA"}]}}]
    native = tmp_path / "parent.jsonl"
    native.write_text("\n".join(json.dumps(r) for r in transcript) + "\n", encoding="utf-8")
    shutil.copy2(native, run / "transcript.jsonl")
    runner.BASE.save(run / "metrics.json", {"status": "completed", "actual_models": ["gpt-5.6-luna"],
        "actual_effort": "high", "recording_complete": True, "report_present": True,
        "session_id": PARENT, "transcript_sha256": runner.BASE.sha(native)})
    parser = runner.RAW.parser()
    monkeypatch.setattr(parser, "find_codex_transcript", lambda session: native)
    monkeypatch.setattr(runner.RAW, "parser", lambda: parser)
    cli = tmp_path / "fake-cli"
    cli.write_text("never executed", encoding="utf-8")
    monkeypatch.setattr(runner.RAW, "command", lambda *_: [str(cli), "exec", "-"])
    monkeypatch.setattr(runner.RAW, "launch", lambda *_: pytest.fail("offline model call"))
    monkeypatch.setattr(runner.PAIRED, "verify", lambda root: {"verified": root == review})

    def prepare(out, identity):
        if out.exists():
            raise FileExistsError(out)
        work = out / "workspace"
        skill = work / ".agents/skills/migloop-investigate"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("production skill fixture", encoding="utf-8")
        (out / "code/src/migloop").mkdir(parents=True)
        store.Store.build(out / "index.sqlite", [registration]).close()
        runner.BASE.save(work / "investigation.json", task)
        runner.BASE.save(out / "settings.json", {})
        for name in ("prompt.md", "driver.py", "luna-audit.py"):
            (out / name).write_text("original prepared " + name, encoding="utf-8")
        runner.BASE.save(out / "manifest.json", {
            "case": {"id": identity, **task}, "workspace": str(work),
            "code_inventory": runner.BASE.tree_manifest(out / "code/src/migloop"),
            "pool_inventory": runner.BASE.tree_manifest(task["pool"]),
            "workspace_inventory": runner.BASE.tree_manifest(work),
            **{key + "_sha256": runner.BASE.sha(out / name) for key, name in
               (("prompt", "prompt.md"), ("settings", "settings.json"), ("driver", "driver.py"), ("audit", "luna-audit.py"))}})

    monkeypatch.setattr(runner.SKILL, "prepare", prepare)
    return review, parent, native, tmp_path / "completion"


def test_prepare_reseals_only_own_answers_and_preserves_original_manifest(prepared_inputs):
    review, parent, native, out = prepared_inputs
    before = runner.BASE.sha(native)
    runner.prepare(out, review, "F10-test")
    m = runner.verify(out)
    original = runner.BASE.read(out / "prepare-manifest.json")
    assert original["workspace_inventory"] != m["workspace_inventory"]
    assert original["prompt_sha256"] != m["prompt_sha256"]
    assert (out / "workspace/initial-report.md").read_bytes() == (parent / "workspace/initial-report.md").read_bytes()
    assert (out / "workspace/review-delta.md").read_bytes() == (parent / "rep1/report.md").read_bytes()
    assert runner.BASE.sha(out / "parent-native.jsonl") == runner.BASE.sha(native) == before
    assert m["completion"]["parent_end_ordinal"] == 17
    assert m["completion"]["parent_bytes"] == native.stat().st_size
    assert not m["completion"]["reviewer_inputs"]
    assert m["timeout_seconds"] == 1200
    assert str(runner.RAW.OLD_RUNNER) in m["completion"]["files"]
    assert not (out / "runs").exists()


@pytest.mark.parametrize("changed", ["native", "source_delta", "copy", "prompt", "adapter"])
def test_any_frozen_parent_or_input_change_stops_completion(prepared_inputs, changed):
    review, parent, native, out = prepared_inputs
    runner.prepare(out, review, "F10-test")
    path = {"native": native, "source_delta": parent / "rep1/report.md", "copy": out / "parent-native.jsonl",
            "prompt": out / "prompt.md", "adapter": out / "completion-driver.py"}[changed]
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen"):
        runner.verify(out)


def test_non_model_review_text_is_rejected_before_preparing_workspace(prepared_inputs):
    review, parent, _, out = prepared_inputs
    (parent / "rep1/report.md").write_text("REVIEWER REPLACEMENT", encoding="utf-8")
    with pytest.raises(ValueError, match="native final"):
        runner.prepare(out, review, "F10-test")
    assert not out.exists()


def test_run_forks_exact_parent_once_and_reuses_existing_runner(prepared_inputs, monkeypatch):
    review, _, _, out = prepared_inputs
    runner.prepare(out, review, "F10-test")
    command, calls = runner.RAW.command, []

    def run(target):
        calls.append(runner.RAW.command(target / "workspace", {}))
        (target / "runs/inquiry/rep1").mkdir(parents=True)

    monkeypatch.setattr(runner.SKILL, "run", run)
    monkeypatch.setattr(runner, "audit", lambda target: calls.append("offline audit"))
    runner.run(out)
    assert calls == [command(None, {})[:-1] + ["fork", PARENT, "-"], "offline audit"]
    assert runner.RAW.command is command
    with pytest.raises(FileExistsError, match="already started"):
        runner.run(out)


def test_original_raw_ancestor_guard_is_required(prepared_inputs, monkeypatch):
    review, _, _, out = prepared_inputs
    runner.prepare(out, review, "F10-test")

    def changed(root):
        assert root == review
        raise ValueError("Parent thread changed")

    monkeypatch.setattr(runner.PAIRED, "verify", changed)
    with pytest.raises(ValueError, match="Parent thread changed"):
        runner.verify(out)


def test_parent_ledger_handles_survive_and_clone_writes_do_not_touch_parent(prepared_inputs):
    review, parent, _, out = prepared_inputs
    original = parent.parent / "index.sqlite"
    before = runner.BASE.sha(original)
    runner.prepare(out, review, "F10-test")
    with sqlite3.connect(original) as db:
        original_handles = db.execute("SELECT * FROM handles").fetchall()
        assert not db.execute("SELECT 1 FROM files WHERE path='/source/app/input.xml'").fetchone()
    with sqlite3.connect(out / "index.sqlite") as db:
        assert db.execute("SELECT * FROM handles").fetchall() == original_handles
        assert db.execute("SELECT 1 FROM files WHERE path='/source/app/input.xml'").fetchone()
        assert db.execute("SELECT 1 FROM mentions WHERE name='/source/app/input.xml'").fetchone()
        assert db.execute("SELECT id FROM runs ORDER BY rowid").fetchall() == [("q-z",), ("q-a",)]
        assert db.execute("SELECT count(*) FROM frames").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM visible").fetchone()[0] == 1
        db.execute("INSERT INTO handles VALUES ('e-new','e','child coordinates')")
    assert runner.BASE.sha(original) == before
    m = runner.verify(out)
    assert m["completion"]["parent_index"]["source_sha256"] == before
    assert m["completion"]["parent_index"]["snapshot_sha256"] == runner.BASE.sha(out / "parent-index.sqlite")
    assert m["completion"]["parent_index"]["inherited"] == {"handles": 1, "runs": 2, "frames": 1, "visible": 1}
    with sqlite3.connect(original) as db:
        assert db.execute("SELECT count(*) FROM handles").fetchone()[0] == 1
    with sqlite3.connect(out / "parent-index.sqlite") as db:
        db.execute("DELETE FROM handles")
    with pytest.raises(ValueError, match="Frozen completion input"):
        runner.verify(out)


@pytest.mark.parametrize("fault", ["sources", "records", "schema", "handle"])
def test_inheritance_rejects_different_pool_schema_and_conflicting_rows(prepared_inputs, monkeypatch, fault):
    review, parent, _, out = prepared_inputs
    original = parent.parent / "index.sqlite"
    before, prepare = runner.BASE.sha(original), runner.SKILL.prepare

    def mismatched(target, identity):
        prepare(target, identity)
        with sqlite3.connect(target / "index.sqlite") as db:
            if fault == "sources":
                db.execute("UPDATE sources SET name='different'")
            elif fault == "records":
                db.execute("UPDATE records SET sha='different'")
            elif fault == "schema":
                db.execute("ALTER TABLE frames ADD COLUMN extra TEXT")
            else:
                with sqlite3.connect(original) as source:
                    handle = source.execute("SELECT * FROM handles").fetchone()
                db.execute("INSERT INTO handles VALUES (?,?,?)", (*handle[:2], "conflicting payload"))

    monkeypatch.setattr(runner.SKILL, "prepare", mismatched)
    with pytest.raises(ValueError, match="Different|collision"):
        runner.prepare(out, review, "F10-test")
    assert runner.BASE.sha(original) == before
    with sqlite3.connect(out / "index.sqlite") as db:
        assert db.execute("SELECT 1 FROM files WHERE path='/source/app/input.xml'").fetchone()
        assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
