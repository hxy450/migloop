"""Unrecoverable body windows return honest recovery pointers, not the same long index."""
from migloop import atom_queries, atoms, via
from tests.test_multi_search import _ledger, _call


def fixture(tmp_path):
    ledger = _ledger(tmp_path, _call("2026-01-01T00:00:01Z", "w", "Write",
        {"file_path": "/proj/A.ets", "content": "original"}))
    version = ledger.stories["/proj/A.ets"].versions[0]
    version.content = version.partial = None
    return ledger


def test_unavailable_range_keeps_exact_node_and_original_pointer(tmp_path):
    ledger = fixture(tmp_path)
    before = atoms.ledger_identity(ledger)
    args = {"path": "A.ets", "v": 1, "content": True, "start": 190, "n": 60}
    text = atom_queries.render_text(ledger, "/proj", "file", args)
    assert "请求正文不可满足：start=190, n=60" in text
    assert "没有交付所请求的正文行" in text and "未展开索引" in text
    assert "content=false" in text and "原始动作：#" in text
    assert "## 写者脊柱" not in text
    assert via.returned_node(ledger, "file", text) == ("file", "/proj/A.ets", 1)
    assert atoms.ledger_identity(ledger) == before
    second = atom_queries.render_text(ledger, "/proj", "file", {**args, "start": 700})
    assert "start=700, n=60" in second and text != second


def test_explicit_other_sections_and_full_index_are_not_suppressed(tmp_path):
    ledger = fixture(tmp_path)
    base = {"path": "A.ets", "v": 1, "content": True, "start": 190, "n": 60}
    for extra in ({"readers": True}, {"diff": True}, {"m_n": 40}, {"m_all": True}, {"content": False}):
        text = atom_queries.render_text(ledger, "/proj", "file", {**base, **extra})
        assert "## 写者脊柱" in text and "请求正文不可满足" not in text


def test_partial_and_known_content_keep_their_existing_disclosure_path(tmp_path):
    ledger = fixture(tmp_path)
    version = ledger.stories["/proj/A.ets"].versions[0]
    args = {"path": "A.ets", "v": 1, "content": True, "start": 1, "n": 1}
    version.partial = "partial fragment"
    text = atom_queries.render_text(ledger, "/proj", "file", args)
    assert "请求正文不可满足" not in text and "partial fragment" in text
    version.content, version.partial = "known body", None
    text = atom_queries.render_text(ledger, "/proj", "file", args)
    assert "known body" in text and "请求正文不可满足" not in text


def test_unlocated_unknown_body_does_not_offer_a_made_up_reference(tmp_path):
    ledger = fixture(tmp_path)
    ledger.locs.clear()
    text = atom_queries.render_text(ledger, "/proj", "file",
        {"path": "A.ets", "v": 1, "content": True, "start": 1, "n": 10})
    assert "原始定位未记录" in text and "原始动作：#" not in text
