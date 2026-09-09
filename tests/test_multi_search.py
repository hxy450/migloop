"""Bounded literal OR is one search, not additional evidence or navigation."""
import asyncio
from copy import deepcopy
import hashlib
import json

import pytest

from migloop import atom_queries, atoms, atoms_text, probe, via
from tests.test_atoms import MAIN_ID, _call, _ledger, _rec


@pytest.mark.parametrize("terms", [[], ["a"], ["a"] * 9, ["a", ""], ["a", "  "],
                                  ["a", 1], ["a", True], "a|b", ["x" * 257, "b"],
                                  [str(i) + "x" * 200 for i in range(8)]])
def test_invalid_or_arguments_fail_before_search(terms):
    with pytest.raises(ValueError):
        atom_queries.parameters("search", {"q_any": terms, "agent": "a"})


def test_or_arguments_and_legacy_defaults_are_distinct():
    args = atom_queries.parameters("search", {"q_any": ["Alpha", "颜色"], "agent": "a"})
    assert args["q_any"] == ["Alpha", "颜色"] and args["q"] == ""
    with pytest.raises(ValueError, match="互斥"):
        atom_queries.parameters("search", {"q": "x", "q_any": ["a", "b"]})
    assert "q_any" not in via.search_args({"q": "x"})
    assert via.search_args({"q": "x"}) == via.search_args({"q": "x", "q_any": None})


def test_agent_or_deduplicates_fields_and_keeps_long_line_literal(tmp_path):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "one", "Bash",
        {"command": "echo Alpha"}, out="x" * 500 + 'ALPHA 颜色 "quoted"'))
    before = deepcopy(ledger)
    result = atoms.search_agent(ledger, MAIN_ID, "", q_any=["alpha", "颜色"])
    assert len(result["hits"]) == 2  # input and output, not three term-hits
    output = next(h for h in result["hits"] if h["field"] == "output")
    assert output["matched_terms"] == ["alpha", "颜色"]
    text = atoms_text.render_search(ledger, "", agent=MAIN_ID, q_any=["alpha", "颜色"])
    assert "ALPHA" in text and "颜色" in text and "字面量 OR" in text
    assert ledger == before


def test_union_sampling_does_not_hide_rare_term_and_receipts_only_show_selected(tmp_path):
    records = [_rec(f"2026-01-01T00:00:{i:02d}Z", "assistant", f"common {i}") for i in range(40)]
    records += _call("2026-01-01T00:00:41Z", "rare", "Write",
                     {"file_path": "/proj/A.ets", "content": "rare token"})
    ledger = _ledger(tmp_path, records)
    hits = []
    text = atoms_text.render_search(ledger, "", agent=MAIN_ID, q_any=["common", "rare"], navigation_hits=hits)
    assert "rare token" in text and "未展示" in text
    assert len(text) < 24000 and len(hits) <= 48
    assert any(h["seq"] == ledger.agents[MAIN_ID].actions[-1].seq for h in hits)
    args = {"q_any": ["common", "rare"], "agent": MAIN_ID}
    result = via.search_return(ledger, via.ViaState(), args, text, hits)
    receipt = via.search_receipt(result, args)
    assert receipt["schema"] == "migloop-search/2"
    assert via.search_receipt(result, {**args, "q_any": ["common", "different"]}) is None
    assert via.search_receipt(result, {"q": "common", "agent": MAIN_ID}) is None
    assert via.search_receipt(result.replace("rare token", "wrong token"), args) is None


