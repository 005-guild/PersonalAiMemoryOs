"""Strict backup verification and restoration into a NEW isolated directory."""

import json
from contextlib import closing
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
from uuid import uuid4

from app.desktop.bootstrap import _check_vault, _inspect_database
from app.desktop.storage_backup import file_digest
from app.paths import portable_path
from app.repositories.migrations import migration_config
from alembic.script import ScriptDirectory


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)


def relative_name(value: str) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or "\x00" in value or any(p in {"", ".", ".."} for p in value.split("/"))
            or PurePosixPath(value).is_absolute()):
        raise ValueError("Unsafe backup path")
    if any(p.rstrip(" .") != p or p.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)]} for p in value.split("/")):
        raise ValueError("Unsafe Windows backup path")
    return value


def verify_backup(backup: Path, *, require_configuration: bool = True) -> dict:
    backup = backup.absolute()
    portable_path(backup, backup)
    manifest = load_json(portable_path(backup, backup / "manifest.json"))
    if (not isinstance(manifest, dict) or manifest.get("database") != "memory.db"
            or manifest.get("knowledge") != "knowledge" or not isinstance(manifest.get("files"), list)
            or not isinstance(manifest.get("directories"), list)):
        raise ValueError("Unsupported storage manifest")
    files, names = {}, set()
    for entry in manifest["files"]:
        name = relative_name(entry["path"])
        if name != "memory.db" and not name.startswith("knowledge/"):
            raise ValueError("Storage manifest contains a non-storage file")
        if name.casefold() in names or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Duplicate path or invalid digest")
        names.add(name.casefold())
        path = portable_path(backup, backup / name)
        if not path.is_file() or file_digest(path) != entry["sha256"]:
            raise ValueError("Backup file missing or digest mismatch")
        files[name] = entry["sha256"]
    if "memory.db" not in files:
        raise ValueError("Backup has no database")
    directories = []
    for name in manifest["directories"]:
        name = relative_name(name)
        if name != "knowledge" and not name.startswith("knowledge/"):
            raise ValueError("Non-vault directory")
        if name.casefold() in names:
            raise ValueError("Duplicate or overlapping directory")
        names.add(name.casefold())
        if not portable_path(backup, backup / name).is_dir():
            raise ValueError("Backup directory missing")
        directories.append(name)
    if "knowledge" not in directories:
        raise ValueError("Backup lacks vault directory")
    actual_vault = {p.relative_to(backup).as_posix() for p in (backup / "knowledge").rglob("*")
                    if portable_path(backup, p).is_file()}
    if actual_vault != {name for name in files if name.startswith("knowledge/")}:
        raise ValueError("Unlisted vault file")
    configuration = {}
    config_manifest = portable_path(backup, backup / "configuration-manifest.json")
    if require_configuration or config_manifest.exists():
        configuration = load_json(config_manifest)
        if not isinstance(configuration, dict) or ".env" not in configuration:
            raise ValueError("Configuration backup lacks .env")
        seen = set()
        for name, expected in configuration.items():
            name = relative_name(name)
            if name != ".env" and not name.startswith("config/"):
                raise ValueError("Unsupported configuration path; map custom paths separately")
            if name.casefold() in seen or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError("Duplicate configuration or invalid digest")
            seen.add(name.casefold())
            path = portable_path(backup, backup / "configuration" / name)
            if not path.is_file() or file_digest(path) != expected:
                raise ValueError("Configuration file missing or digest mismatch")
        actual = {p.relative_to(backup / "configuration").as_posix()
                  for p in (backup / "configuration").rglob("*") if portable_path(backup, p).is_file()}
        if actual != set(configuration):
            raise ValueError("Unlisted configuration file")
    known = {s.revision for s in ScriptDirectory.from_config(migration_config()).walk_revisions()}
    revision, record, count = _inspect_database(backup / "memory.db", known)
    if revision != manifest.get("schema_revision"):
        raise ValueError("Backup revision differs from manifest")
    _check_vault(backup, backup / "knowledge", record, count)
    return {"schema": revision, "files": files, "directories": directories, "configuration": configuration}


def restore_new(backup: Path, target: Path) -> dict:
    """Never restore over an installation; leave personal configuration bytes intact.

    This helper does not launch the app or evaluate restored Settings. Callers must
    disable AI/RAG and validate all restored paths before their first startup.
    """
    backup, target = backup.absolute(), target.absolute()
    portable_path(target.parent, target)
    if target.exists() or target.is_relative_to(backup) or backup.is_relative_to(target):
        raise ValueError("Restore target must be a new, separate directory")
    saved = verify_backup(backup)
    stage = target.with_name(".restore-" + uuid4().hex)
    stage.mkdir()
    try:
        for name in saved["directories"]:
            (stage / name).mkdir(parents=True, exist_ok=True)
        database = stage / "data/memory.db"
        database.parent.mkdir()
        for name, expected in saved["files"].items():
            output = database if name == "memory.db" else stage / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / name, output)
            if file_digest(output) != expected:
                raise ValueError("Restore copy digest mismatch")
        for name, expected in saved["configuration"].items():
            output = stage / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / "configuration" / name, output)
            if file_digest(output) != expected:
                raise ValueError("Restore configuration digest mismatch")
        # Detect changes to the backup while copying, before publishing the copy.
        if saved != verify_backup(backup):
            raise ValueError("Backup changed during restore")
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Restored database is invalid")
        stage.rename(target)
    except BaseException:
        # Keep the failed isolated staging directory for inspection; never delete
        # a user-supplied path or publish a partially restored installation.
        raise
    return {"status": "restored", "schema": saved["schema"], "files": len(saved["files"]),
            "configuration_files": len(saved["configuration"]), "target": str(target),
            "ai_rag_started": False}


def backup_configuration(root: Path, backup: Path) -> None:
    paths = [root / ".env", *sorted((root / "config").rglob("*"))]
    manifest = {}
    for path in paths:
        portable_path(root, path)
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        output = backup / "configuration" / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        expected = file_digest(path)
        shutil.copy2(path, output)
        if file_digest(path) != expected or file_digest(output) != expected:
            raise ValueError("Configuration changed during backup")
        manifest[relative] = expected
    (backup / "configuration-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
