"""The suite monitor can update progress without rerunning investigators."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def test_suite_collects_more_than_one_completed_worker(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "docs/experiments/inquiry-20260911/run_skill_case.py"
    spec = importlib.util.spec_from_file_location("card_suite_test", source)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    (tmp_path / "suite.json").write_text(json.dumps({"cases": ["A", "B"]}))
    for name in ("A", "B"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(runner, "verify", lambda _: None)

    def completed(command, **_):
        case = Path(command[-1])
        run = case / "runs/inquiry/rep1"
        run.mkdir(parents=True)
        (run / "metrics.json").write_text(json.dumps({"status": "completed", "elapsed_seconds": 1}))
        (run / "card-audit.json").write_text(json.dumps({"status": "draft", "report_id": case.name}))
        return SimpleNamespace(returncode=0, stdout="one investigation", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", completed)
    runner.run_suite(tmp_path)
    results = json.loads((tmp_path / "suite-results.json").read_text(encoding="utf-8"))
    assert {r["case"] for r in results} == {"A", "B"} and len(results) == 2
    assert all(r["status"] == "completed" and r["worker_exit_code"] == 0 for r in results)
