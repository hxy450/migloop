"""Freeze transfer source bytes and audit registry metadata; never builds gold.

All writes are exclusive and confined to a new output. Failure preserves the
partial output without SOURCE_READY; reruns never overwrite or remove it.
"""
from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import stat
import subprocess
import sys
import unicodedata
import zipfile

SCHEMA = "migloop-transfer-source-freeze/1"
CHUNK = 1024 * 1024
MAX_MEMBERS = 10000
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def regular(path, directory=False):
    info = Path(path).lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Symlink/reparse path rejected: " + str(path))
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("Special/nonregular path rejected: " + str(path))
    return info


def no_link_ancestors(path):
    absolute = Path(os.path.abspath(path))
    for node in [*reversed(absolute.parents), absolute]:
        if os.path.lexists(node):
            info = node.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Symlink/reparse ancestor rejected: " + str(node))
    if os.path.normcase(str(absolute.resolve())) != os.path.normcase(str(absolute)):
        raise ValueError("Resolved path differs from literal path: " + str(path))
    return absolute


def relative_name(name, directory=False):
    if not isinstance(name, str) or not name or "\0" in name or "\\" in name:
        raise ValueError("Noncanonical member path")
    if ntpath.splitdrive(name)[0] or name.startswith("/"):
        raise ValueError("Absolute or drive-relative member rejected: " + name)
    value = name[:-1] if directory and name.endswith("/") else name
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    for part in parts:
        if part in ("", ".", "..") or part.rstrip(" .") != part:
            raise ValueError("Traversal/alias component rejected: " + name)
        if any(ord(c) < 32 or c in '<>:"|?*' for c in part):
            raise ValueError("Unsafe Windows component rejected: " + name)
        if part.split(".")[0].upper() in reserved:
            raise ValueError("Reserved Windows component rejected: " + name)
    return "/".join(parts)


class Names:
    def __init__(self):
        self.paths = {}
        self.explicit = set()

    def add(self, name, directory=False):
        rel = relative_name(name, directory)
        folded = unicodedata.normalize("NFC", rel).casefold()
        if folded in self.explicit:
            raise ValueError("Duplicate/case-colliding member: " + rel)
        self.explicit.add(folded)
        parts = rel.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            kind = "dir" if index < len(parts) or directory else "file"
            key = unicodedata.normalize("NFC", prefix).casefold()
            previous = self.paths.get(key)
            if previous and previous != (prefix, kind):
                raise ValueError("Case/prefix/type collision: " + prefix)
            self.paths[key] = (prefix, kind)
        return rel


def inside(root, relative):
    rel = relative_name(relative)
    target = no_link_ancestors(Path(root) / rel)
    base = Path(root).resolve()
    try:
        target.resolve().relative_to(base)
    except ValueError:
        raise ValueError("Destination escaped new root") from None
    return target


def file_hash(path):
    before = regular(path)
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(CHUNK):
            value.update(chunk)
    after = regular(path)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Source changed while hashing: " + str(path))
    return value.hexdigest()


def directory_inventory(root):
    root = no_link_ancestors(root)
    regular(root, directory=True)
    names, files, directories = Names(), [], []

    def walk(folder):
        for entry in sorted(os.scandir(folder), key=lambda e: e.name):
            path = Path(entry.path)
            info = path.lstat()
            rel = path.relative_to(root).as_posix()
            is_dir = stat.S_ISDIR(info.st_mode)
            regular(path, directory=is_dir)
            names.add(rel, is_dir)
            if is_dir:
                directories.append(rel)
                walk(path)
            else:
                files.append({"path": rel, "bytes": info.st_size, "sha256": file_hash(path)})
    walk(root)
    return {"files": sorted(files, key=lambda row: row["path"]),
            "directories": sorted(directories)}


