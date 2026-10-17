"""Validate isolated portable storage and explicitly initialize or upgrade it."""

import logging
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic.script import ScriptDirectory
from alembic.util import CommandError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, resolve_database_url
from app.desktop.storage_backup import backup_storage
from app.models import Base
from app.paths import portable_path, resource_root
from app.repositories.database import Database
from app.repositories.migrations import check_schema, migration_config, upgrade_database

logger = logging.getLogger(__name__)
MARKER = ".memory-os-vault"


class DesktopStorageError(RuntimeError):
    """A safe, Chinese startup error that may be shown without sensitive values."""


def _public_templates(root: Path) -> None:
    templates = ((".env.example", ".env"),
                 ("config/ai-providers.example.yml", "config/ai-providers.yml"),
                 ("config/embedding-providers.example.yml", "config/embedding-providers.yml"))
    for source_name, destination_name in templates:
        destination = portable_path(root, root / destination_name)
        if destination.exists():
            if not destination.is_file():
                raise DesktopStorageError("配置路径不是普通文件，请检查便携目录。")
            continue
        source = resource_root() / source_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents overwriting configurations on a repeated run.
        with destination.open("xb") as output:
            output.write(source.read_bytes())


def _required_tables(revision: str) -> set[str]:
    tables = {"sources", "knowledge", "sync_vault", "sync_states", "sync_conflicts", "sync_operations"}
    if int(revision) >= 2:
        tables.add("source_origins")
    if int(revision) >= 3:
        tables.add("processing_runs")
    if int(revision) >= 4:
        tables.update({"rag_index_generations", "rag_note_index_states", "rag_index_jobs"})
    if int(revision) >= 5:
        tables.update({"knowledge_sources", "prompt_templates", "prompt_revisions",
                       "processing_batches", "processing_batch_items"})
    return tables


