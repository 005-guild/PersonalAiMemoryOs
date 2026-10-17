"""Recoverable two-file configuration commits; journal files contain credentials."""

import hashlib
import json
import os
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.paths import portable_path

CONFIGURATION_LOCK = RLock()
JOURNAL_DIRECTORY = ".memory-os-config-transactions"
MAX_FILE_BYTES = 1024 * 1024


class ConfigurationFileError(RuntimeError):
    def __init__(self, code="configuration_io_error"):
        self.code = code
        super().__init__("AI 配置文件操作未完成，请检查权限或配置恢复记录。")


def digest(value: bytes | None) -> str | None:
    return None if value is None else hashlib.sha256(value).hexdigest()


def read_file(root: Path, path: Path) -> bytes | None:
    path = portable_path(root, path)
    try:
        with path.open("rb") as handle:
            value = handle.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(value) > MAX_FILE_BYTES:
        raise ConfigurationFileError("configuration_too_large")
    return value


def _write(path: Path, content: bytes) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _replace(root: Path, path: Path, content: bytes, temporary: Path) -> None:
    path, temporary = portable_path(root, path), portable_path(root, temporary)
    if path.parent != temporary.parent:
        raise ConfigurationFileError()
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(temporary, content)
    os.replace(temporary, path)


def _manifest(root: Path, directory: Path, value: dict) -> None:
    temporary = portable_path(root, directory / "manifest.tmp")
    _write(temporary, json.dumps(value, sort_keys=True).encode("utf-8"))
    os.replace(temporary, portable_path(root, directory / "manifest.json"))


def _clean(root: Path, directory: Path, entries=()) -> None:
    for entry in entries:
        temporary = portable_path(root, root / entry["temporary"])
        if temporary.exists():
            temporary.unlink()
    for path in sorted(directory.iterdir(), key=lambda path: path.name == "manifest.json"):
        path = portable_path(root, path)
        if not path.is_file():
            raise ConfigurationFileError("configuration_recovery_conflict")
        path.unlink()
    directory.rmdir()


def _roles(root: Path, entries: list, protected_paths: list[str]) -> None:
    if len(entries) != 2 or root / entries[0]["path"] != root / ".env":
        raise ValueError()
    ai = portable_path(root, root / entries[1]["path"])
    protected = [root / "data", root / "knowledge", root / JOURNAL_DIRECTORY]
    protected.extend(portable_path(root, root / path) for path in protected_paths)
    if ai.suffix.lower() not in {".yml", ".yaml"} or any(ai == path or ai.is_relative_to(path) for path in protected):
        raise ValueError()


