"""Execute the real model-usage renderer with a minimal DOM (Node, no npm deps)."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

import pytest

from migloop.adapters import codex, deveco
from migloop.render import load_template


@pytest.fixture(scope="module")
def render_usage() -> Any:
    node = shutil.which("node")
    if not node:
        pytest.skip("model-usage JavaScript tests require Node.js")
    template = load_template()

    def section(start: str, end: str) -> str:
        return start + template.split(start, 1)[1].split(end, 1)[0]

    js = r"""
const D = JSON.parse(require('fs').readFileSync(0, 'utf8'));
function element(tag) {
  return {tag, style: {}, children: [], textContent: '',
    appendChild(child) { this.children.push(child); return child; }};
}
const box = element('div');
const document = {createElement: element, getElementById: () => box};
"""
    js += section("  function fmtTok(n)", "  function hhmm(ts)")
    js += section("  function el(tag, cls, text)", "  function svgEl(tag)")
    js += section("  (function buildModels()", "  /* ---------- topo DAG ---------- */")
    js += "\nprocess.stdout.write(JSON.stringify(box));"

    def render(billing: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
        trace = {"billing": billing, "meta": {}, "agents": [], "totals": {}, **extra}
        result = subprocess.run(
            [node, "-e", js], input=json.dumps(trace), capture_output=True,
            text=True, encoding="utf-8", check=True, timeout=20,
        )
        return json.loads(result.stdout)

    return render


def rows(box: dict[str, Any]) -> list[dict[str, Any]]:
    table = next(c for c in box["children"] if c["tag"] == "table")
    return table["children"][0]["children"]


def test_all_models_total_includes_both_cache_write_ttls_and_keeps_details(render_usage: Any) -> None:
    # Historical noarch630 billing: the large input is mostly repeated cache reads.
    billing = {
        "claude-opus-4-8": {"req": 290, "inp": 9675, "cread": 125454492,
                            "cw5": 1385868, "cw1h": 4937293, "out": 636373},
        "claude-sonnet-5": {"req": 5510, "inp": 156412, "cread": 1770894567,
                            "cw5": 23118059, "cw1h": 0, "out": 4995772},
    }
    box = render_usage(billing, meta={"model": "claude-opus-4-8"},
                       agents=[{"model": "claude-sonnet-5"}, {"model": "claude-opus-4-8"}])
    rendered = rows(box)
    assert len(rendered) == 3
    total = rendered[0]
    assert total["className"] == "usage-total"
    assert [c["textContent"] for c in total["children"]] == [
        "全部模型合计", "5,800", "1.93B", "166.1K", "1.9B", "29.44M", "5.63M", "主线 + 子代理",
    ]
    assert total["children"][2]["title"] == "1,925,956,366 tokens"
    assert total["children"][6]["title"] == "5,632,145 tokens"
    assert [r["children"][0]["textContent"] for r in rendered[1:]] == ["sonnet-5", "opus-4-8"]
    assert rendered[2]["children"][7]["textContent"] == "主线 + 1 个子代理"
    table = next(c for c in box["children"] if c["tag"] == "table")
    assert table["innerHTML"].count("<th>") == 8
    assert any("不是去重后的原文大小" in c["textContent"] for c in box["children"])


def test_codex_total_does_not_count_cached_input_twice(render_usage: Any) -> None:
    billing: dict[str, dict[str, int]] = {}
    codex._billing_add(billing, "gpt-test", {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20})
    codex._billing_add(billing, "gpt-test", {"input_tokens": 80, "cached_input_tokens": 20, "output_tokens": 30})
    total = rows(render_usage(billing))[0]["children"]
    assert [c["textContent"] for c in total[2:7]] == ["180", "120", "60", "0", "50"]


def test_deveco_normalized_input_and_reasoning_output(render_usage: Any) -> None:
    billing: dict[str, dict[str, int]] = {}
    deveco._accumulate_usage(billing, [], {"tokens": {
        "input": 100, "cache": {"read": 40, "write": 20}, "output": 30, "reasoning": 10,
    }}, "model-test")
    total = rows(render_usage(billing))[0]["children"]
    assert [c["textContent"] for c in total[2:7]] == ["160", "100", "40", "20", "40"]


@pytest.mark.parametrize("bucket", [{"req": 1, "inp": 23, "out": 7}, {}])
def test_optional_cache_fields_default_to_zero(render_usage: Any, bucket: dict[str, int]) -> None:
    rendered = rows(render_usage({"model-test": bucket}))
    assert len(rendered) == 2
    cells = rendered[0]["children"]
    assert cells[2]["textContent"] == str(bucket.get("inp", 0))
    assert cells[5]["textContent"] == "0"
    assert cells[6]["textContent"] == str(bucket.get("out", 0))


@pytest.mark.parametrize("billing", [None, {}])
def test_missing_billing_does_not_fabricate_a_zero_total(render_usage: Any, billing: Any) -> None:
    box = render_usage(billing)
    assert box["style"]["display"] == "none"
    assert box["children"] == []


def test_existing_output_composition_is_preserved(render_usage: Any) -> None:
    box = render_usage({"model-test": {"req": 1, "inp": 10, "out": 60}},
                       totals={"output_split": {"thinking": 10, "text": 20, "tool": 30}})
    assert any(c["textContent"].startswith("Output 构成") for c in box["children"])
    assert rows(box)[0]["children"][6]["textContent"] == "60"
