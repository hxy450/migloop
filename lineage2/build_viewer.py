# -*- coding: utf-8 -*-
"""把 trace JSON 注入 viewer 模板,产出自包含 HTML。
用法: python build_viewer.py trace-arch9.json [--out dist/migloop-arch9.html]
"""
import json
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out", default=None)
    ap.add_argument("--template", default=os.path.join(HERE, "viewer_template.html"))
    args = ap.parse_args()

    with open(args.trace, encoding="utf-8") as f:
        data = json.load(f)
    # compact 序列化;转义 </ 防止 JSON 字符串里的 </script> 截断内联块
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    # 源 transcript 可能带 U+FFFD 乱码替换符,部分发布通道会拒收,统一替换
    payload = payload.replace("�", "?")

    with open(args.template, encoding="utf-8") as f:
        tpl = f.read()
    if "__TRACE_JSON__" not in tpl:
        sys.exit("template missing __TRACE_JSON__ placeholder")
    html = tpl.replace("__TRACE_JSON__", payload)
    # 每页唯一标题:tab / 发布画廊全靠它区分(与 migloop.py page_title 同规则)
    meta = data.get("meta") or {}
    label = os.path.basename((meta.get("cwd") or "").rstrip("\\/")) or "Trace"
    sid8 = (meta.get("session_id") or "")[:8]
    title = ("%s · %s" % (label, sid8)) if sid8 else label
    html = html.replace("<title>MigLoop Trace</title>",
                        "<title>%s</title>" % title, 1)

    out = args.out or os.path.join(HERE, "dist", "migloop-" + os.path.splitext(os.path.basename(args.trace))[0] + ".html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("written -> %s (%.0f KB)" % (out, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main()
