import json

from migloop.inquiry import report
from tests.test_inquiry_core import build, record, result, ts, use


def test_plain_message_projection_preserves_real_line_windows(tmp_path):
    engine = build(
        tmp_path,
        [
            {
                "timestamp": ts(1),
                "type": "user",
                "message": {"content": "first\nrequirement\nlast"},
            }
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    whole = engine.query({"op": "open", "ref": ref, "at": ts(2)})
    assert whole["text"] == "first\nrequirement\nlast"
    window = engine.query(
        {"op": "open", "ref": ref, "at": ts(2), "terms": ["requirement"], "context": 0}
    )
    assert window["content_line_ranges"] == [[2, 2]] and "first" not in window["text"]
    assert (
        '"message"'
        in engine.query({"op": "open", "ref": ref, "at": ts(2), "pointer": ""})["text"]
    )
    engine.store.close()


def test_cited_native_links_are_materialized_without_rewriting_claims(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Read", file_path="/proj/spec.md")),
            record(2, result("r", "spec input")),
            record(3, use("w", file_path="/proj/A.ets", content="new")),
            record(4, result("w")),
        ],
    )

    def ref(line):
        return engine.store.locate("a.jsonl", line)

    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(5)},
        "findings": [
            {
                "id": "A",
                "title": "model title",
                "reason": "model finding unchanged",
                "changes": [ref(3)],
                "nodes": [
                    {
                        "id": "actor",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(4),
                        "role": "origin",
                        "reason": "model cause unchanged",
                        "evidence": [ref(2), ref(3)],
                    }
                ],
            }
        ],
    }
    graph = report.check(engine, json.dumps(doc))
    assert graph["document"] == doc
    assert len(graph["edges"]) == 2 and not graph["issues"]
    assert graph["nodes"][0]["reason"] == "model cause unchanged"
    assert all(n["role"] == "context" for n in graph["nodes"] if n["generated_context"])
    assert all(
        e["source"] == "native_evidence" and not e["semantic_verified"]
        for e in graph["edges"]
    )
    assert all(e["to"] == "A:actor" for e in graph["edges"] if e["relation"] == "read")
    assert all(
        e["from"] == "A:actor" for e in graph["edges"] if e["relation"] == "write"
    )
    engine.store.close()


def test_independent_spec_lookup_does_not_invent_delivery_to_writer(tmp_path):
    engine = build(
        tmp_path,
        [
            record(3, use("w", file_path="/proj/A.ets", content="new")),
            record(4, result("w")),
        ],
        second=[
            record(1, use("s", file_path="/proj/spec.md", content="right input")),
            record(2, result("s")),
        ],
    )
    a = engine.store.locate("a.jsonl", 1)
    b = engine.store.locate("b.jsonl", 1)
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(5)},
        "findings": [
            {
                "id": "A",
                "title": "independent comparison",
                "reason": "unknown delivery",
                "changes": [a],
                "nodes": [
                    {
                        "id": "writer",
                        "kind": "agent",
                        "key": "a",
                        "at": ts(5),
                        "role": "unknown",
                        "reason": "not proven",
                        "evidence": [a, b],
                    }
                ],
            }
        ],
    }
    graph = report.check(engine, json.dumps(doc))
    assert len(graph["edges"]) == 2
    assert all(edge["relation"] == "write" for edge in graph["edges"])
    assert not graph["semantic_verified"]
    engine.store.close()


def test_opaque_command_citation_never_materializes_a_write(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("s", "Bash", command="python patch.py A.ets")),
            record(2, result("s", "done")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(3)},
        "findings": [
            {
                "id": "A",
                "title": "possible change",
                "reason": "opaque script",
                "changes": [ref],
                "nodes": [],
            }
        ],
    }
    graph = report.check(engine, json.dumps(doc))
    assert graph["edges"] == [] and graph["nodes"] == []
    engine.store.close()


def test_completed_write_crossing_start_boundary_is_still_unattributed(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="changed")),
            record(4, result("w")),
        ],
    )
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "since": ts(2), "at": ts(5)},
        "findings": [],
    }
    graph = report.check(engine, json.dumps(doc))
    assert len(graph["coverage"]["unattributed_native_writes"]) == 1
    assert graph["mechanical_status"] == "needs_revision"
    engine.store.close()


def test_unknown_candidate_accounting_is_not_native_write_certification(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("x", "Bash", command="python mystery.py A.ets")),
            record(2, result("x", "unknown effect")),
        ],
    )
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(3)},
        "findings": [],
    }
    graph = report.check(engine, json.dumps(doc))
    assert graph["mechanical_status"] == "valid"
    assert len(graph["coverage"]["unassessed"]) == 1
    assert not graph["coverage"]["unattributed_native_writes"]
    assert not graph["semantic_verified"] and not graph["coverage"]["complete"]
    engine.store.close()


def test_inline_fake_citations_do_not_escape_report_validation(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="new")),
            record(2, result("w")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(3)},
        "findings": [
            {
                "id": "A",
                "title": "example",
                "reason": "claimed source e-0000000000000000",
                "changes": [ref],
                "nodes": [],
            }
        ],
    }
    graph = report.check(engine, json.dumps(doc))
    assert graph["mechanical_status"] == "needs_revision"
    assert any(issue.get("ref") == "e-0000000000000000" for issue in graph["issues"])
    engine.store.close()


def test_native_change_expansion_keeps_full_old_new_and_does_not_parse_shell(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "e",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="old\n" * 2500,
                    new_string="new\n" * 2500,
                ),
            ),
            record(2, result("e")),
            record(3, use("s", "Bash", command="python patch.py A.ets")),
            record(4, result("s", "done")),
        ],
    )
    query = {"op": "file", "key": "A.ets", "at": ts(5), "view": "changes"}
    data = engine.query(query)
    assert data["total"] == 1 and data["next"] is None
    assert data["rows"][0]["payloads"][0]["body"]["new_string"] == "new\n" * 2500
    rendered = engine.render(1, {"query": query, "ok": True, "data": data})
    assert "OLD_STRING\nold\nold" in rendered and "NEW_STRING\nnew\nnew" in rendered
    assert (
        engine.query({"op": "file", "key": "A.ets", "at": ts(5), "view": "calls"})[
            "total"
        ]
        == 2
    )
    engine.store.close()


def test_unknown_disposition_cannot_hide_unattributed_native_change(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use(
                    "e",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="old",
                    new_string="new",
                ),
            ),
            record(2, result("e")),
        ],
    )
    ref = engine.store.locate("a.jsonl", 1)
    doc = {
        "schema": "inquiry/1",
        "target": {"file": "A.ets", "at": ts(3)},
        "findings": [],
        "reviewed": [{"ref": ref, "effect": "unknown", "reason": "not opened yet"}],
    }
    graph = report.check(engine, json.dumps(doc))
    assert graph["mechanical_status"] == "needs_revision"
    assert len(graph["coverage"]["unattributed_native_writes"]) == 1
    engine.store.close()
