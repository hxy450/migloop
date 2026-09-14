"""Replay adjudicated MemberCenter evidence as paired check inputs, not model scores.

Uses the retained narrative-pilot index and original-byte validation. Rolls back
all navigation handles; does not change frozen reports or original evidence.
"""

import argparse
import json

from migloop.inquiry.check_receipts import bind_checks
from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check
from migloop.inquiry.store import Store, iso, parts


def replay(index):
    store = Store(index)
    store.db.execute("BEGIN")
    try:
        engine = Engine(store)
        result = []
        cutoff = "2026-07-26T21:48:57.793Z"
        actor = lambda cite: store.source_record(cite)[0]["agent"]
        for label, cite, wrong_actor in [
            ("product_xml_receipt", "e-231e7f5e3492", actor("e-7bbf87ca6062")),
            ("compile_edit_author", "e-546548020715", actor("e-68ce7f991dc3")),
        ]:
            record, _ = store.source_record(cite)
            operations = store.rows("SELECT * FROM effects WHERE request=? OR result=?", (record["ref"], record["ref"]))
            assert len(operations) == 1, label
            op = operations[0]
            for wrong in (False, True):
                refs = [op["request"], op["result"]]
                for ref in refs:
                    store.source_record(ref)
                edge = {"from": "file" if op["op"] == "read" else "actor", "to": "actor" if op["op"] == "read" else "file",
                        "relation": op["op"], "evidence": refs, "claim": "adjudicated relation control"}
                doc = {"schema": "inquiry/1", "target": {"file": op["path"], "at": cutoff}, "findings": [{
                    "id": "A", "title": label, "reason": "counterfactual endpoint test; not a new investigation",
                    "nodes": [{"id": "actor", "kind": "agent", "key": wrong_actor if wrong else op["agent"],
                               "at": cutoff, "role": "context", "reason": label, "evidence": refs},
                              {"id": "file", "kind": "file", "key": op["path"], "at": cutoff,
                               "role": "context", "reason": label, "evidence": refs}], "edges": [edge]}]}
                graph = check(engine, json.dumps(doc))
                accepted = any(e["operation"] == op["id"] for e in graph["edges"])
                assert accepted is not wrong, (label, wrong, graph["unverified_edges"])
                result.append({"case": label, "wrong_actor": wrong, "bound": accepted,
                    "source": record["name"], "line": record["line"], "actual_agent": op["agent"],
                    "at": iso(op["at"]), "diagnostics": graph["unverified_edges"]})

        receipt, _ = store.source_record("e-67b279e75764")
        pair, = store.rows("SELECT * FROM call_pairs WHERE result=?", (receipt["ref"],))
        request, raw = store.source_record(pair["request"])
        tool = next(p[4] for p in parts(json.loads(raw)) if p[0] == pair["request_slot"] and p[2] == "request")
        node = {"id": "A:checker", "kind": "agent", "key": receipt["agent"], "at": cutoff, "exists": True}
        for summary in (False, True):
            item = {"node": "checker", "request": request["ref"], "result": "e-9c5d49ac9177" if summary else receipt["ref"],
                    "tool": tool, "claim": "actual build receipt, not an assistant assertion"}
            doc = {"target": {"file": "MemberCenterPage.ets", "at": cutoff}, "findings": [{"id": "A", "checks": [item]}]}
            issues = []
            bound = bind_checks(engine, doc, [node], issues)
            assert bool(bound) is not summary, issues
            result.append({"case": "build_receipt", "assistant_summary": summary, "bound": bool(bound), "issues": issues})
        return {"schema": "delivery-replay/1", "checks": result, "passed": len(result),
                "model_calls": 0, "semantic_verified": False, "note": "Adjudicated endpoint/receipt controls, not attribution accuracy or model self-correction."}
    finally:
        store.db.rollback()
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.index), ensure_ascii=False, indent=2))
