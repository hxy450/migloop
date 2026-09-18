"""Synthetic contract tests, not migration attribution or recall-accuracy scores."""
import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "migloop-memory-maintain" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from memorylib.cases import dispatch, pack
from memorylib.common import fingerprint, load, write_new
from memorylib.provenance import collect
from memorylib.registry import Memory, revision_of
from memorylib.retrieval import browse, notice, read, search


@pytest.fixture
def prepared(tmp_path):
    pool = tmp_path / "pool"
    pool.mkdir()
    rows = [
        {"type": "assistant", "sessionId": "session-1", "agentId": "worker-1", "version": "2.0", "cwd": "/app",
         "timestamp": "2026-01-01T00:00:01Z", "message": {"model": "recorded-generation-model"}},
        {"type": "assistant", "sessionId": "session-1", "agentId": "worker-1", "version": "2.0",
         "timestamp": "2026-01-01T00:00:02Z", "message": {"model": "another-recorded-model"}},
    ]
    (pool / "agent.jsonl").write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
    server = tmp_path / "server.json"
    write_new(server, {"migration": {"id": "migration-1", "tool_versions": {"converter": "recorded-version"}},
                       "analysis": {"models": ["analysis-only-model"]}})
    meta = tmp_path / "metadata.json"
    write_new(meta, collect(pool, server))
    task = {"schema": "migloop-repair-triage/1", "scope": {"project_roots": ["/app"], "materials": [str(pool)],
            "generation_end": "2026-01-01T00:00:03Z", "observation_end": "2026-01-01T00:00:10Z"},
            "issues": [{"title": "Test issue", "changes": [{"files": ["src/Page.ets"], "change": "Test change", "evidence": ["agent.jsonl:L1"]}],
                        "participants": [{"agent": "agent.jsonl"}]}]}
    tasks = tmp_path / "tasks.json"
    write_new(tasks, task)
    jobs = tmp_path / "jobs"
    dispatch(tasks, meta, jobs)
    job = Path(load(jobs / "jobs.json")["jobs"][0]["job"])
    graph = {"target": {"key": "/app/src/Page.ets", "since": task["scope"]["generation_end"], "at": task["scope"]["observation_end"]},
             "summary": "Test claim, not a real historical finding", "recommendations": ["Check current input"],
             "nodes": [{"key": "agent.jsonl", "at": "2026-01-01T00:00:02Z", "reason": "Test", "problem": True}],
             "edges": [{"from": 1, "to": "target"}]}
    draft = {"title": "Test issue", "when": "Working on styled text", "summary": "Test diagnosis",
             "recommendations": ["Keep segment styles"], "unknown": ["Synthetic test only"], "graphs": [graph]}
    draft_path, card_path = tmp_path / "draft.json", tmp_path / "case.json"
    write_new(draft_path, draft)
    pack(job, draft_path, card_path)
    return {"pool": pool, "meta": meta, "tasks": tasks, "job": job, "draft": draft, "card_path": card_path,
            "card": load(card_path), "root": tmp_path}


def make_lesson(card, identity="lesson-text", **changes):
    return {"id": identity, "title": "富文本 text segments", "topic": ["ui", "text"],
            "when": "迁移富文本或 Span 时", "unless": ["全串相同样式"], "why": "Avoid losing segment style",
            "how": ["保留数字和后缀的独立字号"], "check": ["Compare each segment"], "requires": [],
            "evidence": [{"case": card["id"], "claim": "diagnosis", "revision": card["revision"]}],
            "status": "active", **changes}


def memory_with(prepared, lessons=None):
    memory = Memory(prepared["root"] / "memory")
    memory.init()
    memory.ingest([prepared["card_path"]])
    memory.apply({"base_revision": memory.current()["revision"], "upsert": lessons or [make_lesson(prepared["card"])],
                  "topic_descriptions": {"ui": "界面布局和文本", "ui/text": "字号、富文本和数字单位"}})
    return memory


def test_metadata_preserves_mixed_models_and_distinguishes_analyst(prepared):
    meta = load(prepared["meta"])
    assert meta["observed"]["models"] == ["another-recorded-model", "recorded-generation-model"]
    assert meta["analysis"]["models"] == ["analysis-only-model"]
    assert meta["observed"]["platforms"] == ["claude-code"]
    assert meta["sources"][0]["models"][0]["first_ref"] == "agent.jsonl:L1"
    assert meta["migration"]["tool_versions"] == {"converter": "recorded-version"}
    assert "models" not in meta["unknown"]


