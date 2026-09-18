"""Restore i14's empty host-skill catalog without changing global settings.

The historical disabled list predates newly installed skills. Extend only that
negative list per run, then refreeze before launching. Never alter prior runs.
"""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("exact_replay", HERE / "run_i14_exact.py")
REPLAY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REPLAY)
RAW = REPLAY.RAW


def prepare(out, historical_case, backend):
    REPLAY.prepare(out, historical_case, backend)
    config = RAW.read(out / "settings.json")
    command = RAW.read(out / "expected-command.json")
    alignment = RAW.read(out / "alignment.json")
    existing = {entry["path"] for entry in config["skills.config"]}
    added = []
    for skill in RAW.host_skills():
        for path in (str(Path(skill)), str(Path(skill).parent)):
            if path not in existing:
                added.append({"path": path, "enabled": False})
                existing.add(path)
    config["skills.config"].extend(added)
    index = next(i for i, arg in enumerate(command["argv"]) if arg.startswith("skills.config="))
    command["argv"][index] = "skills.config=" + RAW.parser().toml_value(config["skills.config"])
    original = RAW.read(historical_case / "runs/inquiry/rep1/command.json")
    differences = [i for i, (a,b) in enumerate(zip(command["argv"], original["argv"])) if a != b]
    allowed = {i for i,arg in enumerate(original["argv"]) if arg.startswith(("mcp_servers=", "skills.config="))}
    if not set(differences) <= allowed:
        raise ValueError("Unexpected argv change")
    alignment.update(argv_changed_indices=differences, only_mcp_launch_argument_changed=False,
        non_mcp_settings_identical=not added, skill_catalog_disabled_entries_added=added,
        skill_catalog_restoration="Restore historical absence of all host skills. No instructions added; runtime developer message must match historical hash.",
        argv_identical_except_backend_and_catalog_restoration=True)
    for name,value in [("settings.json",config),("expected-command.json",command),("alignment.json",alignment)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest = RAW.read(out / "manifest.json")
    manifest["files"] = {name:RAW.sha(out/name) for name in manifest["files"]}
    manifest["dependencies"][str(Path(__file__))] = RAW.sha(__file__)
    manifest["catalog_restoration"] = {"added_disabled_entries": len(added), "before_model_launch": True}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    REPLAY.verify(out)
    print(json.dumps({"ready":str(out),"backend":backend,"disabled_entries_added":len(added),"argv_changed_indices":differences},ensure_ascii=False),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--historical-case",type=Path,required=True)
    parser.add_argument("--backend",choices=("historical","current"),required=True)
    args=parser.parse_args()
    prepare(args.out.resolve(),args.historical_case.resolve(),args.backend)
