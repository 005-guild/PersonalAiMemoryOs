"""Upgrade a stopped portable installation, preserving verified user data."""

import json
from pathlib import Path
import shutil
import sqlite3

from app.config import Settings, resolve_database_url
from app.desktop.bootstrap import _check_vault, _inspect_database
from app.desktop.instance import SingleInstance
from app.desktop.storage_backup import backup_storage
from app.desktop.update_resources import digest, install_resources, previous_names, read_manifest
from app.paths import portable_path
from app.repositories.migrations import migration_config, upgrade_database
from alembic.script import ScriptDirectory


def _settings(root: Path, resource_names: set[str]):
    settings = Settings(_env_file=root / ".env", runtime_root=root)
    database = portable_path(root, Path(resolve_database_url(settings.database_url, root=root).database))
    vault = portable_path(root, settings.knowledge_path)
    configs = {portable_path(root, root / ".env"), portable_path(root, settings.ai_config_path),
               portable_path(root, settings.embedding_config_path)}
    for path in {database, vault, *configs}:
        relative = path.relative_to(root)
        if (not relative.parts or relative.parts[0].lower() == "_internal"
                or relative.as_posix().lower() in {name.lower() for name in resource_names}):
            raise ValueError("个人数据或配置路径与程序资源重叠，已停止升级。")
    return settings, database, vault, configs


def _legacy_snapshot(database: Path, columns=None):
    """Compare every existing row/column, allowing only additive migrations."""
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        if columns is None:
            names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                     if r[0] != "alembic_version" and not r[0].startswith("sqlite_")]
            columns = {name: [r[1] for r in connection.execute(f'PRAGMA table_info("{name}")')] for name in names}
        data = {}
        for name, fields in columns.items():
            # Names come exclusively from SQLite schema, never request strings.
            quoted = lambda value: '"' + value.replace('"', '""') + '"'
            rows = connection.execute("SELECT " + ",".join(map(quoted, fields)) + " FROM " + quoted(name)).fetchall()
            data[name] = sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    return columns, data


def _config_files(root: Path, configs: set[Path]):
    folder = portable_path(root, root / "config")
    if folder.exists():
        configs |= {portable_path(root, path) for path in folder.rglob("*") if path.is_file()}
    return {path: digest(path) for path in configs if path.is_file()}


def upgrade_portable(bundle: Path, target: Path, archive: Path | None = None, *, lease_factory=SingleInstance):
    """Caller must close the app normally; no process is killed or auto-reopened."""
    target, bundle = Path(target).absolute(), Path(bundle).absolute()
    portable_path(target, target)
    pending = portable_path(target, target / ".memory-os-upgrade.json")
    if pending.exists():
        raise RuntimeError("已有未完成升级记录，请先核对备份并恢复，不重复替换程序。")
    manifest = read_manifest(bundle)
    if bundle.is_relative_to(target) or target.is_relative_to(bundle):
        raise ValueError("干净构建目录与安装目录必须分开。")
    names = previous_names(target, archive)
    resources = names | {entry["path"] for entry in manifest["files"]}
    settings, database, vault, configs = _settings(target, resources)
    lease = lease_factory(target)
    try:
        if not lease.owner:
            raise RuntimeError("程序仍在运行；请在窗口正常退出并等待在途任务结束后再升级。")
        scripts = ScriptDirectory.from_config(migration_config())
        known = {script.revision for script in scripts.walk_revisions()}
        if manifest["schema"] != scripts.get_current_head():
            raise ValueError("构建与升级器支持的数据库版本不一致。")
        revision, record, count = _inspect_database(database, known)
        if revision is None:
            raise ValueError("此升级器只处理已有便携安装；新安装请完整解压干净发行包。")
        _check_vault(target, vault, record, count)
        columns, before = _legacy_snapshot(database)
        saved_configs = _config_files(target, configs)
        backup = backup_storage(target, database, vault, revision)
        for path, expected in saved_configs.items():
            saved = backup / "configuration" / path.relative_to(target)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
            if digest(path) != expected or digest(saved) != expected:
                raise RuntimeError("配置在备份时变化，未升级。")
        (backup / "configuration-manifest.json").write_text(json.dumps(
            {path.relative_to(target).as_posix(): value for path, value in saved_configs.items()},
            ensure_ascii=False, indent=2), encoding="utf-8")
        if before != _legacy_snapshot(database, columns)[1] or saved_configs != _config_files(target, configs):
            raise RuntimeError("备份期间数据或配置变化，未升级。")
        with pending.open("x", encoding="utf-8") as stream:
            json.dump({"backup": str(backup), "version": manifest["version"], "phase": "prepared"}, stream)
        try:
            install_resources(bundle, target, backup, names)
        except Exception:
            journal_path = backup / "program-update.json"
            if journal_path.is_file() and json.loads(journal_path.read_text(encoding="utf-8")).get("phase") == "rolled_back":
                pending.unlink()
            raise
        url = resolve_database_url(settings.database_url, root=target).render_as_string(hide_password=False)
        if revision != manifest["schema"]:
            upgrade_database(url)
        if before != _legacy_snapshot(database, columns)[1]:
            raise RuntimeError("升级后原有记录核验失败；请保留备份并停止启动。")
        if saved_configs != _config_files(target, configs):
            raise RuntimeError("升级后配置核验失败；请保留备份并停止启动。")
        final_revision, final_record, final_count = _inspect_database(database, known)
        if final_revision != manifest["schema"]:
            raise RuntimeError("升级后数据库版本核验失败。")
        _check_vault(target, vault, final_record, final_count)
        pending.unlink()
        result = {"status": "upgraded", "version": manifest["version"], "schema": manifest["schema"],
                  "target": str(target), "backup": str(backup), "legacy_rows_preserved": True,
                  "configuration_preserved": True}
        (backup / "upgrade-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        lease.close()