def test_unknown_not_inferred_and_codex_metadata(tmp_path):
    path = tmp_path / "rollout.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": "codex-session", "cli_version": "0.2"}}) + "\n"
                    + json.dumps({"type": "turn_context", "payload": {"model": "recorded-model"}}) + "\n"
                    + "invalid json\n", encoding="utf-8")
    value = collect(path)
    assert value["observed"]["models"] == ["recorded-model"]
    assert value["observed"]["platforms"] == ["codex"]
    assert value["sources"][0]["invalid_json_records"] == 1
    assert "historical_migration_tool_versions" in value["unknown"]
    assert "analysis_models" in value["unknown"]


def test_deveco_only_selected_descendants_and_model_not_message_id(tmp_path):
    path = tmp_path / "deveco.db"
    connection = sqlite3.connect(path)
    connection.executescript("CREATE TABLE session(id TEXT, parent_id TEXT, directory TEXT, version TEXT);"
                             "CREATE TABLE message(id TEXT, session_id TEXT, data TEXT);"
                             "CREATE TABLE account(secret TEXT);")
    connection.executemany("INSERT INTO session VALUES(?,?,?,?)", [("root", None, "/app", "1"),
                             ("child", "root", "/app", "1"), ("other", None, "/private", "1")])
    connection.execute("INSERT INTO message VALUES(?,?,?)", ("msg1", "child", json.dumps({"id": "msg1", "modelID": "deveco-model", "providerID": "provider"})))
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="session-id"):
        collect(path)
    value = collect(path, session_id="root")
    assert value["observed"]["session_ids"] == ["child", "root"]
    assert value["observed"]["models"] == ["deveco-model"]
    assert value["observed"]["platforms"] == ["deveco"]
    assert "private" not in json.dumps(value)


def test_pack_autofills_identity_and_no_false_graph_certification(prepared):
    card = prepared["card"]
    assert card["provenance"]["observed"]["session_ids"] == ["session-1"]
    assert card["claims"]["diagnosis"]["text"] == prepared["draft"]["summary"]
    assert "agent.jsonl" in card["node_provenance"]
    assert card["validation"]["graph_check"] == "not_run"
    assert card["validation"]["causal_correctness"] == "not_certified"
    assert load(prepared["root"] / "case.views/target-1.json") == prepared["draft"]["graphs"][0]


def test_pack_rejects_model_metadata_and_missing_target(prepared):
    path = prepared["root"] / "bad.json"
    write_new(path, {**prepared["draft"], "metadata": {"models": ["made-up"]}})
    with pytest.raises(ValueError, match="unknown"):
        pack(prepared["job"], path, prepared["root"] / "bad-card.json")
    write_new(prepared["root"] / "missing.json", {**prepared["draft"], "graphs": []})
    with pytest.raises(ValueError, match="Targets without"):
        pack(prepared["job"], prepared["root"] / "missing.json", prepared["root"] / "missing-card.json")


def test_missing_target_can_remain_explicitly_unresolved(prepared):
    draft = {**prepared["draft"], "graphs": [], "unresolved_targets": [{"key": "src/Page.ets", "reason": "Missing source evidence"}]}
    path = prepared["root"] / "unresolved.json"
    write_new(path, draft)
    result = pack(prepared["job"], path, prepared["root"] / "unresolved-card.json")
    assert result["validation"]["unresolved_targets"] == ["/app/src/Page.ets"]


def test_browse_is_paginated_and_search_reaches_other_topics(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card), make_lesson(card, "lesson-layout", topic=["layout"], title="布局边距", when="尺寸与留白", why="Avoid width overflow")])
    first = browse(memory, limit=1)
    assert first["total"] == 2 and first["next"] == 1 and not first["complete"]
    assert browse(memory, offset=first["next"], limit=1)["complete"]
    assert search(memory, "字号")["total"] == 2  # searches full body, not only the index preview
    assert search(memory, "overflow")["items"][0]["id"] == "lesson-layout"
    assert search(memory, "不存在的词 xyzxyz")["total"] == 0
    output = read(memory, ["lesson-text"])
    assert "provenance" not in json.dumps(output) and "recorded-generation-model" not in json.dumps(output)
    assert output["complete"] and "how" in output["lessons"][0]


