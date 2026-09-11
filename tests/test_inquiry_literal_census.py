"""Literal excerpt accounting cannot certify a semantic absence."""

from migloop.inquiry.engine import content_windows


def test_windows_report_every_term_including_zero_and_repeated_hits():
    text = "Item(\n  key: 1,\n  key: 2,\n  value: 'Item Item'\n)\nother"
    selected, data = content_windows(text, ["item", "key", "absent"], 0)
    assert data["literal_counts"] == [
        {"term": "item", "matched_lines": 2, "occurrences": 3},
        {"term": "key", "matched_lines": 2, "occurrences": 2},
        {"term": "absent", "matched_lines": 0, "occurrences": 0},
    ]
    assert data["window_omitted_content_lines"] == 2
    assert "other" not in selected
    assert "not a syntax block" in data["selection"]


def test_context_does_not_certify_an_unsearched_property_is_absent():
    text = "Widget(\n" + "option,\n" * 12 + "preserve: true\n)"
    selected, data = content_windows(text, ["Widget"], 6)
    assert "preserve" not in selected and data["window_omitted_content_lines"] > 0
    assert data["literal_counts"] == [
        {"term": "Widget", "matched_lines": 1, "occurrences": 1}
    ]
    found, checked = content_windows(text, ["preserve"], 0)
    assert "preserve: true" in found
    assert checked["literal_counts"][0]["occurrences"] == 1


def test_literal_census_is_casefolded_including_multiline_literals():
    text = "Straße STRASSE\na\nb"
    selected, data = content_windows(text, ["strasse", "a\nb"], 0)
    assert data["literal_counts"][0]["occurrences"] == 2
    assert data["literal_counts"][1] == {
        "term": "a\nb", "matched_lines": 2, "occurrences": 1
    }
    assert "a\nb" in selected
    assert "selected payload" in data["literal_count_basis"]


def test_crlf_offsets_empty_text_and_overlapping_terms():
    selected, data = content_windows("a\r\nStraße\r\nx\r\ny", ["strasse\r\nx", "x"], 0)
    assert data["content_line_ranges"] == [[2, 3]]
    assert "Straße\nx" in selected and data["matched_lines"] == 2
    _, empty = content_windows("", ["missing"], 0)
    assert empty["literal_counts"][0]["occurrences"] == 0
    assert empty["window_omitted_content_lines"] == 0
