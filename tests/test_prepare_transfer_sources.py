"""New-source freezing safety; all content is small local synthetic data."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import zipfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "docs/experiments/generalization-20260910/prepare_transfer_sources.py"
SPEC = importlib.util.spec_from_file_location("prepare_transfer_sources_tests", SCRIPT)
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


def fixtures(tmp_path):
    source = tmp_path / "original"
    nested = source / "root/subagents/workflows/wf-one"
    nested.mkdir(parents=True)
    (source / "root.jsonl").write_bytes(b'{"metadata":"root"}\n')
    (nested / "agent-one.jsonl").write_bytes(b'{"metadata":"child"}\n')
    (nested / "agent-one.meta.json").write_bytes(b'{"id":"child"}\n')
    (source / "empty-directory").mkdir()
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("zroot.jsonl", b'{"metadata":"archive-root"}\n')
        z.writestr("zroot/subagents/agent-two.jsonl", b'{"metadata":"archive-child"}\n')
        z.writestr("zroot/subagents/agent-two.meta.json", b'{"id":"child"}\n')
    specs = [
        {"id": "dynamic1", "kind": "directory", "path": str(source), "root_transcript": "root.jsonl",
         "expected_manifest": freeze.directory_inventory(source)["files"], "file_count": 3, "jsonl_count": 2},
        {"id": "arch11", "kind": "zip", "path": str(archive), "root_transcript": "zroot.jsonl",
         "expected_sha256": freeze.file_hash(archive), "expected_members": 3, "file_count": 3, "jsonl_count": 2},
    ]
    return source, archive, specs


def test_freeze_preserves_every_byte_and_nested_hierarchy(tmp_path):
    source, archive, specs = fixtures(tmp_path)
    before = freeze.directory_inventory(source)
    zip_before = freeze.file_hash(archive)
    out = tmp_path / "new-freeze"
    manifest = freeze.prepare(specs, out)
    assert manifest["status"] == "sources_frozen"
    assert (out / "dynamic1/pool/root/subagents/workflows/wf-one/agent-one.jsonl").read_bytes() == b'{"metadata":"child"}\n'
    assert (out / "dynamic1/pool/empty-directory").is_dir()
    assert freeze.verify(out) == manifest
    assert freeze.directory_inventory(source) == before and freeze.file_hash(archive) == zip_before
    assert [x["file_count"] for x in manifest["cohorts"]] == [3, 3]
    assert [x["jsonl_count"] for x in manifest["cohorts"]] == [2, 2]
    assert json.loads((out / "SOURCE_READY.json").read_text())["registry_passed"] is False
    for c in manifest["cohorts"]:
        assert Path(c["sid"]).parent == out / c["pool"]
        assert c["roots"] == [c["sid"]]
        assert c["origin"]["sha256_before"] == c["origin"]["sha256_after"]


def test_repeat_rejected_without_overwrite_or_removal(tmp_path):
    _, _, specs = fixtures(tmp_path)
    out = tmp_path / "new-freeze"
    freeze.prepare(specs, out)
    previous = (out / "source-manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        freeze.prepare(specs, out)
    assert (out / "source-manifest.json").read_bytes() == previous


@pytest.mark.parametrize("name", [
    "/absolute.jsonl", "//server/share/a", "C:/absolute.jsonl", "C:relative.jsonl",
    "../escape", "ok/../../escape", "ok/../escape", r"..\escape",
    "./alias", "a//b", "name.", "name ", "a:stream", "NUL.jsonl", "COM1",
])
def test_rejects_unsafe_zip_before_creating_output(tmp_path, name):
    _, archive, specs = fixtures(tmp_path)
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("zroot.jsonl", b"root")
        z.writestr(name, b"unsafe")
    specs[1].pop("expected_sha256")
    specs[1].pop("expected_members")
    out = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        freeze.prepare(specs, out)
    assert not out.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("names", [
    ["a.jsonl", "A.jsonl"], ["a.jsonl", "a.jsonl"], ["Dir/a", "dir/b"],
    ["dir", "dir/child"], ["dir/child", "dir"], ["dir/", "DIR/"],
])
def test_rejects_case_duplicate_and_prefix_collisions(tmp_path, names):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in names:
            z.writestr(name, b"" if name.endswith("/") else b"body")
    with pytest.raises(ValueError):
        freeze.archive_plan(archive)


@pytest.mark.parametrize("kind", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK])
def test_rejects_symlink_and_special_archive_entries(tmp_path, kind):
    archive = tmp_path / "special.zip"
    entry = zipfile.ZipInfo("evil")
    entry.create_system = 3
    entry.external_attr = (kind | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(entry, "target")
    with pytest.raises(ValueError, match="special"):
        freeze.archive_plan(archive)


def test_accepts_regular_files_and_explicit_directories(tmp_path):
    archive = tmp_path / "normal.zip"
    folder = zipfile.ZipInfo("folder/")
    folder.create_system = 3
    folder.external_attr = ((stat.S_IFDIR | 0o755) << 16) | 0x10
    file = zipfile.ZipInfo("folder/regular.jsonl")
    file.create_system = 3
    file.external_attr = (stat.S_IFREG | 0o644) << 16
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(folder, b"")
        z.writestr(file, b"data")
    assert freeze.archive_plan(archive)["member_count"] == 2


def test_windows_zip_separators_are_normalized_without_flattening(tmp_path):
    archive = tmp_path / "windows.zip"
    child = zipfile.ZipInfo("placeholder")
    child.filename = r"zroot\subagents\workflows\wf-one\agent.jsonl"
    folder = zipfile.ZipInfo("placeholder")
    folder.filename = "empty\\"
    folder.external_attr = 0x10
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("zroot.jsonl", b"root")
        z.writestr(child, b"child")
        z.writestr(folder, b"")
    spec = {"id": "archive", "kind": "zip", "path": str(archive), "root_transcript": "zroot.jsonl"}
    out = tmp_path / "out"
    manifest = freeze.prepare([spec], out)
    assert (out / "archive/pool/zroot/subagents/workflows/wf-one/agent.jsonl").read_bytes() == b"child"
    assert "\\" in manifest["cohorts"][0]["archive_members"][1]["original_name"]
    assert (out / "archive/pool/empty").is_dir()
    assert freeze.verify(out) == manifest


def test_normalized_slash_collision_and_nul_rejected(tmp_path):
    archive = tmp_path / "aliases.zip"
    aliased = zipfile.ZipInfo("placeholder")
    aliased.filename = r"folder\child"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("folder/child", b"a")
        z.writestr(aliased, b"b")
    with pytest.raises(ValueError):
        freeze.archive_plan(archive)
    malicious = zipfile.ZipInfo("placeholder")
    malicious.filename = "prefix\0hidden"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(malicious, b"x")
    with pytest.raises(ValueError, match="NUL"):
        freeze.archive_plan(archive)


def test_preflight_size_and_member_limits(tmp_path, monkeypatch):
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("a", b"a" * 20)
        z.writestr("b", b"b" * 20)
    monkeypatch.setattr(freeze, "MAX_FILE_BYTES", 10)
    with pytest.raises(ValueError, match="size"):
        freeze.archive_plan(archive)
    monkeypatch.setattr(freeze, "MAX_FILE_BYTES", 100)
    monkeypatch.setattr(freeze, "MAX_TOTAL_BYTES", 30)
    with pytest.raises(ValueError, match="total"):
        freeze.archive_plan(archive)
    monkeypatch.setattr(freeze, "MAX_TOTAL_BYTES", 100)
    monkeypatch.setattr(freeze, "MAX_MEMBERS", 1)
    with pytest.raises(ValueError, match="member"):
        freeze.archive_plan(archive)


def test_manifest_mismatch_and_output_inside_source_rejected(tmp_path):
    source, _, specs = fixtures(tmp_path)
    specs[0]["expected_manifest"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="manifest"):
        freeze.prepare(specs, tmp_path / "out")
    with pytest.raises(ValueError, match="inside original"):
        freeze.prepare(specs, source / "new")
    assert not (tmp_path / "out").exists()


def test_archive_hash_mismatch_rejected(tmp_path):
    _, _, specs = fixtures(tmp_path)
    specs[1]["expected_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="archive"):
        freeze.prepare(specs, tmp_path / "out")


def test_source_mutation_preserves_partial_output_without_ready(tmp_path, monkeypatch):
    source, _, specs = fixtures(tmp_path)
    old = freeze.copy_stream
    changed = False

    def mutate(*args):
        nonlocal changed
        result = old(*args)
        if not changed:
            (source / "root.jsonl").write_bytes(b"changed source")
            changed = True
        return result
    monkeypatch.setattr(freeze, "copy_stream", mutate)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        freeze.prepare(specs, out)
    assert out.is_dir() and not (out / "SOURCE_READY.json").exists()
    with pytest.raises(FileExistsError):
        freeze.prepare(specs, out)


def test_verify_rejects_changed_or_extra_frozen_file(tmp_path):
    _, _, specs = fixtures(tmp_path)
    out = tmp_path / "out"
    freeze.prepare(specs, out)
    (out / "arch11/pool/extra").write_bytes(b"extra")
    with pytest.raises(ValueError, match="changed"):
        freeze.verify(out)


def test_symlink_source_and_destination_ancestor_rejected(tmp_path):
    source, _, specs = fixtures(tmp_path)
    link = tmp_path / "link"
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit synthetic symlink creation")
    with pytest.raises(ValueError, match="Symlink"):
        freeze.prepare(specs, link / "out")
    (source / "bad").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="Symlink"):
        freeze.prepare(specs, tmp_path / "out")


def test_registry_records_missing_sources_as_failure_without_rewriting_manifest(tmp_path, monkeypatch):
    _, _, specs = fixtures(tmp_path)
    out = tmp_path / "out"
    freeze.prepare(specs, out)
    manifest = (out / "source-manifest.json").read_bytes()
    repo = tmp_path / "code"
    package = repo / "src/migloop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"# synthetic package")

    class Result:
        returncode = 0
        stderr = ""
        stdout = json.dumps({"id": "synthetic", "passed": False, "registered_count": 1,
                             "missing": ["nested/child.jsonl"], "unexpected": []})
    monkeypatch.setattr(freeze.subprocess, "run", lambda *args, **kw: Result())
    report = freeze.validate_registry(out, repo, Path(os.sys.executable), "registry-1.json")
    assert not report["passed"]
    assert report["coverage_kind"] == "all_registered_text_or_decode_gap"
    assert report["source_manifest_sha256"] == freeze.file_hash(out / "source-manifest.json")
    assert len(report["code_digest"]) == 64
    assert (out / "source-manifest.json").read_bytes() == manifest
    with pytest.raises(FileExistsError):
        freeze.validate_registry(out, repo, Path(os.sys.executable), "registry-1.json")


def test_encoding_gap_is_not_claimed_readable(tmp_path):
    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"\xff\xfe\x00")
    value = freeze.decode_metadata(binary)
    assert value["status"] == "decode_gap" and value["text_readable"] is False
    assert "text_chars" not in value
    text = tmp_path / "text.txt"
    text.write_bytes(b"plain text\n")
    assert freeze.decode_metadata(text) == {"status": "utf8_decodable", "text_chars": 11, "text_readable": True}


def test_registry_worker_compares_all_files_not_only_jsonl(tmp_path, monkeypatch):
    from types import ModuleType, SimpleNamespace
    _, _, specs = fixtures(tmp_path)
    out = tmp_path / "out"
    manifest = freeze.prepare(specs, out)
    cohort = manifest["cohorts"][0]
    pool = out / cohort["pool"]
    monkeypatch.setattr(freeze.os, "environ", dict(os.environ))
    registry = {str(pool / row["path"]): set() for row in cohort["files"]}
    runtime = ModuleType("migloop")
    runtime.service = SimpleNamespace(
        observation_scope=lambda sid: {"roots": [sid], "mode": "synthetic"},
        session_ledger=lambda sid: object())
    runtime.transcript_store = SimpleNamespace(sources=lambda ledger: registry)
    monkeypatch.setitem(freeze.sys.modules, "migloop", runtime)
    monkeypatch.setattr(freeze.sys, "path", list(freeze.sys.path))
    checked = freeze.registry_worker(out, tmp_path / "unused-code", "dynamic1")
    assert checked["passed"] and checked["registered_count"] == 3
    assert checked["registered_jsonl_count"] == checked["expected_jsonl_count"] == 2
    assert checked["registered_text_decodable_count"] == 3
    assert checked["coverage_kind"] == "all_registered_text_or_decode_gap"
    attachment = next(path for path in registry if path.endswith(".meta.json"))
    del registry[attachment]
    missing = freeze.registry_worker(out, tmp_path / "unused-code", "dynamic1")
    assert not missing["passed"] and missing["registered_jsonl_count"] == 2
    assert len(missing["missing"]) == 1 and not missing["all_expected_text_decodable"]
