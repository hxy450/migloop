"""Pure disclosure of selected annotations; never admission, search or proof."""
from collections import Counter
from copy import deepcopy

FIELDS = {"annotation_offset": 0, "annotation_limit": None,
          "relation_offset": 0, "relation_limit": None}


def validate(**options):
    for name, default in FIELDS.items():
        value = options.get(name, default)
        if name.endswith("limit") and value is None:
            continue
        if type(value) is not int or value < (1 if name.endswith("limit") else 0):
            raise ValueError(f"{name} 必须是{'1–200' if name.endswith('limit') else '非负'}整数")
        if name.endswith("limit") and value > 200:
            raise ValueError(f"{name} 必须在1–200之间")


def _counts(values, key):
    return dict(sorted(Counter(str(v.get(key, "unknown")) for v in values).items()))


def _page(total, offset, count, requested, *, summary=False):
    next_offset = (0 if count < total else None) if summary else (
        offset + count if offset + count < total else None)
    return {"total": total, "offset": offset, "returned": count,
            "limit": count, "requested_limit": requested,
            "remaining": max(0, total - (count if summary else offset + count)),
            "next_offset": next_offset, "mode": "summary" if summary else "page"}


def project(annotations, kind, key, details, *, annotation_offset=0,
            annotation_limit=None, relation_offset=0, relation_limit=None):
    """Keep original indices so focused summaries can reopen exhaustive pages."""
    options = dict(annotation_offset=annotation_offset, annotation_limit=annotation_limit,
                   relation_offset=relation_offset, relation_limit=relation_limit)
    validate(**options)
    summary = not details and all(value == FIELDS[name] for name, value in options.items())
    indexed = list(enumerate(annotations))
    if summary and kind == "file":
        indexed.sort(key=lambda pair: not any(r.get("path") == key for r in pair[1]["relations"]))
    limit = annotation_limit if annotation_limit is not None else len(annotations) if details else 4
    selected = indexed[annotation_offset:annotation_offset + limit]
    shown = []
    for index, annotation in selected:
        relations = annotation["relations"]
        candidates = [r for r in relations if r.get("path") == key] if summary and kind == "file" else relations
        rlimit = relation_limit if relation_limit is not None else len(relations) if details else 6
        visible = candidates[relation_offset:relation_offset + rlimit]
        shown.append({**deepcopy({name: value for name, value in annotation.items() if name != "relations"}),
            "annotation_index": index,
            "relations": deepcopy(visible), "relation_count": len(relations),
            "relations_omitted": len(relations) - len(visible),
            "relation_status_counts": _counts(relations, "status"),
            "relation_kind_counts": _counts(relations, "kind"),
            "relation_page": _page(len(relations), relation_offset, len(visible), rlimit, summary=summary)})
    page = _page(len(annotations), annotation_offset, len(shown), limit, summary=summary)
    page["state_counts"] = _counts(annotations, "state")
    page["note"] = "回执state与关系status不同；returned不等于读写效应confirmed。省略注释不是未记录。"
    return shown, len(annotations) - len(shown), page


def _request(template, **args):
    out = deepcopy(template)
    out["args"].update(args)
    return out


def bind(row, template, row_offset):
    """All continuations repeat the same selected raw row and query scope."""
    if not row.get("annotation_page"):
        return
    page = row["annotation_page"]
    base = _request(template, offset=row_offset, limit=1, details=True,
                    annotation_offset=0, annotation_limit=1, relation_offset=0, relation_limit=40)
    page["query"] = base
    refresh(row)


def refresh(row):
    page = row["annotation_page"]
    base = page["query"]
    page["next_query"] = (_request(base, annotation_offset=page["next_offset"])
                          if page["next_offset"] is not None else None)
    for annotation in row["annotations"]:
        rp = annotation["relation_page"]
        limit = min(200, max(1, rp.get("requested_limit") or 40))
        rp["next_query"] = (_request(base, annotation_offset=annotation["annotation_index"],
                                     relation_offset=rp["next_offset"], relation_limit=limit)
                            if rp["next_offset"] is not None else None)


def compact(row, *, annotations=1, relations=1):
    """Fold only our recoverable disclosure shape, retaining original counts."""
    if not isinstance(row.get("annotation_page"), dict) or not isinstance(row["annotation_page"].get("query"), dict):
        return None
    out = deepcopy(row)
    out["annotations"] = out["annotations"][:annotations]
    page = out["annotation_page"]
    page.update(_page(page["total"], page["offset"], len(out["annotations"]),
                      page["requested_limit"], summary=page["mode"] == "summary"))
    out["annotations_omitted"] = page["total"] - len(out["annotations"])
    for annotation in out["annotations"]:
        annotation["relations"] = annotation["relations"][:relations]
        rp = annotation["relation_page"]
        rp.update(_page(rp["total"], rp["offset"], len(annotation["relations"]),
                        rp["requested_limit"], summary=rp["mode"] == "summary"))
        annotation["relations_omitted"] = annotation["relation_count"] - len(annotation["relations"])
    out["annotation_budget_folded"] = True
    refresh(out)
    return out


def continuations(row):
    page = row.get("annotation_page") or {}
    queries = []
    if page.get("next_query"):
        queries.append({"kind": "annotation_page", "ref": row.get("ref"), "next_query": page["next_query"]})
    for annotation in row.get("annotations", []):
        rp = annotation.get("relation_page") or {}
        if rp.get("next_query"):
            queries.append({"kind": "relation_page", "ref": row.get("ref"),
                            "annotation_index": annotation["annotation_index"], "next_query": rp["next_query"]})
    return deepcopy(queries)
