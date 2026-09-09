"""An invalid model request must remain auditable without crashing the viewer."""
import pytest

from migloop import probe
from tests.test_codex_probe import _call, _result, _run, _pool


@pytest.mark.parametrize("bad", ["all", [], {}, True, 1.5])
def test_bad_body_range_is_kept_as_request_not_fabricated_range(tmp_path, bad):
    ledger = _pool(tmp_path)
    args = {"path": "A.ets", "v": 2, "via": "sessions", "content": True, "start": bad, "n": 10}
    run = _run(tmp_path, [_call("bad", "file", args), _result("bad", "parameter validation failed", failed=True)])
    payload = probe.probe_payload(ledger, run)
    assert len(payload["steps"]) == 1
    assert payload["steps"][0]["args"]["start"] == bad
    assert "行范围未确认" in payload["steps"][0]["scope"]
    assert payload["trajectory"]["visits"][0]["status"] == "error"
    assert not payload["trajectory"]["nodes"] and not payload["evidence_graph"]["edges"]


@pytest.mark.parametrize("bad", [True, False, 1.5, float("inf")])
def test_malformed_version_is_not_truncated_to_an_existing_node(bad):
    assert probe._int(bad) is None


def test_false_string_requests_are_not_labelled_as_body_or_diff():
    assert probe._step_scope("file", {"v": 2, "content": "false", "diff": "false"}) == "索引 v2"


def test_valid_http_integer_strings_keep_requested_range():
    assert probe._step_scope("file", {"v": 2, "content": True, "start": "3", "n": "5"}) == "正文 v2 3-7行"
