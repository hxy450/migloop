"""Standalone publishing entrypoint; no migloop application import."""
import sys
from memorylib.registry import main

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.exit(str(exc))
