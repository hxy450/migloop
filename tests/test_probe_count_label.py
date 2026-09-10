"""Execute the template's real pure label helper, not a copied implementation."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_time_trace_count_does_not_read_empty_legacy_steps_or_double_count_subitems():
    node = shutil.which("node")
    if not node:
        pytest.skip("optional Node runtime unavailable")
    template = (Path(__file__).parents[1] / "src/migloop/render/templates/fixchain.html").read_text(encoding="utf-8")
    code = template.split("    function probeCallCountText(data) {", 1)[1].split("    function renderProbe() {", 1)[0]
    code = "function probeCallCountText(data) {" + code
    cases = [{"steps": [], "query_trace": {"steps": [{"tool": "exec"}, {"tool": "batch", "items": [{}, {}]}]}},
             {"steps": [{}, {}, {}]}, {"steps": [], "query_trace": {"steps": []}}]
    code += "\nprocess.stdout.write(JSON.stringify(" + json.dumps(cases) + ".map(probeCallCountText)));"
    result = subprocess.run([node, "-e", code], check=True, capture_output=True, encoding="utf-8")
    assert json.loads(result.stdout) == ["2 条录制步骤 · 2 个批内项", "3 条调用记录", "0 条录制步骤 · 0 个批内项"]