def test_withdraw_claim_invalidates_only_its_dependents_and_transitive(prepared):
    card = prepared["card"]
    a = make_lesson(card)
    b = make_lesson(card, "lesson-child", requires=[a["id"]])
    independent = make_lesson(card, "lesson-independent", evidence=[{"case": card["id"], "claim": "recommendation:1", "revision": card["revision"]}])
    memory = memory_with(prepared, [a, b, independent])
    old = memory.current()["revision"]
    result = memory.withdraw(card["id"], "Diagnosis disproved", old, "diagnosis")
    assert set(result["affected"]) == {a["id"], b["id"]}
    assert search(memory, "富文本")["total"] == 1
    assert search(memory, "富文本", all_statuses=True)["total"] == 3
    with pytest.raises(ValueError, match="not active"):
        read(memory, [a["id"]])
    assert memory.current(old)["lessons"][a["id"]]["status"] == "active"  # immutable audit history
    assert memory.case(card["id"])["revision"] == card["revision"]
    assert memory.impact(card["id"], "diagnosis")["all"] == sorted([a["id"], b["id"]])


def test_reingest_does_not_resurrect_withdrawn_card(prepared):
    memory = memory_with(prepared)
    identity = prepared["card"]["id"]
    memory.withdraw(identity, "Wrong repair", memory.current()["revision"])
    memory.ingest([prepared["card_path"]], memory.current()["revision"])
    assert memory.current()["cases"][identity]["status"] == "withdrawn"
    assert search(memory, "text")["total"] == 0


def test_changed_card_revision_requires_rereview(prepared):
    memory = memory_with(prepared)
    card = copy.deepcopy(prepared["card"])
    card["draft"]["summary"] = "Revised diagnosis"
    card["claims"]["diagnosis"]["text"] = "Revised diagnosis"
    card["revision"] = revision_of(card)
    revised = prepared["root"] / "revised.json"
    write_new(revised, card)
    result = memory.ingest([revised], memory.current()["revision"])
    assert result["affected"] == ["lesson-text"]
    assert memory.current()["lessons"]["lesson-text"]["status"] == "needs_review"
    memory.apply({"base_revision": memory.current()["revision"], "upsert": [make_lesson(card)]})
    assert read(memory, ["lesson-text"])["lessons"][0]["status"] == "active"


def test_bad_evidence_or_cycle_cannot_publish_partial_state(prepared):
    memory = memory_with(prepared)
    old = memory.current()["revision"]
    with pytest.raises(ValueError, match="existing claim"):
        memory.apply({"base_revision": old, "upsert": [make_lesson(prepared["card"], evidence=[{"case": "missing", "claim": "diagnosis", "revision": "f" * 64}])]})
    assert memory.current()["revision"] == old
    with pytest.raises(ValueError, match="cycle"):
        memory.apply({"base_revision": old, "upsert": [make_lesson(prepared["card"], requires=["lesson-text"])]})
    assert memory.current()["revision"] == old


def test_stale_publish_and_active_on_candidate_rejected(prepared):
    memory = memory_with(prepared)
    old = memory.current()["revision"]
    memory.apply({"base_revision": old, "upsert": [make_lesson(prepared["card"], status="candidate")]})
    with pytest.raises(ValueError, match="Stale"):
        memory.apply({"base_revision": old})
    with pytest.raises(ValueError, match="inactive"):
        memory.apply({"base_revision": memory.current()["revision"], "upsert": [make_lesson(prepared["card"], "child", requires=["lesson-text"])]})


def test_updated_lesson_invalidates_consumers(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card), make_lesson(card, "child", requires=["lesson-text"])])
    memory.apply({"base_revision": memory.current()["revision"], "upsert": [make_lesson(card, how=["Revised action"])]})
    assert memory.current()["lessons"]["child"]["status"] == "needs_review"
    assert memory.current()["lessons"]["lesson-text"]["status"] == "active"


def test_tamper_lock_and_notice_no_global_hook_mutation(prepared):
    memory = memory_with(prepared)
    with memory.lock():
        with pytest.raises(ValueError, match="publisher"):
            memory.apply({"base_revision": memory.current()["revision"]})
    assert not (memory.root / ".publish.lock").exists()
    assert notice(memory)["hook_installed"] is False
    old = memory.current()["revision"]
    path = memory.root / "snapshots" / (old + ".json")
    value = load(path)
    value["sequence"] += 1
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        memory.current()


