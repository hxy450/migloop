"""Atom navigation survives budgets without converting locators into reads."""
from copy import deepcopy

import pytest

from migloop import atom_queries, atoms, delivery_budget, investigation, temporal_atom_text, time_receipts
from tests.test_temporal import source, ts


def messages(tmp_path):
    rows = [{"timestamp": ts(i), "type": "user", "message": {"role": "user", "content":
             f"task {i}: " + "actual input " * 90}} for i in range(12)]
    path = source(tmp_path, rows)
    return atoms.build_ledger({"a": atoms.AgentRec("a", "s", sources=[path])})


def execute(ledger, request):
    return investigation.query(ledger, request["tool"], {**request["args"], **(
        {"scope": request["scope"]} if "scope" in request else {})})


def test_default_navigation_and_raw_view_are_distinct_but_search_scope_is_not(tmp_path):
    ledger = messages(tmp_path)
    default = investigation.query(ledger, "agent", {"id": "a", "at": ts(11)})
    assert default["schema"] == "migloop-time-atom/1"
    assert len(default["sections"]["messages"]["rows"]) == 2
    assert default["raw_index"]["total"] == 12
    raw = execute(ledger, default["raw_index"]["query"])
    assert raw["schema"] == "migloop-time-view/1" and raw["total"] == 12
    searched = investigation.query(ledger, "search", {"scope": default["scope"], "q": "task 11:"})
    assert searched["total"] == 1
    assert default["scope"] == raw["scope"] == searched["scope"]


def test_section_budget_keeps_prefix_and_real_resumable_cursor(tmp_path):
    ledger = messages(tmp_path)
    data = investigation.query(ledger, "agent", {"id": "a", "at": ts(11), "view": "messages", "limit": 12})
    original = deepcopy(data)
    budget = delivery_budget.size(data) - 5000
    fitted = delivery_budget.fit(data, budget)
    assert fitted["status"] == "ok", fitted
    page = fitted["data"]["sections"]["messages"]
    assert 0 < len(page["rows"]) < 12
    assert page["rows"] == data["sections"]["messages"]["rows"][:len(page["rows"])]
    assert page["remaining"] == 12 - len(page["rows"])
    continuation = page["next_query"]
    assert continuation["args"]["view"] == "messages"
    next_data = execute(ledger, continuation)
    assert next_data["scope"] == data["scope"]
    assert next_data["sections"]["messages"]["rows"][0]["ref"] == data["sections"]["messages"]["rows"][len(page["rows"])]["ref"]
    delivered = investigation._delivery(fitted["data"])["records"]
    assert [r["ref"] for r in delivered] == [r["ref"] for r in page["rows"]]
    assert all(r["extent"] == "preview_or_pointer" for r in delivered)
    assert fitted["data_chars"] <= budget and data == original


def test_scalar_preview_and_batch_receipt_agree_but_navigation_is_not_body(tmp_path):
    ledger = messages(tmp_path)
    args = {"id": "a", "at": ts(11)}
    data = investigation.query(ledger, "agent", args)
    text = atom_queries.render_text(ledger, "", "agent", args)
    receipt = time_receipts.parse(ledger, "agent", args, text)
    assert receipt
    assert receipt["records"] == [r["ref"] for r in investigation._delivery(data)["records"]]
    assert text.split(time_receipts.MARKER)[0] == temporal_atom_text.render(data)
    assert len(receipt["records"]) == 2
    data["body_sources"] = {"total": 1, "entries": [{"ref": "raw:only:L9:locator", "chars": 50000}], "query": {}}
    assert len(investigation._delivery(data)["records"]) == 2


@pytest.mark.parametrize("view", ["writes", "reads", "candidates", "messages"])
def test_group_selector_rejects_raw_annotation_cursor(view):
    with pytest.raises(ValueError, match="view=records"):
        atom_queries.parameters("agent", {"id": "a", "at": ts(11), "view": view, "annotation_limit": 1})


def test_explicit_default_selector_has_its_own_request_identity():
    plain = time_receipts.canonical("agent", {"id": "a", "at": ts(11)})
    explicit = time_receipts.canonical("agent", {"id": "a", "at": ts(11), "view": "overview"})
    assert "view" not in plain and explicit["view"] == "overview"


def test_preview_prefix_span_describes_actual_delivered_characters():
    row = {"ref": "raw:source:L1:hash", "preview": "abcdefgh", "chars": 100,
           "preview_start": 7, "preview_span": {"offset": 7, "chars": 8}}
    actual = delivery_budget._row_prefix(row, "preview", 3)
    assert actual["preview"] == "abc" and actual["preview_span"] == {"offset": 7, "chars": 3}
    assert actual["chars"] == 100 and actual["preview_budget_truncated"]
    assert row["preview_span"]["chars"] == 8
