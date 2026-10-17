"""Install only declared program files; never package or replace portable user data."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from app.paths import portable_path

MANIFEST = "program-manifest.json"


def _temporary(destination: Path) -> Path:
    # Dependency/license directories can already be near Windows MAX_PATH.
    # Reserve a short, unique sibling without replacing an unknown file.
    descriptor, name = tempfile.mkstemp(prefix=".u-", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    return Path(name)


def digest(path: Path):
    if not path.is_file():
        return None
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def resource_name(name: str) -> str:
    parts = name.split("/")
    if (not name or "\\" in name or ":" in name or any(part in {"", ".", ".."} for part in parts)
            or not (name in {"PersonalAiMemoryOs.exe", "使用说明.txt", MANIFEST} or parts[0] == "_internal")):
        raise ValueError("发行文件路径不属于程序资源。")
    return name


def create_manifest(bundle: Path, version: str, schema: str):
    files = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name != MANIFEST:
            name = resource_name(path.relative_to(bundle).as_posix())
            portable_path(bundle, path)
            files.append({"path": name, "sha256": digest(path)})
    result = {"version": version, "schema": schema, "files": files}
    (bundle / MANIFEST).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def read_manifest(bundle: Path):
    path = portable_path(bundle, bundle / MANIFEST)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("程序清单过大。")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or not isinstance(data.get("version"), str)
            or not isinstance(data.get("schema"), str) or not isinstance(data.get("files"), list)
            or not 2 <= len(data["files"]) <= 10000):
        raise ValueError("程序清单格式无效。")
    names = set()
    for entry in data["files"]:
        if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None):
            raise ValueError("程序清单哈希无效。")
        name = resource_name(entry["path"])
        if name in names or digest(portable_path(bundle, bundle / name)) != entry["sha256"]:
            raise ValueError("程序清单校验失败。")
        names.add(name)
    if not {"PersonalAiMemoryOs.exe", "_internal/python312.dll"}.issubset(names):
        raise ValueError("发行包缺少程序资源。")
    return data


def previous_names(target: Path, archive: Path | None):
    if (target / MANIFEST).is_file():
        path = portable_path(target, target / MANIFEST)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("旧程序清单过大。")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {resource_name(entry["path"]) for entry in data["files"]} | {MANIFEST}
    if archive is None or not archive.is_file():
        raise ValueError("旧安装没有资源清单；请提供原始发行 ZIP 以确认可替换文件。")
    with zipfile.ZipFile(archive) as source:
        result = set()
        for entry in source.infolist():
            if entry.is_dir():
                continue
            parts = entry.filename.split("/", 1)
            if len(parts) != 2:
                raise ValueError("旧发行 ZIP 路径无效。")
            result.add(resource_name(parts[1]))
        return result


def install_resources(bundle: Path, target: Path, backup: Path, old_names: set[str]):
    """Rollback file replacements on error; unknown files are preserved or rejected."""
    manifest = read_manifest(bundle)
    new_names = {entry["path"] for entry in manifest["files"]} | {MANIFEST}
    records = []
    for index, name in enumerate(sorted(new_names | old_names)):
        destination = portable_path(target, target / resource_name(name))
        source = portable_path(bundle, bundle / name)
        if destination.exists() and name not in old_names:
            raise ValueError("新程序文件与未纳管文件冲突，未覆盖。")
        old_hash = digest(destination)
        backup_name = f"program/{index:06d}.bin" if old_hash else None
        if old_hash:
            # Deep dependency/license paths otherwise exceed Windows MAX_PATH
            # once the portable root and backup timestamp are prepended.
            saved = portable_path(backup, backup / backup_name)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, saved)
            if digest(saved) != old_hash:
                raise RuntimeError("旧程序备份校验失败。")
        records.append({"path": name, "backup": backup_name, "before": old_hash,
                        "after": digest(source) if name in new_names else None})
    journal = backup / "program-update.json"
    journal.write_text(json.dumps({"phase": "prepared", "files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = []
    try:
        for record in records:
            destination = portable_path(target, target / record["path"])
            if digest(destination) != record["before"]:
                raise RuntimeError("升级期间程序文件发生变化，停止替换。")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if record["after"] is None:
                destination.unlink(missing_ok=True)
            else:
                temporary = portable_path(target, _temporary(destination))
                try:
                    shutil.copy2(bundle / record["path"], temporary)
                    if digest(temporary) != record["after"]:
                        raise RuntimeError("新程序文件校验失败。")
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
            changed.append(record)
        for record in records:
            if digest(target / record["path"]) != record["after"]:
                raise RuntimeError("安装后程序文件校验失败。")
        journal.write_text(json.dumps({"phase": "installed", "files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        try:
            for record in reversed(changed):
                destination = portable_path(target, target / record["path"])
                if digest(destination) != record["after"]:
                    raise RuntimeError("程序回滚遇到外部修改，请保留备份并人工恢复。")
                if record["before"] is None:
                    destination.unlink(missing_ok=True)
                else:
                    saved = portable_path(backup, backup / record["backup"])
                    if digest(saved) != record["before"]:
                        raise RuntimeError("程序备份已损坏，停止回滚。")
                    temporary = portable_path(target, _temporary(destination))
                    try:
                        shutil.copy2(saved, temporary)
                        temporary.replace(destination)
                    finally:
                        temporary.unlink(missing_ok=True)
                if digest(destination) != record["before"]:
                    raise RuntimeError("程序回滚校验失败。")
        except Exception:
            journal.write_text(json.dumps({"phase": "recovery_required", "files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        journal.write_text(json.dumps({"phase": "rolled_back", "files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    return manifest
