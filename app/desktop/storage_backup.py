"""Verified pre-migration copies of the selected SQLite database and full vault."""

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.paths import portable_path


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _vault_entries(root: Path, vault: Path) -> tuple[list[Path], list[Path]]:
    directories, files = [], []

    def fail(error):
        raise error

    for current, folder_names, file_names in os.walk(vault, followlinks=False, onerror=fail):
        folder_names.sort()
        for name in folder_names:
            directories.append(portable_path(root, Path(current) / name))
        for name in sorted(file_names):
            path = portable_path(root, Path(current) / name)
            if not path.is_file():
                raise ValueError("知识目录包含非常规文件，无法备份。")
            files.append(path)
    return directories, files


def backup_storage(root: Path, database: Path, vault: Path, revision: str) -> Path:
    """Use SQLite's backup API; preserve every vault file, including its marker."""
    parent = portable_path(root, root / "backups")
    if parent.is_relative_to(vault):
        raise ValueError("备份目录不能位于知识目录内。")
    parent.mkdir(exist_ok=True)
    target = parent / (datetime.now(timezone.utc).strftime("upgrade-%Y%m%d-%H%M%S-") + uuid4().hex[:8])
    target.mkdir()
    directories = ["knowledge"]
    files = []
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(target / "memory.db") as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("数据库备份完整性检查失败。")
    files.append({"path": "memory.db", "sha256": file_digest(target / "memory.db")})
    (target / "knowledge").mkdir()
    if vault.exists():
        source_directories, source_files = _vault_entries(root, vault)
        for directory in source_directories:
            relative = Path("knowledge") / directory.relative_to(vault)
            (target / relative).mkdir()
            directories.append(relative.as_posix())
        for path in source_files:
            relative = Path("knowledge") / path.relative_to(vault)
            expected = file_digest(path)
            shutil.copy2(path, target / relative)
            if file_digest(path) != expected or file_digest(target / relative) != expected:
                raise RuntimeError("知识文件在备份期间变化，已停止升级。")
            files.append({"path": relative.as_posix(), "sha256": expected})
        if _vault_entries(root, vault) != (source_directories, source_files):
            raise RuntimeError("知识目录在备份期间变化，已停止升级。")
        for entry in files[1:]:
            if file_digest(vault / Path(entry["path"]).relative_to("knowledge")) != entry["sha256"]:
                raise RuntimeError("知识文件在备份期间变化，已停止升级。")
    manifest = {"schema_revision": revision, "database": "memory.db", "knowledge": "knowledge",
                "directories": directories, "files": files}
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # Verify from the saved manifest, rather than relying on successful copy calls.
    saved = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    for entry in saved["files"]:
        if file_digest(target / entry["path"]) != entry["sha256"]:
            raise RuntimeError("备份清单校验失败，已停止升级。")
    return target