def test_unknown_or_path_like_ids_rejected(prepared):
    memory = memory_with(prepared)
    with pytest.raises(ValueError):
        memory.case("../secret")
    with pytest.raises(ValueError):
        browse(memory, limit=0)
    with pytest.raises(ValueError):
        read(memory, ["missing"])


def test_no_identity_drift_when_sources_grow_or_tasks_reorder(prepared):
    old_id = prepared["card"]["id"]
    (prepared["pool"] / "additional.jsonl").write_text(json.dumps({"type": "assistant", "sessionId": "new-child-session", "message": {"model": "extra-model"}}), encoding="utf-8")
    updated_metadata = prepared["root"] / "new-metadata.json"
    write_new(updated_metadata, collect(prepared["pool"], prepared["root"] / "server.json"))
    out = prepared["root"] / "new-jobs"
    dispatch(prepared["tasks"], updated_metadata, out)
    new_job = load(out / "jobs.json")["jobs"][0]["job"]
    packed = pack(new_job, prepared["root"] / "draft.json", prepared["root"] / "new-case.json")
    assert packed["id"] == old_id
    assert packed["revision"] != prepared["card"]["revision"]
    memory = memory_with(prepared)
    result = memory.ingest([prepared["root"] / "new-case.json"], memory.current()["revision"])
    assert result["affected"] == ["lesson-text"]


def test_metadata_recapture_does_not_invalidate_identical_case(prepared):
    metadata = load(prepared["meta"])
    metadata["captured_at"] = "2030-01-01T00:00:00Z"
    new_meta = prepared["root"] / "recaptured.json"
    write_new(new_meta, metadata)
    out = prepared["root"] / "recaptured-jobs"
    dispatch(prepared["tasks"], new_meta, out)
    job = load(out / "jobs.json")["jobs"][0]["job"]
    result = pack(job, prepared["root"] / "draft.json", prepared["root"] / "recaptured-case.json")
    assert result["revision"] == prepared["card"]["revision"]


def test_task_cannot_use_unrelated_pool_metadata(prepared):
    metadata = load(prepared["meta"])
    metadata["materials"] = str(prepared["root"] / "unrelated")
    bad = prepared["root"] / "wrong-meta.json"
    write_new(bad, metadata)
    out = prepared["root"] / "wrong-jobs"
    with pytest.raises(ValueError, match="do not match"):
        dispatch(prepared["tasks"], bad, out)
    assert not out.exists()


@pytest.mark.parametrize("bad_time", [None, "not-a-time", "2026-01-01T00:00:02"])
def test_pack_rejects_invalid_time_before_writing(prepared, bad_time):
    draft = copy.deepcopy(prepared["draft"])
    draft["graphs"][0]["nodes"][0]["at"] = bad_time
    path = prepared["root"] / "bad-time.json"
    write_new(path, draft)
    out = prepared["root"] / "bad-time-case.json"
    with pytest.raises(ValueError):
        pack(prepared["job"], path, out)
    assert not out.exists()


def test_view_conflict_does_not_leave_partial_case(prepared):
    out = prepared["root"] / "collision.json"
    out.with_suffix(".views").mkdir()
    with pytest.raises(ValueError, match="View output"):
        pack(prepared["job"], prepared["root"] / "draft.json", out)
    assert not out.exists()


def test_pack_preserves_shared_input_and_multiple_problem_branches(prepared):
    draft = copy.deepcopy(prepared["draft"])
    graph = draft["graphs"][0]
    graph["nodes"] = [
        {"key": "/app/spec.md", "at": "2026-01-01T00:00:01Z", "reason": "Shared relevant input", "problem": False},
        {"key": "agent-a.jsonl", "at": "2026-01-01T00:00:02Z", "reason": "Deviation A", "problem": True},
        {"key": "agent-b.jsonl", "at": "2026-01-01T00:00:03Z", "reason": "Deviation B", "problem": True},
    ]
    graph["edges"] = [{"from": 1, "to": 2}, {"from": 1, "to": 3},
                      {"from": 2, "to": "target"}, {"from": 3, "to": "target"}]
    path = prepared["root"] / "branches.json"
    write_new(path, draft)
    output = prepared["root"] / "branches-card.json"
    result = pack(prepared["job"], path, output)
    # The wrapper preserves branches; only the existing checker may certify edges.
    assert load(output)["draft"]["graphs"] == draft["graphs"]
    assert result["validation"]["graph_check"] == "not_run"
    assert load(output.with_name("branches-card.views") / "target-1.json") == graph


