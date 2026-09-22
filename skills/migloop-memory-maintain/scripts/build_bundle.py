"""Build independently movable skills from one runtime source; no runtime downloads."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

NAMES = ("migloop-repair-triage", "migloop-build-cards", "migloop-memory-maintain", "migloop-memory-recall")
ENTRIES = {NAMES[0]: ("triage.py",), NAMES[1]: ("cases.py",),
           NAMES[2]: ("memory.py", "recall.py"), NAMES[3]: ("recall.py",)}
YAML_VERSION = "6.0.3"
CORE_EXCLUDED = {"__main__.py", "interfaces.py", "web.py", "viewer.py"}


def build(source, out):
    source, out = Path(source).resolve(), Path(out).absolute()
    out = out.parent.resolve() / out.name
    if out.exists():
        raise ValueError("Release output must be a new directory")
    repo = source.parent
    if out == repo or repo in out.parents:
        raise ValueError("Build outside the source checkout; releases are not a second source tree")
    scripts = source / "migloop-memory-maintain/scripts"
    core = repo / "src/migloop/inquiry"
    if not core.is_dir() or not (scripts / "package_entry.py").is_file():
        raise ValueError("Build requires the canonical source checkout, not an installed skill")
    distribution = importlib.metadata.distribution("PyYAML")
    if distribution.version != YAML_VERSION:
        raise ValueError(f"Release builder requires PyYAML=={YAML_VERSION}; installed {distribution.version}")
    yaml_root = Path(distribution.locate_file("yaml"))
    license_path = next((distribution.locate_file(p) for p in distribution.files
                         if str(p).lower().endswith("licenses/license")), None)
    if license_path is None:
        raise ValueError("PyYAML license missing")
    version_scope = {}
    exec((scripts / "memorylib/__init__.py").read_text(encoding="utf-8"), version_scope)
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout.strip())
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".migloop-release-", dir=out.parent) as temporary:
        staged = Path(temporary) / "bundle"
        staged.mkdir()
        for name in NAMES:
            src, dst = source / name, staged / name
            # Instructions/assets only; scripts are selected below, never copied from old installations.
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("scripts", "__pycache__", "*.pyc"))
            target_scripts = dst / "scripts"
            runtime = target_scripts / "_runtime"
            runtime.mkdir(parents=True)
            shutil.copytree(scripts / "memorylib", runtime / "memorylib",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (runtime / "yaml").mkdir()
            for path in sorted(yaml_root.glob("*.py")):
                shutil.copy2(path, runtime / "yaml" / path.name)
            (dst / "licenses").mkdir()
            shutil.copy2(license_path, dst / "licenses/PyYAML-LICENSE.txt")
            if name == "migloop-build-cards":
                target_core = runtime / "migloop/inquiry"
                target_core.mkdir(parents=True)
                shutil.copy2(repo / "src/migloop/__init__.py", runtime / "migloop/__init__.py")
                for path in sorted(core.glob("*.py")):
                    if path.name not in CORE_EXCLUDED:
                        shutil.copy2(path, target_core / path.name)
            for entry in ENTRIES[name]:
                shutil.copy2(scripts / "package_entry.py", target_scripts / entry)
            if name == "migloop-memory-maintain":
                shutil.copy2(scripts / "install_bundle.py", target_scripts / "install_bundle.py")
            if name == "migloop-memory-recall":
                hook = src / "scripts/claude_hook.py"
                if hook.is_file():
                    shutil.copy2(hook, target_scripts / hook.name)
            files = {p.relative_to(dst).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(dst.rglob("*")) if p.is_file()}
            digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            manifest = {"schema": "migloop-skill-package/1", "skill": name,
                        "version": version_scope["VERSION"], "source_commit": commit, "source_dirty": dirty,
                        "content_sha256": digest, "files": files,
                        "dependencies": {"Python": ">=3.10", "PyYAML": YAML_VERSION},
                        "inquiry_included": name == "migloop-build-cards"}
            (dst / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Publishing only after every package is complete. Never replace an existing release.
        if out.exists():
            raise ValueError("Release destination appeared during build")
        staged.rename(out)
    return {"release": str(out), "version": version_scope["VERSION"],
            "skills": [str(out / name / "SKILL.md") for name in NAMES]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(Path(__file__).resolve().parents[2], args.out), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
