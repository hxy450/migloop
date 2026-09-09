"""文本体量消融，不是 LLM token/准确率试验；只重放本地 render_file。"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from migloop import atoms, atoms_text, probe, service  # noqa: E402

TITLE = "文本体量消融，不是LLM token/准确率试验"
SOURCE_FILES = ("atoms.py", "atoms_collect.py", "atoms_text.py", "filestory.py", "service.py", "probe.py")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((REPO / "src/migloop" / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def saved_queries(run_dir: Path, sid: str) -> list[dict[str, Any]]:
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    transcript = probe._transcript_calls(str(run_dir))
    seq = transcript if transcript is not None else metrics["transcript"]["seq"]
    return [{"kind": "saved_query", "label": metrics["label"], "sid": sid,
             "source": str(run_dir.relative_to(REPO)), "source_kind": "transcript" if transcript is not None else "metrics",
             "source_step": i, "source_result_ref": row.get("id"), "source_is_error": row.get("is_error"),
             "saved_input": row.get("input") or {}, "historical_return_chars": row.get("chars")}
            for i, row in enumerate(seq, 1) if row.get("tool") == "file"]


def mention_parts(text: str) -> tuple[list[str], list[str]]:
    """Return non-mention content and the mention section; content may follow it."""
    outside: list[str] = []
    section: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## 提到它的命令("):
            inside = True
        elif inside and line.startswith("## "):
            inside = False
        (section if inside else outside).append(line)
    return outside, section


def candidate_rows(section: list[str]) -> list[str]:
    return [line for line in section if re.match(r"^- (?:v\d+ 窗口|最新版之后) \|", line)]


def compare(ledger: Any, cwd: str, query: dict[str, Any]) -> dict[str, Any]:
    original = dict(query["saved_input"])
    hint = str(original.pop("path", ""))
    # via is navigation metadata, not a render_file argument. Both arms use identical other arguments.
    ignored = {k: original.pop(k) for k in ("sid", "via", "m_n") if k in original}
    allowed = set(inspect.signature(atoms_text.render_file).parameters) - {"ledger", "hint", "root", "m_n"}
    unsupported = sorted(set(original) - allowed)
    if unsupported:
        return {**query, "status": "unsupported_arguments", "unsupported": unsupported}
    atom = atoms.file_atom(ledger, hint, original.get("v"), with_diff=False, with_content=False)
    if atom is None:
        return {**query, "status": "missing_file_in_current_ledger"}
    outputs = {n: atoms_text.render_file(ledger, hint, root=cwd, m_n=n, **original) for n in (40, 0)}
    if any(text.startswith("⛔") for text in outputs.values()):
        return {**query, "status": "invalid_current_window", "return": outputs[0], "effective_args": original,
                "current_file": atom["path"], "current_anchor_v": atom["v"], "current_total_versions": atom["n_versions"]}
    outer40, section40 = mention_parts(outputs[40])
    outer0, section0 = mention_parts(outputs[0])
    mentions = atom.get("mentions") or []
    missing = [m for m in mentions if m.get("effect") is None]
    eligible = [m for m in missing if original.get("m_all") or m.get("cls") not in atoms_text._MENTION_FOLD]
    recovery_args = {k: v for k, v in original.items() if k != "m_from"}
    restored: list[str] = []
    recovery_pages = 0
    for start in range(1, len(eligible) + 1, 40):
        text = atoms_text.render_file(ledger, hint, root=cwd, m_n=40, m_from=start, **recovery_args)
        restored.extend(candidate_rows(mention_parts(text)[1]))
        recovery_pages += 1
    # This extra diagnostic explicitly changes m_all as well; it is not part of the two-arm size comparison.
    all_args = {k: v for k, v in recovery_args.items() if k != "m_all"}
    all_restored: list[str] = []
    for start in range(1, len(missing) + 1, 40):
        text = atoms_text.render_file(ledger, hint, root=cwd, m_n=40, m_from=start, m_all=True, **all_args)
        all_restored.extend(candidate_rows(mention_parts(text)[1]))
    restored40 = atoms_text.render_file(ledger, hint, root=cwd, m_n=40, **original)
    important = [line for line in outer40 if any(word in line for word in
                 ("无法复原", "内容未知", "断点", "部分已知", "外部输入", "候选", "实录外"))]
    spine = [line for line in outer40 if line.startswith("- v")]
    count_lines = [line for line in section0 if line.startswith(("## 提到它的命令(", "已入账的", "折叠 ", "候选仅计数"))]
    checks = {
        "non_mention_sections_identical": outer40 == outer0,
        "writer_spine_preserved": all(line in outer0 for line in spine),
        "unknown_and_candidate_signals_preserved": all(line in outer0 for line in important),
        "mention_header_count_preserved": (section40[:1] == section0[:1]),
        "zero_mode_has_no_candidate_rows": not candidate_rows(section0),
        "zero_mode_has_expansion_hint_when_needed": not eligible or any("m_n=40" in line for line in section0),
        "explicit_40_restores_baseline_exactly": restored40 == outputs[40],
        "explicit_40_pagination_recovers_all_eligible_candidates": len(restored) == len(eligible),
        "explicit_all_with_40_pagination_recovers_all_missing_candidates": len(all_restored) == len(missing),
    }
    chars40, chars0 = len(outputs[40]), len(outputs[0])
    return {**query, "status": "ok" if all(checks.values()) else "check_failed", "current_file": atom["path"],
            "current_anchor_v": atom["v"], "current_total_versions": atom["n_versions"],
            "effective_common_args": {"path": hint, "root": cwd, **original}, "ignored_navigation_or_treatment_args": ignored,
            "anchor_note": "saved v retained" if original.get("v") is not None else "saved v omitted; both arms use current latest version",
            "chars_m_n_40": chars40, "chars_m_n_0": chars0, "chars_saved": chars40 - chars0,
            "reduction_pct": round((chars40 - chars0) / chars40 * 100, 3) if chars40 else 0,
            "output_sha256": {str(n): digest(text) for n, text in outputs.items()},
            "preserved": {"writer_spine_rows": len(spine), "unknown_candidate_signal_rows": len(important),
                          "signal_lines": important, "count_lines": count_lines},
            "candidates": {"all_mentions": len(mentions), "missing_read_write": len(missing),
                           "eligible_with_same_m_all": len(eligible), "folded_with_same_m_all": len(missing) - len(eligible),
                           "displayed_m_n_40": len(candidate_rows(section40)), "displayed_m_n_0": len(candidate_rows(section0)),
                           "recovery_m_n_40_pages": recovery_pages, "recovered_eligible_rows": len(restored),
                           "recovered_all_rows_with_explicit_m_all": len(all_restored),
                           "recovered_eligible_sha256": digest("\n".join(restored))},
            "checks": checks}


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [r for r in rows if r.get("status") in ("ok", "check_failed")]
    before = sum(r["chars_m_n_40"] for r in measured)
    after = sum(r["chars_m_n_0"] for r in measured)
    return {"queries": len(measured), "chars_m_n_40": before, "chars_m_n_0": after, "chars_saved": before - after,
            "reduction_pct": round((before - after) / before * 100, 3) if before else 0,
            "check_failures": sum(r["status"] == "check_failed" for r in measured),
            "excluded_queries": len(rows) - len(measured)}


def main() -> None:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("query-size.json"))
    args = parser.parse_args()
    source_before = source_hashes()
    dice_run = REPO / "docs/experiments/2026-09-08-verdict-ui/dice_via3/chain02-EntryAbility.ets/rep1"
    cases_base = REPO / "docs/experiments/2026-09-07-six-cases"
    cases_label = "cases_tools6" if (cases_base / "cases_tools6").is_dir() else "cases_tools4"
    runs = [(dice_run, "49d451b1", "EntryAbility.ets"),
            (cases_base / cases_label / "chain10-SplashPage.ets", "ff019d8a", "SplashPage.ets"),
            (cases_base / cases_label / "chain08-MemberCenterPage.ets", "ff019d8a", "MemberCenterPage.ets")]
    ledger_cache: dict[str, tuple[Any, str]] = {}
    ledger_info: dict[str, Any] = {}
    queries: list[dict[str, Any]] = []
    for run, sid, target in runs:
        rows = saved_queries(run, sid)
        if sid not in ledger_cache:
            print(f"Building ledger once: {sid}", flush=True)
            started = time.perf_counter()
            session = service.locate_session(sid)
            ledger = service.session_ledger(session)
            cwd = service.session_cwd(session)
            ledger_cache[sid] = (ledger, cwd)
            ledger_info[sid] = {"identity": atoms.ledger_identity(ledger), "session": session,
                                "build_seconds": round(time.perf_counter() - started, 3),
                                "agents": len(ledger.agents), "files": len(ledger.stories)}
            print(f"Built {sid}: {ledger_info[sid]}", flush=True)
        ledger, cwd = ledger_cache[sid]
        targets = [r for r in rows if str(r["saved_input"].get("path", "")).endswith(target)]
        if not targets:
            raise RuntimeError(f"No saved file call for {target} in {run}")
        target_path = targets[0]["saved_input"]["path"]
        atom = atoms.file_atom(ledger, target_path)
        if atom is None:
            raise RuntimeError(f"Target absent in current ledger: {target_path}")
        # Fixed, documented supplemental versions: generation, saved repair-window endpoints, latest.
        versions = {1, atom["n_versions"]}
        for row in targets:
            for key in ("v", "v_from", "v_to"):
                v = row["saved_input"].get(key)
                if isinstance(v, int) and 1 <= v <= atom["n_versions"]:
                    versions.add(v)
        if len(versions) < 3 and atom["n_versions"] >= 3:
            versions.add(max(2, atom["n_versions"] // 2))
        supplemental = [{"kind": "supplemental_version", "label": targets[0]["label"], "sid": sid,
                         "source": str(run.relative_to(REPO)), "source_kind": "documented_version_sample",
                         "selection": "generation v1, saved repair-window endpoints and latest", "target": target,
                         "saved_input": {"path": target_path, "v": v}} for v in sorted(versions)]
        for query in [*rows, *supplemental]:
            result = compare(ledger, cwd, query)
            queries.append(result)
            print(f"{query['kind']} {target} {result.get('current_anchor_v')}: {result.get('chars_m_n_40')} -> {result.get('chars_m_n_0')} [{result['status']}]", flush=True)
    source_after = source_hashes()
    sources_changed = source_before != source_after
    report = {"title": TITLE, "generated_at": datetime.now(timezone.utc).isoformat(),
              "method": "Current render_file and the same cached ledger per sid; only m_n changes from 40 to 0 in the paired text-size comparison.",
              "limitations": ["Character counts are Python len(str), not bytes or LLM tokens; no model was called and no accuracy was evaluated.",
                              "Historical return character counts are context only; they are not a baseline because tool code and current ledger can differ.",
                              "Saved queries omitting v use current latest in both arms and are labelled explicitly.",
                              "Explicit m_n=40 is a page of up to 40 eligible rows; recovery checks paginate all rows, and folded classes additionally require m_all=True."],
              "selection": {"dice": "dice_via3", "0723": cases_label,
                            "fallback_reason": "cases_tools6 is absent from saved repository runs; use clearly labelled cases_tools4" if cases_label != "cases_tools6" else None},
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
              "source_sha256": source_before, "source_changed_during_run": sources_changed,
              "ledgers": ledger_info, "ledger_builds": len(ledger_cache),
              "saved_queries_total": totals([r for r in queries if r["kind"] == "saved_query"]),
              "supplemental_versions_total": totals([r for r in queries if r["kind"] == "supplemental_version"]),
              "all_queries_total": totals(queries),
              "by_case": {name: totals([r for r in queries if str((r.get("effective_common_args") or r["saved_input"]).get("path", "")).endswith(name)])
                          for name in ("EntryAbility.ets", "SplashPage.ets", "MemberCenterPage.ets")},
              "queries": queries}
    report["measurement_status"] = ("failed" if sources_changed or report["all_queries_total"]["check_failures"] else
                                    "completed_with_exclusions" if report["all_queries_total"]["excluded_queries"] else "completed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "total": report["all_queries_total"], "sources_changed": sources_changed}, ensure_ascii=False), flush=True)
    if sources_changed or report["all_queries_total"]["check_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