def _load(root: Path, directory: Path) -> dict:
    try:
        data = json.loads(read_file(root, directory / "manifest.json"))
        if data["version"] != 1 or data["phase"] not in {"prepared", "committed", "rolled_back"}:
            raise ValueError()
        _roles(root, data["files"], data["protected_paths"])
        paths = set()
        for index, entry in enumerate(data["files"]):
            target = portable_path(root, root / entry["path"])
            temporary = portable_path(root, root / entry["temporary"])
            if (target in paths or target.is_relative_to(root / JOURNAL_DIRECTORY)
                    or temporary.parent != target.parent
                    or temporary.name != f".memory-os-ai-{directory.name}-{index}.tmp"):
                raise ValueError()
            paths.add(target)
            if (entry["before"] is not None and (not isinstance(entry["before"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["before"]))
                    or not isinstance(entry["after"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["after"])):
                raise ValueError()
            if data["phase"] == "prepared":
                old = None if entry["before"] is None else read_file(root, directory / f"old-{index}")
                new = read_file(root, directory / f"new-{index}")
                if digest(old) != entry["before"] or digest(new) != entry["after"]:
                    raise ValueError()
        return data
    except (OSError, ValueError, KeyError, TypeError, RecursionError, ConfigurationFileError):
        raise ConfigurationFileError("configuration_recovery_conflict") from None


def _rollback(root: Path, directory: Path, data: dict) -> bool:
    entries = data["files"]
    observed = [digest(read_file(root, root / entry["path"])) for entry in entries]
    if any(current not in {entry["before"], entry["after"]} for entry, current in zip(entries, observed)):
        raise ConfigurationFileError("configuration_recovery_conflict")
    changed = False
    for index, (entry, current) in enumerate(zip(entries, observed)):
        if current == entry["before"]:
            continue
        target = portable_path(root, root / entry["path"])
        if digest(read_file(root, target)) != current:
            raise ConfigurationFileError("configuration_recovery_conflict")
        if entry["before"] is None:
            target.unlink()
        else:
            old = read_file(root, directory / f"old-{index}")
            if digest(old) != entry["before"]:
                raise ConfigurationFileError("configuration_recovery_conflict")
            _replace(root, target, old, root / entry["temporary"])
        changed = True
    if any(digest(read_file(root, root / entry["path"])) != entry["before"] for entry in entries):
        raise ConfigurationFileError("configuration_recovery_conflict")
    data["phase"] = "rolled_back"
    _manifest(root, directory, data)
    _clean(root, directory, entries)
    return changed


def recover_ai_settings(root: Path) -> bool:
    """Run before Settings/.env is loaded; return whether target files were restored."""
    with CONFIGURATION_LOCK:
        try:
            root = Path(root).absolute()
            journal = portable_path(root, root / JOURNAL_DIRECTORY)
            if not journal.exists():
                return False
            changed = False
            for directory in sorted(journal.iterdir()):
                portable_path(root, directory)
                if not directory.is_dir() or len(directory.name) != 32 or any(c not in "0123456789abcdef" for c in directory.name):
                    raise ConfigurationFileError("configuration_recovery_conflict")
                if not (directory / "manifest.json").exists():
                    _clean(root, directory)
                    continue
                data = _load(root, directory)
                if data["phase"] in {"committed", "rolled_back"}:
                    # A durable commit already completed both replaces. Preserve
                    # any subsequent manual edits rather than rolling them back.
                    _clean(root, directory, data["files"])
                else:
                    changed = _rollback(root, directory, data) or changed
            return changed
        except ConfigurationFileError:
            raise
        except (OSError, ValueError):
            raise ConfigurationFileError("configuration_recovery_conflict") from None


def write_configuration(root: Path, replacements: dict[Path, bytes], expected: dict[Path, str | None],
                        *, protected_paths=()) -> None:
    """Prepare durable old/new copies before the first visible file replacement."""
    with CONFIGURATION_LOCK:
        directory = None
        try:
            root = Path(root).absolute()
            if len(replacements) != 2:
                raise ConfigurationFileError()
            recover_ai_settings(root)
            if any(digest(read_file(root, path)) != expected[path] for path in replacements):
                raise ConfigurationFileError("configuration_changed")
            journal = portable_path(root, root / JOURNAL_DIRECTORY)
            directory = journal / uuid4().hex
            directory.mkdir(parents=True, mode=0o700)
            data = {"version": 1, "phase": "prepared", "files": [], "protected_paths": [
                path.relative_to(root).as_posix() for path in protected_paths if path.is_relative_to(root)]}
            for index, (path, content) in enumerate(replacements.items()):
                path = portable_path(root, path)
                if path.is_relative_to(journal) or len(content) > MAX_FILE_BYTES:
                    raise ConfigurationFileError()
                old = read_file(root, path)
                if digest(old) != expected[path]:
                    raise ConfigurationFileError("configuration_changed")
                if old is not None:
                    _write(directory / f"old-{index}", old)
                _write(directory / f"new-{index}", content)
                data["files"].append({"path": path.relative_to(root).as_posix(),
                    "temporary": (path.parent / f".memory-os-ai-{directory.name}-{index}.tmp").relative_to(root).as_posix(),
                    "before": digest(old), "after": digest(content)})
            _roles(root, data["files"], data["protected_paths"])
            _manifest(root, directory, data)
            for (path, content), entry in zip(replacements.items(), data["files"]):
                if digest(read_file(root, path)) != entry["before"]:
                    raise ConfigurationFileError("configuration_changed")
                _replace(root, path, content, root / entry["temporary"])
            if any(digest(read_file(root, path)) != digest(content) for path, content in replacements.items()):
                raise ConfigurationFileError("configuration_changed")
            data["phase"] = "committed"
            _manifest(root, directory, data)
            _clean(root, directory, data["files"])
        except Exception as error:
            if directory is not None and (directory / "manifest.json").exists():
                try:
                    data = _load(root, directory)
                    if data["phase"] == "prepared":
                        _rollback(root, directory, data)
                except Exception:
                    raise ConfigurationFileError("configuration_recovery_required") from None
            if isinstance(error, ConfigurationFileError):
                raise error from None
            raise ConfigurationFileError() from None