def archive_plan(path):
    no_link_ancestors(path)
    regular(path)
    names, members, total = Names(), [], 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("Archive member limit exceeded")
        for info in infos:
            archive_name = info.orig_filename
            normalized = archive_name.replace("\\", "/")
            if "\0" in archive_name or normalized != info.filename.replace("\\", "/"):
                raise ValueError("Altered/NUL member name")
            mode = stat.S_IFMT(info.external_attr >> 16)
            directory = normalized.endswith("/")
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.external_attr & 0x400:
                raise ValueError("ZIP symlink/special/reparse member rejected: " + info.filename)
            if (mode == stat.S_IFDIR and not directory) or (mode == stat.S_IFREG and directory):
                raise ValueError("ZIP member type/name mismatch")
            if bool(info.external_attr & 0x10) and not directory:
                raise ValueError("ZIP directory attribute mismatch")
            if info.flag_bits & 1:
                raise ValueError("Encrypted ZIP member rejected")
            rel = names.add(normalized, directory)
            if info.file_size < 0 or info.file_size > MAX_FILE_BYTES or (directory and info.file_size):
                raise ValueError("Archive member size rejected")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Archive total size limit exceeded")
            members.append({"name": info.filename, "original_name": archive_name,
                            "path": rel, "directory": directory,
                            "bytes": info.file_size, "crc": info.CRC})
    return {"members": members, "member_count": len(members), "uncompressed_bytes": total}


def copy_stream(stream, destination, expected_size):
    destination.parent.mkdir(parents=True, exist_ok=True)
    inside(destination.parent, destination.name)
    value, count = hashlib.sha256(), 0
    with destination.open("xb") as output:
        while chunk := stream.read(CHUNK):
            count += len(chunk)
            if count > expected_size or count > MAX_FILE_BYTES:
                raise ValueError("Actual stream exceeds declared size")
            output.write(chunk)
            value.update(chunk)
    if count != expected_size:
        raise ValueError("Actual stream differs from declared size")
    return value.hexdigest()


def prepare(specs, output):
    output = no_link_ancestors(output)
    if os.path.lexists(output):
        raise FileExistsError("Output already exists; no overwrite: " + str(output))
    plans = []
    ids = Names()
    for spec in specs:
        identity = ids.add(spec["id"], directory=True)
        if "/" in identity:
            raise ValueError("Cohort id must be one component")
        source = no_link_ancestors(spec["path"])
        if spec["kind"] == "directory":
            if output == source or source in output.parents:
                raise ValueError("Output cannot be inside original pool")
            prior = directory_inventory(source)
            expected = spec.get("expected_manifest")
            if expected is not None and sorted(expected, key=lambda row: row["path"]) != prior["files"]:
                raise ValueError("Original directory differs from qualification manifest")
            plan = {"inventory": prior}
            origin_hash = digest(prior)
            file_rows = prior["files"]
        elif spec["kind"] == "zip":
            origin_hash = file_hash(source)
            if spec.get("expected_sha256") and origin_hash != spec["expected_sha256"]:
                raise ValueError("Original archive differs from qualification hash")
            plan = archive_plan(source)
            file_rows = [{"path": row["path"], "bytes": row["bytes"]} for row in plan["members"] if not row["directory"]]
            if spec.get("expected_members") is not None and len(plan["members"]) != spec["expected_members"]:
                raise ValueError("Unexpected ZIP member count")
        else:
            raise ValueError("Unknown source kind")
        counts = {"file_count": len(file_rows),
                  "jsonl_count": sum(row["path"].lower().endswith(".jsonl") for row in file_rows)}
        if any(row["bytes"] > MAX_FILE_BYTES for row in file_rows) or sum(row["bytes"] for row in file_rows) > MAX_TOTAL_BYTES:
            raise ValueError("Source size limit exceeded")
        roots = [row["path"] for row in file_rows if "/" not in row["path"] and row["path"].endswith(".jsonl")]
        if roots != [spec["root_transcript"]]:
            raise ValueError("Unexpected root transcript set")
        for key, value in counts.items():
            if spec.get(key) is not None and spec[key] != value:
                raise ValueError("Unexpected source " + key)
        plans.append((spec, source, plan, origin_hash))
    output.mkdir(parents=True, exist_ok=False)
    cohorts = []
    for spec, source, plan, prior_hash in plans:
        pool = inside(output, spec["id"] + "/pool")
        pool.mkdir(parents=True, exist_ok=False)
        files = []
        if spec["kind"] == "directory":
            for rel in plan["inventory"]["directories"]:
                inside(pool, rel).mkdir(parents=True, exist_ok=True)
            for row in plan["inventory"]["files"]:
                target = inside(pool, row["path"])
                original = inside(source, row["path"])
                regular(original)
                with original.open("rb") as stream:
                    copied_hash = copy_stream(stream, target, row["bytes"])
                if copied_hash != row["sha256"]:
                    raise ValueError("Source changed while copying")
                files.append(dict(row))
            after_hash = digest(directory_inventory(source))
        else:
            with zipfile.ZipFile(source) as archive:
                for row in plan["members"]:
                    target = inside(pool, row["path"])
                    if row["directory"]:
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        with archive.open(row["name"], "r") as stream:
                            copied_hash = copy_stream(stream, target, row["bytes"])
                        files.append({"path": row["path"], "bytes": row["bytes"], "sha256": copied_hash})
            after_hash = file_hash(source)
        if after_hash != prior_hash:
            raise ValueError("Original source changed during freeze")
        files.sort(key=lambda row: row["path"])
        copied = directory_inventory(pool)
        if copied["files"] != files:
            raise ValueError("Copied file manifest mismatch")
        root_row = next(row for row in files if row["path"] == spec["root_transcript"])
        if spec.get("root_sha256") and root_row["sha256"] != spec["root_sha256"]:
            raise ValueError("Root transcript hash differs from qualification")
        sid = str(pool / spec["root_transcript"])
        cohorts.append({**spec.get("metadata", {}), "id": spec["id"], "pool": spec["id"] + "/pool",
            "sid": sid, "root_transcript": spec["root_transcript"], "roots": [sid],
            "files": files, "directories": copied["directories"], "file_count": len(files),
            "jsonl_count": sum(row["path"].lower().endswith(".jsonl") for row in files),
            "file_manifest_sha256": digest(files),
            "origin": {"kind": spec["kind"], "path": str(source), "sha256_before": prior_hash,
                       "sha256_after": after_hash, "hash_kind": "archive_bytes" if spec["kind"] == "zip" else "canonical_directory_inventory",
                       "member_count": plan.get("member_count")},
            "archive_members": plan.get("members") if spec["kind"] == "zip" else None,
            "registry_env": {"MIGLOOP_FROZEN_POOL": str(pool), "MIGLOOP_FROZEN_ANCHOR": sid,
                             "MIGLOOP_FROZEN_ROOTS": json.dumps([sid])}})
    manifest = {"schema": SCHEMA, "status": "sources_frozen", "created_at": datetime.now(timezone.utc).isoformat(),
                "cohorts": cohorts, "model_calls": 0, "gold_built": False,
                "note": "Byte freeze only. Registry validation is a separate artifact and may fail; no causal completeness claim."}
    save(output / "source-manifest.json", manifest)
    save(output / "SOURCE_READY.json", {"schema": "migloop-transfer-source-ready/1",
         "manifest_sha256": file_hash(output / "source-manifest.json"), "registry_passed": False})
    return manifest


