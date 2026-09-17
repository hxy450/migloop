"""Install all three sibling skills together without overwriting existing skills."""
import argparse
import shutil
from pathlib import Path

NAMES = ("migloop-build-cards", "migloop-memory-maintain", "migloop-memory-recall")


def install(destination):
    source = Path(__file__).resolve().parents[2]
    destination = Path(destination).resolve()
    for name in NAMES:
        if not (source / name / "SKILL.md").is_file():
            raise ValueError("Missing sibling skill: " + name)
        if (destination / name).exists():
            raise ValueError("Refusing to overwrite installed skill: " + str(destination / name))
        if source / name == destination or source / name in destination.parents:
            raise ValueError("Cannot install inside a source skill")
    destination.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        shutil.copytree(source / name, destination / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return [str(destination / name / "SKILL.md") for name in NAMES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    for path in install(args.destination):
        print(path)