def test_legacy_receipt_bytes_survive_and_cannot_be_reused_for_or():
    args = {"q": "alpha", "until_ts": "2026-01-01T01:00:00Z"}
    old_args = {"q": "alpha", "agent": None, "v": None, "since": None, "file": None,
                "after": False, "since_ts": None, "until_ts": args["until_ts"], "kind": None}
    body = "# original literal result\nalpha"
    row = {"schema": "migloop-search/1", "id": "a" * 24, "ledger": "old-identity", "args": old_args,
           "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "hits": []}
    text = body + "\n" + via.SEARCH_RECEIPT + json.dumps(row, separators=(",", ":"))
    assert via.search_receipt(text, args) == row
    assert via.search_receipt(text, {**args, "q_any": None}) == row
    assert via.search_receipt(text, {**args, "q_any": ["beta", "gamma"]}) is None


def test_or_respects_return_time_not_invocation_time(tmp_path):
    records = _call("2026-01-01T00:00:01Z", "slow", "Bash", {"command": "echo alpha"}, out="beta later")
    records[-1]["timestamp"] = "2026-01-01T00:00:10Z"
    ledger = _ledger(tmp_path, records)
    result = atoms.search_agent(ledger, MAIN_ID, "", q_any=["alpha", "beta"],
                                until_ts="2026-01-01T00:00:05Z")
    assert [h["field"] for h in result["hits"]] == ["input"]
    assert "beta later" not in atoms_text.render_search(ledger, "", agent=MAIN_ID,
        q_any=["alpha", "beta"], until_ts="2026-01-01T00:00:05Z")


def test_or_unknown_return_time_is_not_replaced_by_use_time(tmp_path):
    records = _call("2026-01-01T00:00:01Z", "slow", "Bash", {"command": "echo alpha"}, out="beta unknown")
    records[-1].pop("timestamp")
    ledger = _ledger(tmp_path, records)
    ledger.agents[MAIN_ID].actions[0].done_ts = None
    result = atoms.search_agent(ledger, MAIN_ID, "", q_any=["alpha", "beta"],
                                until_ts="2026-01-01T00:00:05Z")
    assert [h["field"] for h in result["hits"]] == ["input"]
    assert result["unknown_times"] == 1


@pytest.mark.parametrize("stamp", ["2026-01-01T00:00:05Z", "2026-01-01T08:00:05+08:00"])
def test_or_accepts_only_explicit_timezone_windows(stamp):
    from migloop import search_terms
    assert search_terms.valid_time(stamp)
    assert atom_queries.parameters("search", {"q_any": ["alpha", "beta"], "until_ts": stamp})["until_ts"] == stamp


@pytest.mark.parametrize("stamp", ["2026-01-01", "2026-01-01T00:00:05", "2026-01-01 00:00:05",
                                   " 2026-01-01T00:00:05Z "])
def test_search_rejects_timezone_free_or_noncanonical_new_windows(stamp):
    from migloop import search_terms
    assert not search_terms.valid_time(stamp)
    with pytest.raises(ValueError, match="ISO"):
        atom_queries.parameters("search", {"q_any": ["alpha", "beta"], "until_ts": stamp})
    with pytest.raises(ValueError, match="ISO"):
        atom_queries.parameters("search", {"q": "alpha", "until_ts": stamp})


@pytest.mark.parametrize("stamp", ["2026-01-01", "2026-01-01T00:00:02"])
def test_or_timezone_free_actual_result_and_file_version_are_unknown(tmp_path, stamp):
    records = _call("2026-01-01T00:00:01Z", "w", "Write",
                    {"file_path": "/proj/A.ets", "content": "alpha"}, out="beta")
    records[-1]["timestamp"] = stamp
    ledger = _ledger(tmp_path, records)
    ledger.agents[MAIN_ID].actions[0].done_ts = stamp
    ledger.stories["/proj/A.ets"].versions[0].ts = stamp
    result = atoms.search_pool(ledger, "", "2026-01-01T00:01:00Z", q_any=["alpha", "beta"])
    assert result["unknown_times"] >= 2
    assert not any(r.get("kind") == "file" or r.get("field") == "output" for r in result["rows"])


def test_or_scope_is_reported_without_regex_or_graph_semantics():
    scope = probe._step_scope("search", {"q_any": ["a|b", "颜色"], "v": 2})
    assert "字面量 OR" in scope and "a|b" in scope and "v2" in scope


def test_literal_or_has_no_regex_casefold_or_whitespace_reinterpretation(tmp_path):
    from migloop import search_terms
    terms = ["a|b", '颜色 "Q"']
    result = search_terms.scan('prefix a|b and 颜色 "q" suffix', terms)
    assert result["matched_terms"] == terms
    assert search_terms.scan("a b", terms) is None
    assert search_terms.scan("STRASSE", ["straße", "other"]) is None  # lower, not casefold
    result = search_terms.scan("İ" + "x" * 500 + "NEEDLE", ["i", "needle"])
    assert all(e["text"] == ("İ" + "x" * 500 + "NEEDLE")[e["start"]:e["end"]] for e in result["excerpts"])
    text = "İ " + "x" * 600 + " ΟΣ σίγμα"
    result = search_terms.scan(text, ["ος", "σίγμα"])
    assert result["matched_terms"] == ["ος", "σίγμα"]
    assert {t for e in result["excerpts"] for t in e["matched_terms"]} == {"ος", "σίγμα"}
    assert all(e["text"] == text[e["start"]:e["end"]] for e in result["excerpts"])
    with pytest.raises(ValueError, match="重复"):
        atom_queries.parameters("search", {"q_any": ["Alpha", "ALPHA"]})


def test_file_and_pool_or_do_not_compress_away_later_term(tmp_path):
    ledger = _ledger(tmp_path, [
        *_call("2026-01-01T00:00:01Z", "w1", "Write", {"file_path": "/proj/A.ets", "content": "common"}),
        *_call("2026-01-01T00:00:03Z", "w2", "Write", {"file_path": "/proj/A.ets", "content": "common rare"})])
    for args in ({"file": "A.ets"}, {"until_ts": "2026-01-01T00:01:00Z"}):
        hits = []
        text = atoms_text.render_search(ledger, "", q_any=["common", "rare"], navigation_hits=hits, **args)
        assert "common rare" in text
        assert any(h["kind"] == "file" and h["v"] == 2 and "rare" in h["matched_terms"] for h in hits)
    limited = atoms_text.render_search(ledger, "", file="A.ets", v=1, q_any=["common", "rare"])
    assert "common rare" not in limited and '词 "rare": 命中 0 条' in limited


def test_eight_terms_are_fair_across_source_groups_with_fixed_budget():
    from migloop import search_terms
    rows = []
    terms = [f"term{i}" for i in range(8)]
    for i, term in enumerate(terms):
        for field, kind in (("input", "write"), ("output", "read"), ("text", "say"),
                            ("text", "instruction"), ("content", "file"), ("text", "other")):
            rows.append({"record_key": (i, field, kind), "field": field, "kind": kind,
                         **search_terms.scan(term, terms)})
    selected = search_terms.fair_rows(rows, terms)
    assert len(selected) == search_terms.MAX_ROWS
    assert {t for r in selected for t in r["matched_terms"]} == set(terms)


def test_single_pass_matches_same_record_count_as_scalar_scan(tmp_path, monkeypatch):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "one", "Bash",
        {"command": "echo common"}, out="common rare"))
    real = atoms._record_texts
    calls = []
    def count(record, action):
        calls.append(action.seq)
        return real(record, action)
    monkeypatch.setattr(atoms, "_record_texts", count)
    atoms.search_agent(ledger, MAIN_ID, "common")
    scalar_reads = len(calls)
    calls.clear()
    atoms.search_agent(ledger, MAIN_ID, "", q_any=["common", "rare", "x", "y", "z", "a", "b", "c"])
    assert len(calls) == scalar_reads


