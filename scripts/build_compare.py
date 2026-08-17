# -*- coding: utf-8 -*-
"""开发用:trace JSON 列表 -> 跨会话对比 HTML。
用法: python build_compare.py trace-a.json trace-b.json ... [--out dist/compare.html]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from migloop.render import load_asset
from migloop.render import compare


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist", "migloop-compare.html"))
    args = ap.parse_args()

    traces = []
    for path in args.traces:
        with open(path, encoding="utf-8") as stream:
            traces.append(json.load(stream))
    font = compare.extract_font_face(load_asset("viewer.html"))
    html = compare.build_compare_html(traces, load_asset("compare.html"), font)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("written -> %s (%.0f KB)" % (args.out, os.path.getsize(args.out) / 1024))


if __name__ == "__main__":
    main()
