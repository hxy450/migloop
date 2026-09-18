"""Install four sibling skills; explicit updates keep a recoverable backup."""
import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

NAMES = ("migloop-repair-triage", "migloop-build-cards", "migloop-memory-maintain", "migloop-memory-recall")


def _plain(path):
    """Never replace or traverse a symlink/junction as an owned package."""
    if path.is_symlink() or (path.exists() and
            getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError("Linked directory is not supported: " + str(path))


def _source_tree(path):
    _plain(path)
    if not (path / "SKILL.md").is_file():
        raise ValueError("Missing sibling skill: " + str(path))
    pending = [path]
    while pending:
        for child in pending.pop().iterdir():
            _plain(child)
            if child.is_dir():
                pending.append(child)


def _targets(destination, update):
    for name in NAMES:
        target = destination / name
        _plain(target)
        if target.exists() and not target.is_dir():
            raise ValueError("Installed skill is not a directory: " + str(target))
        if target.exists() and not update:
            raise ValueError("Refusing to overwrite installed skill; use --update: " + str(target))


def _replace(source, destination, names, *, update, restoring=False):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    _plain(destination)
    destination = destination.resolve()
    _targets(destination, update)
    for name in NAMES:
        target = destination / name
        for source_name in names:
            package = source / source_name
            if target == package or target in package.parents or package in target.parents:
                raise ValueError("Source and destination packages overlap")
    for name in names:
        _source_tree(source / name)
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / ".migloop-install.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("Another installation or interrupted transaction holds " + str(lock)) from exc
    stage = None
    keep_stage = False
    try:
        with handle:
            handle.write(str(os.getpid()))
        _targets(destination, update)  # Recheck after acquiring the installation lock.
        # Copy the entire replacement before touching any installed package.
        stage = Path(tempfile.mkdtemp(prefix=".migloop-stage-", dir=destination.parent)).resolve()
        for name in names:
            shutil.copytree(source / name, stage / name,
                            ignore=None if restoring else shutil.ignore_patterns("__pycache__", "*.pyc"))
        backup_root = destination.parent / ".migloop-skill-backups"
        _plain(backup_root)
        backup_root.mkdir(exist_ok=True)
        backup = backup_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:12])
        previous = backup / "previous"
        previous.mkdir(parents=True)
        present = [name for name in NAMES if (destination / name).exists()]
        manifest = {"schema": "migloop-skill-install/1", "destination": str(destination),
                    "source": str(source), "present_before": present, "installed": list(names),
                    "mode": "restore" if restoring else "update" if update else "install",
                    "state": "installing", "stage": str(stage)}
        record = backup / "manifest.json"
        record.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        moved, published = [], []
        try:
            for name in present:
                (destination / name).rename(previous / name)
                moved.append(name)
            for name in names:
                (stage / name).rename(destination / name)
                published.append(name)
            manifest["state"] = "completed"
            record.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except BaseException as exc:
            errors = []
            # Move replacements aside; never recursively delete the old installation.
            for name in reversed(published):
                try:
                    (destination / name).rename(stage / name)
                except OSError as error:
                    errors.append(str(error))
            for name in reversed(moved):
                try:
                    (previous / name).rename(destination / name)
                except OSError as error:
                    errors.append(str(error))
            keep_stage = bool(errors)
            manifest.update(state="rollback_failed" if errors else "rolled_back", errors=errors)
            record.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            raise RuntimeError(f"Installation failed; {manifest['state']}. Recovery record: {record}") from exc
        return {"skills": [str(destination / name / "SKILL.md") for name in names], "backup": str(backup)}
    finally:
        # Only this invocation's unique, resolved staging directory is disposable.
        try:
            if stage and not keep_stage and stage.parent == destination.parent and stage.name.startswith(".migloop-stage-"):
                shutil.rmtree(stage)
        finally:
            lock.unlink()


def install(destination, update=False):
    return _replace(Path(__file__).resolve().parents[2], destination, NAMES, update=update)


def restore(destination, backup):
    backup = Path(backup).resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    names = manifest.get("present_before")
    if (manifest.get("schema") != "migloop-skill-install/1" or manifest.get("state") != "completed"
            or not isinstance(names, list) or len(names) != len(set(names)) or any(n not in NAMES for n in names)):
        raise ValueError("Expected a completed installation backup with known package names")
    if Path(manifest["destination"]).resolve() != Path(destination).resolve():
        raise ValueError("Backup belongs to a different destination")
    return _replace(backup / "previous", destination, names, update=True, restoring=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true", help="Back up existing packages before replacing all four")
    mode.add_argument("--restore", metavar="BACKUP", help="Restore the pre-install state from a completed backup")
    args = parser.parse_args()
    result = restore(args.destination, args.restore) if args.restore else install(args.destination, args.update)
    print("Backup: " + result["backup"], file=sys.stderr)
    for path in result["skills"]:
        print(path)