def test_force_without_checker_is_not_accepted(prepared):
    draft = copy.deepcopy(prepared["draft"])
    draft["graphs"][0]["edges"][0].update(force=True, reason="Claim", evidence=[])
    path = prepared["root"] / "force.json"
    write_new(path, draft)
    with pytest.raises(ValueError, match="force requires"):
        pack(prepared["job"], path, prepared["root"] / "force-case.json")


def test_real_inquiry_checker_is_reused_without_core_changes(prepared):
    pytest.importorskip("migloop.inquiry")
    from migloop.inquiry.store import Store, Source
    from tests.test_inquiry_core import record, use, result
    path = prepared["pool"] / "agent.jsonl"
    rows = [record(1, use("write", file_path="/app/src/Page.ets", content="bad")), record(2, result("write")),
            record(5, use("fix", "Edit", file_path="/app/src/Page.ets", old_string="bad", new_string="good")), record(6, result("fix"))]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    db = prepared["root"] / "index.sqlite"
    store = Store.build(db, [Source(str(path), "agent.jsonl", "agent", "/app")])
    store.close()
    refreshed = prepared["root"] / "inquiry-metadata.json"
    write_new(refreshed, collect(prepared["pool"], prepared["root"] / "server.json"))
    jobs = prepared["root"] / "inquiry-jobs"
    dispatch(prepared["tasks"], refreshed, jobs)
    job = load(jobs / "jobs.json")["jobs"][0]["job"]
    result = pack(job, prepared["root"] / "draft.json", prepared["root"] / "checked.json", db)
    assert result["validation"]["graph_check"] == "performed"
    receipt = result["validation"]["graph_checks"][0]["receipt"]
    assert receipt["mechanical_status"] == "valid"
    assert "report_id" in receipt
    assert result["validation"]["causal_correctness"] == "not_certified"


def test_source_mutation_cannot_keep_old_model_binding(prepared):
    path = prepared["pool"] / "agent.jsonl"
    path.write_text('{"sessionId":"unrelated","type":"assistant"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Transcript changed"):
        pack(prepared["job"], prepared["root"] / "draft.json", prepared["root"] / "stale-card.json")


def test_installed_bundle_runs_outside_repo_and_refuses_overwrite(tmp_path):
    destination = tmp_path / "installed"
    installed = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "install_bundle.py"),
                                "--destination", str(destination)], capture_output=True, text=True, encoding="utf-8")
    assert installed.returncode == 0, installed.stderr
    assert len(installed.stdout.strip().splitlines()) == 4
    store = tmp_path / "isolated-store"
    initialized = subprocess.run([sys.executable, "-B", "-X", "utf8",
        str(destination / "migloop-memory-maintain/scripts/memory.py"), "init", "--store", str(store)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert initialized.returncode == 0, initialized.stderr
    assert len(json.loads(initialized.stdout)["revision"]) == 64
    recalled = subprocess.run([sys.executable, "-B", "-X", "utf8",
        str(destination / "migloop-memory-recall/scripts/recall.py"), "browse", "--store", str(store)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert recalled.returncode == 0, recalled.stderr
    assert json.loads(recalled.stdout)["total"] == 0
    again = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "install_bundle.py"),
                             "--destination", str(destination)], capture_output=True, text=True, encoding="utf-8")
    assert again.returncode != 0 and "Refusing to overwrite" in again.stderr


@pytest.mark.parametrize("skill,script,expected,rejected", [
    ("migloop-repair-triage", "triage.py", "dispatch", "pack"),
    ("migloop-build-cards", "cases.py", "pack", "dispatch"),
])
def test_role_specific_cli_does_not_mix_triage_and_cards(tmp_path, skill, script, expected, rejected):
    entry = SCRIPTS.parents[1] / skill / "scripts" / script
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(entry), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(entry), rejected],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode != 0 and "invalid choice" in result.stderr


def test_placeholder_model_is_not_a_real_model(tmp_path):
    path = tmp_path / "synthetic.jsonl"
    path.write_text(json.dumps({"type": "assistant", "sessionId": "session", "message": {"model": "<synthetic>"}}), encoding="utf-8")
    metadata = collect(path)
    assert metadata["observed"]["models"] == []
    assert metadata["sources"][0]["model_placeholders"][0]["value"] == "<synthetic>"
    assert "models" in metadata["unknown"]


