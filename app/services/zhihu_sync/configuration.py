"""Private per-installation configuration; no cookie values enter the API."""

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.zhihu_sync.storage import SyncError, atomic_json, read_json, safe_path


class SyncConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool = False
    collection_url: str = Field(default='', max_length=4096)
    target_dir: str = Field(default='', max_length=2048)
    interval_seconds: int = Field(default=3600, ge=900, le=86400)

    @model_validator(mode='after')
    def validate_destination(self):
        if self.collection_url:
            parsed = urlsplit(self.collection_url)
            if (parsed.scheme != 'https' or parsed.hostname != 'www.zhihu.com'
                    or parsed.username or parsed.password or parsed.port is not None
                    or not re.fullmatch(r'/collection/[1-9][0-9]*/?', parsed.path)
                    or parsed.query or parsed.fragment):
                raise ValueError('invalid_collection_url')
        if self.target_dir:
            if not Path(self.target_dir).is_absolute():
                raise ValueError('absolute_target_required')
            safe_path(Path(self.target_dir))
        if self.enabled and not (self.collection_url and self.target_dir):
            raise ValueError('configuration_incomplete')
        return self

    @property
    def collection_id(self):
        return self.collection_url.rstrip('/').rsplit('/', 1)[-1]


class SyncConfigurationWrite(SyncConfiguration):
    expected_revision: str


class Configuration:
    def __init__(self, root):
        self.root = Path(root)
        self.path = safe_path(self.root / 'config/zhihu-sync.yml')

    def load(self):
        try:
            return SyncConfiguration.model_validate(read_json(self.path)) if self.path.exists() else SyncConfiguration()
        except ValueError:
            raise SyncError('configuration_invalid') from None

    @staticmethod
    def revision(config):
        return hashlib.sha256(json.dumps(config.model_dump(), sort_keys=True).encode()).hexdigest()

    def save(self, payload):
        if self.revision(self.load()) != payload.expected_revision:
            raise SyncError('configuration_changed')
        config = SyncConfiguration.model_validate(payload.model_dump(exclude={'expected_revision'}))
        if config.target_dir:
            target = safe_path(Path(config.target_dir))
            for protected in ('data', 'knowledge', 'config', '_internal', 'logs', 'backups'):
                if target.is_relative_to((self.root / protected).resolve()):
                    raise SyncError('target_protected')
        atomic_json(self.path, config.model_dump())
        return config
