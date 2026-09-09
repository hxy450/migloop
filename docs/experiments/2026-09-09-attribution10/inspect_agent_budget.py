"""Read-only text-budget breakdown. Characters are not investigator token usage."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--v", type=int, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    case = json.loads((args.case_dir / "case.json").read_text(encoding="utf-8"))
    source = args.source or Path(case["source"])
    os.environ.update(MIGLOOP_FROZEN_POOL=case["pool"], MIGLOOP_FROZEN_ANCHOR="", MIGLOOP_FROZEN_ROOTS="")
    sys.path.insert(0, str(source / "src"))
    from migloop import atom_queries, atoms, atoms_text, service
    ledger = service.session_ledger(case["current_root"])
    data = atom_queries.agent_data(ledger, args.agent, args.v)
    text = atoms_text.render_agent(ledger, args.agent, args.v, root=service.session_cwd(case["current_root"]), reads=False, seen=True)
    indexed_refs = [atoms_text._core(action["seq"], ledger.locs.get(action["seq"])) for action in data["actions"]]
    visible_refs = [ref for ref in indexed_refs if ref in text]
    sections = defaultdict(int)
    section = "header"
    for line in text.splitlines():
        if line.startswith("## "):
            section = line.split("(", 1)[0][:40]
        sections[section] += len(line) + 1
    print(json.dumps({"source": str(source), "identity": atoms.ledger_identity(ledger),
        "query": {"agent": args.agent, "v": args.v, "reads": False, "seen": True}, "chars": len(text),
        "actions": len(data["actions"]), "action_kinds": dict(Counter(a["kind"] for a in data["actions"])),
        "reads": len(data["reads"]), "inbox": len(data["inbox"]), "sections_chars": dict(sections),
        "action_reference_presence": {"visible": len(visible_refs), "omitted": len(indexed_refs) - len(visible_refs),
            "ordered_visible_sha256": hashlib.sha256(json.dumps(visible_refs).encode()).hexdigest()},
        "longest_lines": [{"chars": len(line), "prefix": line[:100]} for line in sorted(text.splitlines(), key=len, reverse=True)[:8]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