def test_no_unshown_or_invalid_target_gets_or_navigation_receipt(tmp_path):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "one", "Write",
        {"file_path": "/proj/A.ets", "content": "alpha beta"}))
    args = {"file": "A.ets", "q_any": ["alpha", "beta"]}
    hits = [{"kind": "file", "key": "/proj/A.ets", "v": 1},
            {"kind": "file", "key": "/proj/A.ets", "v": 2, "matched_terms": ["alpha"]},
            {"kind": "file", "key": "/proj/A.ets", "v": 1, "matched_terms": ["not-queried"]}]
    output = via.search_return(ledger, via.ViaState(), args, "# no displayed target", hits)
    assert via.search_receipt(output, args)["hits"] == []
    assert via.search_receipt(output[:-12], args) is None
    assert via.search_receipt(output, []) is None
    assert via.search_receipt(output, {**args, "q_any": ["beta", "alpha"]}) is None


def test_mcp_or_schema_and_navigation_do_not_create_search_nodes(tmp_path):
    from migloop import mcp_server
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "one", "Write",
        {"file_path": "/proj/A.ets", "content": "alpha beta"}))
    class Backend:
        async def get_ledger(self, sid):
            return ledger
        async def get_session_cwd(self, sid):
            return "/proj"
    server = mcp_server.build_server(Backend())
    async def run():
        tools = await server.list_tools()
        schema = next(t for t in tools if t.name == "search").inputSchema
        assert "q_any" in schema["properties"]
        args = {"q_any": ["alpha", "beta"], "file": "A.ets"}
        result = await server.call_tool("search", {"sid": "s", **args})
        blocks = result[0] if isinstance(result, tuple) else result
        text = probe._unwrap_result("".join(getattr(b, "text", "") for b in blocks))
        receipt = via.search_receipt(text, args)
        assert receipt and receipt["schema"] == via.SEARCH_OR_SCHEMA
        assert receipt["hits"] and all(h["kind"] in ("file", "agent") for h in receipt["hits"])
        assert via.trace_identity(ledger, [{"tool": "search", "input": args, "has_result": True,
                                         "text": text}], {})["bound"] is True
        assert via.trace_identity(ledger, [{"tool": "search", "input": args, "has_result": True,
                                         "is_error": True, "text": text}], {})["bound"] is None
    asyncio.run(run())


def test_http_array_normalization_and_unsupported_scope_fail_explicitly():
    assert atom_queries.parameters("search", {"q_any": '["a", "b"]'})["q_any"] == ["a", "b"]
    for extra in ({"agent": "a", "file": "b"}, {"file": "b", "until_ts": "t"},
                  {"kind": "write", "agent": "a"}, {"kind": "not-known"}):
        with pytest.raises(ValueError):
            atom_queries.parameters("search", {"q_any": ["a", "b"], **extra})


