"""Read-only indexer for the two frozen Codex JSONL rollouts."""

from __future__ import annotations

import json
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterator


def strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if len(sys.argv) == 5 and sys.argv[1] == "--validate-reference":
        reference = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        sources = {Path(name).name: Path(name) for name in sys.argv[3:]}
        failures = []
        for case in reference["cases"]:
            for evidence in case["evidence"]:
                path = sources[evidence["file"]]
                raw = path.read_text(encoding="utf-8").splitlines()[evidence["line"] - 1]
                record = json.loads(raw)
                actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                if actual != evidence["record_sha256"]:
                    failures.append((case["id"], evidence["line"], "record_sha256", actual, evidence["record_sha256"]))
                delivered = "\n".join(strings(record))
                fragments = evidence.get("quote_fragments", [])
                if not 1 <= len(fragments) <= 2:
                    failures.append((case["id"], evidence["line"], "quote_fragment_count", len(fragments)))
                for fragment in fragments:
                    if fragment not in delivered:
                        failures.append((case["id"], evidence["line"], "quote_fragment_missing", fragment))
                call_id = evidence.get("call_id")
                if call_id is not None:
                    actual_call_ids = set()
                    stack = [record]
                    while stack:
                        value = stack.pop()
                        if isinstance(value, dict):
                            if isinstance(value.get("call_id"), str):
                                actual_call_ids.add(value["call_id"])
                            stack.extend(value.values())
                        elif isinstance(value, list):
                            stack.extend(value)
                    if call_id not in actual_call_ids:
                        failures.append((case["id"], evidence["line"], "call_id_missing", call_id, sorted(actual_call_ids)))
                if "excerpt_summary" not in evidence:
                    failures.append((case["id"], evidence["line"], "excerpt_summary_missing"))
        print(json.dumps({"evidence_count": sum(len(c["evidence"]) for c in reference["cases"]), "failures": failures}, ensure_ascii=False))
        raise SystemExit(1 if failures else 0)
    if len(sys.argv) > 3 and sys.argv[1] == "--hash-lines":
        path = Path(sys.argv[2])
        wanted = {int(value) for value in sys.argv[3:]}
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if number in wanted:
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                print(f"{path.name}:{number} sha256:{digest}")
        return
    if len(sys.argv) > 3 and sys.argv[1] == "--query":
        pattern = re.compile(sys.argv[2], re.IGNORECASE)
        for raw_name in sys.argv[3:]:
            path = Path(raw_name)
            for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not pattern.search(raw):
                    continue
                text = "\n".join(strings(json.loads(raw))).replace("\\n", "\n")
                match = pattern.search(text)
                if match is None:
                    continue
                start = max(0, match.start() - 450)
                end = min(len(text), match.end() + 900)
                call_ids = sorted(set(re.findall(r"(?:call|toolu)_[A-Za-z0-9_-]+", raw)))
                print(f"{path.name}:{number} calls={','.join(call_ids)}")
                print(text[start:end].replace("\r", " "))
                print("---")
        return
    for raw_name in sys.argv[1:]:
        path = Path(raw_name)
        changed: Counter[str] = Counter()
        mentioned: Counter[str] = Counter()
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            obj = json.loads(raw)
            text = "\n".join(strings(obj))
            for match in re.finditer(r"\*\*\* (?:Update|Add) File: ([^\s\"\\]+)", text):
                changed[match.group(1)] += 1
            for match in re.finditer(r"(?:/Users/ventiu/Desktop/HUAWEI/AIPPT_830_test/)?([\w./-]+\.ets)\b", text):
                mentioned[match.group(1)] += 1
        print(path.name)
        print("CHANGED")
        for name, count in changed.most_common(80):
            print(count, name)
        print("MENTIONED")
        for name, count in mentioned.most_common(80):
            print(count, name)


if __name__ == "__main__":
    main()
