"""Human-readable disclosure of the same time-atom selection used by HTTP.

Only original message excerpts produce raw-preview receipt rows. Operation and
body locators are navigation: printing their references is not reading the body.
"""
from __future__ import annotations

import json


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _is_preview(row):
    return (isinstance(row.get("ref"), str) and row["ref"].startswith("raw:")
            and isinstance(row.get("preview"), str))


def preview_rows(data):
    return [row for page in data.get("sections", {}).values() for row in page.get("rows", [])
            if _is_preview(row)]


def render(data):
    node = data["node"]
    out = [f"# 时间原子 {node['kind']}:{node['key']} · 截至 {node['at']}",
           "范围 " + _json(data["scope"]),
           "视图 " + data["view"] + "；分组是索引，不是因果链；原文入口不等于全文已读。"]
    if data.get("participants"):
        out += ["## 全范围参与者目录（确认操作与候选分列，不是根因判定）", _json(data["participants"])]
    navigation = data.get("body_sources")
    if navigation:
        out += ["## 历史正文入口（不是当前快照；正文另行展开）", _json(navigation)]
    labels = {"writes": "已索引写入/产出", "reads": "已索引读取/输入",
              "candidates": "候选/尚未确定效应的调用", "messages": "已记录任务与输入消息"}
    for name, page in data["sections"].items():
        out.append("## " + labels.get(name, name))
        out.append(f"共 {page['total']} 条；已展示 {len(page['rows'])} 条；"
                   f"offset={page['offset']}；剩余 {page['remaining']} 条。")
        for row in page["rows"]:
            if _is_preview(row):
                # This address line is owned by the renderer. All historical
                # text is indented, so even quoted raw-address-looking lines
                # cannot masquerade as additional delivery receipt entries.
                out.append(f"- {row.get('ts') or '?'} {row['ref']} · 原始字段片段 · {row.get('chars', '?')} 字")
                out.append("  " + _json({k: v for k, v in row.items() if k != "preview"}))
                out.append("  摘录:\n    " + row["preview"].replace("\n", "\n    "))
            else:
                out.append("- 操作导航 " + _json(row))
        if page.get("next_query"):
            out.append("续读 " + _json(page["next_query"]))
        elif not page["rows"] and page.get("query") and page["total"]:
            out.append("展开 " + _json(page["query"]))
    out += ["## 原始材料与边界", "原始记录索引 " + _json(data["raw_index"]),
            "原生调用索引 " + _json(data["events_query"]),
            "覆盖边界 " + _json(data["coverage"])]
    if data.get("warnings"):
        out.append("警告 " + _json(data["warnings"]))
    if data.get("stale_annotation_sources"):
        out.append("失效的关系注释来源 " + _json(data["stale_annotation_sources"]))
    out.append(data["note"])
    return "\n".join(out)
