"""The experiment must not substitute service returns for visible outputs."""

import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "inquiry_luna_audit",
    Path(__file__).resolve().parents[1]
    / "docs/experiments/inquiry-20260911/luna-audit.py",
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_plain_frame_and_legitimate_json_envelope():
    frame = "RESULT fixed range=0:3\n中文x\nEND FRAME next=none"
    envelope = {"content": [{"type": "text", "text": frame}]}
    for output in (
        frame,
        envelope,
        json.dumps(envelope),
        [{"text": json.dumps(envelope)}],
    ):
        assert any(frame in text for _, text in AUDIT.views(output))


def test_truncation_is_not_repaired_from_partial_json():
    frame = "RESULT fixed\ncritical actual source\nEND FRAME next=none"
    broken = json.dumps({"text": frame}).replace(
        "critical actual source", "…100 tokens truncated…"
    )
    assert not any(frame in text for _, text in AUDIT.views(broken))
    assert not any(frame in text for _, text in AUDIT.views('{"text": "RESULT fixed'))


def test_contiguous_coverage_not_just_last_page():
    assert AUDIT.covered([(0, 5), (5, 10)], 10)
    assert AUDIT.covered([(0, 7), (4, 10)], 10)
    assert not AUDIT.covered([(5, 10)], 10)
    assert not AUDIT.covered([(0, 4), (5, 10)], 10)
    assert not AUDIT.covered([(0, 5)], 10)


def test_attempting_open_does_not_count_as_successful_open():
    bodies = [
        {
            "queries": [
                {
                    "query": {"op": "open", "ref": "e-a"},
                    "ok": False,
                    "result_visible": "complete",
                },
                {
                    "query": {"op": "open", "ref": "e-b"},
                    "ok": True,
                    "result_visible": "partial",
                },
                {"query": {"op": "search"}, "ok": True, "result_visible": "complete"},
            ]
        }
    ]
    assert AUDIT.query_stats(bodies) == {
        "query_attempts": 3,
        "query_succeeded": 2,
        "query_failed": 1,
        "open_attempts": 2,
        "open_succeeded": 1,
        "open_failed": 1,
    }
