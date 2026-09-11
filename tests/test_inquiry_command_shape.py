import pytest

from migloop.inquiry.command_shape import read_only_shape
from tests.test_inquiry_core import build, record, result, ts, use


@pytest.mark.parametrize(
    "command",
    [
        "cat A.ets",
        "cd /proj && grep -n 'Span' A.ets | head -20",
        "sed -n '20,60p' /proj/A.ets",
        "wc -l A.ets\nls /proj",
        "grep needle A.ets || true",
        "cat 'space path/A.ets';",
    ],
)
def test_literal_standard_read_shapes(command):
    assert read_only_shape(command)


@pytest.mark.parametrize(
    "command",
    [
        "false && cp a A.ets",
        "grep needle A.ets\nrm A.ets",
        "cat A.ets > B.ets",
        "cat A.ets # read\nrm A.ets",
        "sed -i 's/a/b/' A.ets",
        "sed -n '1,9w out' A.ets",
        "sed -n '1e rm A.ets' A.ets",
        "sed -n 1p *",
        "rg --pre python A.ets",
        "printf -v name test",
        "cat $(python x.py)",
        "cat `python x.py`",
        "find . -delete",
        "grep x A.ets | tee B.ets",
        "alias cat=rm; cat A.ets",
        "python patch.py",
        "cat A.ets &",
        "cat A.ets &&",
        "cat 'unterminated",
        'cat A.ets; "&&" cp a A.ets',
        "eval cat A.ets",
        "sed -n 1p -i A.ets",
        "grep needle A.ets || (cp a A.ets)",
        "cat A.ets; printf test",
    ],
)
def test_uncertain_or_writing_shapes_stay_visible(command):
    assert read_only_shape(command) is None


def test_classification_does_not_create_effects_or_hide_mixed_record(tmp_path):
    engine = build(
        tmp_path,
        [
            record(1, use("r", "Bash", command="grep x A.ets")),
            record(2, result("r", "x")),
            record(
                3,
                use("r2", "Read", file_path="A.ets"),
                use("w", "Bash", command="python patch.py A.ets"),
            ),
        ],
    )
    calls = engine.query({"op": "file", "key": "A.ets", "at": ts(5), "view": "calls"})
    assert calls["folded_read_calls"] == 1 and calls["total"] == 1
    assert calls["rows"][0]["tools"] == ["Read", "Bash"]
    all_calls = engine.query(
        {
            "op": "file",
            "key": "A.ets",
            "at": ts(5),
            "view": "calls",
            "include_reads": True,
        }
    )
    assert all_calls["total"] == 2
    assert not engine.store.rows("SELECT * FROM effects WHERE op='write'")
    # The full-text search is never limited by the presentation fold.
    assert (
        engine.query(
            {
                "op": "search",
                "kind": "file",
                "key": "A.ets",
                "at": ts(5),
                "terms": ["grep"],
            }
        )["total"]
        == 1
    )
    engine.store.close()
