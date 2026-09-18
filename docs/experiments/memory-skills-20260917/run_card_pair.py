"""Same multi-target job/runtime/tools; vary only the selected card skill.

Reuse existing frozen-run recorders. No model hints, fork, resume, or retry.
"""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paired_card_trial", HERE / "run_i14_skill.py")
TRIAL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TRIAL)
BASE = TRIAL.BASE
CHOICES = {"standard": "migloop-build-cards", "i14": "migloop-build-cards-i14"}


def prepare(out, tasks, title, arm):
    # Both arms get the identical bundle and production MCP, not different tools.
    for name in (*BASE.NAMES, TRIAL.SKILL):
        installed = Path.home() / ".codex/skills" / name
        if BASE.inventory(installed) != BASE.inventory(BASE.REPO / "skills" / name):
            raise ValueError("Installed and repository skill differ: " + name)
    TRIAL.prepare(out, tasks, title)
    selected = CHOICES[arm]
    workspace = out / "workspace"
    prompt = (f"使用 {(workspace / 'skills' / selected / 'SKILL.md').as_posix()}。\n"
              f"转录：{(out / 'materials').as_posix()}；本次任务：当前目录 job.json。\n")
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    manifest = BASE.RAW.read(out / "manifest.json")
    manifest.update(schema="migloop-card-skill-pair/1", arm=arm,
                    comparison_skill=selected,
                    limitation="One run per arm on one 19-target issue; shared current MCP, kernel, schema and packer. Not a raw baseline or exact i14 replay.",
                    no_parent_followup=True, no_reviewer_materials=True)
    manifest["files"] = {p: BASE.RAW.sha(out / p) for p in manifest["files"]}
    manifest["dependencies"][str(Path(__file__))] = BASE.RAW.sha(__file__)
    manifest["target_count"] = len(BASE.RAW.read(workspace / "job.json")["targets"])
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    BASE.verify(out)
    print(json.dumps({"ready": str(out), "arm": arm, "targets": manifest["target_count"],
                      "prompt": prompt}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "verify"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--arm", choices=CHOICES)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.mode == "prepare":
        if not args.tasks or not args.title or not args.arm:
            parser.error("prepare requires tasks, title and arm")
        prepare(out, args.tasks.resolve(), args.title, args.arm)
    elif args.mode == "run":
        BASE.run(out)
    else:
        BASE.verify(out)
        print("verified")
