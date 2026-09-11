"""Default page composition and the executable, pure time-tree contract."""
from pathlib import Path
import shutil
import subprocess

import pytest

from migloop import service


def test_default_explorer_is_time_scoped_and_script_safe(monkeypatch):
    monkeypatch.setattr(service, "fixchain_light", lambda _: {
        "sid": "example", "project": "</script><script>bad()</script>"})
    html = service.fixchain_html("unused")
    assert "__TIME_TREE_CORE__" not in html and "__FIXCHAIN_JSON__" not in html
    assert 'id="at"' in html and 'id="since"' in html
    assert 'id="graph"' in html and "MigloopTimeTree" in html
    assert "PROBE.byKey" not in html and "probeIndex(" not in html
    assert "bad()</script>" not in html
    assert "\\u003c/script>" in html


def test_executable_time_tree_contract():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the browser-independent JS contract")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, str(root / "tests/browser/time_tree_core.test.cjs")],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
