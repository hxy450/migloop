"""Original input fields: wider disclosure never bypasses time or delivery."""
import pytest

from migloop import atom_queries, delivery_budget, investigation, temporal_atom, transcript_store
from tests.test_temporal_atom import message, pool, ts


@pytest.mark.parametrize("length", [239, 240, 241, 967, 4096, 4097, 9000])
def test_input_prefix_and_original_field_expansion_are_exact(tmp_path, length):
    original = ("界\n\"\\constraint; " * 1000)[:length]
    ledger, agent, _ = pool(tmp_path, [message(1, original)])
    data = investigation.query(ledger, "agent", {"id": agent, "at": ts(3)})
    row, = data["sections"]["messages"]["rows"]
    expected = min(length, temporal_atom._MESSAGE_PREVIEW_CHARS)
    assert row["preview"] == original[:expected]
    assert row["chars"] == length
    assert row["preview_span"] == {"offset": 0, "chars": expected}
    assert transcript_store.resolve(ledger, row["ref"]).value["message"]["content"] == original
    expanded = investigation.query(ledger, "expand", {**row["expand_query"]["args"], "scope": data["scope"]})
    assert expanded["items"][0]["records"][0]["text"] == original
    delivered, = investigation._delivery(data)["records"]
    assert delivered["chars"] == expected and delivered["ref"] == row["ref"]


def test_wider_input_does_not_change_cutoff_or_promote_final_prompt(tmp_path):
    old = "earlier source input " * 100
    current = "current input " * 100
    future = "LATER_SOURCE_SECRET " * 100
    ledger, agent, _ = pool(tmp_path, [message(1, old), message(3, current),
                                     message(6, future), message(None, "UNDATED_SOURCE_SECRET")])
    ledger.agents[agent].prompt = "FINAL_SUMMARY_NOT_A_RECORDED_INPUT"
    data = investigation.query(ledger, "agent", {"id": agent, "at": ts(4), "since_ts": ts(2)})
    row, = data["sections"]["messages"]["rows"]
    assert row["preview"] == current
    for forbidden in (old, future, "UNDATED_SOURCE_SECRET", "FINAL_SUMMARY_NOT_A_RECORDED_INPUT"):
        assert forbidden not in str(data)
    assert data["raw_index"]["counts"]["undated"] > 0


def test_budget_receipt_counts_only_the_actual_prefix_not_the_wider_selection(tmp_path):
    ledger, agent, _ = pool(tmp_path, [message(1, "input clause; " * 500)])
    data = investigation.query(ledger, "agent", {"id": agent, "at": ts(3)})
    original = data["sections"]["messages"]["rows"][0]["preview"]
    assert len(original) == 4096
    # The minimum count-only packet plus a small allowance forces a field cut.
    minimum = delivery_budget.fit(data, 0)
    assert minimum["status"] == "deferred"
    count_only = investigation.query(ledger, "agent", {"id": agent, "at": ts(3), "view": "reads"})
    budget = delivery_budget.size(count_only) + 1900
    fitted = delivery_budget.fit(data, budget)
    assert fitted["status"] == "ok"
    row, = fitted["data"]["sections"]["messages"]["rows"]
    assert 0 < len(row["preview"]) < len(original)
    assert original.startswith(row["preview"])
    assert row["preview_span"]["chars"] == len(row["preview"])
    receipt, = investigation._delivery(fitted["data"])["records"]
    assert receipt["chars"] == len(row["preview"])
    assert fitted["data_chars"] <= budget
    assert len(data["sections"]["messages"]["rows"][0]["preview"]) == 4096


def test_scalar_and_batch_select_identical_original_input(tmp_path):
    ledger, agent, _ = pool(tmp_path, [message(1, "unchanged original constraint; " * 40)])
    args = {"id": agent, "at": ts(3)}
    scalar = atom_queries.json_data(ledger, "agent", args)
    batch = investigation.batch(ledger, [{"tool": "agent", "args": args}], 100000)
    assert batch["items"][0]["data"]["sections"] == scalar["sections"]
    assert len(batch["items"][0]["delivery"]["records"]) == 1
