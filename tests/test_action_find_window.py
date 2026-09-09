"""A failed literal lookup is not a request to retransmit an unrelated prefix."""
import pytest

from migloop import atoms_text, search_terms


def test_miss_discloses_exact_searched_suffix_without_sending_prefix():
    body = "secret prefix" * 1000
    piece, note = atoms_text._window(body, 7000, offset=250, find="needle")
    assert piece == "" and "未命中" in note
    assert f"[250,{len(body)})" in note and "去掉find" in note
    assert "secret prefix" not in note and "其他字段/范围" in note


def test_removing_find_still_opens_original_requested_range():
    body = "0123456789" * 100
    assert atoms_text._window(body, 30, offset=20)[0] == body[20:50]


@pytest.mark.parametrize("prefix", ["İ" * 700, "abc" * 700, "ΣΟΣ" * 700])
def test_find_keeps_original_offsets_and_shows_hit_even_with_small_budget(prefix):
    body = prefix + "Needle" + "tail" * 30
    piece, note = atoms_text._window(body, 12, find="needle")
    assert "Needle" in piece and len(piece) <= 12
    start = len(prefix) - 6
    assert piece == body[start:start + 12]
    assert f"第 {start + 1}-" in note


def test_find_original_offset_excludes_earlier_hit_after_unicode_expansion():
    body = "İ" * 100 + "needle" + "x" * 10 + "needle"
    assert search_terms.literal_span(body, "needle", 107) == (116, 122)
    assert search_terms.literal_span(body, "needle", 123) is None


def test_keyword_larger_than_budget_is_not_silently_clipped():
    piece, note = atoms_text._window("abcdef", 3, find="abcdef")
    assert piece == "" and "超过 max_chars=3" in note and "正文未展开" in note


def test_lower_expanding_match_maps_to_one_original_character():
    assert search_terms.literal_span("xxİyy", "i\u0307") == (2, 3)
    piece, _ = atoms_text._window("xxİyy", 1, find="i\u0307")
    assert piece == "İ"


def test_eof_is_not_misreported_as_a_full_field_zero_match():
    piece, note = atoms_text._window("needle", 10, offset=50, find="needle")
    assert piece == "" and "EOF" in note and "未命中" not in note


def test_empty_field_miss_explicitly_has_empty_search_range():
    piece, note = atoms_text._window("", 10, find="needle")
    assert piece == "" and "[0,0)" in note and "共 0 字" in note


@pytest.mark.parametrize("body", ["ΟΣΑ", "İΟΣΑ"])
def test_contextual_lowercase_does_not_claim_small_slice_contains_literal(body):
    piece, note = atoms_text._window(body, 2, find="οσ")
    assert piece == "" and "不是零命中" in note and "上下文" in note
    piece, _ = atoms_text._window(body, 4, find="οσ")
    assert "οσ" in piece.lower()
