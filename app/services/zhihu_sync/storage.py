"""Durable completion ledger and one-writer lock, independent of the app database."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from app.paths import portable_path
from app.services.zhihu_markdown import _entry
from app.services.import_types import ParsedZhihuItem


class SyncError(RuntimeError):
    """Only controlled codes, never upstream bodies or credentials."""


def safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    return portable_path(Path(path.anchor), path)


def atomic_json(path: Path, value) -> None:
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = safe_path(path.with_name(path.name + '.' + uuid4().hex + '.tmp'))
    try:
        with temporary.open('xb') as handle:
            handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path):
    try:
        path = safe_path(path)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError()
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, RecursionError):
        raise SyncError('state_invalid') from None


def identity_key(identity) -> str:
    return identity.resource_type + ':' + identity.external_id


def digest(path: Path) -> str:
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


@contextmanager
def writer_lock(directory: Path):
    directory = safe_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with safe_path(directory / 'writer.lock').open('a+b') as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SyncError('target_busy') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Ledger:
    def __init__(self, target: Path, collection_id: str):
        self.target = safe_path(target)
        self.directory = safe_path(target.parent / '.sync')
        self.path = self.directory / 'state.json'
        self.collection_id = collection_id
        self.records = {}

    def load(self):
        if self.path.exists():
            data = read_json(self.path)
            if (not isinstance(data, dict) or data.get('version') != 1
                    or data.get('collection_id') != self.collection_id
                    or data.get('target') != str(self.target)
                    or not isinstance(data.get('completed'), dict)):
                raise SyncError('state_invalid')
            for key, item in data['completed'].items():
                if (not re.fullmatch(r'(answer|article|pin):[1-9][0-9]*', key)
                        or not isinstance(item, dict) or not isinstance(item.get('path'), str)):
                    raise SyncError('state_invalid')
            self.records = data['completed']
        elif (self.directory / 'initialized').exists() or (self.directory / 'state.backup.json').exists():
            raise SyncError('state_missing')
        # Existing files are authoritative even after a crash between publish and ledger commit.
        seen, local = set(), {}
        registered_paths = {item['path'] for item in self.records.values()}
        for index, path in enumerate(sorted(self.target.glob('*.md'))):
            if path.name.casefold() == 'readme.md' or path.name in registered_paths:
                continue
            try:
                content = safe_path(path).read_text(encoding='utf-8-sig')
                parsed, _ = _entry(index, {'relative_path':path.name, 'content':content}, seen)
            except (OSError, ValueError):
                raise SyncError('existing_file_invalid') from None
            if not isinstance(parsed, ParsedZhihuItem):
                raise SyncError('existing_file_invalid')
            key = identity_key(parsed)
            local[key] = {'path':path.name}
        if not self.path.exists():
            old_path = self.target.parent.parent / f'export-progress-{self.collection_id}.json'
            if old_path.exists():
                old = read_json(old_path)
                try:
                    ids = set(old['articles']['exportedIds'])
                    if not ids.issubset({key.split(':')[1] for key in local}):
                        raise ValueError()
                except (ValueError, TypeError, KeyError):
                    raise SyncError('legacy_inventory_mismatch') from None
        self.records.update({key:value for key,value in local.items() if key not in self.records})
        return self

    def save(self):
        value = {'version':1, 'collection_id':self.collection_id,
                 'target':str(self.target), 'completed':self.records}
        # A missing or malformed primary is never silently replaced by an older backup.
        if self.path.exists():
            atomic_json(self.directory / 'state.backup.json', read_json(self.path))
        atomic_json(self.path, value)
        safe_path(self.directory / 'initialized').touch(exist_ok=True)

    def complete(self, identity, filename):
        self.records[identity_key(identity)] = {'path':filename}
        self.save()
