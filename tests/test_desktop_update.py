"""Resource updates preserve portable data and unknown files, with verified rollback."""

from pathlib import Path
import json
import shutil
import pytest

from app.desktop.update_resources import create_manifest, install_resources, read_manifest, resource_name


def bundle(root):
    for name in ("PersonalAiMemoryOs.exe", "_internal/python312.dll", "_internal/app/web/index.html", "使用说明.txt"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"new resource " + name.encode())
    create_manifest(root, "0.7.0", "0005")


def test_inplace_update_preserves_private_and_unknown_files(tmp_path):
    source, target, backup = (tmp_path / name for name in ("bundle", "installation", "backup"))
    bundle(source)
    shutil.copytree(source, target)
    old = read_manifest(target)
    owned = {item["path"] for item in old["files"]} | {"program-manifest.json"}
    private = {".env": b"private sentinel", "data/memory.db": b"business sentinel",
               "knowledge/.memory-os-vault": b"vault", "exports/report.json": b"report",
               "_internal/user-document.txt": b"unknown"}
    for name, content in private.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (target / "PersonalAiMemoryOs.exe").write_bytes(b"old executable")
    backup.mkdir()
    result = install_resources(source, target, backup, owned)
    assert result["version"] == "0.7.0"
    assert all((target / name).read_bytes() == content for name, content in private.items())
    journal = json.loads((backup / "program-update.json").read_text(encoding="utf-8"))
    saved_exe = next(item["backup"] for item in journal["files"] if item["path"] == "PersonalAiMemoryOs.exe")
    assert (backup / saved_exe).read_bytes() == b"old executable"
    assert all(len(Path(item["backup"]).parts) == 2 for item in journal["files"] if item["backup"])


def test_replacement_failure_rolls_back_without_touching_data(tmp_path, monkeypatch):
    source, target, backup = (tmp_path / name for name in ("bundle", "installation", "backup"))
    bundle(source)
    shutil.copytree(source, target)
    owned = {item["path"] for item in read_manifest(target)["files"]} | {"program-manifest.json"}
    before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    backup.mkdir()
    replace = Path.replace
    counter = 0
    def failed(path, destination):
        nonlocal counter
        counter += 1
        if counter == 3:
            raise PermissionError("synthetic locked file")
        return replace(path, destination)
    monkeypatch.setattr(Path, "replace", failed)
    with pytest.raises(PermissionError):
        install_resources(source, target, backup, owned)
    assert {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("path", ["../.env", "data/memory.db", "_internal/../data/memory.db", "D:/outside", "_internal\\file"])
def test_manifest_cannot_target_user_data_or_escape(path):
    with pytest.raises(ValueError):
        resource_name(path)


def test_unowned_collision_is_rejected(tmp_path):
    source, target, backup = (tmp_path / name for name in ("bundle", "installation", "backup"))
    bundle(source)
    target.mkdir()
    (target / "PersonalAiMemoryOs.exe").write_bytes(b"unknown file")
    backup.mkdir()
    with pytest.raises(ValueError, match="未纳管"):
        install_resources(source, target, backup, set())
    assert (target / "PersonalAiMemoryOs.exe").read_bytes() == b"unknown file"


def test_missing_source_with_null_hash_is_rejected(tmp_path):
    bundle(tmp_path)
    path = tmp_path / "program-manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["files"][0]["sha256"] = None
    (tmp_path / data["files"][0]["path"]).unlink()
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        read_manifest(tmp_path)


class Lease:
    owner = True
    def __init__(self, root):
        self.root = root
    def close(self):
        pass


def installation(root):
    from test_desktop_storage import make_old_database
    bundle(root)
    make_old_database(root, "0004")
    for name, content in {".env": b"MEMORY_OS_AI_ENABLED=false\n", "config/ai-providers.yml": b"private sentinel",
                          "config/embedding-providers.yml": b"embedding sentinel", "unknown.txt": b"keep me"}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_upgrade_migrates_in_place_with_verified_data_and_configuration(tmp_path):
    from app.desktop.update import upgrade_portable
    from test_desktop_storage import revision
    source, target = tmp_path / "clean", tmp_path / "fixed-installation"
    bundle(source)
    installation(target)
    config = (target / "config/ai-providers.yml").read_bytes()
    result = upgrade_portable(source, target, lease_factory=Lease)
    backup = Path(result["backup"])
    assert revision(target / "data/memory.db") == "0005"
    assert revision(backup / "memory.db") == "0004"
    assert (backup / "configuration/config/ai-providers.yml").read_bytes() == config
    assert (target / "config/ai-providers.yml").read_bytes() == config
    assert (target / "unknown.txt").read_bytes() == b"keep me"
    assert (target / "knowledge/.memory-os-vault").read_text() == "vault-token"
    assert not (target / ".memory-os-upgrade.json").exists()


def test_live_installation_refuses_update_without_changing_program(tmp_path):
    from app.desktop.update import upgrade_portable
    source, target = tmp_path / "clean", tmp_path / "fixed"
    bundle(source)
    installation(target)
    before = (target / "PersonalAiMemoryOs.exe").read_bytes()
    class Busy(Lease):
        owner = False
    with pytest.raises(RuntimeError, match="仍在运行"):
        upgrade_portable(source, target, lease_factory=Busy)
    assert (target / "PersonalAiMemoryOs.exe").read_bytes() == before
    assert not (target / "backups").exists()


@pytest.mark.parametrize("setting", ["MEMORY_OS_KNOWLEDGE_DIR=_internal/notes", "MEMORY_OS_AI_CONFIG_FILE=_internal/private.yml"])
def test_overlapping_custom_paths_stop_upgrade(tmp_path, setting):
    from app.desktop.update import upgrade_portable
    source, target = tmp_path / "clean", tmp_path / "fixed"
    bundle(source)
    installation(target)
    (target / ".env").write_text(setting, encoding="utf-8")
    with pytest.raises(ValueError, match="重叠"):
        upgrade_portable(source, target, lease_factory=Lease)
    assert not (target / "backups").exists()


def test_interrupted_upgrade_blocks_startup_and_repeated_update(tmp_path):
    from app.desktop.update import upgrade_portable
    from app.desktop.bootstrap import DesktopStorageError, prepare_desktop
    source, target = tmp_path / "clean", tmp_path / "fixed"
    bundle(source)
    installation(target)
    (target / ".memory-os-upgrade.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="未完成"):
        upgrade_portable(source, target, lease_factory=Lease)
    with pytest.raises(DesktopStorageError, match="未完成"):
        prepare_desktop(target, lambda _: True)
