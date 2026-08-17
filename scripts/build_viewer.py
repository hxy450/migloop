# -*- coding: utf-8 -*-
"""把 trace JSON 注入 viewer 模板,产出自包含 HTML。
用法: python build_viewer.py trace-arch9.json [--out dist/migloop-arch9.html]
"""
import json
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from migloop.render import build_html, load_template


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out", default=None)
    ap.add_argument("--template", default=None)
    args = ap.parse_args()

    with open(args.trace, encoding="utf-8") as f:
        data = json.load(f)
    if args.template:
        with open(args.template, encoding="utf-8") as f:
            template = f.read()
    else:
        template = load_template()
    html = build_html(data, template)

    out = args.out or os.path.join(ROOT, "dist", "migloop-" + os.path.splitext(os.path.basename(args.trace))[0] + ".html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("written -> %s (%.0f KB)" % (out, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main()
