"""Display-only history: observe exact text without replaying or promoting effects."""

import json

import pytest

from migloop.inquiry.viewer import viewer_query
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.fixture
def observed(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("w", file_path="/proj/A.ets", content="alpha\nbeta\n")),
            record(2, result("w")),
            record(
                3,
                use(
                    "e",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="beta",
                    new_string="gamma",
                ),
            ),
            record(4, result("e")),
            record(5, use("r", "Read", file_path="/proj/A.ets", offset=2, limit=1)),
            record(8, result("r", "2\tgamma")),
            record(
                9,
                use(
                    "bad",
                    "Edit",
                    file_path="/proj/A.ets",
                    old_string="missing",
                    new_string="new",
                ),
            ),
            record(10, result("bad", "not found", error=True)),
            record(11, use("opaque", "Bash", command="python rewrite.py /proj/A.ets")),
            record(12, result("opaque", "done")),
        ],
    )
    yield engine
    engine.store.close()


def scope(at=12):
    return {"kind": "file", "key": "A.ets", "at": ts(at)}


def test_history_is_confirmed_writes_not_every_candidate_or_read(observed):
    before = observed.store.rows("SELECT * FROM effects")
    page = viewer_query(observed, {**scope(), "view": "history"})
    assert page["scope"]["key"] == "/proj/A.ets"
    assert [r["at"] for r in page["rows"]] == [
        ts(2).replace("Z", "+00:00"),
        ts(4).replace("Z", "+00:00"),
    ]
    assert page["changes"] == 2 and page["reads"] == 1
    assert observed.store.rows("SELECT * FROM effects") == before
    assert any(r["strength"] == "candidate" for r in before)
    assert observed.trace() == []


def test_write_body_is_known_edit_has_only_delta_and_read_is_partial(observed):
    history = viewer_query(observed, {**scope(), "view": "history"})
    write, edit = history["rows"]
    original = viewer_query(
        observed, {**scope(), "view": "operation", "id": write["id"]}
    )
    assert (
        original["content"] == "alpha\nbeta\n"
        and original["content_kind"] == "write_body"
    )
    delta = viewer_query(observed, {**scope(), "view": "operation", "id": edit["id"]})
    assert delta["content"] is None and "-beta" in delta["changes"][0]["text"]
    assert "+gamma" in delta["changes"][0]["text"]
    reads = viewer_query(observed, {**scope(), "view": "history", "category": "reads"})
    read = viewer_query(
        observed, {**scope(), "view": "operation", "id": reads["rows"][0]["id"]}
    )
    assert read["content_kind"] == "read_observation" and read["content"] == "2\tgamma"
    assert "可能只有片段" in read["note"]


def test_future_read_and_out_of_scope_operation_cannot_be_opened(observed):
    assert (
        viewer_query(observed, {**scope(6), "view": "history", "category": "reads"})[
            "total"
        ]
        == 0
    )
    reads = viewer_query(observed, {**scope(), "view": "history", "category": "reads"})
    with pytest.raises(ValueError, match="没有可确认"):
        viewer_query(
            observed, {**scope(6), "view": "operation", "id": reads["rows"][0]["id"]}
        )
    with pytest.raises(ValueError, match="没有可确认"):
        viewer_query(
            observed,
            {
                **scope(),
                "key": "unrelated.ets",
                "view": "operation",
                "id": reads["rows"][0]["id"],
            },
        )
    bounded = viewer_query(observed, {**scope(), "since": ts(3), "view": "history"})
    assert len(bounded["rows"]) == 1 and bounded["scope"]["since"] == ts(3).replace(
        "Z", "+00:00"
    )


def test_read_expansion_selects_exact_result_slot(tmp_path):
    engine = build(
        tmp_path,
        [
            record(
                1,
                use("a", "Read", file_path="/proj/A.ets"),
                use("b", "Read", file_path="/proj/B.ets"),
            ),
            record(2, result("a", "TEXT A"), result("b", "TEXT B")),
        ],
    )
    try:
        page = viewer_query(
            engine, {**scope(3), "view": "history", "category": "reads"}
        )
        data = viewer_query(
            engine, {**scope(3), "view": "operation", "id": page["rows"][0]["id"]}
        )
        assert data["content"] == "TEXT A" and "TEXT B" not in data["content"]
    finally:
        engine.store.close()


def test_stale_snapshot_does_not_remain_known(observed, tmp_path):
    page = viewer_query(observed, {**scope(), "view": "history"})
    path = tmp_path / "a.jsonl"
    path.write_bytes(path.read_bytes().replace(b"alpha", b"ALPHA"))
    with pytest.raises(ValueError, match="bytes changed"):
        viewer_query(
            observed, {**scope(), "view": "operation", "id": page["rows"][0]["id"]}
        )


def test_pagination_keeps_individual_operation_ids(observed):
    first = viewer_query(observed, {**scope(), "view": "history", "limit": 1})
    second = viewer_query(
        observed, {**scope(), "view": "history", "limit": 1, "offset": first["next"]}
    )
    assert first["rows"][0]["id"] != second["rows"][0]["id"] and second["next"] is None
    assert "guide" not in viewer_query(observed, {"view": "overview"})


def test_catalog_counts_native_changes_without_promoting_candidates(observed):
    before = observed.store.rows("SELECT * FROM effects")
    data = viewer_query(observed, {"view": "catalog"})
    assert data["files"] == [{"path": "/proj/A.ets", "n_events": 2}]
    assert data["agents"][0]["id"] == "a"
    assert data["agents"][0]["n_events"] == 2
    assert data["agents"][0]["parent"] is None
    assert data["agents"][0]["label"] == "a"
    assert before == observed.store.rows("SELECT * FROM effects")
    assert observed.trace() == []


def test_report_listing_groups_before_paging_and_preserves_old_ids(observed):
    def save(key, file):
        data = {"target": {"file": file, "at": ts(12)}, "document": {
            "findings": [{"title": key, "reason": "not needed to list a report"}]}}
        observed.store.db.execute(
            "INSERT INTO runs(id,kind,data) VALUES (?,'report',?)",
            (key, json.dumps(data)),
        )

    save("old-b", "/proj/B.ets")
    for n in range(110):
        save(f"draft-{n}", "/proj/A.ets")
    first = viewer_query(observed, {"view": "reports", "limit": 1})
    assert first["total"] == 2 and first["next"] == 1
    assert first["rows"][0]["id"] == "draft-109"
    second = viewer_query(observed, {"view": "reports", "offset": first["next"]})
    assert [r["id"] for r in second["rows"]] == ["old-b"]
    assert second["next"] is None
    assert observed.store.db.execute("SELECT data FROM runs WHERE id='draft-0'").fetchone()
    for n in range(105):
        save(f"other-{n}", f"/proj/Other{n:03}.ets")
    overview = viewer_query(observed, {"view": "overview"})
    assert overview["reports_total"] == 107 and overview["reports_next"] == 100
    rest = viewer_query(observed, {"view": "reports", "offset": 100})
    assert len(rest["rows"]) == 7 and rest["next"] is None
    assert len({r["file"] for r in overview["reports"] + rest["rows"]}) == 107
    assert observed.trace() == []


@pytest.mark.parametrize("page_request", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                     {"limit": True}, {"offset": "0"}])
def test_report_listing_rejects_invalid_page(observed, page_request):
    with pytest.raises(ValueError, match="reports require"):
        viewer_query(observed, {"view": "reports", **page_request})
