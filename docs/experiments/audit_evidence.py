"""Read-only evidence audit; no model calls and no transcript command execution.

python docs/experiments/audit_evidence.py <root.jsonl> [<prior/root.jsonl> ...]
--source selects a frozen migloop checkout for before/after comparisons.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--file", action="append", dest="hints")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source / "src"))
    from migloop import atoms, atoms_collect, atoms_text, filestory

    spec = importlib.util.spec_from_file_location(
        "audit_cites", args.source / "docs/experiments/2026-09-07-six-cases/cite_check.py"
    )
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    roots = [str(Path(r).resolve()) for r in args.roots]
    for root in roots:
        if not Path(root).is_file():
            parser.error(f"Missing transcript: {root}")
    start = time.perf_counter()
    agents = {}
    seq = [0]
    if hasattr(atoms_collect, "collect_cc_pool"):
        agents = atoms_collect.collect_cc_pool(roots, seq)
    else:
        for root in roots:
            agents.update(atoms_collect.collect_cc(root, seq))
    ledger = atoms.build_ledger(agents)
    elapsed = time.perf_counter() - start
    actions = {act.seq: act for agent in agents.values() for act in agent.actions}
    versions = [v for story in ledger.stories.values() for v in story.versions]
    refs = "\n".join(atoms_text._core(s, loc) for s, loc in ledger.locs.items())
    result = {
        "agents": len(agents), "stories": len(ledger.stories), "actions": len(actions),
        "build_seconds": round(elapsed, 3), "versions": len(versions),
        "known_versions": sum(v.content is not None for v in versions),
        "sealed_versions": sum(v.sealed for v in versions),
        "conditional_write_actions": sum(bool(a.detail.get("conditional")) for a in actions.values()),
        "conditional_read_actions": sum(bool(a.detail.get("conditional_reads")) for a in actions.values()),
        "scan_gap_actions": len(getattr(ledger, "scan_gaps", [])),
        "generated_references": len(ledger.locs), "ambiguous_locations": len(ledger.loc_ambiguous),
        "citations": checker.check_report(ledger, checker.Pool(roots), refs),
        "coverage": [],
    }
    files = list(dict.fromkeys(p for root in roots for p in
                              [root, *glob.glob(str(Path(root).with_suffix("")) + "/subagents/*.jsonl")]))
    hints = args.hints or ["SplashPage.ets", "EntryAbility.ets", "MemberCenterPage.ets"]
    raw_hits = {hint: set() for hint in hints}
    for path in files:
        with open(path, encoding="utf-8", errors="ignore") as stream:
            for number, line in enumerate(stream, 1):
                present = [hint for hint in hints if hint in line]
                if not present:
                    continue
                try:
                    json.loads(line)
                except ValueError:
                    continue
                for hint in present:
                    raw_hits[hint].add((str(Path(path).resolve()), number))
    for hint in hints:
        path = filestory.find_story_path(ledger.stories, hint)
        story = ledger.stories.get(path)
        reachable = set()
        if story:
            action_ids = {v.act_seq for v in story.versions if v.act_seq is not None}
            action_ids.update(s for (p, _), s in ledger.read_act.items() if p == path)
            action_ids.update(t.seq for t in story.touches)
            action_ids.update(m.seq for m in ledger.mentions.get(path, []))
            for s in action_ids:
                action = actions.get(s)
                if action and action.src:
                    source, use, end = action.src
                    reachable.add((str(Path(source).resolve()), use + 1))
                    if end is not None:
                        reachable.add((str(Path(source).resolve()), end + 1))
        hits = raw_hits[hint]
        result["coverage"].append({"file": hint, "raw_records": len(hits),
                                   "reachable_records": len(hits & reachable),
                                   "gap_records": len(hits - reachable)})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
