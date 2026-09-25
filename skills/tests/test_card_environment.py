"""Recorded environment enrichment; never infer historical SDKs from today's checkout."""
import copy
import json
from pathlib import Path

import pytest

from test_memory_bundle import prepared, make_lesson, memory_with
from memorylib.common import load, write_new
from memorylib.environment import Observer, enrich_cards, for_card
from memorylib.provenance import collect
from memorylib.registry import Memory, validate_case
from memorylib.cases import dispatch, pack


def row(second, role, content):
    return {"type": role, "timestamp": f"2026-01-01T00:00:{second:02d}Z", "cwd": "/app",
            "sessionId": "session-1", "message": {"content": content}}


def call(second, name, args, identity="c"):
    return row(second, "assistant", [{"type": "tool_use", "id": identity, "name": name, "input": args}])


def result(second, text, identity="c", **kwargs):
    return row(second, "user", [{"type": "tool_result", "tool_use_id": identity, "content": text, **kwargs}])


def scan(rows):
    observer = Observer()
    for index, value in enumerate(rows, 1):
        observer.observe(value, f"agent.jsonl:L{index}")
    return list(observer.observations.values())


def test_read_and_successful_write_capture_only_literal_config_fields():
    observations = scan([
        call(1, "Read", {"file_path": "/app/build-profile.json5"}),
        result(2, '1→ "targetSdkVersion": "6.1.0(23)",\n2→ "password": "never-store-me"'),
        call(3, "Write", {"file_path": "/app/build-profile.json5", "content": '"compatibleSdkVersion": "6.0.0(20)",'}),
        result(4, "ok")])
    assert [(x["name"], x["value"]) for x in observations] == [
        ("harmonyos.target_sdk", "6.1.0(23)"), ("harmonyos.compatible_sdk", "6.0.0(20)")]
    assert observations[0]["ref"] == "agent.jsonl:L2" and observations[1]["at"].endswith("04Z")
    assert "never-store-me" not in json.dumps(observations)


@pytest.mark.parametrize("rows", [
    [row(1, "assistant", [{"type": "text", "text": 'targetSdkVersion: "23"'}])],
    [result(2, 'targetSdkVersion: "23"')],
    [call(1, "Read", {"file_path": "/app/SKILL.md"}), result(2, 'targetSdkVersion: "23"')],
    [call(1, "Read", {"file_path": "/app/build-profile.json5"}), result(2, 'targetSdkVersion: "23"', is_error=True)],
    [call(1, "Read", {"file_path": "/app/build-profile.json5"}), result(2, '// targetSdkVersion: "23"\nAPI 22 is available')],
    [call(1, "Bash", {"command": 'echo build-profile.json5'}), result(2, 'targetSdkVersion: "23"')],
    [call(1, "Write", {"file_path": "/app/build-profile.json5", "content": 'targetSdkVersion: "23"'})],
])
def test_narrative_docs_failed_calls_and_unacknowledged_writes_are_not_environment(rows):
    assert scan(rows) == []


def test_catalog_bom_and_variable_references_are_not_resolved_library_versions():
    observations = scan([call(1, "Bash", {"command": "cat gradle/libs.versions.toml app/build.gradle.kts"}),
                         result(2, '[versions]\ncompileSdk = "35"\nminSdk = "23"\nandroidxComposeBom = "2026.05.00"\nkotlin = "2.1.0"\ntargetSdk = libs.versions.targetSdk.get()')])
    assert {x["name"] for x in observations} == {"android.compile_sdk", "android.min_sdk", "libraries.compose_bom", "toolchain.kotlin"}
    assert all(x["basis"] == "configuration" for x in observations)


def test_codex_pairs_calls_and_ignores_nonzero_exit():
    observer = Observer()
    for index, (kind, payload) in enumerate([
        ("function_call", {"name": "functions.exec_command", "call_id": "a", "arguments": json.dumps({"cmd": "cat build-profile.json5"})}),
        ("function_call_output", {"call_id": "a", "output": json.dumps({"exit_code": 0, "output": '"targetSdkVersion": "23",'})}),
        ("function_call", {"name": "exec_command", "call_id": "b", "arguments": json.dumps({"cmd": "cat build-profile.json5"})}),
        ("function_call_output", {"call_id": "b", "output": json.dumps({"exit_code": 1, "output": '"targetSdkVersion": "99",'})}),
    ], 1):
        observer.observe({"type": "response_item", "timestamp": f"2026-01-01T00:00:0{index}Z", "payload": {"type": kind, **payload}}, f"rollout.jsonl:L{index}")
    assert [x["value"] for x in observer.observations.values()] == ["23"]


