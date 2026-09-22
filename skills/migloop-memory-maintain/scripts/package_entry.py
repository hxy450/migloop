"""Generated-package launcher. Business logic comes from the one source runtime."""
import hashlib
import json
from pathlib import Path
import sys


def main():
    scripts = Path(__file__).resolve().parent
    package = scripts.parent
    manifest = json.loads((package / "package-manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        path = (package / name).resolve()
        if package not in path.parents or not path.is_file():
            raise ValueError("Incomplete skill package: " + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Skill package changed; rebuild from its source: " + name)
    sys.path.insert(0, str(scripts / "_runtime"))
    command = Path(__file__).stem
    if command in ("cases", "triage"):
        from memorylib.cases import main as run
        run("card" if command == "cases" else "triage")
    elif command == "memory":
        from memorylib.registry import main as run
        run()
    elif command == "recall":
        from memorylib.retrieval import main as run
        run()
    else:
        raise ValueError("Unknown packaged entrypoint: " + command)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError, ImportError) as exc:
        sys.exit(str(exc))
