"""Shared disclosure hints must not obstruct otherwise valid investigations."""
import asyncio

import pytest

from migloop import atom_queries, investigation, mcp_server
from tests.test_temporal import corpus, ts


@pytest.mark.parametrize("tool,args", [
    ("diff", {"path": "/p/A.ets"}),
    ("blame", {"path": "/p/A.ets"}),
    ("events", {"file": "/p/A.ets"}),
    ("changes", {"path": "/p/A.ets"}),
])
def test_details_hint_preserves_selection_and_time(tmp_path, tool, args):
    ledger, _, _ = corpus(tmp_path)
    plain = investigation.query(ledger, tool, {**args, "at": ts(10)})
    detailed = investigation.query(ledger, tool, {**args, "at": ts(10), "details": True})
    detailed.pop("details")
    assert detailed.pop("details_effect")
    # A second query may hit the raw index cache; that is not selected evidence.
    plain.pop("cache", None)
    detailed.pop("cache", None)
    assert detailed == plain
    assert "LATE_SECRET" not in str(detailed)


@pytest.mark.parametrize("tool", ["diff", "blame"])
def test_scalar_time_parameters_accept_shared_hint_but_legacy_still_rejects(tool):
    assert atom_queries.parameters(tool, {"path": "/p/A.ets", "at": ts(10), "details": True})["details"]
    with pytest.raises(ValueError, match="details"):
        atom_queries.parameters(tool, {"path": "/p/A.ets", "v": 1, "details": True})


def test_hint_cannot_hide_invalid_selection_or_time(tmp_path):
    ledger, aid, _ = corpus(tmp_path)
    requests = [
        {"tool": "events", "args": {"at": ts(10), "details": "unparseable"}},
        {"tool": "diff", "args": {"path": "/p/A.ets", "at": ts(10), "details": True, "at_typo": ts(17)}},
        {"tool": "agent", "args": {"id": aid, "at": ts(10)}},
    ]
    out = investigation.batch(ledger, requests)
    assert out["delivery_summary"]["error"] == 2
    assert out["delivery_summary"]["ok"] == 1
    assert [item["item_index"] for item in out["attention"]] == [0, 1]
    assert all(not item["delivery"]["records"] for item in out["items"][:2])


@pytest.mark.parametrize("tool", ["events", "search"])
def test_path_alias_must_not_be_silently_replaced_by_inherited_file_scope(tmp_path, tool):
    ledger, _, _ = corpus(tmp_path)
    current = investigation.scope(ledger, "file", "/p/A.ets", ts(10))
    with pytest.raises(ValueError, match="不一致"):
        investigation.query(ledger, tool, {"scope": current, "path": "/p/B.ets"})
    with pytest.raises(ValueError, match="冲突"):
        investigation.query(ledger, tool, {"at": ts(10), "path": "/p/B.ets", "file": "/p/A.ets"})
    by_alias = investigation.query(ledger, tool, {"scope": current, "path": "/p/A.ets"})
    assert by_alias["scope"] == current


def test_delivery_counts_native_previews_but_not_body_navigation_as_full_reads():
    data = {"rows": [{"native_io": {
        "requests": [{"ref": "raw:s:L1:h", "preview": "request bytes"}],
        "results": [{"ref": "raw:s:L2:h", "preview": "returned bytes"}],
    }}], "events": [{"ref": "raw:s:L3:h", "pointer": "/input/content", "chars": 60000}]}
    refs = investigation._delivery(data)["records"]
    assert [ref["ref"] for ref in refs] == ["raw:s:L1:h", "raw:s:L2:h"]
    assert all(ref["extent"] == "preview_or_pointer" for ref in refs)


@pytest.mark.parametrize("tool,args", [("file", {"path": "/p/A.ets", "v": 1}),
                                     ("agent", {"id": "unused", "v": 1}), ("search", {"q": "needle"})])
@pytest.mark.parametrize("field", ["annotation_limit", "relation_limit"])
def test_scalar_legacy_does_not_silently_treat_zero_annotation_limit_as_default(tmp_path, tool, args, field):
    ledger, _, _ = corpus(tmp_path)

    class Backend:
        async def get_ledger(self, _sid):
            return ledger

        async def get_session_cwd(self, _sid):
            return "/p"

    server = mcp_server.build_server(Backend())
    blocks = asyncio.run(server.call_tool(tool, {"sid": "synthetic", **args, field: 0}))
    assert "注释分页仅用于at时间查询" in blocks[0].text