def test_card_scope_keeps_distinct_versions_and_marks_generation_vs_repair():
    observations = scan([call(1, "Read", {"file_path": "build-profile.json5"}), result(2, '"targetSdkVersion": "20",'),
                         call(3, "Read", {"file_path": "build-profile.json5"}), result(4, '"targetSdkVersion": "23",'),
                         call(5, "Read", {"file_path": "build-profile.json5"}), result(6, '"targetSdkVersion": "99",')])
    metadata = {"sources": [{"source": "agent.jsonl", "sha256": "a" * 64, "environment": observations}]}
    env = for_card(metadata, {"generation_end": "2026-01-01T00:00:03Z", "observation_end": "2026-01-01T00:00:05Z"})
    assert [(x["value"], x["phase"]) for x in env["facts"]] == [("20", "generation"), ("23", "repair")]
    assert "harmonyos.compile_sdk" in env["unknown"]  # target does not imply compile or device SDK.
    assert "harmonyos.target_sdk" not in env["unknown"]
    assert env["sources"] == {"agent.jsonl": "a" * 64}


def test_metadata_pack_automatically_attaches_environment_without_draft_fields(prepared):
    path = prepared["pool"] / "config.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in [call(1, "Read", {"file_path": "build-profile.json5"}),
                                                        result(2, '"targetSdkVersion": "23",')]), encoding="utf-8")
    metadata_path = prepared["root"] / "new-metadata.json"
    write_new(metadata_path, collect(prepared["pool"]))
    destination = prepared["root"] / "new-jobs"
    dispatch(prepared["tasks"], metadata_path, destination)
    job = load(destination / "jobs.json")["jobs"][0]["job"]
    output = prepared["root"] / "new-card.json"
    pack(job, prepared["root"] / "draft.json", output)
    card = load(output)
    assert card["draft"] == prepared["draft"]
    assert card["environment"]["facts"][0]["value"] == "23"
    validate_case(card)


def test_enrichment_preserves_original_and_does_not_bypass_existing_review_gate(prepared):
    memory = memory_with(prepared)
    old = memory.current()
    original = prepared["card_path"].read_bytes()
    out = prepared["root"] / "enriched"
    enriched = enrich_cards([prepared["card_path"]], prepared["meta"], out)
    new_card = load(enriched["cards"][0]["path"])
    assert prepared["card_path"].read_bytes() == original
    assert new_card["draft"] == prepared["card"]["draft"]
    assert new_card["claims"] == prepared["card"]["claims"]
    assert new_card["validation"] == prepared["card"]["validation"]
    assert new_card["environment"]["unknown"]
    # The fresh card already had identical empty environment metadata: re-enrichment is idempotent.
    assert new_card["revision"] == prepared["card"]["revision"]
    legacy = copy.deepcopy(prepared["card"])
    legacy.pop("environment")
    from memorylib.registry import revision_of
    legacy["revision"] = revision_of(legacy)
    legacy_path = prepared["root"] / "legacy.json"
    write_new(legacy_path, legacy)
    memory.ingest([legacy_path], old["revision"])
    # Restore the unchanged lesson through normal explicit maintenance, then enrich its source.
    memory.apply({"base_revision": memory.current()["revision"], "upsert": [make_lesson(legacy)]})
    enriched = enrich_cards([legacy_path], prepared["meta"], prepared["root"] / "legacy-enriched")
    memory.ingest([enriched["cards"][0]["path"]], memory.current()["revision"])
    assert memory.current()["lessons"]["lesson-text"]["status"] == "needs_review"


def test_enrichment_rejects_other_pool_or_changed_history_before_output(prepared):
    metadata = load(prepared["meta"])
    metadata["materials"] = str(prepared["root"] / "not-this-pool")
    path = prepared["root"] / "other.json"
    write_new(path, metadata)
    out = prepared["root"] / "no-output"
    with pytest.raises((ValueError, FileNotFoundError)):
        enrich_cards([prepared["card_path"]], path, out)
    assert not out.exists()
    with (prepared["pool"] / "agent.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n{}")
    with pytest.raises(ValueError, match="Transcript changed"):
        enrich_cards([prepared["card_path"]], prepared["meta"], out)
    assert not out.exists()
