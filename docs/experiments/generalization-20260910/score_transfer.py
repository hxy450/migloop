"""Validate reviewed transfer grades and summarize complete, manifest-bound arms.

No models, semantic inference, runtime fallback, or writes to frozen artifacts.
Only the package's hash-bound runner.verify is imported; reference bodies are
never parsed. Core contracts are parsed only by this separate scoring process.
Grade layout: GRADES/{raw|tools}/TASK-ID/repN.json. Run with Python -B.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

GRADE_SCHEMA = "migloop-transfer-grade/1"
SCORE_SCHEMA = "migloop-transfer-scores/1"
UNIT_OUTCOMES = ("correct", "partial", "missing", "wrong")
CLAIM_OUTCOMES = ("supported", "contradicted", "unsupported_asserted_as_fact", "explicitly_hypothetical")
TERMINAL = ("completed", "timeout", "incomplete")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _json(text):
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)


def read(path):
    return _json(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    """Explicit new outputs only. Never truncates an existing grade/summary."""
    body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(body)


def _load(path):
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("transfer_score_frozen_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


def verify_package(base, *, manifest_sha256=None):
    """Integrity verification, not authentication against a hostile filesystem.

    verify() hashes complete source/candidate/helper/private/settings trees; it
    does not build a ledger or execute historical commands. No current-code
    fallback is accepted, even if the package runner is unavailable.
    """
    base = Path(base).resolve()
    digest = sha(base / "manifest.json")
    manifest = read(base / "manifest.json")
    if manifest_sha256 is not None and manifest_sha256 != digest:
        raise ValueError("Unexpected transfer manifest SHA")
    if (manifest.get("schema") != "migloop-transfer-run/1"
            or manifest.get("status") != "frozen_ready"
            or read(base / "READY.json").get("manifest_sha256") != digest):
        raise ValueError("Frozen transfer manifest/READY required")
    runner_path = base / "run_transfer.py"
    if (runner_path.is_symlink() or sha(runner_path) != manifest["runner_origin"]["sha256"]
            or len([e for e in manifest["artifacts"] if e["path"] == "run_transfer.py"
                    and e["sha256"] == sha(runner_path)]) != 1):
        raise ValueError("Frozen package runner missing or changed")
    runner = _load(runner_path)
    if runner.verify(base) != manifest:
        raise ValueError("Frozen verifier returned different manifest")
    contracts_path = Path(manifest["inputs"]["contracts"]["path"])
    contracts = read(contracts_path)
    source = read(manifest["inputs"]["source_manifest"]["path"])
    cases = {c["id"]: c for c in manifest["cases"]}
    if len(cases) != len(manifest["cases"]) or not cases:
        raise ValueError("Nonempty unique case registry required")
    cores = {}
    for cohort in contracts["cohorts"]:
        # Exactly one core per cohort; any number of separately sealed references.
        entries = [a for a in cohort["artifacts"] if a["role"] == "core"]
        if len(entries) != 1:
            raise ValueError("Exactly one core artifact per cohort required")
        path = (contracts_path.parent / entries[0]["path"]).resolve()
        core = read(path)
        if core.get("schema") != "migloop-causal-core-contract/1" or not isinstance(core.get("units"), dict):
            raise ValueError("Unknown causal core contract")
        task_ids = cohort["task_ids"]
        required = {tid: [] for tid in task_ids}
        for key in core["units"]:
            if not isinstance(key, str) or "/" not in key:
                raise ValueError("Core key must be TASK-ID/unit-id")
            tid, uid = key.split("/", 1)
            if tid not in required or not uid or uid.strip() != uid:
                raise ValueError("Core has foreign task or invalid unit ID")
            required[tid].append(uid)
        if any(not units for units in required.values()):
            raise ValueError("Every frozen task needs a nonempty assessable core")
        cores[cohort["id"]] = {"path": path, "sha256": sha(path), "required": required}
    return {"base": base, "manifest": manifest, "manifest_sha256": digest,
            "runner": runner, "cores": cores, "cases": cases, "source": source}


def _case(context, case, rep, condition):
    if condition not in ("raw", "tools") or case not in context["cases"]:
        raise ValueError("Unknown condition or case")
    if type(rep) is not int or not 1 <= rep <= context["manifest"]["repetitions"]:
        raise ValueError("Invalid repetition")
    task = context["cases"][case]
    directory = context["base"] / condition / "runs" / case / f"rep{rep}"
    return task, directory, context["cores"][task["cohort"]]


def _metric(context, task, directory, condition):
    path = directory / "metrics.json"
    if not path.exists():
        return None, None
    metric = read(path)
    expected = {"condition": condition, "cohort": task["cohort"],
                "transfer_manifest_sha256": context["manifest_sha256"],
                "code_digest": context["manifest"]["code_digest"]}
    if any(metric.get(key) != value for key, value in expected.items()):
        raise ValueError("Run condition/cohort/manifest/code binding differs")
    if metric.get("automatic_retry") is not False or metric.get("format_repair") is not False:
        raise ValueError("Run retry/format protocol differs")
    return metric, sha(path)


def _native_initial_task(directory, metric, expected):
    """Narrow Codex recorder proof; never search arbitrary leaves for a task.

    The first response_item after the first turn_context must be the complete
    single-block user task. Earlier environment messages and later messages,
    quotes or tool results cannot rescue a mismatch. This is integrity evidence,
    not authentication of a hostile recorder or an OS isolation guarantee.
    """
    digest, session = metric.get("transcript_sha256"), metric.get("session_id")
    if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(session, str) or not session):
        raise ValueError("native_recording_binding_missing")
    raw = (directory / "transcript.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("native_transcript_hash_not_bound")
    # Parse the hash-checked bytes, not a separately reopened/normalized stream.
    rows = [_json(line) for line in raw.decode("utf-8").splitlines()]
    if (not rows or not isinstance(rows[0], dict) or rows[0].get("type") != "session_meta"
            or not isinstance(rows[0].get("payload"), dict)
            or rows[0]["payload"].get("id") != session):
        raise ValueError("native_session_identity_not_bound")
    turn_line, task_line = None, None
    for line, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError("unknown_native_record_layout")
        if row.get("type") == "turn_context":
            if turn_line is not None and task_line is None:
                raise ValueError("second_turn_before_initial_user")
            if turn_line is None:
                turn_line = line
        elif row.get("type") == "response_item" and turn_line is not None:
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("unknown_native_response_layout")
            user = payload.get("type") == "message" and payload.get("role") == "user"
            if task_line is not None:
                if user:
                    raise ValueError("additional_native_user_message")
                continue
            content = payload.get("content")
            if (not user or not isinstance(content, list) or len(content) != 1
                    or not isinstance(content[0], dict) or content[0].get("type") != "input_text"
                    or not isinstance(content[0].get("text"), str)):
                raise ValueError("initial_turn_response_is_not_complete_user_task")
            if content[0]["text"] != expected.decode("utf-8"):
                raise ValueError("initial_native_user_task_differs")
            task_line = line
    if turn_line is None or task_line is None:
        raise ValueError("initial_native_task_layout_missing")
    return {"native_transcript_sha256": digest, "native_session_id": session,
            "native_turn_context_line": turn_line, "native_task_line": task_line,
            "native_task_pointer": "/payload/content/0/text",
            "native_task_sha256": hashlib.sha256(expected).hexdigest()}


def _prompt_binding(context, metric, directory, condition, task):
    """Exact bytes, or the one proven Windows write_text LF->CRLF copy case."""
    audit = {"schema": "migloop-transfer-prompt-binding/1", "bound": False,
             "status": "unbound", "native_task_checked": False,
             "expected_sha256": None, "actual_sha256": None}
    try:
        expected = (context["base"] / task["prompts"][condition]).read_bytes()
        actual = (directory / "prompt.md").read_bytes()
        audit.update(expected_sha256=hashlib.sha256(expected).hexdigest(),
                     actual_sha256=hashlib.sha256(actual).hexdigest())
        if actual == expected:
            audit.update(bound=True, status="exact_bytes")
            return audit
        # Do not normalize mixed newlines, whitespace, BOM, text or final LF.
        if b"\r" in expected or b"\n" not in expected or actual != expected.replace(b"\n", b"\r\n"):
            audit["reason"] = "not_exact_bytes_or_pure_lf_to_crlf_copy"
            return audit
        audit["native_task_checked"] = True
        audit.update(_native_initial_task(directory, metric, expected))
        audit.update(bound=True, status="windows_crlf_copy_native_exact")
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        audit["reason"] = type(error).__name__ + ": " + str(error)
    return audit


def _health(context, metric, directory, condition, task):
    if metric is None:
        return "pending", [], None
    status = metric.get("status")
    if status in ("starting", "running"):
        return "pending", [], None
    failures = []
    if status not in TERMINAL:
        failures.append("non_evaluable_status:" + str(status))
    if (metric.get("actual_models") != [context["manifest"]["model"]]
            or metric.get("actual_effort") != context["manifest"]["effort"]):
        failures.append("model_or_effort_not_verified")
    if metric.get("recording_complete") is not True or metric.get("host_skill_catalog_absent") is not True:
        failures.append("recording_or_instruction_audit_incomplete")
    if condition == "tools" and (metric.get("postprocess") or {}).get("status") != "completed":
        failures.append("postprocess_not_completed")
    prompt_binding = _prompt_binding(context, metric, directory, condition, task)
    if not prompt_binding["bound"]:
        failures.append("run_task_prompt_not_bound")
    audit_path = directory / "immutability.json"
    audit = read(audit_path) if audit_path.exists() else []
    if (not isinstance(audit, list) or any(not isinstance(a, dict) for a in audit)
            or [a.get("phase") for a in audit] != ["before", "after"]
            or any(a.get("passed") is not True for a in audit)):
        failures.append("run_immutability_audit_not_passed")
    transcript_sha = metric.get("transcript_sha256")
    if transcript_sha is not None:
        transcript = directory / "transcript.jsonl"
        if not transcript.exists() or sha(transcript) != transcript_sha:
            failures.append("native_transcript_hash_not_bound")
        elif metric.get("session_id"):
            with transcript.open(encoding="utf-8") as handle:
                first = _json(handle.readline())
            if (first.get("type") == "session_meta"
                    and (first.get("payload") or {}).get("id") != metric["session_id"]):
                failures.append("native_session_identity_differs")
    return ("harness_failure" if failures else "evaluable"), failures, prompt_binding


def _pointer(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("Evidence pointer must be an explicit JSON pointer")
    if not pointer:
        return value
    for part in pointer[1:].split("/"):
        if re.search(r"~(?![01])", part):
            raise ValueError("Invalid JSON pointer escape")
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) >= len(value):
                raise ValueError("Evidence pointer index missing")
            value = value[int(key)]
        elif isinstance(value, dict) and key in value:
            value = value[key]
        else:
            raise ValueError("Evidence pointer does not resolve")
    return value


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)


def _native_ids(value):
    """Only native-shaped typed call/use/result fields, never prose mentions.

    Literal shape check only, NOT registered SourceSpec kind/time eligibility,
    one-to-one pairing, success, authorship, ordering, or code-host execution.
    """
    if not isinstance(value, dict):
        return set()
    found = set()
    kind = value.get("type")
    key = ("id" if kind == "tool_use" else "tool_use_id" if kind == "tool_result" else
           "call_id" if kind in ("function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output",
                                  "exec_command_begin", "exec_command_end", "patch_apply_begin", "patch_apply_end") else None)
    if key and isinstance(value.get(key), str) and value[key].strip():
        found.add(value[key])
    if key is not None:
        return found  # A typed tool block's contents are data, not new calls.
    # Descend only protocol structure, not arbitrary output/arguments objects.
    for field in ("payload", "msg", "message"):
        if isinstance(value.get(field), dict):
            found.update(_native_ids(value[field]))
    content = value.get("content")
    if isinstance(content, list):
        for block in content:
            found.update(_native_ids(block))
    return found


def _original(context, path, line):
    cache = context.setdefault("evidence_records", {})
    key = (str(path), line)
    if key not in cache:
        raw = None
        with path.open(encoding="utf-8") as handle:
            for number, text in enumerate(handle, 1):
                if number == line:
                    raw = text.rstrip("\r\n")
                    break
        if raw is None:
            raise ValueError("Original evidence physical line does not exist")
        try:
            record = _json(raw)
        except (ValueError, json.JSONDecodeError):
            record = None  # Plain attachments stay plain; no invented time/call.
        cache[key] = (raw, record)
    return cache[key]


def _timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an explicit ISO string or unknown null")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Timestamp timezone required")
    return stamp


def _evidence(items, context, cohort):
    """Check original coordinates against registry, not their semantic support."""
    if not isinstance(items, list):
        raise ValueError("Evidence must be an array")
    src = next(c for c in context["source"]["cohorts"] if c["id"] == cohort)
    pool = Path(context["manifest"]["inputs"]["source_manifest"]["path"]).parent / src["pool"]
    paths = [row["path"] for row in src["files"]]
    checked = Counter()
    for item in items:
        # Legacy reference identifiers remain valid as reviewer cross-references.
        if isinstance(item, str) and item.strip():
            checked["opaque_cross_reference_occurrences"] += 1
            continue
        if not isinstance(item, dict) or type(item.get("line")) is not int or item["line"] < 1:
            raise ValueError("Original evidence requires source and positive physical line")
        source = item.get("source")
        if not isinstance(source, str) or not source:
            raise ValueError("Original evidence source missing")
        normalized = source.replace("\\", "/")
        matches = [p for p in paths if normalized == p or normalized == str((pool / p).resolve()).replace("\\", "/")
                   or ("/" not in normalized and Path(p).name == normalized)]
        if len(matches) != 1:
            raise ValueError("Evidence source is foreign or ambiguous; use pool-relative path")
        original_path = pool / matches[0]
        raw, record = _original(context, original_path, item["line"])
        checked["physical_line_occurrences"] += 1
        # Source manifests freeze complete bytes but do not necessarily encode
        # SourceSpec policy. Never treat suffix/JSON appearance as native source
        # identity. Non-JSONL attachments are text; JSONL field comparisons stay
        # literal-only and explicitly leave source/time policy unverified.
        is_jsonl = original_path.suffix.lower() == ".jsonl"
        event_record = record if is_jsonl else None
        checked["jsonl_source_policy_unverified_occurrences" if is_jsonl else "text_attachment_occurrences"] += 1
        actual_ts = next((event_record[k] for k in ("timestamp", "ts", "time") if k in event_record), None) if isinstance(event_record, dict) else None
        for field in ("timestamp", "ts", "time"):
            if field in item:
                if _timestamp(item[field]) != _timestamp(actual_ts):
                    raise ValueError("Evidence timestamp differs from original record (unknown is not inferred)")
                checked["literal_timestamp_match" if item[field] is not None else "absent_timestamp_occurrences"] += 1
        for field in ("call_id", "callid"):
            if field in item:
                ids = _native_ids(event_record)
                if item[field] is None:
                    if ids:
                        raise ValueError("Evidence call ID declared absent but typed ID field exists")
                    checked["absent_typed_call_id_occurrences"] += 1
                    continue
                if not isinstance(item[field], str) or item[field] not in ids:
                    raise ValueError("Evidence call ID is not a native call/result field on this record")
                checked["typed_id_field_match"] += 1
        selected = _pointer(record, item["pointer"]) if "pointer" in item else record
        if "excerpt" in item:
            excerpt = item["excerpt"]
            if (not isinstance(excerpt, str) or not excerpt
                    or not (any(excerpt in text for text in _strings(selected))
                            or ("pointer" not in item and excerpt in raw))):
                raise ValueError("Exact evidence excerpt absent from raw/decoded selected content")
            checked["excerpt_occurrences"] += 1
    return checked


def _score(report, required, grade, context, cohort):
    units, claims = grade.get("units"), grade.get("claims")
    if not isinstance(units, list) or not isinstance(claims, list):
        raise ValueError("Units and claims arrays required")
    if (any(not isinstance(u, dict) or not isinstance(u.get("id"), str) for u in units)
            or len(units) != len(required) or {u.get("id") for u in units} != set(required)):
        raise ValueError("Every frozen core unit must appear exactly once")
    if (any(not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"] for c in claims)
            or len({c["id"] for c in claims}) != len(claims)):
        raise ValueError("Unique nonempty claim IDs required")
    if grade.get("claims_review_complete") is not True:
        raise ValueError("Full-report substantive claim review must be explicitly complete")
    evidence_checks = Counter()
    for item in units + claims:
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("Reviewed reason required")
        spans = item.get("report_spans", [])
        if not isinstance(spans, list) or any(not isinstance(s, str) or not s or s not in report for s in spans):
            raise ValueError("Exact report span is not present in this final report")
        evidence_checks.update(_evidence(item.get("evidence", []), context, cohort))
    for unit in units:
        if unit.get("outcome") not in UNIT_OUTCOMES:
            raise ValueError("Invalid unit outcome")
        if unit["outcome"] != "missing" and not unit.get("report_spans"):
            raise ValueError("Nonmissing unit needs an exact report span")
        if unit["outcome"] in ("correct", "wrong") and not unit.get("evidence"):
            raise ValueError("Correct/wrong unit needs original or frozen reference basis")
    for claim in claims:
        if claim.get("outcome") not in CLAIM_OUTCOMES or not claim.get("report_spans"):
            raise ValueError("Claim needs a valid outcome and exact span")
        if type(claim.get("major_error")) is not bool:
            raise ValueError("Claim major_error must be an explicit boolean")
        if claim["major_error"] and (claim["outcome"] not in CLAIM_OUTCOMES[1:3]
                or not any(isinstance(e, dict) for e in claim.get("evidence", []))):
            raise ValueError("Major needs an actual false assertion and original source basis")
    counts = {name: sum(u["outcome"] == name for u in units) for name in UNIT_OUTCOMES}
    asserted = [c for c in claims if c["outcome"] != "explicitly_hypothetical"]
    supported = sum(c["outcome"] == "supported" for c in asserted)
    major = sum(c["major_error"] for c in claims)
    return {"units": len(units), **counts, "correct_attribution_coverage": counts["correct"] / len(units),
            "asserted_claims": len(asserted), "supported_claims": supported,
            "attribution_precision": supported / len(asserted) if asserted else None,
            "major_errors": major, "file_pass": counts["correct"] == len(units) and major == 0,
            "full_report_no_contradicted_or_unsupported_assertions": all(c["outcome"] == "supported" for c in asserted),
            "claims_review_complete": True, "evidence_checks": dict(evidence_checks), "source_policy_verified": False,
            "evidence_check_scope": "Physical location and supplied literal fields only. SourceSpec identity/time policy is unverified, including JSONL journals: matching timestamp/typed ID literals do not certify native registration, temporal eligibility, pairing/success/author, or semantic support. Non-JSONL attachments have no authenticated event time/ID. Null time/call_id records absence, not a successful ID match. Opaque cross-references are unchecked. JSON pointers/decoded excerpts are independent per-physical-line checks, not MCP scope/delivery certification. claims_review_complete is the reviewer's declaration."}


def _validate(context, case, rep, grade, condition):
    task, directory, core = _case(context, case, rep, condition)
    metric, metric_sha = _metric(context, task, directory, condition)
    health, _, prompt_binding = _health(context, metric, directory, condition, task)
    if health != "evaluable":
        raise ValueError("A grade cannot certify an unready or harness-failed run")
    report_path = directory / "report.md"
    if not report_path.exists() or not report_path.read_text(encoding="utf-8").strip():
        raise ValueError("No final report for manual grade")
    expected = {"schema": GRADE_SCHEMA, "case": case, "rep": rep, "condition": condition,
                "cohort": task["cohort"], "report_sha256": sha(report_path), "metrics_sha256": metric_sha,
                "core_contract_sha256": core["sha256"], "transfer_manifest_sha256": context["manifest_sha256"]}
    if any(type(grade.get(k)) is not type(v) or grade[k] != v for k, v in expected.items()):
        raise ValueError("Grade artifact/case/rep/condition/cohort/report/core binding differs")
    result = _score(report_path.read_text(encoding="utf-8"), core["required"][case], grade, context, task["cohort"])
    result["prompt_binding"] = prompt_binding
    if sha(report_path) != expected["report_sha256"] or sha(directory / "metrics.json") != metric_sha:
        raise ValueError("Report/metrics changed during adjudication validation")
    if sha(directory / "prompt.md") != prompt_binding["actual_sha256"]:
        raise ValueError("Prompt copy changed during adjudication validation")
    if (prompt_binding.get("native_transcript_sha256")
            and sha(directory / "transcript.jsonl") != prompt_binding["native_transcript_sha256"]):
        raise ValueError("Native prompt proof changed during adjudication validation")
    return result


def validate_grade(base, case, rep, grade, *, condition, manifest_sha256=None):
    context = verify_package(base, manifest_sha256=manifest_sha256)
    result = _validate(context, case, rep, grade, condition)
    context["runner"].verify(context["base"])
    return result


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _stat(values):
    observed = [v for v in values if _number(v)]
    return {"observed_runs": len(observed), "expected_runs": len(values),
            "sum": sum(observed) if observed else None,
            "mean": sum(observed) / len(observed) if observed else None,
            "complete": len(observed) == len(values)}


def _cost(metric):
    metric = metric or {}
    usage = metric.get("usage") or {}
    def number(value):
        return value if _number(value) else None
    ins, outs = number(usage.get("input_total")), number(usage.get("output"))
    return {"input_tokens": ins, "output_tokens": outs,
            "tokens_total": ins + outs if ins is not None and outs is not None else None,
            "cache_read_tokens": number(usage.get("cache_read")),
            "cache_creation_tokens": number(usage.get("cache_creation")),
            "investigator_elapsed_seconds": number(metric.get("investigator_elapsed_seconds", metric.get("elapsed_seconds"))),
            "system_elapsed_seconds": number(metric.get("system_elapsed_seconds")),
            "postprocess_elapsed_seconds": number((metric.get("postprocess") or {}).get("elapsed_seconds"))}


def _mechanical(directory, metric):
    path = directory / "verdict.json"
    expected = (metric.get("postprocess") or {}).get("verdict_sha256")
    if not path.exists():
        if expected:
            raise ValueError("Bound mechanical verdict missing")
        return None
    if expected and sha(path) != expected:
        raise ValueError("Bound mechanical verdict changed")
    value = read(path)
    if value.get("schema") != "migloop-transfer-final-verification/1":
        raise ValueError("Unknown mechanical verdict schema")
    report = directory / "report.md"
    digest = sha(report) if report.exists() else None
    claimed = value.get("report_sha256")
    if claimed is not None and claimed != digest:
        raise ValueError("Mechanical report binding differs")
    bound = bool(expected and claimed is not None and claimed == digest)
    built = value.get("verification") or {}
    graph = built.get("argument_graph") or {}
    refs = [e for n in graph.get("nodes", []) for k in ("evidence", "counterevidence") for e in n.get(k, [])]
    refs.extend(e for edge in graph.get("edges", []) for e in edge.get("evidence", []))
    document = value.get("data")
    observed = bound and type(value.get("found")) is bool
    return {"verdict_sha256": sha(path), "report_bound": bound,
            "document_checks_pass": bool(value.get("found") and isinstance(document, dict)
                and document.get("schema") == "migloop-verdict/3" and not value.get("errors")) if observed else None,
            "document_error_count": len(value.get("errors", [])),
            "identity_bound": (built.get("identity") or {}).get("bound"),
            "reference_status_counts": dict(Counter(e.get("status", "unknown") for e in refs)),
            "semantic_checked": False}


def _queue(base, condition, expected):
    path = base / condition / "queue.jsonl"
    if not path.exists():
        return {"complete": False, "status": "not_started", "makespan_seconds": None}
    records = [_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    starts = [r for r in records if r.get("event") == "start"]
    ends = [r for r in records if r.get("event") == "end"]
    if len(starts) != 1 or len(ends) > 1 or records[0] != starts[0]:
        raise ValueError("Invalid queue journal boundaries")
    if starts[0].get("jobs") != len(expected) or starts[0].get("condition") != condition:
        raise ValueError("Queue denominator/condition differs")
    seen = {}
    for event in ("launch", "finish"):
        keys = [(r.get("case"), r.get("rep")) for r in records if r.get("event") == event]
        if len(keys) != len(set(keys)) or not set(keys) <= expected:
            raise ValueError("Unregistered or duplicate queue attempt")
        seen[event] = set(keys)
    if not seen["finish"] <= seen["launch"]:
        raise ValueError("Queue finish without launch")
    end = ends[0] if ends else {}
    if ends and records[-1] != end:
        raise ValueError("Records after queue end")
    complete = (end.get("status") == "finished" and end.get("unstarted") == 0
                and end.get("unstarted_jobs") == [] and seen["finish"] == expected)
    makespan = None
    if ends:
        a, b = (datetime.fromisoformat(r["time"].replace("Z", "+00:00")) for r in (starts[0], end))
        if a.tzinfo is None or b.tzinfo is None or b < a:
            raise ValueError("Invalid queue timestamps")
        makespan = (b - a).total_seconds()
    return {"complete": complete, "status": end.get("status", "running"), "makespan_seconds": makespan,
            "queue_sha256": sha(path), "launched": len(seen["launch"]), "finished": len(seen["finish"])}


def _mechanical_summary(rows):
    checks = [r["mechanical"] for r in rows if r["mechanical"] is not None]
    observed = [c for c in checks if c["document_checks_pass"] is not None]
    refs = Counter()
    for check in checks:
        refs.update(check["reference_status_counts"])
    return {"runs_expected": len(rows), "runs_with_verdict": len(checks), "document_checks_observed": len(observed),
            "document_checks_passed": sum(c["document_checks_pass"] for c in observed),
            "reference_occurrences": sum(refs.values()), "reference_status_counts": dict(refs),
            "semantic_checked": False,
            "caution": "Recorded mechanical checks only; references are declaration occurrences, not unique verified causes. Missing checks are not failed semantic grades."}


def _aggregate(rows):
    totals = {key: sum(r["grade"][key] for r in rows)
              for key in ("units", *UNIT_OUTCOMES, "asserted_claims", "supported_claims", "major_errors")}
    files = []
    for case in dict.fromkeys(r["case"] for r in rows):
        repetitions = [r for r in rows if r["case"] == case]
        files.append({"case": case, "repetitions": len(repetitions),
                      "correct_coverage": sum(r["grade"]["correct_attribution_coverage"] for r in repetitions) / len(repetitions),
                      "passing_repetitions": sum(r["grade"]["file_pass"] for r in repetitions)})
    reviewed = [r for r in rows if r["grade"].get("claims_review_complete") is True]
    return {**totals, "files": files, "distinct_files": len(files), "file_runs": len(rows),
            "file_macro_correct_attribution_coverage": sum(f["correct_coverage"] for f in files) / len(files),
            "unit_weighted_correct_attribution_coverage": totals["correct"] / totals["units"],
            "attribution_precision": totals["supported_claims"] / totals["asserted_claims"] if totals["asserted_claims"] else None,
            "file_runs_passed": sum(r["grade"]["file_pass"] for r in rows),
            "full_reports_claim_reviewed": len(reviewed),
            "full_reports_no_contradicted_or_unsupported_assertions": sum(r["grade"]["full_report_no_contradicted_or_unsupported_assertions"] for r in reviewed),
            "caution": "File repetitions are paired observations, not independent business samples. Core pass does not mean the entire report is factually clean."}


def summarize(base, grades, *, condition, manifest_sha256=None):
    context = verify_package(base, manifest_sha256=manifest_sha256)
    base, grades = context["base"], Path(grades).resolve()
    if condition not in ("raw", "tools"):
        raise ValueError("Unknown condition")
    manifest = context["manifest"]
    expected = {(c["id"], rep) for c in manifest["cases"] for rep in range(1, manifest["repetitions"] + 1)}
    for root, suffix in ((base / condition / "runs", "metrics.json"), (grades / condition, "*.json")):
        for path in root.glob("*/*") if root.exists() else []:
            match = re.fullmatch(r"rep([1-9][0-9]*)" + (r"\.json" if suffix == "*.json" else ""), path.name)
            if not match or (path.parent.name, int(match[1])) not in expected:
                raise ValueError("Unregistered run/adjudication artifact: " + str(path))
    queue = _queue(base, condition, expected)
    rows = []
    for case in manifest["cases"]:
        for rep in range(1, manifest["repetitions"] + 1):
            task, directory, core = _case(context, case["id"], rep, condition)
            metric, metric_sha = _metric(context, task, directory, condition)
            state, failures, prompt_binding = _health(context, metric, directory, condition, task)
            report = directory / "report.md"
            present = report.exists() and bool(report.read_text(encoding="utf-8").strip())
            grade_path = grades / condition / task["id"] / f"rep{rep}.json"
            grade = None
            if grade_path.exists():
                grade = _validate(context, task["id"], rep, read(grade_path), condition)
                state = "adjudicated"
            elif state == "evaluable" and metric.get("status") in ("timeout", "incomplete") and not present:
                total = len(core["required"][task["id"]])
                grade = {"units": total, "correct": 0, "partial": 0, "missing": total, "wrong": 0,
                         "correct_attribution_coverage": 0, "asserted_claims": 0, "supported_claims": 0,
                         "attribution_precision": None, "major_errors": 0, "file_pass": False,
                         "claims_review_complete": False, "full_report_no_contradicted_or_unsupported_assertions": None,
                         "automatic_basis": "Terminal timeout/incomplete without a final report: missing delivery, not wrong causal claims"}
                state = "terminal_no_final"
            elif state == "evaluable":
                state = "pending_adjudication" if present else "pending_final_delivery_audit"
            rows.append({"case": task["id"], "cohort": task["cohort"], "file": task["file"], "rep": rep,
                         "condition": condition, "run_status": (metric or {}).get("status", "not_started"),
                         "state": state, "harness_failures": failures, "grade": grade,
                         "prompt_binding": prompt_binding,
                         "metrics_sha256": metric_sha, "report_sha256": sha(report) if report.exists() else None,
                         "grade_sha256": sha(grade_path) if grade_path.exists() else None,
                         "session_id": (metric or {}).get("session_id"),
                         "transcript_sha256": (metric or {}).get("transcript_sha256"),
                         "mechanical": _mechanical(directory, metric or {}) if condition == "tools" else None,
                         **_cost(metric)})
    for field in ("session_id", "transcript_sha256"):
        observed = [row[field] for row in rows if row[field] is not None]
        if any(not isinstance(value, str) or not value for value in observed) or len(observed) != len(set(observed)):
            raise ValueError("Reused or invalid native run identity across repetitions/cases: " + field)
    ready = queue["complete"] and all(r["grade"] is not None for r in rows)
    cohorts = []
    for cid in manifest["cohorts"]:
        selected = [r for r in rows if r["cohort"] == cid]
        cohorts.append({"id": cid, "files_expected": len({r["case"] for r in selected}),
                        "runs_expected": len(selected), "runs_adjudicated": sum(r["grade"] is not None for r in selected),
                        "harness_failure_runs": sum(r["state"] == "harness_failure" for r in selected),
                        "aggregate": _aggregate(selected) if ready else None,
                        "costs": {field: _stat([r[field] for r in selected]) for field in _cost(None)},
                        "mechanical": _mechanical_summary(selected)})
    costs = {field: _stat([r[field] for r in rows]) for field in _cost(None)}
    result = {"schema": SCORE_SCHEMA, "condition": condition,
              "bindings": {"transfer_manifest_sha256": context["manifest_sha256"], "code_digest": manifest["code_digest"],
                           "source_manifest_sha256": manifest["inputs"]["source_manifest"]["sha256"],
                           "candidate_manifest_sha256": manifest["inputs"]["candidate_manifest"]["sha256"],
                           "contracts_sha256": manifest["inputs"]["contracts"]["sha256"],
                           "cohort_core_sha256": {cid: c["sha256"] for cid, c in context["cores"].items()},
                           "scorer_sha256": sha(__file__)},
              "runs_expected": len(rows), "runs_recorded": sum(r["metrics_sha256"] is not None for r in rows),
              "runs_adjudicated": sum(r["grade"] is not None for r in rows), "aggregate_ready": ready,
              "harness_failure_runs": sum(r["state"] == "harness_failure" for r in rows),
              "queue": queue, "cohorts": cohorts, "runs": rows, "costs": costs,
              "mechanical": _mechanical_summary(rows),
              "cost_scope": "Input includes cache; total=input+output, never add cache/reasoning twice. Investigator and postprocess are inside system time. Queue makespan is separate. Missing/skipped costs are unknown, not zero.",
              "semantic_scope": "Reviewed judgments, not automatic semantic certification. No cross-cohort pooled accuracy. Mechanical schema/reference checks neither add nor subtract causal credit."}
    context["runner"].verify(base)
    for row in rows:
        directory = base / condition / "runs" / row["case"] / f"rep{row['rep']}"
        paths = [(directory / "metrics.json", row["metrics_sha256"]),
                 (directory / "report.md", row["report_sha256"]),
                 (grades / condition / row["case"] / f"rep{row['rep']}.json", row["grade_sha256"])]
        prompt_binding = row.get("prompt_binding")
        if prompt_binding and prompt_binding.get("actual_sha256"):
            paths.append((directory / "prompt.md", prompt_binding["actual_sha256"]))
        if prompt_binding and prompt_binding.get("native_transcript_sha256"):
            paths.append((directory / "transcript.jsonl", prompt_binding["native_transcript_sha256"]))
        if row["mechanical"] is not None:
            paths.append((directory / "verdict.json", row["mechanical"]["verdict_sha256"]))
        if any((sha(path) if path.exists() else None) != digest for path, digest in paths):
            raise ValueError("Run/adjudication changed during summary; retry read-only after writers finish")
    if queue.get("queue_sha256") and sha(base / condition / "queue.jsonl") != queue["queue_sha256"]:
        raise ValueError("Queue journal changed during summary")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("validate", "summarize"))
    ap.add_argument("--base", required=True, type=Path)
    ap.add_argument("--condition", choices=("raw", "tools"), required=True)
    ap.add_argument("--manifest-sha256")
    ap.add_argument("--grades", type=Path)
    ap.add_argument("--grade", type=Path)
    ap.add_argument("--case")
    ap.add_argument("--rep", type=int)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.mode == "validate":
        if not args.grade or not args.case or args.rep is None:
            ap.error("validate requires --grade --case --rep")
        result = validate_grade(args.base, args.case, args.rep, read(args.grade), condition=args.condition,
                                manifest_sha256=args.manifest_sha256)
    else:
        if not args.grades:
            ap.error("summarize requires --grades")
        result = summarize(args.base, args.grades, condition=args.condition, manifest_sha256=args.manifest_sha256)
    if args.out:
        save(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
