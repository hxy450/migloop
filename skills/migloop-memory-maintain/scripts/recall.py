"""Maintenance lookup entry; one shared retrieval implementation."""
import sys
from memorylib.retrieval import main

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
