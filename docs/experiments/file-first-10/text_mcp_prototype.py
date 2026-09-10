"""Offline, lossless readable-text MCP presentation experiment (NOT runtime).

Only identical JSON values are shared. All anchors resolve in the same response.
The experimental receipt hashes actual UTF-8 text, and records only material
actually present in the decoded body, not navigation targets. No model calls.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import yaml


MARKER = "\nMIGLOOP_TEXT_PROTOTYPE_RECEIPT "
SCHEMA = "migloop-text-prototype/1"
EXTENTS = ["derived_diff", "derived_line", "raw_field_segment", "raw_segment", "preview_or_pointer", "decoded_native_payload_excerpt"]
ARRAY_CHILDREN = ("rows", "items", "records", "requests", "results", "pointers", "events")
MAP_CHILDREN = ("unclassified_related", "undated", "unknown_records", "native_io")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def catalogs(data):
    scopes, refs, pointers = {}, {}, {}
    for value in walk(data):
        if not isinstance(value, dict):
            continue
        if {"kind", "key", "at", "since_ts"} <= value.keys():
            scopes.setdefault(canonical(value), value)
        if isinstance(value.get("ref"), str) and value["ref"].startswith(("raw:", "#")):
            refs.setdefault(value["ref"], value["ref"])
        if isinstance(value.get("pointer"), str):
            pointers.setdefault(value["pointer"], value["pointer"])
    return {"scopes": list(scopes.values()), "refs": list(refs), "pointers": list(pointers)}


def material_records(data, catalog):
    """Known payload containers only; do not descend into queries/nav/delivery.

    This is an experimental projection, not evidence authentication. Counts are
    visible occurrences, never independent accesses or confirmed relations.
    """
    scopes = {canonical(value): i for i, value in enumerate(catalog["scopes"])}
    refs = {value: i for i, value in enumerate(catalog["refs"])}
    pointers = {value: i for i, value in enumerate(catalog["pointers"])}
    records = Counter()
    delivered_scopes = set()

    def visit(value, current=None):
        if not isinstance(value, dict):
            return
        if isinstance(value.get("scope"), dict):
            current = value["scope"]
        if value.get("scope_relation") == "independent_antecedent":
            current = value.get("expand_query", {}).get("scope")
        if current is not None:
            delivered_scopes.add(scopes[canonical(current)])
        ref = value.get("ref")
        field = next((key for key in ("text", "preview", "diff") if isinstance(value.get(key), str)), None)
        if ref in refs and field is not None:
            extent = ("derived_diff" if "diff" in value else
                      "derived_line" if "line" in value and ref.startswith("#") else
                      "raw_field_segment" if "text" in value and value.get("pointer") is not None else
                      "raw_segment" if "text" in value else
                      "decoded_native_payload_excerpt" if value.get("preview_kind") == "decoded_native_payload_excerpt" else
                      "preview_or_pointer")
            # Include actual text in the internal identity. Equal coordinates
            # with different previews are not silently coalesced.
            record = (scopes[canonical(current)] if current is not None else None,
                      refs[ref], pointers.get(value.get("pointer")), EXTENTS.index(extent),
                      value.get("offset", value.get("preview_start")), len(value[field]), value.get("next_offset"), value[field])
            records[record] += 1
        for name in ARRAY_CHILDREN:
            for child in value.get(name, []) if isinstance(value.get(name), list) else []:
                visit(child, current)
        for name in MAP_CHILDREN:
            if isinstance(value.get(name), dict):
                visit(value[name], current)
        # A batch envelope carries the selected payload under data. The other
        # children above intentionally exclude source catalogs and continuations.
        if isinstance(value.get("data"), dict):
            visit(value["data"], current)

    visit(data)
    return {"scope_indices": sorted(delivered_scopes),
            "records": [list(key[:-1]) + [count] for key, count in records.items()]}


class ReadableDumper(yaml.SafeDumper):
    def ignore_aliases(self, value):
        return not isinstance(value, (dict, list)) and not (isinstance(value, str) and (len(value) >= 60 or value.startswith("raw:")))

    def generate_anchor(self, node):
        self.last_anchor_id += 1
        label = "shared"
        if isinstance(node, yaml.nodes.MappingNode):
            keys = {key.value for key, _ in node.value}
            if {"kind", "key", "at", "since_ts"} <= keys:
                label = "scope"
            elif {"tool", "args"} <= keys:
                label = "query"
        elif isinstance(node, yaml.nodes.ScalarNode) and node.value.startswith("raw:"):
            label = "raw"
        return f"{label}_{self.last_anchor_id}"


def literal(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value,
                                   style="|" if "\n" in value else None)


ReadableDumper.add_representer(str, literal)


def intern_tree(value, memo):
    """Intern equal containers/long strings, preserving all keys and list order."""
    if isinstance(value, dict):
        result = {key: intern_tree(child, memo) for key, child in value.items()}
    elif isinstance(value, list):
        result = [intern_tree(child, memo) for child in value]
    else:
        result = value
    if isinstance(value, (dict, list)) or isinstance(value, str) and (len(value) >= 60 or value.startswith("raw:")):
        key = canonical(value)
        return memo.setdefault(key, result)
    return result


def render(data, request):
    catalog = catalogs(data)
    document = {"format": SCHEMA,
        "reading_rule": "&name defines a value here; *name repeats exactly that value. All definitions are in this response. No extra query is needed to decode aliases.",
        "receipt_rule": "Receipt binds visible text, not causal truth. Catalog entries alone are navigation, not reads. Records count visible occurrences, not independent access or authorship.",
        "record_columns": ["scope_index", "ref_index", "pointer_index", "extent_index", "offset", "chars", "next_offset", "occurrences"],
        "extent_values": EXTENTS, "catalog": catalog, "data": data}
    body = yaml.dump(intern_tree(document, {}), Dumper=ReadableDumper,
                     allow_unicode=True, sort_keys=False, width=160)
    receipt = {"schema": "migloop-text-prototype-receipt/1", "ledger": data.get("ledger"),
        "request_sha256": sha(canonical(request)), "text_sha256": sha(body),
        **material_records(data, catalog), "semantic_checked": False}
    return body + MARKER + compact(receipt)


def validate(rendered, request, expected=None):
    body, marker, tail = rendered.rpartition(MARKER)
    if not marker:
        raise ValueError("missing experimental marker")
    receipt = json.loads(tail)
    if receipt.get("schema") != "migloop-text-prototype-receipt/1":
        raise ValueError("wrong receipt schema")
    if receipt.get("text_sha256") != sha(body) or receipt.get("request_sha256") != sha(canonical(request)):
        raise ValueError("text/request hash mismatch")
    document = yaml.safe_load(body)
    if document.get("format") != SCHEMA:
        raise ValueError("wrong readable format")
    data = document["data"]
    if document["catalog"] != catalogs(data):
        raise ValueError("catalog mismatch")
    if receipt.get("ledger") != data.get("ledger") or receipt.get("semantic_checked") is not False:
        raise ValueError("ledger/semantic boundary mismatch")
    actual = material_records(data, document["catalog"])
    if any(receipt.get(key) != value for key, value in actual.items()):
        raise ValueError("actual visible-material receipt mismatch")
    if expected is not None and canonical(data) != canonical(expected):
        raise ValueError("lossless round-trip mismatch")
    return data


def expect_failure(callback):
    try:
        callback()
    except (ValueError, KeyError):
        return
    raise AssertionError("corruption was accepted")


def checks():
    scope = {"kind": "file", "key": "x", "at": "2026-09-10T00:00:00Z", "since_ts": "2026-09-09T00:00:00Z", "id": "scope:example"}
    earlier = {key: value for key, value in scope.items() if key != "id"}
    earlier["since_ts"] = None
    part = {"ref": "raw:example:L1", "pointer": "/content", "preview": "yes\nfalse\n: *not_an_alias\n",
        "preview_start": 12, "preview_kind": "decoded_native_payload_excerpt",
        "scope_relation": "independent_antecedent", "expand_query": {"tool": "expand", "scope": earlier,
        "args": {"refs": [{"ref": "raw:example:L1", "pointer": "/content"}]}}}
    data = {"ledger": "fixture", "scope": scope, "gaps": ["unknown"], "rows": [{"native_io": {"requests": [part]}}],
        "body_sources": {"entries": [{"ref": "raw:navigation:L3", "pointer": "/body"}]},
        "next_query": {"scope": scope, "tool": "changes", "args": {"offset": 1}},
        "null": None, "false": False, "empty": "", "unicode": "原文", "timestamp_string": "2026-09-10"}
    request = {"tool": "changes"}
    rendered = render(data, request)
    assert validate(rendered, request, data) == data
    body, _, tail = rendered.rpartition(MARKER)
    receipt = json.loads(tail)
    assert len(receipt["records"]) == 1
    assert catalogs(data)["scopes"][receipt["records"][0][0]] == earlier
    assert receipt["records"][0][4] == 12
    assert EXTENTS[receipt["records"][0][3]] == "decoded_native_payload_excerpt"
    expect_failure(lambda: validate(rendered + " ", {"tool": "other"}))
    expect_failure(lambda: validate(body.replace("原文", "改写") + MARKER + tail, request))
    receipt["records"][0][5] += 1
    expect_failure(lambda: validate(body + MARKER + compact(receipt), request))
    # Duplicate values remain equal, and navigation is never counted as a read.
    repeated = {"ledger": "fixture", "items": [{"data": data}, {"data": data}]}
    text = render(repeated, request)
    assert validate(text, request, repeated) == repeated
    assert json.loads(text.rpartition(MARKER)[2])["records"][0][-1] == 2
    return 9


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def measure(data, request):
    json_body = compact(data)
    readable = render(data, request)
    parsed = validate(readable, request, data)
    body, _, receipt = readable.rpartition(MARKER)
    return readable, {"json_body_chars": len(json_body), "json_body_utf8_bytes": len(json_body.encode()),
        "text_body_chars": len(body), "text_body_utf8_bytes": len(body.encode()),
        "prototype_marker_receipt_chars": len(MARKER + receipt),
        "text_total_chars": len(readable), "text_total_utf8_bytes": len(readable.encode()),
        "body_char_reduction_percent": round(100 * (1 - len(body) / len(json_body)), 2),
        "text_total_vs_json_body_reduction_percent": round(100 * (1 - len(readable) / len(json_body)), 2),
        "roundtrip_exact": True, "data_sha256": sha(canonical(parsed)),
        "text_sha256": sha(body), "material_records": len(json.loads(receipt)["records"]),
        "visible_material_occurrences": sum(row[-1] for row in json.loads(receipt)["records"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    output = args.out or args.capture
    if args.out:
        output.mkdir(parents=True, exist_ok=False)
    count = checks()
    request_full = json.loads((args.capture / "request.json").read_text(encoding="utf-8"))
    request = {key: request_full[key] for key in ("requests", "max_chars")}
    results = {"schema": "text-prototype-measurement/1", "self_checks": count,
        "interpretation": "Same-tree serialization only. No token/model-quality claims; selected and projected have different delivery coverage.", "cases": {}}
    for name in ("selected", "projected"):
        data = json.loads((args.capture / f"{name}.json").read_text(encoding="utf-8"))
        rendered, metrics = measure(data, request)
        write_new(output / f"{name}.readable.txt", rendered)
        write_new(output / f"{name}.compact.json", compact(data))
        if name == "projected":
            # Byte-for-byte algorithm of current investigation.render_batch,
            # derived offline from the same saved tree; not a new MCP receipt.
            json_body = compact(data)
            receipt = {"schema": "migloop-investigation-receipt/1", "ledger": data["ledger"],
                "request_sha256": sha(canonical(request)), "body_sha256": sha(canonical(json_body))}
            current_wire = json_body + "\nMIGLOOP_INVESTIGATION_RECEIPT " + json.dumps(receipt, separators=(",", ":"))
            write_new(output / "projected.current-renderer.txt", current_wire)
            metrics["current_json_wire_chars"] = len(current_wire)
            metrics["current_json_wire_utf8_bytes"] = len(current_wire.encode())
            metrics["text_total_vs_current_json_wire_reduction_percent"] = round(100 * (1 - len(rendered) / len(current_wire)), 2)
        results["cases"][name] = metrics
        # A single page comparison is useful: batch deduplication and page
        # deduplication are materially different effects.
        first = next(item for item in data["items"] if "data" in item)
        rendered, metrics = measure(first["data"], {"tool": first["tool"], "args": first["args"]})
        write_new(output / f"{name}.first-page.readable.txt", rendered)
        metrics["item_index"] = first["item_index"]
        metrics["requested_offset"] = first["args"].get("offset")
        results["cases"][name + "_first_page"] = metrics
    results["capture_manifest_sha256"] = hashlib.sha256((args.capture / "capture.json").read_bytes()).hexdigest()
    results["renderer_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write_new(output / "measurements.json", json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
