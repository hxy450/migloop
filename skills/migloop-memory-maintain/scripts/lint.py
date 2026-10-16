"""Mechanical check of lessons added or revised since a base revision; run after apply, before export.

Hits are prompts for the maintainer, not verdicts: fix the lesson and apply again, or keep it with a line
"lint lesson-<ID>：<reason>" in REPORT.md. Also prints new active lessons against newly ingested cards.
Standard library only.

    python scripts/lint.py --store STORE --base BASE_REVISION [--report REPORT.md] [--all] [--json OUT.json]
"""
import argparse
import json
from pathlib import Path
import re
import sys

STORY = re.compile(r"来源[中里卡]|另一个?应用|又一个?应用|再一个?应用|第[二三四五六]个应用|[两三四五六]个应用都|追诉|返修[者中时]|"
                   r"上一次迁移|这次迁移|本次迁移|该应用[中里]|生成批次|首看时|生成者把|写者照|写者把")
VALUE = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?(?![0-9A-Za-z])|0x[0-9A-Fa-f]{8}(?![0-9A-Za-z])|"
                   r"(?<![\w.])\d+(?:\.\d+)?\s?(?:dp|dip|sp|vp|fp|px|ms)(?![A-Za-z])")
SOURCED = re.compile(r"例[：:如]|出处|定义|默认值|规范|\.xml|\.java|\.d\.ts|\.kt(?![A-Za-z])|@android:|\?attr|"
                     r"android:attr|API\s?\d+|版本|tokens|公式|换算")
ESCAPE = re.compile(r"待核|取近似|近似值|先空着|暂定|估一个|留空待|先写死")
TEXT = ("title", "when", "description", "unless", "why", "how", "check")
WAIVE = re.compile(r"lint\s+(lesson-[0-9a-f]{20})\s*[：:]")


def snapshot(store, revision):
    f = store / "snapshots" / f"{revision}.json"
    if not f.is_file():
        hits = sorted((store / "snapshots").glob(f"{revision}*.json"))
        if len(hits) != 1:
            sys.exit(f"snapshot {revision} not in {store}")
        f = hits[0]
    return json.loads(f.read_text(encoding="utf-8"))


def projects(store, snap):
    """Project names of the cards in this snapshot; long ones only, so short names do not match ordinary words."""
    names = set()
    for case, head in snap["cases"].items():
        f = store / "cases" / case / f"{head['revision']}.json"
        if f.is_file():
            name = ((json.loads(f.read_text(encoding="utf-8")).get("metadata") or {}).get("migration") or {}).get("project")
            if isinstance(name, str) and len(name.strip()) >= 5:
                names.add(name.strip())
    return sorted(names)


def items(lesson, field):
    v = lesson.get(field)
    return [v] if isinstance(v, str) else [x for x in v or [] if isinstance(x, str)]


def lint(lesson, names):
    hits = []
    title = lesson.get("title", "")
    if len(title) > 80:
        hits.append(("title_long", "title", f"{len(title)} 字"))
    if len(lesson.get("how") or []) > 8:
        hits.append(("how_long", "how", f"{len(lesson['how'])} 步"))
    for field in TEXT:
        for text in items(lesson, field):
            for m in STORY.finditer(text):
                hits.append(("story", field, text[max(0, m.start() - 12):m.end() + 20]))
            low = text.casefold()
            for name in names:
                if name.casefold() in low:
                    hits.append(("app_name", field, name))
            if field == "title":
                continue
            if not SOURCED.search(text):
                for m in VALUE.finditer(text):
                    hits.append(("value", field, text[max(0, m.start() - 16):m.end() + 8]))
            if field in ("how", "check"):
                for m in ESCAPE.finditer(text):
                    hits.append(("escape", field, text[max(0, m.start() - 16):m.end() + 16]))
    return hits


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--store", required=True)
    p.add_argument("--base", required=True, help="revision the delivery started from")
    p.add_argument("--report", help="REPORT.md with 'lint lesson-<ID>：理由' lines")
    p.add_argument("--all", action="store_true", help="check every active lesson, not only changed ones")
    p.add_argument("--json")
    a = p.parse_args()
    store = Path(a.store)
    head = json.loads((store / "HEAD.json").read_text(encoding="utf-8"))["revision"]
    now, base = snapshot(store, head), snapshot(store, a.base)
    names = projects(store, now)
    active = {k: v for k, v in now["lessons"].items() if v.get("status") == "active"}
    added = [k for k in active if k not in base["lessons"]]
    revised = [k for k in active if k in base["lessons"] and active[k].get("version") != base["lessons"][k].get("version")]
    scope = sorted(active) if a.all else sorted(added + revised)
    waived = set(WAIVE.findall(Path(a.report).read_text(encoding="utf-8"))) if a.report and Path(a.report).is_file() else set()
    rows, open_ids = [], set()
    for k in scope:
        for check, field, excerpt in lint(active[k], names):
            rows.append({"lesson": k, "check": check, "field": field, "excerpt": excerpt, "waived": k in waived})
            if k not in waived:
                open_ids.add(k)
    new_cards = [c for c in now["cases"] if c not in base["cases"]]
    retired = [k for k, v in now["lessons"].items() if v.get("status") == "retired"
               and base["lessons"].get(k, {}).get("status") != "retired"]
    summary = {"head": head, "base": base["revision"], "checked": len(scope), "hits": len(rows),
               "lessons_with_open_hits": len(open_ids), "by_check": {}, "active_before": sum(
                   v.get("status") == "active" for v in base["lessons"].values()), "active_after": len(active),
               "new_lessons": len(added), "revised_lessons": len(revised), "retired_lessons": len(retired),
               "new_cards": len(new_cards),
               "new_lessons_per_new_card": round(len(added) / len(new_cards), 2) if new_cards else None}
    for r in rows:
        summary["by_check"][r["check"]] = summary["by_check"].get(r["check"], 0) + 1
    for r in rows:
        print(f"{r['lesson']}\t{r['check']}\t{r['field']}\t{'(已说明) ' if r['waived'] else ''}{r['excerpt']}")
    print(json.dumps(summary, ensure_ascii=False))
    if a.json:
        Path(a.json).write_text(json.dumps({"summary": summary, "hits": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if open_ids else 0)


if __name__ == "__main__":
    main()
