"""Codex 原始 rollout 按 call_id 对齐,不能用 stdout item.id 伪装原始证据。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from migloop import atoms, probe
from tests.test_atoms import _write_jsonl
from tests.test_trajectory import _block, _pool, _run_dir


def _call(call_id: str | None, tool: str, arguments: Any) -> dict[str, Any]:
    return {"type": "response_item", "payload": {"type": "function_call", "call_id": call_id,
            "name": "mcp__migloop__" + tool,
            "arguments": json.dumps(arguments) if isinstance(arguments, dict) else arguments}}


def _result(call_id: str | None, text: Any, failed: bool = False) -> dict[str, Any]:
    return {"type": "response_item", "payload": {"type": "function_call_output", "call_id": call_id,
            "output": json.dumps({"content": [{"type": "text", "text": text}], "isError": failed})}}


def _run(tmp_path: Path, records: list[dict[str, Any]], report: str = "") -> str:
    run_dir = _run_dir(tmp_path, [], report)
    _write_jsonl(str(Path(run_dir) / "transcript.jsonl"), [
        {"type": "session_meta", "payload": {"id": "test-thread", "cwd": "/proj"}}, *records])
    return run_dir


def test_historical_query_identity_does_not_rebind_same_numbered_version(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    report = "```json\n" + json.dumps({"schema": "migloop-verdict/1", "ledger": atoms.ledger_identity(led),
        "defects": [{"id": "A", "title": "claim", "nodes": [{"node": "file:/proj/entry/A.ets@v2",
        "role": "带病传递", "reason": "model typed current identity despite old runtime"}]}]}) + "\n```"
    run_dir = _run(tmp_path, [
        _call("s", "sessions", {"file": "A.ets"}), _result("s", "账本身份: old-ledger\n# chains"),
        _call("f", "file", {"path": "A.ets", "v": 2, "via": "sessions"}), _result("f", "# entry/A.ets@v2"),
    ], report)
    result = probe.probe_payload(led, run_dir)
    assert result["trace_identity"]["bound"] is False
    assert result["structured"]["identity"]["bound"] is False
    assert result["roles"] == {} and result["trajectory"]["nodes"] == []
    assert result["trajectory"]["visits"][0]["status"] == "unverified"
    assert "账本身份" in result["trajectory"]["visits"][0]["note"]


def test_sessions_file_argument_is_a_real_chain_anchor(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [_call("s", "sessions", {"file": "A.ets"}),
                             _result("s", "账本身份: " + atoms.ledger_identity(led) + "\n# chains")])
    result = probe.probe_payload(led, run_dir)
    assert result["root"] == "/proj/entry/A.ets" and result["trace_identity"]["bound"] is True


def test_legacy_without_via_cannot_draw_current_ledger_after_identity_conflict(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [
        _call("s", "sessions", {"file": "A.ets"}), _result("s", "账本身份: old-ledger\n# chains"),
        _call("f", "file", {"path": "A.ets", "v": 2}), _result("f", "# entry/A.ets@v2"),
    ])
    result = probe.probe_payload(led, run_dir)
    assert result["structured"] is None and result["trace_identity"]["bound"] is False
    assert result["trajectory"]["nodes"] == [] and result["trajectory"]["edges"] == []
    assert result["trajectory"]["visits"][0]["status"] == "unverified"


def test_rollout_pairs_native_ids_and_preserves_physical_positions(tmp_path: Path) -> None:
    first = _call("call-a", "file", {"path": "A.ets", "v": 2, "via": "sessions"})
    run_dir = _run(tmp_path, [first, _call("call-b", "agent", {"id": "fixer", "v": 1}),
                             _result("call-b", "# agent-f v1"), first,
                             _result("call-b", "replayed result must not replace first")])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and len(calls) == 2
    assert calls[0]["id"] == calls[0]["call_id"] == "call-a"
    assert calls[0]["use_line"] == 2 and not calls[0]["has_result"]
    assert calls[1]["input"] == {"id": "fixer", "v": 1}
    assert calls[1]["text"] == "# agent-f v1" and calls[1]["has_result"]
    assert (calls[1]["use_line"], calls[1]["result_line"]) == (3, 4)
    assert calls[1]["use_event"] < calls[1]["result_event"]
    assert {k: v for k, v in calls[1]["provenance"].items() if k != "tool_origin"} == {
        "format": "codex_rollout", "path": "transcript.jsonl", "pairing": "call_id", "complete_pair": True}


def test_missing_id_prior_output_and_invalid_arguments_never_establish_success(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, [
        _result("old", "# entry/A.ets@v2"),
        _call("old", "file", {"path": "A.ets", "v": 2}),
        _call(None, "file", {"path": "A.ets", "v": 2}), _result(None, "# entry/A.ets@v2"),
        _call("bad", "file", "[not-json"), _result("bad", "# entry/A.ets@v2"),
        _call("list", "file", "[]"), _result("list", "# entry/A.ets@v2"),
    ])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and len(calls) == 4
    assert not calls[0]["has_result"] and not calls[1]["has_result"]
    assert calls[1]["call_id"] is None
    assert all(c["has_result"] and c["is_error"] and c["parse_error"] for c in calls[2:])


def test_rollout_revisits_self_loop_errors_and_pending_keep_the_route_contract(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    a = {"path": "A.ets", "v": 2, "via": "sessions"}
    revisit = {"path": "A.ets", "v": 2, "via": "file:A.ets@v2", "content": True, "start": 3, "n": 5}
    run_dir = _run(tmp_path, [
        _call("first", "file", a), _result("first", '{"result": "# entry/A.ets@v2"}'),
        _call("self", "file", revisit), _result("self", "# entry/A.ets@v2"),
        _call("error", "agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}),
        _result("error", "# agent-f v1", failed=True),
        _call("pending", "file", a),
    ])
    payload = probe.probe_payload(led, run_dir)
    tree = payload["trajectory"]
    assert [v["status"] for v in tree["visits"]] == ["opened", "opened", "error", "pending"]
    assert len(tree["nodes"]) == 1 and tree["nodes"][0]["opened"] == [1, 2]
    assert tree["transitions"][0]["from"] == tree["transitions"][0]["to"]
    assert tree["visits"][1]["scope"] == "正文 v2 3-7行"
    assert tree["visits"][1]["call_id"] == "self"
    assert tree["visits"][1]["provenance"]["format"] == "codex_rollout"
    assert not payload["steps"][-1]["ok"] and not payload["steps"][-1]["result_present"]


def test_rollout_parallel_calls_require_source_result_before_target_call(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [
        _call("first", "file", {"path": "A.ets", "v": 2, "via": "sessions"}),
        _call("second", "agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}),
        _result("second", "# agent-f v1"), _result("first", "# entry/A.ets@v2"),
    ])
    tree = probe.probe_payload(led, run_dir)["trajectory"]
    assert len(tree["visits"]) == 2 and tree["transitions"] == []
    assert tree["visits"][1]["note"] == "via 指向调用前尚未成功返回的节点"


def test_codex_response_text_is_loaded_as_the_final_report(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    report = _block(led)
    run_dir = _run(tmp_path, [], report)
    with open(Path(run_dir) / "result.json", "w", encoding="utf-8") as stream:
        json.dump({"schema": "migloop-codex-result/1", "response_text": report}, stream)
    payload = probe.probe_payload(led, run_dir)
    assert payload["report"] == report
    assert payload["structured"]["identity"]["bound"]
    assert payload["roles"]["agent-c"][0]["role"] == "进入·错"


def test_exec_events_fallback_keeps_item_provenance_without_inventing_call_id(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [])
    Path(run_dir, "transcript.jsonl").unlink()
    item = {"type": "mcp_tool_call", "id": "item_1", "server": "migloop", "tool": "file",
            "arguments": {"path": "A.ets", "v": 2, "via": "sessions"}}
    _write_jsonl(str(Path(run_dir) / "events.jsonl"), [
        {"type": "thread.started", "thread_id": "test-thread"},
        {"type": "item.started", "item": item},
        {"type": "item.completed", "item": {**item, "status": "completed",
            "result": {"content": [{"type": "text", "text": "# entry/A.ets@v2"}], "isError": False}}},
        {"type": "item.started", "item": {**item, "id": "item_pending"}},
    ])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and len(calls) == 2
    assert calls[0]["item_id"] == "item_1" and calls[0]["call_id"] is None and calls[0]["id"] is None
    assert (calls[0]["use_line"], calls[0]["result_line"]) == (2, 3)
    assert calls[0]["has_result"] and not calls[1]["has_result"]
    assert {k: v for k, v in calls[0]["provenance"].items() if k != "tool_origin"} == {
        "format": "codex_exec_events", "path": "events.jsonl", "pairing": "item_id", "degraded": True,
        "complete_pair": True}
    payload = probe.probe_payload(led, run_dir)
    assert payload["steps"][0]["result_ref"] is None and payload["steps"][0]["item_id"] == "item_1"
    assert payload["trajectory"]["trace_source"] == "codex_exec_events"
    assert payload["trajectory"]["source_path"] == "events.jsonl"
    assert len(payload["trajectory"]["nodes"]) == 1
    assert [v["status"] for v in payload["trajectory"]["visits"]] == ["opened", "pending"]


def test_exec_events_preserve_failure_and_do_not_normalize_foreign_server_tools(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, [])
    Path(run_dir, "transcript.jsonl").unlink()
    _write_jsonl(str(Path(run_dir) / "events.jsonl"), [
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "id": "failed", "server": "migloop",
            "tool": "file", "arguments": {}, "status": "failed", "error": {"message": "transport failed"}}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "id": "other", "server": "elsewhere",
            "tool": "file", "arguments": {}, "result": {"content": [{"type": "text", "text": "ok"}]}}},
    ])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and calls[0]["has_result"] and calls[0]["is_error"]
    assert calls[0]["text"] == "transport failed" and calls[0]["use_line"] is None
    assert calls[1]["tool"] == "mcp__elsewhere__file"


def test_present_rollout_is_authoritative_even_when_it_has_no_tool_calls(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, [])
    _write_jsonl(str(Path(run_dir) / "events.jsonl"), [
        {"type": "item.started", "item": {"type": "mcp_tool_call", "id": "item_1", "server": "migloop",
                                          "tool": "file", "arguments": {"path": "A.ets", "v": 1}}}])
    assert probe._transcript_calls(run_dir) == []


def _runtime_item(item_id: str, tool: str, args: dict[str, Any], text: str,
                  start: int | None, end: int | None) -> dict[str, Any]:
    return {"type": "event_msg", "payload": {"type": "item_completed", "started_at_ms": start,
            "completed_at_ms": end, "item": {"type": "McpToolCall", "id": item_id, "server": "migloop",
            "tool": tool, "arguments": args, "status": "completed",
            "result": {"content": [{"type": "text", "text": text}], "isError": False}}}}


@pytest.mark.parametrize("case,verified", [("qualified", True), ("native", True), ("dual", True),
    ("unknown", False), ("other", False), ("namespace_conflict", False),
    ("server_conflict", False), ("tool_conflict", False), ("args_conflict", False)])
def test_mcp_origin_must_be_explicit_and_consistent(tmp_path: Path, case: str, verified: bool) -> None:
    from migloop import via
    led = _pool(tmp_path)
    args = {"q": "spec", "file": "/proj/spec/pages/A.md"}
    output = via.search_return(led, via.ViaState(), args, "search hit", [
        {"kind": "file", "key": args["file"], "v": 1}])
    call = _call("s", "search", args)
    if case != "qualified":
        call["payload"]["name"] = "search"
    if case != "unknown":
        call["payload"]["namespace"] = "mcp__other" if case == "other" else "mcp__migloop"
    if case == "namespace_conflict":
        call["payload"].update(name="mcp__other__search", namespace="mcp__migloop")
    rows = [call, _result("s", output)]
    if case in ("dual", "other", "server_conflict", "tool_conflict", "args_conflict"):
        native = _runtime_item("s", "search", args, output, 100, 200)
        if case in ("other", "server_conflict"):
            native["payload"]["item"]["server"] = "other"
        if case == "tool_conflict":
            native["payload"]["item"]["tool"] = "guide"
        if case == "args_conflict":
            native["payload"]["item"]["arguments"] = {**args, "q": "different"}
        rows.insert(1, native)
    run = _run(tmp_path, rows)
    calls = probe._transcript_calls(run)
    assert len(calls) == 1
    assert calls[0]["provenance"]["tool_origin"]["verified"] is verified
    identity = via.trace_identity(led, calls, {})
    assert (identity["bound"] is True) is verified
    if "conflict" in case:
        assert calls[0]["provenance"]["tool_origin"]["errors"]
        assert calls[0]["provenance"]["complete_pair"] is False


@pytest.mark.parametrize("via_arg", ["sessions", None])
def test_unqualified_native_file_is_not_an_authenticated_open(tmp_path: Path, via_arg: str | None) -> None:
    call = _call("f", "file", {"path": "A.ets", "v": 2, "via": "sessions"})
    if via_arg is None:
        call["payload"]["arguments"] = json.dumps({"path": "A.ets", "v": 2})
    call["payload"]["name"] = "file"
    run = _run(tmp_path, [call, _result("f", "# entry/A.ets@v2")])
    tree = probe.probe_payload(_pool(tmp_path), run)["trajectory"]
    assert tree["nodes"] == [] and tree["visits"][0]["status"] == "unverified"


@pytest.mark.parametrize("representation", ["direct", "runtime", "stdout"])
def test_same_id_origin_conflict_on_replay_cannot_open(tmp_path: Path, representation: str) -> None:
    args = {"path": "A.ets", "v": 2, "via": "sessions"}
    if representation == "direct":
        first = _call("same", "file", args)
        replay = _call("same", "file", {**args, "v": 1})
        rows = [first, replay, _result("same", "# entry/A.ets@v2")]
    else:
        first = _runtime_item("same", "file", args, "# entry/A.ets@v2", 100, 200)
        replay = _runtime_item("same", "file", args, "# entry/A.ets@v2", 100, 200)
        replay["payload"]["item"]["server"] = "other"
        rows = [first, replay]
    run = _run(tmp_path, rows)
    if representation == "stdout":
        Path(run, "transcript.jsonl").unlink()
        _write_jsonl(str(Path(run, "events.jsonl")), [
            {"type": "item.started", "item": {**first["payload"]["item"], "type": "mcp_tool_call"}},
            {"type": "item.completed", "item": {**replay["payload"]["item"], "type": "mcp_tool_call"}}])
    calls = probe._transcript_calls(run)
    assert len(calls) == 1 and calls[0]["provenance"]["tool_origin"]["errors"]
    tree = probe.probe_payload(_pool(tmp_path), run)["trajectory"]
    assert tree["nodes"] == [] and tree["visits"][0]["status"] == "unverified"


@pytest.mark.parametrize("namespace", ["mcp__other", "functions"])
def test_other_namespace_cannot_supply_current_file_coordinates(tmp_path: Path, namespace: str) -> None:
    args = {"path": "A.ets", "v": 2, "via": "sessions"}
    call = _call("same", "file", args)
    call["payload"].update(name="file", namespace=namespace)
    runtime = _runtime_item("same", "file", args, "# entry/A.ets@v2", 100, 200)
    runtime["payload"]["item"]["server"] = "other"
    run = _run(tmp_path, [call, runtime, _result("same", "# entry/A.ets@v2")])
    result = probe.probe_payload(_pool(tmp_path), run)
    assert result["trajectory"]["nodes"] == []
    assert all(step["node"] is None for step in result["steps"])


@pytest.mark.parametrize("dual", [False, True])
def test_gpt55_native_namespace_file_and_agent_are_authenticated_visits(tmp_path: Path, dual: bool) -> None:
    led = _pool(tmp_path)
    rows = []
    items = [("s", "sessions", {}, "账本身份: " + atoms.ledger_identity(led) + "\n# chains"),
             ("f", "file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2"),
             ("a", "agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}, "# agent-f v1")]
    for index, (cid, name, args, text) in enumerate(items):
        call = _call(cid, name, args)
        call["payload"].update(name=name, namespace="mcp__migloop")
        rows.append(call)
        if dual:
            rows.append(_runtime_item(cid, name, args, text, index * 300 + 100, index * 300 + 200))
        rows.append(_result(cid, text))
    payload = probe.probe_payload(led, _run(tmp_path, rows))
    assert payload["trace_identity"]["bound"] is True and len(payload["steps"]) == 3
    tree = payload["trajectory"]
    assert tree["root"] == "file:/proj/entry/A.ets@2"
    assert [v["status"] for v in tree["visits"]] == ["opened", "opened"]
    assert all(v["verified"] for v in tree["visits"]) and len(tree["transitions"]) == 1
    assert [v["call_id"] for v in tree["visits"]] == ["f", "a"]


def _native_formatted_result(call_id: str, body: str) -> dict[str, Any]:
    return {"type": "response_item", "payload": {"type": "function_call_output", "call_id": call_id,
        "output": [{"type": "input_text", "text": "Wall time: 0.0284 seconds\nOutput:"},
                   {"type": "input_text", "text": body}]}}


def test_observed_native_transport_blocks_preserve_session_search_and_opened_nodes(tmp_path: Path) -> None:
    from migloop import via
    led = _pool(tmp_path)
    search_args = {"q": "spec", "file": "/proj/spec/pages/A.md"}
    search_body = via.search_return(led, via.ViaState(), search_args, "real hit", [
        {"kind": "file", "key": search_args["file"], "v": 1}])
    handle = via.search_receipt(search_body, search_args)["hits"][0]["via"]
    items = [("s", "sessions", {}, "账本身份: " + atoms.ledger_identity(led) + "\n# chains"),
             ("q", "search", search_args, search_body),
             ("f", "file", {"path": search_args["file"], "v": 1, "via": handle}, "# spec/pages/A.md@v1"),
             ("a", "agent", {"id": "conv-a", "v": 1, "via": "file:spec/pages/A.md@v1"}, "# agent-c v1")]
    records = []
    for index, (cid, name, args, body) in enumerate(items):
        call = _call(cid, name, args)
        call["payload"].update(name=name, namespace="mcp__migloop")
        records.extend([call, _runtime_item(cid, name, args, body, index * 300 + 100, index * 300 + 200),
                        _native_formatted_result(cid, body)])
    run = _run(tmp_path, records)
    calls = probe._transcript_calls(run)
    assert [c["text"] for c in calls] == [row[3] for row in items]
    for index, call in enumerate(calls):
        norm = call["provenance"]["output_normalization"]
        assert norm["status"] == "verified" and norm["runtime_result_line"] == index * 3 + 3
        assert call["result_line"] == index * 3 + 4
        assert call["raw_text"] == "Wall time: 0.0284 seconds\nOutput:\n" + call["text"]
    payload = probe.probe_payload(led, run)
    assert payload["trace_identity"]["source"] == "sessions+search"
    assert [v["status"] for v in payload["trajectory"]["visits"]] == ["opened", "opened"]
    assert payload["trajectory"]["transitions"][0]["source"] == "search"


@pytest.mark.parametrize("case", ["raw_lookalike", "different_body", "other_id", "other_server", "no_runtime", "incomplete_runtime"])
def test_transport_lookalikes_and_unmatched_bodies_are_not_stripped(tmp_path: Path, case: str) -> None:
    body = "# entry/A.ets@v2"
    args = {"path": "A.ets", "v": 2, "via": "sessions"}
    call = _call("f", "file", args)
    call["payload"].update(name="file", namespace="mcp__migloop")
    formatted = _native_formatted_result("f", body)
    runtime = _runtime_item("f", "file", args, body, 100, 200)
    if case == "raw_lookalike":
        runtime["payload"]["item"]["result"]["content"][0]["text"] = "Wall time: 0.0284 seconds\nOutput:\n" + body
    elif case == "different_body":
        runtime["payload"]["item"]["result"]["content"][0]["text"] = "# entry/A.ets@v1"
    elif case == "other_id":
        runtime["payload"]["item"]["id"] = "different"
    elif case == "other_server":
        runtime["payload"]["item"]["server"] = "other"
    elif case == "incomplete_runtime":
        runtime["payload"]["started_at_ms"] = None
    records = [call] + ([] if case == "no_runtime" else [runtime]) + [formatted]
    run = _run(tmp_path, records)
    normalized = next(c for c in probe._transcript_calls(run) if c["call_id"] == "f")
    assert normalized["text"].startswith("Wall time:")
    assert normalized["provenance"]["output_normalization"]["status"] == "unverified"


def test_plain_text_transport_lookalike_is_not_reinterpreted(tmp_path: Path) -> None:
    args = {"path": "A.ets", "v": 2, "via": "sessions"}
    body = "Wall time: 0.0284 seconds\nOutput:\n# entry/A.ets@v2"
    run = _run(tmp_path, [_call("f", "file", args), _runtime_item("f", "file", args, body, 100, 200), _result("f", body)])
    call = probe._transcript_calls(run)[0]
    assert call["text"] == body and "output_normalization" not in call["provenance"]


def test_actual_c1_middle_truncation_shape_authenticates_header_not_full_body(tmp_path: Path) -> None:
    aid = "__main__:01a009fe"
    led = atoms.Ledger({}, {aid: atoms.AgentRec(aid, "01a009fe", actions=[
        atoms.Action("2026-01-01T00:00:00Z", i, "Write", "write", ver=i, at=i) for i in range(1, 253)])})
    prefix = "# agent 主会话·01a009fe  id=__main__:01a009fe  v252 / 共 252 版\n已展示读取: 版本就近"
    suffix = "eturn this.policy.agreementUrls.indexOf(url) >= 0\n可见末尾"
    omitted = "NOT_DELIVERED_BODY" * 200
    runtime_body = prefix + omitted + suffix
    delivered = prefix + "…998 tokens truncated…" + suffix
    args = {"id": aid, "v": 252, "since": 251, "via": "sessions", "seen": True}
    call = _call("c1", "agent", args)
    call["payload"].update(name="agent", namespace="mcp__migloop")
    run = _run(tmp_path, [call, _runtime_item("c1", "agent", args, runtime_body, 100, 200),
                         _native_formatted_result("c1", delivered)])
    parsed = probe._transcript_calls(run)[0]
    assert parsed["text"] == delivered and omitted not in parsed["text"]
    assert parsed["raw_text"].endswith(delivered) and parsed["delivery_truncated"] is True
    norm = parsed["provenance"]["output_normalization"]
    assert norm["omitted_chars"] == len(omitted) and norm["visible_chars"] == len(prefix + suffix)
    assert norm["reported_omitted_tokens"] == 998 and norm["exact_body_match"] is False
    payload = probe.probe_payload(led, run)
    visit = payload["trajectory"]["visits"][0]
    assert visit["status"] == "opened" and visit["verified"] and visit["delivery_truncated"]
    assert "非全文" in visit["scope"] and "返回截断" in visit["note"]


@pytest.mark.parametrize("case", ["prefix_mismatch", "suffix_mismatch", "multiple_markers", "header_cut", "no_omission"])
def test_partial_delivery_rejects_unaligned_or_forged_truncation_markers(tmp_path: Path, case: str) -> None:
    prefix, suffix = "# entry/A.ets@v2\nvisible prefix", "visible suffix"
    runtime_body = prefix + "OMITTED" + suffix
    body = prefix + "…2 tokens truncated…" + suffix
    if case == "prefix_mismatch":
        body = body.replace("@v2", "@v1")
    elif case == "suffix_mismatch":
        body += "forged"
    elif case == "multiple_markers":
        body = prefix + "…1 tokens truncated……1 tokens truncated…" + suffix
    elif case == "header_cut":
        body = "# entry/…2 tokens truncated…" + suffix
    elif case == "no_omission":
        runtime_body = prefix + suffix
    args = {"path": "A.ets", "v": 2, "via": "sessions"}
    run = _run(tmp_path, [_call("f", "file", args), _runtime_item("f", "file", args, runtime_body, 100, 200),
                         _native_formatted_result("f", body)])
    parsed = probe._transcript_calls(run)[0]
    assert parsed["text"].startswith("Wall time:") and not parsed.get("delivery_truncated")
    assert parsed["provenance"]["output_normalization"]["status"] == "unverified"


def test_partial_search_retains_delivered_text_and_cannot_authenticate_full_receipt(tmp_path: Path) -> None:
    from migloop import via
    led = _pool(tmp_path)
    args = {"q": "needle", "file": "/proj/spec/pages/A.md"}
    runtime = via.search_return(led, via.ViaState(), args, "# search needle\nvisible\n" + "OMITTED" * 10 + "\ntail", [
        {"kind": "file", "key": args["file"], "v": 1}])
    delivered = runtime.replace("OMITTED" * 10, "…10 tokens truncated…")
    run = _run(tmp_path, [_call("q", "search", args), _runtime_item("q", "search", args, runtime, 100, 200),
                         _native_formatted_result("q", delivered)])
    parsed = probe._transcript_calls(run)[0]
    assert parsed["delivery_truncated"] and parsed["text"] == delivered
    assert via.search_receipt(parsed["text"], args) is None
    assert via.trace_identity(led, [parsed], {})["bound"] is None


@pytest.mark.parametrize("trace_matches", [True, False])
def test_schema_failure_does_not_relabel_authenticated_trace_identity(tmp_path: Path, trace_matches: bool) -> None:
    led = _pool(tmp_path)
    identity = atoms.ledger_identity(led) if trace_matches else "different-ledger"
    malformed = "```yaml\nschema: migloop-verdict/1\nnotes: reason: invalid\n```"
    run = _run(tmp_path, [_call("s", "sessions", {}), _result("s", "账本身份: " + identity + "\n# chains"),
                          _call("f", "file", {"path": "A.ets", "v": 2, "via": "sessions"}),
                          _result("f", "# entry/A.ets@v2")], malformed)
    payload = probe.probe_payload(led, run)
    assert payload["structured"]["errors"] and payload["structured"]["identity"]["bound"] is False
    assert payload["trace_identity"]["bound"] is trace_matches
    tree = payload["trajectory"]
    if trace_matches:
        assert tree["verification"] == "returned_coordinates"
        assert "身份未绑定" not in tree["verification_note"]
        assert tree["visits"][0]["status"] == "opened" and len(tree["nodes"]) == 1
    else:
        assert tree["verification"] == "unverified" and "身份未绑定" in tree["verification_note"]
        assert tree["visits"][0]["status"] == "unverified" and tree["nodes"] == []


def test_observed_nested_mcp_rollout_runtime_items_keep_real_item_id_and_times(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    records = [
        _runtime_item("exec-first", "file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2", 100, 200),
        _runtime_item("exec-next", "agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}, "# agent-f v1", 250, 300),
    ]
    run_dir = _run(tmp_path, records)
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and [c["tool"] for c in calls] == ["file", "agent"]
    assert calls[0]["id"] is None and calls[0]["call_id"] is None and calls[0]["item_id"] == "exec-first"
    assert calls[0]["use_line"] is None and calls[0]["result_line"] == 2
    assert calls[0]["use_time_ms"] == 100 and calls[0]["result_time_ms"] == 200
    assert calls[0]["provenance"]["format"] == "codex_rollout_event"
    tree = probe.probe_payload(led, run_dir)["trajectory"]
    assert [v["status"] for v in tree["visits"]] == ["opened", "opened"]
    assert len(tree["transitions"]) == 1 and tree["visits"][1]["item_id"] == "exec-next"


def test_runtime_completion_order_does_not_invent_prior_receipt(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    # A started first but finished second; a later-started agent cannot use A's future result.
    run_dir = _run(tmp_path, [
        _runtime_item("agent", "agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}, "# agent-f v1", 200, 300),
        _runtime_item("file", "file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2", 100, 400),
    ])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and [c["item_id"] for c in calls] == ["file", "agent"]
    tree = probe.probe_payload(led, run_dir)["trajectory"]
    assert tree["transitions"] == []
    assert tree["visits"][1]["note"] == "via 指向调用前尚未成功返回的节点"


def test_runtime_completion_without_start_time_is_only_an_unverified_summary(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [_runtime_item("summary", "file", {"path": "A.ets", "v": 2, "via": "sessions"},
                                          "# entry/A.ets@v2", None, 200)])
    tree = probe.probe_payload(led, run_dir)["trajectory"]
    assert tree["nodes"] == [] and tree["visits"][0]["status"] == "unverified"


def test_stdout_completion_without_started_record_cannot_open_a_node(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [])
    Path(run_dir, "transcript.jsonl").unlink()
    _write_jsonl(str(Path(run_dir) / "events.jsonl"), [
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "id": "summary", "server": "migloop",
            "tool": "file", "arguments": {"path": "A.ets", "v": 2, "via": "sessions"},
            "result": {"content": [{"type": "text", "text": "# entry/A.ets@v2"}]}}}])
    tree = probe.probe_payload(led, run_dir)["trajectory"]
    assert tree["nodes"] == [] and tree["visits"][0]["status"] == "unverified"


def test_native_function_and_runtime_item_deduplicate_only_explicit_ids(tmp_path: Path) -> None:
    args = {"path": "A.ets", "v": 2, "via": "sessions"}
    same = _runtime_item("same", "file", args, "# entry/A.ets@v2", 100, 200)
    run_dir = _run(tmp_path, [_call("same", "file", args), same, _result("same", "# entry/A.ets@v2"),
                             _runtime_item("other", "file", args, "# entry/A.ets@v2", 100, 200)])
    calls = probe._transcript_calls(run_dir)
    assert calls is not None and len(calls) == 2
    assert calls[0]["call_id"] == calls[0]["item_id"] == "same"
    assert calls[0]["provenance"]["runtime_item"]["line"] == 3
    assert calls[1]["item_id"] == "other" and calls[1]["call_id"] is None


def test_equal_runtime_milliseconds_are_ambiguous_not_a_future_return_claim(tmp_path: Path) -> None:
    led = _pool(tmp_path)
    run_dir = _run(tmp_path, [
        _runtime_item("first", "file", {"path": "A.ets", "v": 2, "via": "sessions"}, "# entry/A.ets@v2", 100, 200),
        _runtime_item("next", "agent", {"id": "fixer", "v": 1, "via": "file:A.ets@v2"}, "# agent-f v1", 200, 300)])
    tree = probe.probe_payload(led, run_dir)["trajectory"]
    assert tree["transitions"] == []
    assert "时序分辨率不足" in tree["visits"][1]["note"] and "尚未成功返回" not in tree["visits"][1]["note"]
