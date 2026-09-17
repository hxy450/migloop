"""Recall entrypoint; same store and implementation used by the maintainer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "migloop-memory-maintain" / "scripts"))
from memorylib.retrieval import main

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.exit(str(exc))