def verify(output):
    output = no_link_ancestors(output)
    ready = json.loads((output / "SOURCE_READY.json").read_text(encoding="utf-8"))
    if file_hash(output / "source-manifest.json") != ready["manifest_sha256"]:
        raise ValueError("Frozen source manifest hash changed")
    manifest = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    if manifest["schema"] != SCHEMA or manifest["status"] != "sources_frozen":
        raise ValueError("Unsupported source manifest")
    for cohort in manifest["cohorts"]:
        pool = inside(output, cohort["pool"])
        actual = directory_inventory(pool)
        if actual != {"files": cohort["files"], "directories": cohort["directories"]}:
            raise ValueError("Frozen pool files changed: " + cohort["id"])
        if cohort["sid"] != str(pool / cohort["root_transcript"]):
            raise ValueError("Frozen root/sid mismatch")
    return manifest


def qualified_specs(dynamic_metadata, arch_metadata):
    d = json.loads(Path(dynamic_metadata).read_text(encoding="utf-8"))
    a = json.loads(Path(arch_metadata).read_text(encoding="utf-8"))
    if digest(d["source_manifest"]) != d["source_manifest_sha256"]:
        raise ValueError("Qualification manifest digest mismatch")

    def tasks(rows, prefix, exposure):
        values = []
        for i, row in enumerate(rows, 1):
            target = row["path"].replace("\\", "/")
            candidates = [target.find("/" + part + "/") for part in ("entry", "AppScope")]
            positions = [x for x in candidates if x >= 0]
            if not positions:
                raise ValueError("Target is outside registered application scope")
            relative = relative_name(target[min(positions) + 1:])
            values.append({"id": prefix + f"-{i:02d}", "relative_target": relative,
                           "original_target": target, "exposure": exposure})
        return values

    dynamic_tasks = tasks(d["selected_first_six_by_sha256"], "DYNAMIC1", "same_app_cross_run_development_exposed")
    arch_tasks = tasks(a["files"], "ARCH11", "same_app_lineage_post_stage3_checkpoint")
    if len(dynamic_tasks) != 6 or len(arch_tasks) != 7:
        raise ValueError("Qualification task count changed")
    arch_tasks[0]["exposure"] = "same_file_family_prior_pod730_investigation"
    arch_tasks[1]["exposure"] = "prior_transcript_literal_mention_not_proven_prior_target"
    roots = [row for row in d["source_manifest"] if "/" not in row["path"] and row["path"].endswith(".jsonl")]
    if len(roots) != 1:
        raise ValueError("Dynamic root not unique")
    return [
        {"id": "dynamic1", "kind": "directory", "path": d["source_pool"],
         "expected_manifest": d["source_manifest"], "file_count": 169, "jsonl_count": 78,
         "root_transcript": roots[0]["path"], "root_sha256": roots[0]["sha256"],
         "metadata": {"qualification_sha256": file_hash(dynamic_metadata),
          "qualification_source_manifest_sha256": d["source_manifest_sha256"],
          "generation_end": d["boundary"]["generation_workflow_complete"],
          "repair_qualification_start": d["boundary"]["since_exclusive"],
          "observation_end": d["boundary"]["at_inclusive"], "tasks": dynamic_tasks,
          "exposure": {"app_lineage": "AIPPT / DeepAI", "label": "same_app_cross_run_development_exposed",
                       "limitations": "Not unseen app or zero project exposure; no causal answer included."}}},
        {"id": "arch11", "kind": "zip", "path": a["archive"], "expected_sha256": a["archive_sha256"],
         "expected_members": 385, "file_count": 385, "jsonl_count": 193,
         "root_transcript": a["checkpoint"]["declaration"]["source"], "root_sha256": a["root_sha256"],
         "metadata": {"qualification_sha256": file_hash(arch_metadata),
          "generation_end": a["checkpoint"]["declaration"]["ts"],
          "repair_qualification_start": a["checkpoint"]["request"]["ts"],
          "observation_end": a["checkpoint"]["observation_end"]["ts"], "tasks": arch_tasks,
          "exposure": {"app_lineage": "AntennaPod", "label": "same_app_lineage_post_stage3_checkpoint",
                       "limitations": "Not execute-final or first build; Audio file-family exposure retained."}}}]


