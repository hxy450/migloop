"""Offline progressive evidence cards. No production imports, queries or models.

Intentionally NOT lossless. The audit lists every default-omitted leaf. Full
refs stay literal; actual snippets have output ranges and honest source extents.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(compact(value).encode("utf-8")).hexdigest()


def join(path, name):
    return path + "/" + str(name).replace("~", "~0").replace("/", "~1")


def leaves(value, path=""):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, join(path, key))
    elif isinstance(value, list) and value:
        for i, child in enumerate(value):
            yield from leaves(child, join(path, i))
    else:
        yield path, value


def descendants(value, path=""):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from descendants(child, join(path, key))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from descendants(child, join(path, i))


class Presenter:
    def __init__(self, data, request, ledger, row_limit=None):
        if data.get("schema") not in {"migloop-time-changes/1", "migloop-time-view/1"}:
            raise ValueError("prototype supports only changes and file time views")
        self.data, self.request, self.ledger = data, deepcopy(request), ledger
        self.row_limit = row_limit
        self.text = ""
        self.shown, self.reason = set(), {}
        self.materials, self.queries = [], []
        self.current = data["scope"]
        self.target = self.current["key"]

    def line(self, text=""):
        self.text += str(text) + "\n"

    def take(self, obj, path, key, default=None):
        if key not in obj:
            return default
        value = obj[key]
        self.shown.update(p for p, _ in leaves(value, join(path, key)))
        return value

    def hide(self, value, path, reason):
        for pointer, _ in leaves(value, path):
            self.reason[pointer] = reason

    def query(self, label, query, path=None):
        """One explicit parent scope; audit stores the composed real query.

        The display is not claimed to be independently pasteable without that
        scope. This is parameter composition, not a server-side ambient cursor.
        """
        query = deepcopy(query)
        scope = query.pop("scope", self.current)
        args = query.setdefault("args", {})
        # These exact requests came from the already-bound saved query. Its
        # captured scope is authoritative; aliases in original args add no new
        # target/time. Reject a different target instead of silently widening.
        for name in ("path", "file"):
            if name in args:
                if not scope["key"].replace("\\", "/").endswith(args[name].replace("\\", "/")):
                    raise ValueError("query target differs from explicit scope")
                args.pop(name)
        from datetime import datetime
        for name, field in (("at", "at"), ("since_ts", "since_ts")):
            if name not in args:
                continue
            value, expected = args.pop(name), scope.get(field)
            parse = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")) if x is not None else None
            if parse(value) != parse(expected):
                raise ValueError("query time differs from explicit scope")
        full = {**query, "scope": deepcopy(scope)}
        same = all(scope.get(k) == self.current.get(k) for k in ("kind", "key", "at", "since_ts"))
        if same:
            self.line(label + "（加页头scope）: " + compact(query))
        else:
            self.line(label + "（独立范围，不能继承页头since）: " + compact(full))
        self.queries.append({"label": label, "query": full, "scope_binding": "page_header" if same else "explicit_independent"})
        if path:
            self.shown.update(p for p, _ in leaves(query, path))

    def header(self):
        self.line("渐进披露实验：只列下述已显示事实；未显示元数据/正文不算已读取。")
        self.line("ledger: " + str(self.ledger))
        scope = self.current
        self.line("页头scope（对象/时间只定义一次；含端点，since_ts=null表示无下界）: " + compact(scope))
        self.line("标‘加页头scope’的查询须把此完整对象加入query.scope；不是独立可粘贴命令，也不依赖隐藏会话状态。")
        for key in ("kind", "key", "at", "since_ts", "id"):
            self.take(scope, "/scope", key)
        self.line("调用成功不等于目标效应/净修改/语义修复；提及不等于作者。")

    def snippet(self, part, path, *, source=None, direction="记录", current=None):
        field = next((key for key in ("text", "preview", "diff") if isinstance(part.get(key), str)), None)
        if field is None:
            return
        ref = self.take(part, path, "ref", "原始ref未提供")
        pointer = self.take(part, path, "pointer")
        ts = self.take(part, path, "ts", part.get("record_ts"))
        line = self.take(part, path, "line")
        source = self.take(part, path, "source", source or "source未提供")
        kind = self.take(part, path, "preview_kind", field)
        start = self.take(part, path, "offset", part.get("preview_start"))
        if "preview_start" in part:
            start = self.take(part, path, "preview_start")
        text = self.take(part, path, field)
        source_range = f"[{start},{start + len(text)})" if type(start) is int else "未提供，不猜测"
        total = self.take(part, path, "preview_chars", self.take(part,path,"chars","未提供"))
        truncated = self.take(part, path, "preview_truncated", "未提供，不能认定完整")
        self.line(f"  {direction} | {source}:L{line} | {ts or '时刻未知，不算截止证据'}")
        self.line(f"  ref={ref}; pointer={pointer if pointer is not None else '原query未提供'}")
        self.line(f"  {kind} {source_range}，实显{len(text)}字符 / 来源表示总长{total}，截断={truncated}")
        relation = self.take(part, path, "scope_relation", "inherited")
        current = current or self.current
        if relation == "independent_antecedent":
            current = part.get("expand_query", {}).get("scope")
            if current is None:
                raise ValueError("antecedent without explicit scope")
            self.line(f"  独立前置证据：since_ts={compact(current.get('since_ts'))}，at={current['at']}；不是原since窗口内正文。")
        if "in_requested_range" in part:
            in_range = self.take(part, path, "in_requested_range")
            if in_range is not True:
                self.line("  警告：在原请求时间范围内=" + compact(in_range))
        self.line("  ──原文开始──")
        output_start = len(self.text)
        self.text += text
        output_end = len(self.text)
        self.line()
        self.line("  ──原文结束──")
        self.materials.append({"ref": ref, "pointer": pointer, "source": source, "line": line, "ts": ts,
            "selected_pointer": join(path, field), "representation": kind,
            "source_start": start, "source_end": start + len(text) if type(start) is int else None,
            "output_start": output_start, "output_end": output_end, "chars": len(text),
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "scope": deepcopy(current)})
        next_offset = self.take(part, path, "next_offset")
        if next_offset is not None:
            self.line("  未交付后段 next_offset=" + str(next_offset))
        # Native parts have executable exact field expansion. For generic file
        # previews, record-wide expansion is honest; a field pointer is unknown.
        query = part.get("expand_query") or part.get("query")
        if query is None and ref.startswith("raw:"):
            query = {"tool": "expand", "scope": current,
                     "args": {"refs": [{"ref": ref, "pointer": pointer}] if pointer is not None else [ref], "max_chars": 4000}}
        if query:
            self.query("  展开原文（当前未交付的部分）", query)

    def event(self, row, path, ordinal, related=False):
        status = self.take(row, path, "status", "unknown")
        classification = self.take(row, path, "classification")
        agent = self.take(row, path, "agent")
        author = self.take(row, path, "author_status", "unknown")
        self.line()
        self.line(f"事件 {ordinal} | {'关联余项，非目标效应认证' if related else status} | 工具 {self.take(row, path, 'tool', 'unknown')}")
        self.line(f"作者状态={author}; actor={agent or '未知'}; 来源主体={compact(self.take(row,path,'source_agents',[]))}")
        if related or "effect_status" in row:
            self.line(f"调用/记录状态={status}; 目标效应={self.take(row,path,'effect_status', 'unknown')}")
        if classification:
            self.line("关联类别=" + str(classification) + "; " + str(self.take(row, path, "association", "")))
        keys = ("operations", "operation_basis", "reference_status", "semantic_checked")
        self.line("; ".join(key + "=" + compact(self.take(row, path, key)) for key in keys if key in row))
        call = row.get("call_return", {})
        if call:
            keys = ("status", "unambiguous", "success", "subject", "nested_execution", "effect_certified")
            self.line("回执: " + "; ".join(k + "=" + compact(self.take(call, path + "/call_return", k)) for k in keys if k in call))
        native = row.get("native_io", {})
        if native:
            np = path + "/native_io"
            source = self.take(native, np, "source")
            self.line(f"原生记录: 请求{self.take(native,np,'request_total',0)} / 返回{self.take(native,np,'result_total',0)}；未显示部分={self.take(native,np,'parts_omitted',0)}")
            for key, label in (("requests", "请求"), ("results", "返回")):
                for i, part in enumerate(native.get(key, [])):
                    self.snippet(part, f"{np}/{key}/{i}", source=source, direction=label)
            # raw candidate pointers duplicate native_io payloads but can carry
            # a different excerpt. Do not call that excerpt delivered by proxy.
            if row.get("pointers"):
                self.hide(row["pointers"], path + "/pointers", "alternate_pointer_previews_not_delivered; native_io shown")
        else:
            for i, part in enumerate(row.get("pointers", [])):
                self.snippet(part, f"{path}/pointers/{i}", source=row.get("source"), direction=part.get("direction", "记录"))
        # A record can reference broader antecedent evidence even when actual
        # native snippets above remain inherited. Keep the distinction explicit.
        es = row.get("evidence_scope")
        if es and es.get("since_ts") != self.current.get("since_ts"):
            self.line(f"附带依据定位另用范围：since_ts={compact(es.get('since_ts'))}, at={es.get('at')}；不改变以上已显示片段的范围。")
            for key in ("kind", "key", "at", "since_ts"):
                self.take(es, path + "/evidence_scope", key)

    def record(self, row, path, ordinal):
        self.line()
        self.line(f"原始记录 {ordinal} | 关联={self.take(row,path,'association','unknown')}; 引用={self.take(row,path,'reference_status','unknown')}")
        self.line("来源主体=" + compact(self.take(row, path, "agents", [])) + "；不直接认定为目标写者")
        self.snippet(row, path)
        self.line(f"注释：本query选中{len(row.get('annotations',[]))}，原query已省略{self.take(row,path,'annotations_omitted',0)}。")
        for i, annotation in enumerate(row.get("annotations", [])):
            ap = f"{path}/annotations/{i}"
            self.line("注释调用: " + "; ".join(k + "=" + compact(self.take(annotation, ap, k))
                       for k in ("agent", "tool", "state", "use_ts", "done_ts") if k in annotation))
            relations = annotation.get("relations", [])
            matching = [(j, value) for j, value in enumerate(relations) if value.get("path") == self.target]
            other = [value for _, value in enumerate(relations) if value.get("path") != self.target]
            state_counts = dict(Counter(value.get("status", "unknown") for value in other))
            self.line(f"关系：原query总{self.take(annotation,ap,'relation_count',len(relations))}/已省略{self.take(annotation,ap,'relations_omitted',0)}；"
                      f"显示目标{len(matching)}，其它路径{len(other)}仅计数{compact(state_counts)}、未交付明细。")
            for j, relation in enumerate(relations):
                rp = f"{ap}/relations/{j}"
                if relation.get("path") != self.target:
                    self.hide(relation, rp, "non_target_relation_detail_not_delivered")
                    continue
                fields = ("kind", "status", "execution", "delivery", "operation_basis")
                self.line("  目标: " + "; ".join(k + "=" + compact(self.take(relation, rp, k)) for k in fields if k in relation))
                self.take(relation, rp, "path")
            if annotation.get("relation_page", {}).get("next_query"):
                self.query("  关系注释还有未交付项", annotation["relation_page"]["next_query"])
        if row.get("annotation_page", {}).get("next_query"):
            self.query("  注释还有未交付项", row["annotation_page"]["next_query"])

    def page(self):
        rows = self.data.get("rows", [])
        shown = rows if self.row_limit is None else rows[:self.row_limit]
        count = len(shown)
        start = self.take(self.data, "", "offset", 0)
        total = self.take(self.data, "", "total", len(rows))
        self.line(f"当前页 selected={len(rows)}，默认显示={count}，本页未交付={len(rows)-count}；范围内记录总数={total}。")
        for i, row in enumerate(rows):
            path = f"/rows/{i}"
            if i >= count:
                self.hide(row, path, "row_page_not_delivered")
                continue
            if self.request["tool"] == "changes":
                self.event(row, path, start + i)
            else:
                self.record(row, path, start + i)
        next_offset = start + count if start + count < total else None
        if next_offset is not None:
            query = deepcopy(self.request)
            query["scope"] = self.current
            query.setdefault("args", {}).update(offset=next_offset, limit=self.row_limit or self.data.get("limit", 40))
            self.query("继续主记录，不跳过默认未显示项", query)
        related = self.data.get("unclassified_related")
        if related is not None:
            rp = "/unclassified_related"
            self.line()
            self.line(f"关联余项：总{self.take(related,rp,'total')}；本次selected并显示{len(related.get('rows',[]))}；这些行不是已认证的目标修改。")
            alternate = sum(sum(isinstance(p.get("preview"), str) for p in row.get("pointers", []))
                            for row in related.get("rows", []) if row.get("native_io"))
            if alternate:
                self.line(f"本页采用native_io输入/返回片段；另{alternate}段定位器预览未默认交付，可能与下列片段不同，用技术详情恢复，不计已读。")
            for i, row in enumerate(related.get("rows", [])):
                self.event(row, f"{rp}/rows/{i}", i, related=True)
            if related.get("next_query"):
                self.query("继续关联余项", related["next_query"])
            if related.get("undated", {}).get("total", 0):
                self.query("查看未知时间余项（不算截止前证据）", related["undated"]["query"])

    def bodies(self):
        nav = self.data.get("body_sources")
        if not nav:
            return
        self.line()
        self.line(f"原文入口（导航不是已读正文）：共{self.take(nav,'/body_sources','total')}，本页显示{len(nav.get('entries',[]))}，其余{self.take(nav,'/body_sources','remaining')}。")
        for i, row in enumerate(nav.get("entries", [])):
            rp = f"/body_sources/entries/{i}"
            keys = ("kind", "source", "line", "record_ts", "ref", "pointer", "chars", "body_extent", "call_state",
                    "source_agents", "author_certified", "current_state_certified", "reference_status")
            self.line("入口 " + str(i) + ": " + "; ".join(k + "=" + compact(self.take(row,rp,k)) for k in keys if k in row))
            if row.get("query"):
                self.query("  读取该正文（本次实际交付0字符）", row["query"])
        if nav.get("query"):
            self.query("列全部原文入口", nav["query"])

    def boundaries(self):
        self.line()
        self.line("覆盖与未知（仅本次选中/已扫描来源，不是全历史完备）：")
        roots = [("", self.data), ("/unclassified_related", self.data.get("unclassified_related", {})),
                 ("/body_sources", self.data.get("body_sources", {}))]
        keys = ("counts", "source_count", "raw_scan_complete", "registered_scan_ok", "counts_scope", "complete", "causal_complete",
                "current_state_certified", "category_counts", "status_counts", "review_required_total", "excluded_covered_total",
                "kind_counts", "unknown_time_count", "remaining", "next_offset", "actual_limit", "requested_limit", "count_only")
        for path, value in roots:
            if not value:
                continue
            label = path or "主查询"
            parts = [k + "=" + compact(self.take(value,path,k)) for k in keys if k in value]
            if parts:
                self.line(label + ": " + "; ".join(parts))
            for key in ("undated", "readonly", "non_native_mentions"):
                if isinstance(value.get(key), dict):
                    child = value[key]
                    child_keys = ("total", "remaining", "next_offset", "cutoff_evidence", "native_calls", "included_in_total_and_pagination")
                    self.line(label + "/" + key + ": " + "; ".join(k + "=" + compact(self.take(child, path+"/"+key, k)) for k in child_keys if k in child))
        # Keep every non-empty gap/anomaly/unsupported boundary, even for a row
        # hidden by the presentation page. Empty instances are counted, not
        # promoted into a claim of global absence. No raw body is traversed here.
        empty, notes, failure_flags = Counter(), {}, Counter()
        for path, value in descendants(self.data):
            if not isinstance(value, dict):
                continue
            for key in ("gaps", "anomalies", "unsupported_execution", "stale_annotation_sources", "withheld"):
                if key not in value:
                    continue
                field = self.take(value, path, key)
                if field:
                    self.line(path + "/" + key + "=" + compact(field))
                else:
                    empty[key] += 1
            for key in ("note", "scope_note"):
                if isinstance(value.get(key), str):
                    notes.setdefault(value[key], []).append((path, key))
            if "failed" in value:
                flag = self.take(value, path, "failed")
                failure_flags[compact(flag)] += 1
                if flag is True:
                    self.line(path + "/failed=true（保持该原始失败标记，不让外层成功覆盖）")
        if empty:
            self.line("选中对象里空边界字段的出现次数=" + compact(dict(empty)) + "；不等于未注册来源无缺口。")
        if failure_flags:
            self.line("选中原生部件failed标记分布=" + compact(dict(failure_flags)) + "；null仍未知，不按false计。")
        for text, positions in notes.items():
            self.line("边界: " + text)
            for path, key in positions:
                self.shown.add(join(path, key))

    def render(self):
        self.header()
        self.page()
        self.bodies()
        self.boundaries()
        details = deepcopy(self.request)
        details["scope"] = self.current
        details.setdefault("args", {})["details"] = True
        self.line()
        self.line("未显示字段明细不算read；同query details=true用于请求技术详情，仍受真实返回预算/分页限制。")
        self.query("技术详情", details)
        hidden = [{"pointer": path, "reason": self.reason.get(path, "technical_metadata_not_default_delivered"),
                   "value_sha256": digest(value)} for path, value in leaves(self.data) if path not in self.shown]
        # Output positions bind actual text, not arbitrary refs in metadata.
        for record in self.materials:
            actual = self.text[record["output_start"]:record["output_end"]]
            assert len(actual) == record["chars"] and hashlib.sha256(actual.encode()).hexdigest() == record["text_sha256"]
        audit = {"schema": "progressive-text-audit/1", "ledger": self.ledger,
            "selected_data_sha256": digest(self.data), "text_sha256": hashlib.sha256(self.text.encode()).hexdigest(),
            "lossless": False, "metadata_default_delivery": False,
            "raw_materials_actually_displayed": self.materials,
            "queries_displayed": self.queries, "omitted_fields": hidden,
            "omitted_reason_counts": dict(Counter(row["reason"] for row in hidden)),
            "selected_chars": len(compact(self.data)), "text_chars": len(self.text),
            "text_utf8_bytes": len(self.text.encode()), "lines": self.text.count("\n"),
            "shown_top_rows": min(len(self.data.get("rows", [])), self.row_limit or len(self.data.get("rows", []))),
            "selected_top_rows": len(self.data.get("rows", [])), "semantic_checked": False,
            "audit_not_appended_to_model_text": True, "production_receipt_implemented": False}
        return self.text, audit


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def self_checks():
    current = {"kind": "file", "key": "/x.ets", "at": "2026-09-10T00:00:00Z", "since_ts": "2026-09-09T00:00:00Z", "id": "scope:fixture"}
    earlier = {key: value for key, value in current.items() if key != "id"}
    earlier["since_ts"] = None
    ref = "raw:01234567890123456789:L1:01234567890123456789"
    part = {"ref": ref, "line": 1, "ts": "2026-09-08T00:00:00Z", "pointer": "/input", "preview": "actual\n原文",
        "preview_start": 7, "preview_chars": 99, "preview_truncated": True, "preview_kind": "decoded_native_payload_excerpt",
        "in_requested_range": False, "scope_relation": "independent_antecedent",
        "expand_query": {"tool": "expand", "scope": earlier, "args": {"refs": [{"ref": ref, "pointer": "/input"}]}}}
    row = {"status": "candidate", "agent": None, "author_status": "unknown", "tool": "Bash", "effect_status": "unknown",
        "call_return": {"status": "returned_success", "success": True, "effect_certified": False, "subject": "outer_code_host"},
        "native_io": {"source": "fixture.jsonl", "requests": [part], "results": [], "request_total": 1, "result_total": 0}}
    data = {"schema": "migloop-time-changes/1", "scope": current, "rows": [row], "offset": 0, "limit": 1, "total": 1,
        "gaps": [{"source": "missing.jsonl", "error": "unreadable"}], "complete": False, "causal_complete": False,
        "internal_only": "this must not be delivered"}
    request = {"tool": "changes", "args": {"path": "/x.ets", "at": current["at"], "since_ts": current["since_ts"]}}
    text, audit = Presenter(data, request, "fixture").render()
    assert "作者状态=unknown" in text and "returned_success" in text and "effect_certified=false" in text
    assert "独立前置证据：since_ts=null" in text
    assert audit["queries_displayed"][0]["query"]["scope"] == earlier
    assert audit["raw_materials_actually_displayed"][0]["source_start"] == 7
    assert len(audit["raw_materials_actually_displayed"]) == 1 and "this must not be delivered" not in text
    assert "missing.jsonl" in text and '"error":"unreadable"' in text
    assert any(row["pointer"] == "/internal_only" for row in audit["omitted_fields"])
    unknown = deepcopy(part)
    unknown.pop("preview_start")
    data["rows"][0]["native_io"]["requests"] = [unknown]
    _, audit = Presenter(data, request, "fixture").render()
    assert audit["raw_materials_actually_displayed"][0]["source_start"] is None
    return 8


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dice-capture", type=Path, required=True)
    parser.add_argument("--member-capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checked = self_checks()
    args.out.mkdir(parents=True, exist_ok=False)
    dice = json.loads((args.dice_capture / "selected.json").read_text(encoding="utf-8"))
    member = json.loads((args.member_capture / "selected.json").read_text(encoding="utf-8"))
    examples = [
        ("dice-changes", dice["items"][0]["data"], {"tool": "changes", "args": dice["items"][0]["args"]}, dice["ledger"], None),
        ("member-file-three", member["data"], member["request"], member["ledger"], 3),
        ("member-file-all-selected", member["data"], member["request"], member["ledger"], None)]
    summary = {"self_checks": checked}
    for name, data, request, ledger, row_limit in examples:
        before = digest(data)
        text, audit = Presenter(data, request, ledger, row_limit).render()
        assert digest(data) == before
        save(args.out / (name + ".txt"), text)
        save(args.out / (name + ".audit.json"), json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
        summary[name] = {key: audit[key] for key in ("selected_chars", "text_chars", "text_utf8_bytes", "lines", "shown_top_rows", "selected_top_rows", "omitted_reason_counts")}
        summary[name]["displayed_material_segments"] = len(audit["raw_materials_actually_displayed"])
    save(args.out / "measurements.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
