"""Public holdout preparation is oracle-free and fail-closed."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def holdout():
    path = Path(__file__).parents[1] / "docs/experiments/2026-09-09-attribution10/prepare_holdout.py"
    spec = importlib.util.spec_from_file_location("prepare_public_holdout", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture(tmp_path: Path, h):
    source = tmp_path / "candidate-source"
    (source / "src/migloop").mkdir(parents=True)
    (source / "src/migloop/service.py").write_text("# candidate\n", encoding="utf-8")
    parents, sources, questions = [], {}, []
    for group, fmt, count in (("alpha", "claude", 2), ("beta", "codex", 2), ("gamma", "claude", 1)):
        parent = tmp_path / ("parent-" + group)
        pool = parent / "pool"
        pool.mkdir(parents=True)
        roots = []
        for n in range(2):
            root = pool / f"{group}-{n}.jsonl"
            root.write_text('{"type":"record"}\n', encoding="utf-8")
            roots.append(root)
        parent_source = tmp_path / ("old-source-" + group)
        (parent_source / "src/migloop").mkdir(parents=True)
        (parent_source / "src/migloop/service.py").write_text("# old\n", encoding="utf-8")
        task = parent / "common-task.md"
        task.write_text("old task\n", encoding="utf-8")
        pool_state = h.inventory(pool)
        pool_manifest = parent / "pool-manifest.json"
        write_json(pool_manifest, pool_state)
        case = {"schema": "migloop-pair-case/1", "case": group, "file": "Old.ets",
                "source": str(parent_source), "source_digest": h.inventory(parent_source / "src/migloop")["content_digest"],
                "pool": str(pool), "pool_digest": pool_state["content_digest"], "format": fmt,
                "current_root": str(roots[-1]), "roots": [str(x) for x in roots],
                "common_task_sha256": h.sha256(task)}
        case_path = parent / "case.json"
        write_json(case_path, case)
        sources[group] = {"source_parent_case": str(parent), "case_json_sha256": h.sha256(case_path),
                          "pool": str(pool), "declared_pool_digest": pool_state["content_digest"],
                          "current_root": str(roots[-1]), "roots": [str(x) for x in roots],
                          "manifest_path": str(pool_manifest), "manifest_sha256": h.sha256(pool_manifest)}
        for index in range(count):
            qid = f"H-{group}-{index}"
            questions.append({"id": qid, "file": f"entry/{qid}.ets", "source_parent_case": str(parent),
                              "current_root": str(roots[-1]), "question": f"What changed in {qid}?",
                              "scope_limits": ["Use raw evidence.", "Keep unknowns."]})
        parents.append((parent, pool, parent_source))
    package = tmp_path / "package"
    package.mkdir()
    public = package / "questions.json"
    write_json(public, {"schema": "migloop-question-holdout/1", "questions": questions})
    manifest = {"schema": "migloop-holdout-package-manifest/1", "status": "frozen_pre_run",
                "public_file": "questions.json", "private_oracle_file": "oracle.json",
                "artifacts": [{"path": "questions.json", "sha256": h.sha256(public),
                               "visibility": "public_questions"}], "sources": sources}
    write_json(package / "manifest.json", manifest)
    # Deliberately no oracle.json: successful preparation proves it is unnecessary.
    return package, source, parents


def test_prepares_five_independent_shared_pool_cases_without_oracle(tmp_path, holdout):
    package, source, parents = fixture(tmp_path, holdout)
    before = {path: path.read_bytes() for parent, pool, old_source in parents
              for root in (parent, pool, old_source) for path in root.rglob("*") if path.is_file()}
    result = holdout.prepare(package, source, "new-code", tmp_path / "new-store")
    assert len(result["cases"]) == 5 and result["oracle_accessed"] is False
    assert not (package / "oracle.json").exists()
    for row in result["cases"]:
        case_dir = Path(row["case_dir"])
        case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        assert Path(case["pool"]).parent.name.startswith("parent-")
        assert not (case_dir / "pool").exists()
        assert case["question_ids"] == [row["id"]]
        assert case["common_task_sha256"] == holdout.sha256(case_dir / "common-task.md")
        text = (case_dir / "common-task.md").read_text(encoding="utf-8")
        assert "不得访问私有 oracle" in text and row["id"] in text
        if case["format"] == "codex":
            assert "没有随根提供的子代理转录" in text
        runner_path = Path(__file__).parents[1] / "docs/experiments/2026-09-09-fidelity-cost/run_pair.py"
        runner_spec = importlib.util.spec_from_file_location("holdout_pair_runner", runner_path)
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)
        assert all(runner.check_frozen(case_dir, case)[key]
                   for key in ("pool_unchanged", "source_unchanged", "task_unchanged"))
    assert all(path.read_bytes() == body for path, body in before.items())


def test_rejects_public_hash_and_duplicate_id_before_creating_store(tmp_path, holdout):
    package, source, _ = fixture(tmp_path, holdout)
    public = json.loads((package / "questions.json").read_text(encoding="utf-8"))
    public["questions"][1]["id"] = public["questions"][0]["id"]
    write_json(package / "questions.json", public)
    store = tmp_path / "store"
    with pytest.raises(ValueError, match="SHA256"):
        holdout.prepare(package, source, "code", store)
    assert not store.exists()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = holdout.sha256(package / "questions.json")
    write_json(package / "manifest.json", manifest)
    with pytest.raises(ValueError, match="unique"):
        holdout.prepare(package, source, "code", store)
    assert not store.exists()


def test_rejects_escaped_root_existing_or_protected_destination(tmp_path, holdout):
    package, source, parents = fixture(tmp_path, holdout)
    questions = json.loads((package / "questions.json").read_text(encoding="utf-8"))
    questions["questions"][0]["current_root"] = str(tmp_path / "outside.jsonl")
    (tmp_path / "outside.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(package / "questions.json", questions)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = holdout.sha256(package / "questions.json")
    write_json(package / "manifest.json", manifest)
    with pytest.raises(ValueError, match="inside its declared pool"):
        holdout.prepare(package, source, "code", tmp_path / "new")
    assert not (tmp_path / "new").exists()

    package, source, _ = fixture(tmp_path / "second", holdout)
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        holdout.prepare(package, source, "code", existing)
    assert (existing / "keep.txt").read_text() == "keep"
    with pytest.raises(ValueError, match="outside package"):
        holdout.prepare(package, source, "code", source / "new-store")
    assert not (source / "new-store").exists()


def test_parent_pool_source_and_task_hashes_fail_closed(tmp_path, holdout):
    for changed in ("pool", "source", "task"):
        base = tmp_path / changed
        package, source, parents = fixture(base, holdout)
        parent, pool, old_source = parents[0]
        target = {"pool": next(pool.glob("*.jsonl")), "source": old_source / "src/migloop/service.py",
                  "task": parent / "common-task.md"}[changed]
        target.write_text(target.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with pytest.raises(ValueError, match="changed"):
            holdout.prepare(package, source, "code", base / "store")
        assert not (base / "store").exists()


def test_manifest_cannot_redirect_public_read_to_oracle(tmp_path, holdout, monkeypatch):
    package, source, parents = fixture(tmp_path, holdout)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["public_file"] = "oracle.json"
    write_json(package / "manifest.json", manifest)
    real_hash = holdout.sha256

    def guarded_hash(path):
        assert Path(path).name != "oracle.json", "private oracle must not even be opened for hashing"
        return real_hash(path)

    monkeypatch.setattr(holdout, "sha256", guarded_hash)
    with pytest.raises(ValueError, match="must be questions.json"):
        holdout.prepare(package, source, "code", tmp_path / "new")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("bad", [[], None, {"schema": "migloop-question-holdout/1", "questions": [{"id": []}] * 5}])
def test_malformed_public_structure_is_a_validation_error(tmp_path, holdout, bad):
    package, source, _ = fixture(tmp_path, holdout)
    write_json(package / "questions.json", bad)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = holdout.sha256(package / "questions.json")
    write_json(package / "manifest.json", manifest)
    with pytest.raises(ValueError):
        holdout.prepare(package, source, "code", tmp_path / "new")
    assert not (tmp_path / "new").exists()