def decode_metadata(path):
    """Encoding availability only; never return text or infer time/actor."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    count = 0
    try:
        with Path(path).open("rb") as stream:
            while chunk := stream.read(CHUNK):
                count += len(decoder.decode(chunk))
            count += len(decoder.decode(b"", final=True))
    except (UnicodeError, OSError) as exc:
        return {"status": "decode_gap", "error_type": type(exc).__name__,
                "text_readable": False}
    return {"status": "utf8_decodable", "text_chars": count, "text_readable": True}


def registry_worker(output, repo, cohort_id):
    manifest = verify(output)
    cohort = next(c for c in manifest["cohorts"] if c["id"] == cohort_id)
    for key in list(os.environ):
        if key.startswith("MIGLOOP_"):
            del os.environ[key]
    os.environ.update(cohort["registry_env"])
    sys.path.insert(0, str(Path(repo) / "src"))
    from migloop import service, transcript_store
    scope = service.observation_scope(cohort["sid"])
    ledger = service.session_ledger(cohort["sid"])
    pool = inside(output, cohort["pool"])
    actual = sorted(Path(p).resolve().relative_to(pool).as_posix() for p in transcript_store.sources(ledger))
    expected = sorted(row["path"] for row in cohort["files"])
    encoding = [{"path": path, **decode_metadata(inside(pool, path))} for path in actual]
    gaps = [row for row in encoding if not row["text_readable"]]
    verify(output)
    return {"id": cohort_id, "sid": cohort["sid"], "roots": scope["roots"], "mode": scope["mode"],
            "coverage_kind": "all_registered_text_or_decode_gap",
            "expected_count": len(expected), "registered_count": len(actual), "registered": actual,
            "expected_jsonl_count": sum(path.lower().endswith(".jsonl") for path in expected),
            "registered_jsonl_count": sum(path.lower().endswith(".jsonl") for path in actual),
            "missing": sorted(set(expected) - set(actual)), "unexpected": sorted(set(actual) - set(expected)),
            "passed": actual == expected, "semantic_content_reported": False,
            "registered_text_decodable_count": len(encoding) - len(gaps), "decode_gaps": gaps,
            "all_expected_text_decodable": actual == expected and not gaps,
            "readability_note": "UTF8 encoding check only, not an API full-body delivery/semantic/actor/time certificate."}


def validate_registry(output, repo, python, audit_name):
    output, repo = Path(output), Path(repo)
    relative_name(audit_name)
    if "/" in audit_name or os.path.lexists(output / audit_name):
        raise FileExistsError("Registry audit must be a new root-level file")
    manifest = verify(output)

    def code_hashes():
        root = repo / "src/migloop"
        no_link_ancestors(root)
        entries = []
        for p in sorted(root.rglob("*")):
            if "__pycache__" in p.parts or p.suffix in (".pyc", ".pyo"):
                continue
            regular(p, directory=p.is_dir())
            if p.is_file() or p.is_symlink():
                entries.append({"path": p.relative_to(root).as_posix(),
                                "bytes": regular(p).st_size, "sha256": file_hash(p)})
        if not entries:
            raise ValueError("Runtime package is empty")
        content = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"content_digest": content, "entries": entries}
    before = code_hashes()
    rows = []
    for cohort in manifest["cohorts"]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("MIGLOOP_")}
        env["PYTHONUTF8"] = "1"
        command = [str(python), "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "_registry-worker",
                   "--out", str(output), "--repo", str(repo), "--cohort", cohort["id"]]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env,
                timeout=240, check=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if result.returncode:
                rows.append({"id": cohort["id"], "passed": False, "error": "registry_worker_failed",
                    "returncode": result.returncode, "stderr_chars": len(result.stderr),
                    "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest()})
            else:
                rows.append(json.loads(result.stdout))
        except (subprocess.TimeoutExpired, ValueError) as exc:
            rows.append({"id": cohort["id"], "passed": False, "error": type(exc).__name__,
                         "note": "Worker diagnostic body withheld; no causal content included."})
    after = code_hashes()
    verify(output)
    source_digest = file_hash(output / "source-manifest.json")
    data = {"schema": "migloop-transfer-registry-validation/1",
            "coverage_kind": "all_registered_text_or_decode_gap",
            "source_manifest_sha256": source_digest, "manifest_sha256": source_digest,
            "code_digest": before["content_digest"],
            "repo": str(repo.resolve()), "runtime_before": before, "runtime_after": after,
            "runtime_stable": before == after, "cohorts": rows,
            "passed": before == after and all(row["passed"] for row in rows), "model_calls": 0,
            "note": "Actual service.session_ledger/transcript_store registry; counts and paths only. Missing sources are failure, not silently flattened."}
    save(output / audit_name, data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dynamic-metadata", type=Path, required=True)
    p.add_argument("--arch-metadata", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("verify")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("registry")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--python", type=Path, default=Path(sys.executable))
    p.add_argument("--audit-name", required=True)
    p = sub.add_parser("_registry-worker")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--cohort", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        data = prepare(qualified_specs(args.dynamic_metadata, args.arch_metadata), args.out)
        print(json.dumps({"status": data["status"], "cohorts": [
            {"id": c["id"], "files": c["file_count"], "jsonl": c["jsonl_count"]} for c in data["cohorts"]]}))
    elif args.command == "verify":
        data = verify(args.out)
        print(json.dumps({"verified": True, "cohorts": [c["id"] for c in data["cohorts"]]}))
    elif args.command == "_registry-worker":
        print(json.dumps(registry_worker(args.out, args.repo, args.cohort)))
    else:
        data = validate_registry(args.out, args.repo, args.python, args.audit_name)
        print(json.dumps({"passed": data["passed"], "cohorts": data["cohorts"]}))


if __name__ == "__main__":
    main()
