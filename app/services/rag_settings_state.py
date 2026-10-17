"""Validated on-disk RAG snapshots, independently of the running index clients."""

import os
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
import yaml

from app.config import Settings, resolve_database_url
from app.paths import portable_path
from app.services import configuration_env as env
from app.services.ai_settings import AISettingsError, _hash
from app.services.configuration_files import ConfigurationFileError, digest, read_file
from app.vector.configuration import _Document, _PROFILE_ID, _UniqueLoader

PREFIXES = ("MEMORY_OS_RAG_", "MEMORY_OS_EMBEDDING_", "MEMORY_OS_AI_KEYS")
FIELDS = {"enabled": "MEMORY_OS_RAG_ENABLED", "qdrant_url": "MEMORY_OS_RAG_QDRANT_URL",
          "default": "MEMORY_OS_EMBEDDING_DEFAULT_PROFILE"}


class RAGSettingsError(AISettingsError):
    pass


def validate_document(value):
    document = _Document.model_validate(value)
    if (any(not _PROFILE_ID.fullmatch(name) for name in document.profiles)
            or document.default_profile is not None and document.default_profile not in document.profiles):
        raise ValueError()
    return document


def signature(snapshot):
    refs = {profile["api_key_ref"].casefold() for profile in snapshot["profiles"].values() if profile["api_key_ref"]}
    return _hash({**{field: snapshot[field] for field in ("enabled", "default", "qdrant_url", "profiles")},
                  "keys": {ref: snapshot["keys"].get(ref) for ref in refs}})


def semantic(snapshot):
    profile = snapshot["profiles"].get(snapshot["default"])
    if profile is None:
        return None
    return _hash({field: profile[field] for field in ("protocol", "base_url", "model", "model_revision",
                                                       "dimension", "request_dimensions", "extra_body")})


class RAGSettingsState:
    def __init__(self, settings, *, environ=None):
        self.settings, self.root = settings, Path(settings.runtime_root).absolute()
        self.env_file, self.config_file = self.root / ".env", Path(settings.embedding_config_path).absolute()
        self.protected_paths = (settings.knowledge_path.resolve(),
            Path(resolve_database_url(settings.database_url, root=self.root).database), settings.ai_config_path.resolve())
        self.environ = os.environ if environ is None else environ
        self.path_valid = self.config_file.suffix.lower() in {".yml", ".yaml"} and self.config_file != self.env_file
        protected = (*self.protected_paths, self.root / ".memory-os-config-transactions", self.root / "data", self.root / "knowledge")
        self.path_valid = self.path_valid and not any(self.config_file == path or self.config_file.is_relative_to(path) for path in protected)
        try:
            portable_path(self.root, self.config_file)
            portable_path(self.root, self.env_file)
        except ValueError:
            self.path_valid = False

    def snapshot(self):
        try:
            if not self.path_valid:
                raise RAGSettingsError(503, "configuration_path_invalid")
            dotenv, raw_yaml = read_file(self.root, self.env_file), read_file(self.root, self.config_file)
            document = validate_document(yaml.load(raw_yaml.decode("utf-8-sig"), Loader=_UniqueLoader)) if raw_yaml is not None else validate_document(
                {"schema_version": 1, "default_profile": None, "profiles": {}})
            file_values = env.selected_values(dotenv, PREFIXES)
            environment = {name.upper(): value for name, value in self.environ.items() if name.upper().startswith(PREFIXES)}
            effective = {**file_values, **environment}
            configured_path = effective.get("MEMORY_OS_EMBEDDING_CONFIG_FILE")
            if configured_path:
                selected = Path(configured_path)
                selected = selected if selected.is_absolute() else self.root / selected
                if selected.absolute() != self.config_file:
                    raise RAGSettingsError(409, "configuration_path_changed")
            keys = {**env.keys_from(file_values), **env.keys_from(environment)}
            enabled = TypeAdapter(bool).validate_python(effective.get(FIELDS["enabled"], "false"))
            default = effective.get(FIELDS["default"]) or document.default_profile
            if default is not None and default not in document.profiles:
                raise ValueError()
            qdrant = Settings.validate_qdrant_url(effective.get(FIELDS["qdrant_url"], "http://127.0.0.1:6333"))
            profiles = {name: profile.model_dump() for name, profile in document.profiles.items()}
            _hash({"profiles": profiles, "keys": keys})
            return {"dotenv": dotenv, "yaml": raw_yaml, "profiles": profiles, "enabled": enabled,
                "default": default, "qdrant_url": qdrant, "keys": keys, "managed": set(env.keys_from(environment)),
                "environment": environment, "file_values": file_values,
                "revision": _hash({"env": digest(dotenv), "yaml": digest(raw_yaml), "environment": environment})}
        except (OSError, ValueError, UnicodeError, yaml.YAMLError, ValidationError, RecursionError, ConfigurationFileError):
            raise RAGSettingsError(503, "configuration_invalid") from None

    def editable(self):
        if self.settings.configuration_read_only:
            return "configuration_read_only"
        def parent(path):
            while not path.exists():
                path = path.parent
            return path
        return None if all(os.access(parent(path), os.W_OK) for path in (self.env_file, self.config_file)) else "configuration_not_writable"


def preflight(snapshot):
    issues, profile = [], snapshot["profiles"].get(snapshot["default"])
    if profile is None:
        issues.append("embedding_default_profile_missing")
    elif not profile["enabled"]:
        issues.append("embedding_profile_disabled")
    elif profile["auth"] != "none" and not snapshot["keys"].get((profile["api_key_ref"] or "").casefold(), "").strip():
        issues.append("embedding_api_key_missing")
    return {"ready": not issues, "issues": issues, "network_checked": False}
