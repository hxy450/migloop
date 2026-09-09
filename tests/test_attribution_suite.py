"""Suite preparation projects neutral questions and writes new outputs only."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def suite():
    path = Path(__file__).resolve().parents[1] / "docs/experiments/2026-09-09-attribution10/prepare_suite.py"
    spec = importlib.util.spec_from_file_location("attribution_suite", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refs(tmp_path, suite):
    legacy = {"cases": [{"id": key, "target_file": target, "question": "neutral question " + key,
                         "facts": ["SECRET_ANSWER"], "evidence_ids": ["SECRET_WITNESS"]}
                        for key, target in [("D1", "EntryAbility.ets"), ("D2", "EntryAbility.ets"),
                                            ("S1", "SplashPage.ets"), ("S2", "SplashPage.ets"),
                                            ("S3", "MemberCenterPage.ets"), ("S4", "MemberCenterPage.ets")]]}
    codex = {"cases": [{"id": f"C{i}_question", "target_file": f"Codex{i}.ets", "question": f"neutral question C{i}",
                         "facts": ["SECRET_ANSWER"], "inferences": ["SECRET_CAUSE"], "unknown": ["SECRET_UNKNOWN"],
                         "must_reject": ["SECRET_REJECTION"], "case_kind": "SECRET_CLASSIFICATION",
                         "evidence": [{"file": "SECRET_PATH", "line": 999, "call_id": "SECRET_WITNESS"}]}
                        for i in range(1, 5)]}
    paths = [tmp_path / "legacy.json", tmp_path / "codex.json"]
    for path, doc in zip(paths, (legacy, codex)):
        path.write_text(json.dumps(doc), encoding="utf-8")
    pool = tmp_path / "frozen-codex"
    base = tmp_path / "base"
    for group in suite.formal_groups(legacy, codex, base, pool):
        group["pool"].mkdir(parents=True, exist_ok=True)
        (group["pool"] / group["root"]).write_text("frozen source", encoding="utf-8")
    (pool / suite.GENERATION).write_text("frozen generation source", encoding="utf-8")
    return base, pool, *paths


def fake_prepare(suite, *, started=False):
    def run(store, source, code_id, name, pool, root, target, items):
        case_dir = store / name
        case_dir.mkdir()
        (case_dir / "pool").mkdir()
        names = sorted(p.name for p in pool.glob("*.jsonl"))
        for name_in_pool in names:
            (case_dir / "pool" / name_in_pool).write_bytes((pool / name_in_pool).read_bytes())
        task = case_dir / "common-task.md"
        task.write_text("old generic template without questions", encoding="utf-8")
        doc = {"case": name, "file": target, "pool": str(case_dir / "pool"),
               "current_root": str(case_dir / "pool" / root),
               "roots": [str(case_dir / "pool" / n) for n in names],
               "source": str(source), "source_code_id": code_id,
               "pool_digest": "pool-sha", "common_task_sha256": suite.sha(task)}
        suite.write_new(case_dir / "case.json", doc)
        if started:
            (case_dir / "runs").mkdir()
        return {"group": name, "items": items, "case_dir": str(case_dir), "pool_digest": "pool-sha"}
    return run


def test_prepare_all_is_seven_groups_ten_neutral_questions_with_no_answers(tmp_path, suite, monkeypatch):
    base, pool, legacy, codex = refs(tmp_path, suite)
    before = {p: p.read_bytes() for p in (legacy, codex, *pool.glob("*.jsonl"))}
    monkeypatch.setattr(suite, "prepare_group", fake_prepare(suite))
    store = tmp_path / "formal"
    result = suite.prepare_all(store, tmp_path / "source", "frozen-code", base=base, codex_pool=pool,
                               legacy_reference=legacy, codex_reference=codex)
    assert len(result["groups"]) == 7 and len(result["question_ids"]) == 10
    assert result["question_ids"] == ["D1", "D2", "S1", "S2", "S3", "S4", *[f"C{i}_question" for i in range(1, 5)]]
    for row in result["groups"]:
        folder = Path(row["case_dir"])
        task = (folder / "common-task.md").read_text(encoding="utf-8")
        case = json.loads((folder / "case.json").read_bytes())
        assert "SECRET_" not in task + json.dumps(case) + json.dumps(row)
        assert case["question_ids"] == row["items"] == row["question_ids"]
        assert case["common_task_sha256"] == row["task_sha256"] == suite.sha(folder / "common-task.md")
        assert case["task_revision"] == suite.TASK_REVISION and "unresolved" in task
        assert "不要求全文件的冗长返修报告" in task
        if row["group"].startswith("codex-"):
            assert suite.GENERATION in task and suite.REPAIR in task and "未提供的子转录不在池内" in task
            assert Path(case["current_root"]).name == suite.REPAIR
        if row["group"] == "codex-c1":
            assert "生成阶段内部的修正" in task
    assert all(p.read_bytes() == data for p, data in before.items())


def test_answer_changes_cannot_change_neutral_task(tmp_path, suite):
    base, pool, legacy_path, codex_path = refs(tmp_path, suite)
    legacy, codex = json.loads(legacy_path.read_bytes()), json.loads(codex_path.read_bytes())
    before = suite.formal_groups(legacy, codex, base, pool)
    for row in legacy["cases"] + codex["cases"]:
        row.update(facts=["DIFFERENT ANSWER"], unknown=["NEW ANSWER"], evidence=[{"file": "NEW GOLD"}])
    after = suite.formal_groups(legacy, codex, base, pool)
    assert before == after
    case = {"file": "A", "pool": "pool", "current_root": "pool/root.jsonl", "roots": ["pool/root.jsonl"]}
    assert suite.neutral_task(case, before[0]) == suite.neutral_task(case, after[0])


def test_future_variant_keeps_exact_neutral_task_bytes(tmp_path, suite, monkeypatch):
    path = suite.HERE.parent / "2026-09-09-fidelity-cost/run_pair.py"
    spec = importlib.util.spec_from_file_location("attribution_pair_runner", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    base, pool, legacy, codex = refs(tmp_path, suite)
    monkeypatch.setattr(suite, "prepare_group", fake_prepare(suite))
    store = tmp_path / "formal"
    suite.prepare_all(store, tmp_path / "source", "old-code", base=base, codex_pool=pool,
                      legacy_reference=legacy, codex_reference=codex)
    parent = store / "dice-entry"
    before = (parent / "common-task.md").read_bytes()
    suite.write_new(parent / "pool-manifest.json", {"content_digest": "pool-sha"})
    source = tmp_path / "new-source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/service.py").write_text("# frozen source", encoding="utf-8")
    monkeypatch.setattr(runner, "check_frozen", lambda *a: {"pool_unchanged": True, "source_unchanged": True, "task_unchanged": True})
    result = runner.variant(parent, source, tmp_path / "variant", "new-code")
    assert (result / "common-task.md").read_bytes() == before == (parent / "common-task.md").read_bytes()
    case = json.loads((result / "case.json").read_bytes())
    assert case["question_ids"] == ["D1", "D2"] and case["task_revision"] == suite.TASK_REVISION
    assert case["common_task_sha256"] == suite.sha(result / "common-task.md")


def test_prepare_all_refuses_existing_store_without_touching_old_case(tmp_path, suite, monkeypatch):
    base, pool, legacy, codex = refs(tmp_path, suite)
    store = tmp_path / "old-run"
    store.mkdir()
    old = store / "case.json"
    old.write_text("OLD FROZEN CASE", encoding="utf-8")
    monkeypatch.setattr(suite, "prepare_group", lambda *a: pytest.fail("must not invoke runner"))
    with pytest.raises(FileExistsError):
        suite.prepare_all(store, tmp_path / "source", "code", base=base, codex_pool=pool,
                          legacy_reference=legacy, codex_reference=codex)
    assert old.read_text(encoding="utf-8") == "OLD FROZEN CASE"
    with pytest.raises(ValueError, match="input pool"):
        suite.prepare_all(pool / "new-output", tmp_path / "source", "code", base=base, codex_pool=pool,
                          legacy_reference=legacy, codex_reference=codex)
    with pytest.raises(ValueError, match="frozen source"):
        suite.prepare_all(tmp_path / "source/new-output", tmp_path / "source", "code", base=base, codex_pool=pool,
                          legacy_reference=legacy, codex_reference=codex)


def test_prepared_case_with_started_run_cannot_have_its_task_rewritten(tmp_path, suite, monkeypatch):
    base, pool, legacy, codex = refs(tmp_path, suite)
    monkeypatch.setattr(suite, "prepare_group", fake_prepare(suite, started=True))
    store = tmp_path / "started"
    with pytest.raises(RuntimeError, match="run directory"):
        suite.prepare_all(store, tmp_path / "source", "code", base=base, codex_pool=pool,
                          legacy_reference=legacy, codex_reference=codex)
    assert (store / "dice-entry/common-task.md").read_text(encoding="utf-8") == "old generic template without questions"


def test_reference_bundle_preserves_originals_and_records_both_validations(tmp_path, suite, monkeypatch):
    _, pool, legacy, codex = refs(tmp_path, suite)
    old = tmp_path / "legacy-witnesses-v1.json"
    old.write_bytes(b'{"old":"immutable witnesses"}\n')
    originals = {p: p.read_bytes() for p in (legacy, codex, old)}
    calls = []

    def validate(command):
        calls.append(command)
        if "--freeze" in command:
            suite.write_new(Path(command[command.index("--freeze") + 1]), {"witnesses": "verified"})
            return {"witnesses": 55, "locator_checks": "passed"}
        return {"evidence_count": 26, "failures": []}

    monkeypatch.setattr(suite, "_validate", validate)
    bundle = tmp_path / "reference-bundle"
    result = suite.freeze_reference(bundle, codex_pool=pool, legacy_reference=legacy,
                                    codex_reference=codex, legacy_witnesses=old)
    assert result["validation"] == {"legacy": 55, "codex": 26} and result["old_witnesses_preserved"]
    assert (bundle / "legacy-witnesses-v1.json").read_bytes() == originals[old]
    assert all(p.read_bytes() == data for p, data in originals.items())
    assert all(suite.sha(bundle / entry["path"]) == entry["sha256"] for entry in result["files"])
    assert len(calls) == 2 and "--validate-reference" in calls[1]
    assert calls[1][-2:] == [str(pool / suite.GENERATION), str(pool / suite.REPAIR)]
    with pytest.raises(FileExistsError):
        suite.freeze_reference(bundle, codex_pool=pool, legacy_reference=legacy, codex_reference=codex, legacy_witnesses=old)


def test_reference_bundle_fails_closed_on_wrong_counts(tmp_path, suite, monkeypatch):
    _, pool, legacy, codex = refs(tmp_path, suite)
    old = tmp_path / "old.json"
    old.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(suite, "_validate", lambda command: {"witnesses": 54, "locator_checks": "passed", "evidence_count": 26, "failures": []})
    bundle = tmp_path / "invalid-reference"
    with pytest.raises(RuntimeError, match="55 legacy"):
        suite.freeze_reference(bundle, codex_pool=pool, legacy_reference=legacy, codex_reference=codex, legacy_witnesses=old)
    assert not (bundle / "manifest.json").exists()