def test_scalar_q_output_keeps_legacy_literal_guidance(tmp_path):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "one", "Bash",
        {"command": "echo alpha|beta"}, out="alpha|beta"))
    text = atoms_text.render_search(ledger, "alpha|beta", agent=MAIN_ID)
    assert "不支持正则/OR，| 也是普通字符" in text
    assert "字面量 OR" not in text
    assert text == atoms_text.render_search(ledger, "alpha|beta", agent=MAIN_ID, q_any=None)


def test_many_words_large_excerpts_keep_one_total_output_budget(tmp_path):
    from migloop import search_terms
    terms = [f"term{i}" for i in range(8)]
    body = ("x" * 1000).join(terms)
    records = [_rec(f"2026-01-01T00:00:{i:02d}Z", "assistant", body + str(i)) for i in range(45)]
    ledger = _ledger(tmp_path, records)
    hits = []
    text = atoms_text.render_search(ledger, "", agent=MAIN_ID, q_any=terms, navigation_hits=hits)
    assert len(text) <= search_terms.MAX_BODY_CHARS
    for term in terms:
        assert f'词 "{term}": 命中 45 条；片段可见 0 条' not in text
        assert f'词 "{term}": 命中 45 条' in text
    assert "未展示" in text and len(hits) == 0  # these text-only roots have no effect version


def test_write_candidates_search_real_input_not_collector_summary(tmp_path):
    command = "echo " + "x" * 500 + "; touch /proj/rare-file.txt"
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "one", "Bash", {"command": command}))
    action = ledger.agents[MAIN_ID].actions[0]
    # Deliberately different from raw input: collector summaries are not raw.
    action.detail["cmd"] = "summary-only-claim"
    result = atoms.search_window_writes(ledger, None, "2026-01-01T00:01:00Z", q_any=["rare-file", "summary-only-claim"])
    assert len(result["rows"]) == 1
    assert result["rows"][0]["matched_terms"] == ["rare-file"]
    assert result["unknown_inputs"] == 0
    text = atoms_text.render_search(ledger, "", kind="write", until_ts="2026-01-01T00:01:00Z",
                                    q_any=["rare-file", "summary-only-claim"])
    assert "touch /proj/rare-file.txt" in text
    assert '词 "summary-only-claim": 命中 0 条' in text
    action.src = None
    missing = atoms.search_window_writes(ledger, None, "2026-01-01T00:01:00Z", q_any=["rare-file", "summary-only-claim"])
    assert missing["unknown_inputs"] == 1 and missing["rows"] == []
    action.src = (str(tmp_path / "does-not-exist.jsonl"), 0, 1)
    missing = atoms.search_window_writes(ledger, None, "2026-01-01T00:01:00Z", q_any=["rare-file", "summary-only-claim"])
    assert missing["unknown_inputs"] == 1 and missing["rows"] == []


@pytest.mark.parametrize("failure", [None, "failed", "truncated", "identity", "pending"])
def test_native_or_receipt_keeps_search_out_of_readwrite_graph(tmp_path, failure):
    from tests.test_codex_probe import _call as native_call, _runtime_item, _native_formatted_result, _run
    from tests.test_verdict import _pool
    ledger = _pool(tmp_path)
    args = {"q_any": ["spec", "input"], "file": "/proj/spec/pages/A.md"}
    hits = []
    body = atoms_text.render_search(ledger, "", navigation_hits=hits, **args)
    output = via.search_return(ledger, via.ViaState(), args, body, hits)
    receipt = via.search_receipt(output, args)
    assert receipt and receipt["hits"]
    handle = receipt["hits"][0]["via"]
    if failure == "truncated":
        output = output[:100]
    if failure == "identity":
        receipt["ledger"] = "wrong-ledger"
        output = output.rpartition("\n" + via.SEARCH_RECEIPT)[0] + "\n" + via.SEARCH_RECEIPT + json.dumps(receipt)
    records = []
    for i, (cid, name, query, text) in enumerate([
        ("q", "search", args, output),
        ("f", "file", {"path": args["file"], "v": 1, "via": handle}, "# spec/pages/A.md@v1")]):
        call = native_call(cid, name, query)
        call["payload"].update(name=name, namespace="mcp__migloop")
        runtime = _runtime_item(cid, name, query, text, i * 300 + 100, i * 300 + 200)
        result = _native_formatted_result(cid, text)
        if cid == "q" and failure == "pending":
            records.append(call)
            continue
        if cid == "q" and failure == "failed":
            runtime["payload"]["item"]["status"] = "failed"
        records.extend([call, runtime, result])
    payload = probe.probe_payload(ledger, _run(tmp_path, records))
    assert len(payload["steps"]) == 2
    assert len(payload["trajectory"]["visits"]) == 1
    assert payload["evidence_graph"]["edges"] == []
    if failure is None:
        assert payload["trajectory"]["visits"][0]["status"] == "opened"
        assert payload["trajectory"]["transitions"][0]["source"] == "search"
    else:
        assert payload["trajectory"]["transitions"] == []