def test_same_db_different_root_sessions_do_not_share_case_identity(tmp_path):
    path = tmp_path / "deveco.db"
    connection = sqlite3.connect(path)
    connection.executescript("CREATE TABLE session(id TEXT, parent_id TEXT, directory TEXT);"
                             "INSERT INTO session VALUES('root-a',NULL,'/app');"
                             "INSERT INTO session VALUES('root-b',NULL,'/app');")
    connection.close()
    tasks = tmp_path / "tasks.json"
    write_new(tasks, {"schema": "migloop-repair-triage/1", "scope": {"materials": [str(path)]},
                      "issues": [{"title": "same title", "changes": [{"files": ["/app/file"]}]}]})
    identities = []
    for sid in ("root-a", "root-b"):
        meta = tmp_path / (sid + ".json")
        write_new(meta, collect(path, session_id=sid))
        destination = tmp_path / (sid + "-jobs")
        dispatch(tasks, meta, destination)
        identities.append(load(destination / "jobs.json")["jobs"][0]["id"])
    assert identities[0] != identities[1]


def test_card_template_examples_validate_without_declaring_repairer(prepared):
    """Two synthetic input/deviation chains; a third target stays explicitly unresolved."""
    import re
    import yaml
    from migloop.inquiry.store import Store, Source
    from tests.test_inquiry_core import record, use, result, ts

    root = prepared["root"]
    generation = [record(1, use("r", "Read", file_path="/app/spec.md")),
                  record(2, result("r", "Use good for both targets.")),
                  record(3, use("a", file_path="/app/src/Page.ets", content="bad")), record(4, result("a")),
                  record(5, use("b", file_path="/app/src/Other.ets", content="bad")), record(6, result("b"))]
    repairs = [record(8, use("fix-a", "Edit", file_path="/app/src/Page.ets", old_string="bad", new_string="good")),
               record(9, result("fix-a")),
               record(10, use("fix-b", "Edit", file_path="/app/src/Other.ets", old_string="bad", new_string="good")),
               record(11, result("fix-b"))]
    sources = []
    for name, rows in [("agent", generation), ("repairer", repairs)]:
        path = prepared["pool"] / (name + ".jsonl")
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        sources.append(Source(str(path), path.name, name, "/app"))
    db = root / "examples.sqlite"
    Store.build(db, sources).close()
    task = load(prepared["tasks"])
    task["scope"].update(generation_end=ts(7), observation_end=ts(15))
    task["issues"][0]["changes"][0]["files"] += ["src/Other.ets", "src/Uninvestigated.ets"]
    write_new(root / "example-tasks.json", task)
    write_new(root / "example-meta.json", collect(prepared["pool"], root / "server.json"))
    dispatch(root / "example-tasks.json", root / "example-meta.json", root / "example-jobs")
    job = load(root / "example-jobs/jobs.json")["jobs"][0]["job"]
    reference = SCRIPTS.parents[1] / "migloop-build-cards/SKILL.md"
    template = yaml.safe_load(re.search(r"```yaml\n(.*?)\n```", reference.read_text(encoding="utf-8"), re.S)[1])
    draft = copy.deepcopy(template)
    draft["graphs"] = []
    for filename, end in [("Page.ets", 4), ("Other.ets", 6)]:
        graph = copy.deepcopy(template["graphs"][0])
        graph["target"] = {"key": "/app/src/" + filename, "since": ts(7), "at": ts(15)}
        graph["nodes"][0].update(key="/app/spec.md", at=ts(2), reason="Synthetic received good input")
        graph["nodes"][1].update(key="agent", at=ts(end), reason="Synthetic wrong output despite good input")
        draft["graphs"].append(graph)
    draft["unresolved_targets"] = [{"key": "src/Uninvestigated.ets", "reason": "Not investigated in these examples"}]
    write_new(root / "example-draft.json", draft)
    packed = pack(job, root / "example-draft.json", root / "examples.json", db)
    assert packed["validation"]["unresolved_targets"] == ["/app/src/Uninvestigated.ets"]
    assert len(packed["validation"]["graph_checks"]) == 2
    for checked in packed["validation"]["graph_checks"]:
        receipt = checked["receipt"]
        assert receipt["mechanical_status"] == "valid"
        assert receipt["delivery"]["status"] == "ready_for_review"
        assert all(n["key"] != "repairer" for n in receipt["document"]["findings"][0]["nodes"])
        assert {e["relation"] for e in receipt["edges"]} == {"read", "write"}