def _inspect_database(path: Path, known_revisions: set[str]) -> tuple[str | None, tuple | None, int]:
    if not path.exists() or path.stat().st_size == 0:
        return None, None, 0
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise DesktopStorageError("数据库完整性检查失败，请从备份恢复。")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if not row[0].startswith("sqlite_")}
        if not tables:
            return None, None, 0
        if "alembic_version" not in tables:
            raise DesktopStorageError("数据库结构未知，未执行初始化或升级。")
        revisions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        if len(revisions) != 1 or revisions[0][0] not in known_revisions:
            raise DesktopStorageError("数据库版本未知或高于当前支持版本，请使用匹配的应用。")
        revision = revisions[0][0]
        required = _required_tables(revision)
        if tables != required | {"alembic_version"}:
            raise DesktopStorageError("数据库结构不完整或未知，未执行升级。")
        for name in required:
            expected = {column.name for column in Base.metadata.tables[name].columns}
            if name == "processing_runs" and int(revision) < 5:
                expected -= {"source_snapshots", "prompt_snapshot", "generation_settings", "finish_reason", "failure_stage"}
            actual = {row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')}
            if not expected.issubset(actual):
                raise DesktopStorageError("数据库表结构不完整，未执行升级。")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise DesktopStorageError("数据库关联完整性检查失败，未执行升级。")
        vaults = connection.execute("SELECT id, token, initialized FROM sync_vault").fetchall()
        if len(vaults) > 1 or (vaults and vaults[0][0] != 1):
            raise DesktopStorageError("知识目录身份记录无效。")
        note_count = connection.execute("SELECT count(*) FROM knowledge").fetchone()[0]
        return revision, vaults[0] if vaults else None, note_count


def _check_vault(root: Path, vault: Path, record: tuple | None, note_count: int) -> None:
    marker = portable_path(root, vault / MARKER)
    initialized = record is not None and bool(record[2])
    if initialized or note_count:
        if not vault.is_dir() or not marker.is_file():
            raise DesktopStorageError("已有数据库的知识目录或身份标记缺失；请恢复完整知识目录。")
    if marker.exists():
        if record is None or marker.read_text(encoding="utf-8") != record[1]:
            raise DesktopStorageError("知识目录身份标记与数据库不匹配，未自动修复。")
    elif vault.exists() and any(vault.iterdir()):
        raise DesktopStorageError("知识目录包含文件但缺少身份标记，未自动接管。")


def _initialize_vault(database_path: Path, vault: Path) -> None:
    # Persist identity first so an interrupted first launch can safely resume.
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT token FROM sync_vault WHERE id=1").fetchone()
        token = row[0] if row else str(uuid4())
        if row is None:
            connection.execute("INSERT INTO sync_vault (id, token, initialized) VALUES (1, ?, 0)", (token,))
    vault.mkdir(parents=True, exist_ok=True)
    marker = vault / MARKER
    if not marker.exists():
        with marker.open("x", encoding="utf-8", newline="") as stream:
            stream.write(token)
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE sync_vault SET initialized=1 WHERE id=1")


def prepare_desktop(root: Path, confirm_upgrade: Callable[[str], bool]) -> Settings:
    """Prepare only this portable directory; existing upgrades require confirmation."""
    try:
        root = Path(root).absolute()
        portable_path(root, root)
        if not root.is_dir():
            raise DesktopStorageError("便携目录不存在，请先完整解压发行包。")
        if (root / ".memory-os-upgrade.json").exists():
            raise DesktopStorageError("上次程序升级未完成，已停止启动。请检查升级记录和 backups 目录后恢复程序。")
        # Probe before copying templates or touching a database.
        with tempfile.TemporaryFile(prefix=".memory-os-write-check-", dir=root):
            pass
        from app.services.configuration_files import recover_ai_settings
        recover_ai_settings(root)
        for name in (".env", "data", "config", "logs", "knowledge", "backups", ".webview"):
            portable_path(root, root / name)
        _public_templates(root)
        settings = Settings(_env_file=root / ".env", runtime_root=root)
        url = resolve_database_url(settings.database_url, root=root)
        database_path = portable_path(root, Path(url.database))
        vault = portable_path(root, settings.knowledge_path)
        portable_path(root, settings.ai_config_path)
        portable_path(root, settings.embedding_config_path)
        if database_path == root or database_path.is_dir() or (vault.exists() and not vault.is_dir()):
            raise DesktopStorageError("数据库或知识目录类型不正确。")
        # Absolute paths let the ordinary app/Database reuse all existing behavior.
        settings = settings.model_copy(update={"database_url": url.render_as_string(hide_password=False),
            "knowledge_dir": str(vault), "ai_config_file": str(settings.ai_config_path),
            "embedding_config_file": str(settings.embedding_config_path)})
        scripts = ScriptDirectory.from_config(migration_config())
        known = {script.revision for script in scripts.walk_revisions()}
        head = scripts.get_current_head()
        revision, record, count = _inspect_database(database_path, known)
        _check_vault(root, vault, record, count)
        if revision is not None and revision != head:
            if not confirm_upgrade(f"数据库需要从 {revision} 升级至 {head}。升级前将备份数据库和完整知识目录，是否继续？"):
                raise DesktopStorageError("已取消数据库升级，未修改数据库。")
            backup_storage(root, database_path, vault, revision)
        if revision != head:
            upgrade_database(settings.database_url)
        database = Database(settings.database_url)
        try:
            database.initialize()
            check_schema(database.engine)
        finally:
            database.dispose()
        _initialize_vault(database_path, vault)
        return settings
    except DesktopStorageError:
        raise
    except ValidationError:
        raise DesktopStorageError("配置无效，请检查便携目录中的 .env 和配置文件。") from None
    except (OSError, ValueError, sqlite3.Error, RuntimeError, SQLAlchemyError, CommandError) as exc:
        logger.error("Portable storage preparation failed (%s).", type(exc).__name__)
        raise DesktopStorageError("便携目录无法初始化，请检查目录权限、配置、数据库及日志。") from None
