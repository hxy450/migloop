"""Build the zero-dependency MigLoop zipapp distribution.

Usage: ``python scripts/build_pyz.py``
"""
import argparse
import os
import shutil
import tempfile
import zipapp


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "src", "migloop")
DEFAULT_OUT = os.path.join(ROOT, "dist", "migloop-lineage.pyz")


def _ignore(_directory, names):
    return {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}


def build(output):
    output = os.path.abspath(output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="migloop-zipapp-") as stage:
        shutil.copytree(PACKAGE, os.path.join(stage, "migloop"), ignore=_ignore)
        with open(os.path.join(stage, "__main__.py"), "w", encoding="utf-8") as stream:
            stream.write("from migloop.cli import main\nmain()\n")
        temp_output = output + ".tmp"
        zipapp.create_archive(stage, temp_output, interpreter="/usr/bin/env python3")
        os.replace(temp_output, output)
    return output


def main():
    parser = argparse.ArgumentParser(description="Build MigLoop's standalone .pyz")
    parser.add_argument("-o", "--out", default=DEFAULT_OUT)
    args = parser.parse_args()
    output = build(args.out)
    print("built -> %s (%.0f KB)" % (output, os.path.getsize(output) / 1024))


if __name__ == "__main__":
    main()

