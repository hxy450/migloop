# -*- coding: utf-8 -*-
"""开发用:trace JSON 列表 -> 跨会话对比 HTML。
用法: python build_compare.py trace-a.json trace-b.json ... [--out dist/compare.html]
"""
import argparse
import json
import os

import compare_build

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("traces", nargs="+")
    ap.add_argument("--out", default=os.path.join(HERE, "dist", "migloop-compare.html"))
    args = ap.parse_args()

    traces = [json.load(open(p, encoding="utf-8")) for p in args.traces]
    tpl = open(os.path.join(HERE, "compare_template.html"), encoding="utf-8").read()
    font = compare_build.extract_font_face(
        open(os.path.join(HERE, "viewer_template.html"), encoding="utf-8").read())
    html = compare_build.build_compare_html(traces, tpl, font)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("written -> %s (%.0f KB)" % (args.out, os.path.getsize(args.out) / 1024))


if __name__ == "__main__":
    main()
