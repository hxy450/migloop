"""Known-answer reachability checks, not model accuracy or an investigator run."""

import argparse
import json
import time
from pathlib import Path

from migloop.inquiry.engine import Engine
from migloop.inquiry.report import check
from migloop.inquiry.store import Store, encode, timestamp

GEN = "2026-07-24T22:16:20.102Z"
END = "2026-07-26T21:48:57.793Z"
FILE = "entry/src/main/ets/pages/MemberCenterPage.ets"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise ValueError("do not overwrite prior verification")
    store = Store(args.db)
    engine = Engine(store, session="manual-real-acceptance", origin="developer_check")
    audit = {
        "model_runs": 0,
        "baseline_scores_changed": False,
        "checks": [],
        "timing_seconds": {},
    }
    started = time.perf_counter()
    operations = engine.query(
        {"op": "file", "key": FILE, "at": GEN, "view": "relations", "limit": 100}
    )
    audit["timing_seconds"]["generation_relations"] = time.perf_counter() - started
    actor = next(
        r["agent"]
        for r in operations["rows"]
        if r["agent"] and "aslice8-pay-" in r["agent"]
    )
    writer = next(
        r for r in operations["rows"] if r["agent"] == actor and r["op"] == "write"
    )
    inputs = [
        r
        for r in engine.relations("agent", actor, timestamp(GEN))
        if r["op"] == "read"
        and r["path"].endswith("/MemberCenterActivitiy.kt")
        and r["strength"] == "confirmed"
    ]
    reader = next(
        r
        for r in inputs
        if "replaceSpan"
        in engine.query({"op": "open", "ref": r["result"], "at": GEN})["text"]
    )
    source_text = engine.query(
        {
            "op": "open",
            "ref": reader["result"],
            "at": GEN,
            "pointer": "/message/content/0/content",
        }
    )["text"]
    written = engine.query(
        {
            "op": "open",
            "ref": writer["request"],
            "at": GEN,
            "pointer": "/message/content/0/input/content",
        }
    )["text"]
    assert (
        "AbsoluteSizeSpan" in source_text
        and "stripCurrency(product.showNowPrice)" in written
    )
    assert (
        "Text(this.animatedPrice.length > 0 ? this.animatedPrice : this.item.priceText)"
        in written
    )
    audit["checks"].append(
        "Slice8 actual input/output addressable before generation cutoff"
    )
    started = time.perf_counter()
    candidates = engine.query(
        {"op": "file", "key": FILE, "at": END, "since": GEN, "limit": 100}
    )
    audit["timing_seconds"]["repair_record_index"] = time.perf_counter() - started
    audit["repair_related_records"] = candidates["total"]
    for source, line, pointer, expected in [
        (
            "agent-a68daf720e780b4c2.jsonl",
            103,
            "/message/content/0/input/command",
            "write(new)",
        ),
        ("agent-a68daf720e780b4c2.jsonl", 104, "/message/content/0/content", "3 sites"),
        (
            "agent-a68daf720e780b4c2.jsonl",
            233,
            "/message/content/0/input/command",
            ".aspectRatio(840 / 942)",
        ),
        (
            "agent-a68daf720e780b4c2.jsonl",
            234,
            "/message/content/0/content",
            "ok entry/src/main/ets/pages/MemberCenterPage.ets",
        ),
        (
            "agent-af0e3d2ae54dbf769.jsonl",
            24,
            "/message/content/0/content",
            "Property 'priceDigits' is private",
        ),
        (
            "agent-af0e3d2ae54dbf769.jsonl",
            37,
            "/message/content/0/content",
            "BUILD SUCCESSFUL",
        ),
    ]:
        opened = engine.query(
            {
                "op": "open",
                "source": source,
                "line": line,
                "at": END,
                "pointer": pointer,
            }
        )
        assert expected in opened["text"], (source, line)
        audit["checks"].append(
            {
                "source": source,
                "line": line,
                "ref": opened["ref"],
                "complete_selected_text": True,
            }
        )
    model_like_query = [
        {"op": "agent", "key": actor, "at": GEN, "view": "relations", "limit": 20},
        {
            "op": "open",
            "ref": reader["result"],
            "at": GEN,
            "pointer": "/message/content/0/content",
        },
    ]
    frame = engine.investigate(model_like_query)
    assert len(frame) < engine.FRAME + 300 and "END FRAME" in frame
    audit["first_frame_chars"] = len(frame)
    # Developer fixture for the UI only: no earliest-cause or complete-coverage claim.
    doc = {
        "schema": "inquiry/1",
        "target": {"file": writer["path"], "at": END, "since": GEN},
        "findings": [
            {
                "id": "demo",
                "title": "人工取证样例：输入与写出代码的价格渲染差异（不是模型实验）",
                "reason": "只展示实际输入、写出和原生关系能否核回；不是该文件的完整归因报告，也不认定最早或唯一根因。",
                "nodes": [
                    {
                        "id": "input",
                        "kind": "file",
                        "key": reader["path"],
                        "at": GEN,
                        "role": "context",
                        "reason": "保存的Kotlin读取结果包含replaceSpan与AbsoluteSizeSpan；这是输入原文，不是修复者转述。",
                        "evidence": [reader["result"]],
                    },
                    {
                        "id": "actor",
                        "kind": "agent",
                        "key": actor,
                        "at": GEN,
                        "role": "propagated",
                        "reason": "这次代理实际读到了源代码，并写出了统一30字号的价格Text；是否最早引入尚未在本样例核实。",
                        "evidence": [reader["result"], writer["request"]],
                    },
                    {
                        "id": "file",
                        "kind": "file",
                        "key": writer["path"],
                        "at": GEN,
                        "role": "propagated",
                        "reason": "该次Write正文使用stripCurrency与单个Text的fontSize(30)，没有在此组件中复现输入里的数字Span分段方式。",
                        "evidence": [writer["request"], writer["result"]],
                    },
                ],
                "edges": [
                    {
                        "from": "input",
                        "to": "actor",
                        "relation": "read",
                        "evidence": [reader["request"], reader["result"]],
                        "claim": "原生Read请求与结果可核；不证明代理理解或采纳了每项行为。",
                    },
                    {
                        "from": "actor",
                        "to": "file",
                        "relation": "write",
                        "evidence": [writer["request"], writer["result"]],
                        "claim": "原生Write与成功回执可核；这不是唯一作者或最早原因认证。",
                    },
                ],
                "unknown": [
                    "不是正式调查；其他修改、最早引入和机制解释尚未在本样例验收。"
                ],
            }
        ],
    }
    bound = check(engine, encode(doc), save=True)
    assert not bound["issues"] and len(bound["edges"]) == 2
    audit["report_id"] = bound["report_id"]
    audit["graph"] = {
        "nodes": len(bound["nodes"]),
        "confirmed_edges": len(bound["edges"]),
        "semantic_verified": False,
    }
    audit["index_bytes"] = store.path.stat().st_size
    audit["passed"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)
    print(encode(audit))
    store.close()


if __name__ == "__main__":
    main()