def test_card_preserves_stage_and_description_without_changing_graph(prepared):
    draft = copy.deepcopy(prepared["draft"])
    draft.update(when="界面实现阶段，确定图片约束时", description="源图片依赖adjustViewBounds和固有比例")
    path, out = prepared["root"] / "context-draft.json", prepared["root"] / "context-card.json"
    write_new(path, draft)
    pack(prepared["job"], path, out)
    card = load(out)
    assert card["draft"] == draft
    assert card["id"] == prepared["card"]["id"]
    assert card["revision"] != prepared["card"]["revision"]
    assert load(out.with_suffix(".views") / "target-1.json") == draft["graphs"][0]
    memory = memory_with(prepared)
    memory.ingest([out], memory.current()["revision"])
    assert memory.case(card["id"])["draft"]["description"] == draft["description"]
    assert memory.current()["lessons"]["lesson-text"]["status"] == "needs_review"


@pytest.mark.parametrize("description", [None, "", "  ", [], {}])
def test_invalid_card_description_fails_before_writing(prepared, description):
    draft = {**prepared["draft"], "description": description}
    path, out = prepared["root"] / "invalid-context.json", prepared["root"] / "invalid-context-card.json"
    write_new(path, draft)
    with pytest.raises(ValueError, match="draft.description"):
        pack(prepared["job"], path, out)
    assert not out.exists()


def test_description_is_searchable_and_previewed_without_evidence(prepared):
    card = prepared["card"]
    lessons = [make_lesson(card, "spec-lesson", title="Image constraints", when="spec extraction",
                          description="Source uses adjustViewBounds intrinsic ratio"),
               make_lesson(card, "ui-lesson", title="Image constraints", when="interface implementation",
                          description="Source uses adjustViewBounds intrinsic ratio")]
    memory = memory_with(prepared, lessons)
    matched = search(memory, "adjustViewBounds")
    assert {x["id"] for x in matched["items"]} == {"spec-lesson", "ui-lesson"}
    # Prefer matching stage/action, without excluding the other contextual match.
    routed = search(memory, "spec extraction adjustViewBounds")
    assert routed["items"][0]["id"] == "spec-lesson" and len(routed["items"]) == 2
    for value in routed["items"] + browse(memory, "ui/text")["items"]:
        assert value["description"] == lessons[0]["description"]
        assert not {"why", "how", "check", "evidence", "graphs", "provenance"} & value.keys()
    full = read(memory, ["spec-lesson"])["lessons"][0]
    assert full["description"] == lessons[0]["description"] and "how" in full and "evidence" in full


def test_legacy_description_remains_absent_in_storage_and_snapshots(prepared):
    memory = memory_with(prepared)
    original = memory.current()
    old_case = memory.case(prepared["card"]["id"])
    assert "description" not in old_case["draft"]
    assert search(memory, "styled")["total"] == 0  # Card text is not automatically injected into lessons.
    assert search(memory, "text")["items"][0]["description"] == ""
    assert browse(memory, "ui/text")["items"][0]["description"] == ""
    assert "description" not in read(memory, ["lesson-text"])["lessons"][0]
    assert memory.current() == original and memory.case(old_case["id"]) == old_case


@pytest.mark.parametrize("description", [None, "", "  ", [], {}])
def test_invalid_lesson_description_does_not_publish(prepared, description):
    memory = memory_with(prepared)
    old = memory.current()["revision"]
    with pytest.raises(ValueError, match="lesson.description"):
        memory.apply({"base_revision": old, "upsert": [make_lesson(prepared["card"], description=description)]})
    assert memory.current()["revision"] == old


def test_stage_description_update_keeps_id_and_invalidates_dependents(prepared):
    card = prepared["card"]
    memory = memory_with(prepared, [make_lesson(card), make_lesson(card, "child", requires=["lesson-text"])])
    old = memory.current()["revision"]
    memory.apply({"base_revision": old, "upsert": [make_lesson(card, when="规格提取阶段，描述源图片时",
                  description="源布局依赖固有图片比例")]})
    assert memory.current()["lessons"]["lesson-text"]["version"] == 2
    assert memory.current()["lessons"]["child"]["status"] == "needs_review"
    assert memory.current(old)["lessons"]["child"]["status"] == "active"
    assert search(memory, "固有图片比例")["items"][0]["id"] == "lesson-text"
    assert "description" not in memory.current(old)["lessons"]["lesson-text"]
