"""Installer transaction tests using disposable skill roots, not user installs."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "migloop-memory-maintain/scripts/install_bundle.py"
spec = importlib.util.spec_from_file_location("bundle_installer", SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    source = tmp_path / "source"
    for name in installer.NAMES:
        package = source / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text("new " + name, encoding="utf-8")
    monkeypatch.setattr(installer, "__file__", str(source / "migloop-memory-maintain/scripts/install_bundle.py"))
    destination = tmp_path / "profile/skills"
    return source, destination


def seed(destination, names=None):
    for name in installer.NAMES if names is None else names:
        package = destination / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text("old " + name, encoding="utf-8")
        (package / "local-custom.txt").write_text("user content", encoding="utf-8")


def inventory(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_first_install_and_refusal_leave_existing_intact(bundle):
    source, destination = bundle
    result = installer.install(destination)
    assert len(result["skills"]) == 4
    assert inventory(destination) == inventory(source)
    before = inventory(destination)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        installer.install(destination)
    assert inventory(destination) == before


def test_update_backup_restore_and_unrelated_skill(bundle):
    source, destination = bundle
    seed(destination)
    other = destination / "unrelated"
    other.mkdir()
    (other / "keep.txt").write_text("untouched", encoding="utf-8")
    before = inventory(destination)
    updated = installer.install(destination, update=True)
    backup = Path(updated["backup"])
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["state"] == "completed"
    assert manifest["present_before"] == list(installer.NAMES)
    for name in installer.NAMES:
        assert inventory(destination / name) == inventory(source / name)
        assert (backup / "previous" / name / "local-custom.txt").read_text() == "user content"
    after = inventory(destination)
    reverted = installer.restore(destination, backup)
    assert inventory(destination) == before
    installer.restore(destination, reverted["backup"])
    assert inventory(destination) == after  # Restore is itself reversible.


def test_restore_partial_install_recovers_absence_as_well_as_content(bundle):
    _, destination = bundle
    seed(destination, installer.NAMES[:1])
    before = inventory(destination)
    result = installer.install(destination, update=True)
    installer.restore(destination, result["backup"])
    assert inventory(destination) == before
    assert all(not (destination / n).exists() for n in installer.NAMES[1:])


def test_staging_failure_never_touches_installed_packages(bundle, monkeypatch):
    _, destination = bundle
    seed(destination)
    before = inventory(destination)
    original = installer.shutil.copytree

    def fail(source, target, **kwargs):
        if Path(source).name == installer.NAMES[1]:
            raise OSError("injected copy failure")
        return original(source, target, **kwargs)

    monkeypatch.setattr(installer.shutil, "copytree", fail)
    with pytest.raises(OSError, match="injected"):
        installer.install(destination, update=True)
    assert inventory(destination) == before
    assert not list(destination.parent.glob(".migloop-stage-*"))


@pytest.mark.parametrize("phase", ["backup", "publish"])
def test_move_failure_rolls_back_all_four(bundle, monkeypatch, phase):
    _, destination = bundle
    seed(destination)
    before = inventory(destination)
    original = Path.rename
    failed = False

    def fail(path, target):
        nonlocal failed
        trigger = (path.parent == destination if phase == "backup" else path.parent.name.startswith(".migloop-stage-"))
        if trigger and path.name == installer.NAMES[2] and not failed:
            failed = True
            raise OSError("injected rename failure")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(RuntimeError, match="rolled_back"):
        installer.install(destination, update=True)
    assert failed and inventory(destination) == before
    manifests = list((destination.parent / ".migloop-skill-backups").glob("*/manifest.json"))
    assert json.loads(manifests[0].read_text())["state"] == "rolled_back"


def test_rollback_failure_keeps_backup_and_stage_for_recovery(bundle, monkeypatch):
    _, destination = bundle
    seed(destination)
    original = Path.rename

    def fail(path, target):
        if path.parent.name.startswith(".migloop-stage-") and path.name == installer.NAMES[1]:
            raise OSError("publish failure")
        if path.parent.name == "previous" and path.name == installer.NAMES[2]:
            raise OSError("restore failure")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(RuntimeError, match="rollback_failed"):
        installer.install(destination, update=True)
    manifest_path = next((destination.parent / ".migloop-skill-backups").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert manifest["state"] == "rollback_failed" and manifest["errors"]
    assert Path(manifest["stage"]).is_dir()
    assert (manifest_path.parent / "previous" / installer.NAMES[2] / "local-custom.txt").read_text() == "user content"


def test_locked_installation_does_not_touch_existing(bundle):
    _, destination = bundle
    seed(destination)
    lock = destination / ".migloop-install.lock"
    lock.write_text("other process", encoding="utf-8")
    before = inventory(destination)
    with pytest.raises(ValueError, match="holds"):
        installer.install(destination, update=True)
    assert inventory(destination) == before


def test_invalid_source_and_target_rejected_before_replacement(bundle):
    source, destination = bundle
    seed(destination)
    before = inventory(destination)
    (source / installer.NAMES[1] / "SKILL.md").unlink()
    with pytest.raises(ValueError, match="Missing sibling"):
        installer.install(destination, update=True)
    assert inventory(destination) == before


@pytest.mark.parametrize("relative", ["", "migloop-build-cards/nested"])
def test_source_overlap_is_rejected(bundle, relative):
    source, _ = bundle
    before = inventory(source)
    with pytest.raises(ValueError, match="overlap"):
        installer.install(source / relative, update=True)
    assert inventory(source) == before


def test_existing_non_directory_is_preserved(bundle):
    _, destination = bundle
    destination.mkdir(parents=True)
    path = destination / installer.NAMES[0]
    path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory"):
        installer.install(destination, update=True)
    assert path.read_text() == "not a directory"


def test_linked_destination_is_rejected(bundle, tmp_path):
    _, destination = bundle
    outside = tmp_path / "outside"
    outside.mkdir()
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    with pytest.raises(ValueError, match="Linked"):
        installer.install(destination, update=True)
    assert list(outside.iterdir()) == []


def test_restore_checks_destination_and_completed_manifest(bundle, tmp_path):
    _, destination = bundle
    seed(destination)
    result = installer.install(destination, update=True)
    before = inventory(destination)
    with pytest.raises(ValueError, match="different destination"):
        installer.restore(tmp_path / "other", result["backup"])
    manifest = Path(result["backup"]) / "manifest.json"
    data = json.loads(manifest.read_text())
    data["state"] = "installing"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="completed"):
        installer.restore(destination, result["backup"])
    assert inventory(destination) == before
