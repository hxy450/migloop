"""Text payloads must not be mistaken for a second transport envelope."""
import json
from pathlib import Path

import pytest

from migloop import draft_check, probe
from tests.test_codex_probe import _call, _native_formatted_result, _runtime_item
from tests.test_draft_check import data
from tests.test_draft_check_adversarial import _saved_run
from tests.test_verdict import _pool


@pytest.mark.parametrize("kind", ["text", "input_text"])
@pytest.mark.parametrize("body", [
    '{"schema":"example","counts":{"errors":0}}',
    ' { "content": "not an envelope", "result": "keep both" } ',
    '{"error":"a quoted error","isError":true}',
    '[{"type":"text","text":"inner text is not a new return"}]',
    '{"result":"# agent-c v1","other":"this is literal JSON"}',
])
def test_explicit_text_is_opaque_and_byte_preserved(kind, body):
    assert probe._tool_output({"type": kind, "text": body}) == (body, False)
    envelope = {"content": [{"type": kind, "text": body}], "isError": False}
    assert probe._tool_output(envelope) == (body, False)
    assert probe._tool_output(json.dumps(envelope)) == (body, False)
    envelope["isError"] = True
    assert probe._tool_output(envelope) == (body, True)


@pytest.mark.parametrize("body", ['{"result":"# agent-c v1","extra":1}',
                                 '{"result":"first","result":"# agent-c v1"}'])
def test_coordinate_compatibility_does_not_drop_other_fields_or_duplicate_keys(body):
    assert probe._unwrap_result(body) == body


@pytest.mark.parametrize("altered", [False, True])
def test_compact_json_check_authenticates_only_exact_native_body(tmp_path, altered):
    ledger = _pool(tmp_path)
    doc = data(ledger)
    draft = json.dumps(doc, ensure_ascii=False)
    run = _saved_run(tmp_path, ledger, doc, doc, raw=draft)
    path = Path(run) / "transcript.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[:2]]
    args = {"draft": draft}
    body = draft_check.render(ledger, draft)  # Real compact render, not a preformatted test double.
    delivered = body.replace('"semantic_checked":false', '"semantic_checked":true', 1) if altered else body
    call = _call("check-native", "check", args)
    call["payload"].update(name="check", namespace="mcp__migloop")
    rows += [call, _runtime_item("check-native", "check", args, body, 100, 200),
             _native_formatted_result("check-native", delivered)]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    checked_call = probe._transcript_calls(run)[-1]
    normalization = checked_call["provenance"]["output_normalization"]
    assert normalization["exact_body_match"] is (not altered)
    assert normalization["status"] == ("unverified" if altered else "verified")
    if not altered:
        assert checked_call["text"] == body
        assert checked_call["raw_text"] == "Wall time: 0.0284 seconds\nOutput:\n" + body
    result = probe.probe_payload(ledger, run)
    assert result["draft_check"]["status"] == ("unverifiable" if altered else "matched")
    assert result["draft_check"]["semantic_checked"] is False
    assert all(visit["tool"] != "check" for visit in result["trajectory"].get("visits", []))
