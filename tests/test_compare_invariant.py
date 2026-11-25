"""对比页模板缺占位符时要炸 —— python -O 下也一样(移植自 hmigbot-plus e4e24dba)。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from migloop.render import compare

SRC = Path(__file__).resolve().parents[1] / "src"


def test_missing_placeholder_raises() -> None:
    with pytest.raises(AssertionError):
        compare.build_compare_html([], "<html>no placeholder</html>")


def test_missing_placeholder_raises_under_optimized_python() -> None:
    code = ("from migloop.render import compare\n"
            "try:\n    compare.build_compare_html([], '<html></html>')\n"
            "except AssertionError:\n    print('raised')\n")
    out = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(SRC)},
                         timeout=60)
    assert out.stdout.strip() == "raised", out.stderr
