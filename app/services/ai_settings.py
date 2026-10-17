"""Edit persisted AI configuration; active providers remain fixed until restart."""

import hashlib
import json
import os
from pathlib import Path
import secrets

from pydantic import TypeAdapter, ValidationError
import yaml

from app.agents.configuration import AIRegistry, _ProfileDocument, _UniqueKeysLoader, PROFILE_ID
from app.api.settings_schemas import AISettingsWrite
from app.config import resolve_database_url
from app.paths import portable_path
from app.services import configuration_env as env
from app.services.configuration_files import (
    CONFIGURATION_LOCK, ConfigurationFileError, digest, read_file, write_configuration,
)

_UNSET = object()


class AISettingsError(RuntimeError):
    def __init__(self, status_code: int, code: str):
        self.status_code, self.code = status_code, code
        super().__init__(code)


def _validated(value: dict):
    document = _ProfileDocument.model_validate(value)
    if any(not PROFILE_ID.fullmatch(name) for name in document.profiles):
        raise ValueError()
    for profile in document.profiles.values():
        if profile.protocol != "openai_chat" and (profile.response_format != "prompt" or profile.token_limit_field != "max_tokens"):
            raise ValueError()
    if document.default_profile is not None and document.default_profile not in document.profiles:
        raise ValueError()
    return document


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


class AISettingsService:
    def __init__(self, settings, *, registry=None, environ=None):
        self.settings = settings
        self.root = Path(settings.runtime_root).absolute()
        self.env_file = self.root / ".env"
        self.config_file = Path(settings.ai_config_path).absolute()
        self.protected_paths = (settings.knowledge_path.resolve(), Path(resolve_database_url(settings.database_url, root=self.root).database),
                                settings.embedding_config_path.resolve())
        self.path_valid = (self.config_file != self.env_file and self.config_file.suffix.lower() in {".yml", ".yaml"}
            and not any(self.config_file == path or self.config_file.is_relative_to(path) for path in self.protected_paths)
            and not self.config_file.is_relative_to(self.root / ".memory-os-config-transactions")
            and not self.config_file.is_relative_to(self.root / "data")
            and not self.config_file.is_relative_to(self.root / "knowledge"))
        try:
            portable_path(self.root, self.env_file)
            portable_path(self.root, self.config_file)
        except ValueError:
            self.path_valid = False
        self.csrf_token = secrets.token_urlsafe(32)
        self.environ = os.environ if environ is None else environ
        self.registry = registry if registry is not None else AIRegistry(settings)
        self._active = {"enabled": settings.ai_enabled, "default_profile": self.registry.default_profile}
        self._active_signature = None
        try:
            snapshot = self._snapshot()
            self._active_signature = self._signature(snapshot, enabled=settings.ai_enabled,
                default=self.registry.default_profile, profiles={name: profile.model_dump()
                    for name, profile in self.registry.profiles.items()},
                keys={ref: value.get_secret_value() for ref, value in settings.ai_keys.items()})
        except AISettingsError:
            pass

    def _snapshot(self):
        try:
            if not self.path_valid:
                raise AISettingsError(503, "configuration_path_invalid")
            dotenv, raw_yaml = read_file(self.root, self.env_file), read_file(self.root, self.config_file)
            document = _validated(yaml.load(raw_yaml.decode("utf-8-sig"), Loader=_UniqueKeysLoader)) if raw_yaml is not None else _validated(
                {"schema_version": 1, "default_profile": None, "profiles": {}})
            file_values = env.ai_values(dotenv)
            environment = {name.upper(): value for name, value in self.environ.items() if name.upper().startswith(env.PREFIX)}
            effective = {**file_values, **environment}
            keys = {**env.keys_from(file_values), **env.keys_from(environment)}
            _hash(keys)  # Validate UTF-8 without returning credential contents.
            managed = set(env.keys_from(environment))
            enabled = TypeAdapter(bool).validate_python(effective.get("MEMORY_OS_AI_ENABLED", "false"))
            default = effective.get("MEMORY_OS_AI_DEFAULT_PROFILE") or document.default_profile
            if default is not None and default not in document.profiles:
                raise ValueError()
            profiles = {name: profile.model_dump() for name, profile in document.profiles.items()}
            _hash(profiles)  # Reject escaped YAML surrogates before a JSON response.
            revision = _hash({"env": digest(dotenv), "yaml": digest(raw_yaml), "environment": environment})
            return {"dotenv": dotenv, "yaml": raw_yaml, "profiles": profiles, "enabled": enabled,
                    "default": default, "keys": keys, "managed": managed, "environment": environment,
                    "file_values": file_values, "revision": revision}
        except (OSError, ValueError, UnicodeError, yaml.YAMLError, ValidationError, RecursionError, ConfigurationFileError):
            raise AISettingsError(503, "configuration_invalid") from None

    @staticmethod
    def _signature(snapshot, *, enabled=None, default=_UNSET, profiles=None, keys=None):
        return _hash({"enabled": snapshot["enabled"] if enabled is None else enabled,
                      "default": snapshot["default"] if default is _UNSET else default,
                      "profiles": snapshot["profiles"] if profiles is None else profiles,
                      "keys": snapshot["keys"] if keys is None else keys})

    def _describe(self, snapshot):
        refs = set(snapshot["keys"]) | {profile["api_key_ref"].casefold() for profile in snapshot["profiles"].values()
                                       if profile["api_key_ref"] is not None}
        readonly = bool(getattr(self.settings, "configuration_read_only", False))
        def existing_parent(path):
            while not path.exists():
                path = path.parent
            return path
        parents = [existing_parent(self.env_file), existing_parent(self.config_file)]
        permission = all(os.access(path, os.W_OK) for path in parents)
        reason = "configuration_read_only" if readonly else "configuration_not_writable" if not permission else None
        return {"revision": snapshot["revision"], "editable": reason is None, "read_only_reason": reason,
            "restart_required": self._active_signature != self._signature(snapshot), "csrf_token": self.csrf_token,
            "enabled": snapshot["enabled"], "default_profile": snapshot["default"],
            "profiles": [{"id": name, **profile} for name, profile in snapshot["profiles"].items()],
            "keys": [{"ref": ref, "configured": bool(snapshot["keys"].get(ref, "").strip()),
                      "environment_managed": ref in snapshot["managed"]} for ref in sorted(refs)],
            "environment_overrides": sorted(snapshot["environment"]),
            "locations": {"runtime_root": str(self.root), "config_directory": str(self.config_file.parent),
                          "ai_config_file": str(self.config_file), "env_file": str(self.env_file),
                          "database_file": str(self.protected_paths[1]),
                          "data_directory": str(self.protected_paths[1].parent),
                          "knowledge_directory": str(self.protected_paths[0])},
            "active": dict(self._active)}

    def describe(self):
        with CONFIGURATION_LOCK:
            return self._describe(self._snapshot())

    def save(self, payload: AISettingsWrite):
        with CONFIGURATION_LOCK:
            if getattr(self.settings, "configuration_read_only", False):
                raise AISettingsError(409, "configuration_read_only")
            snapshot = self._snapshot()
            if payload.expected_revision != snapshot["revision"]:
                raise AISettingsError(409, "configuration_changed")
            if not self._describe(snapshot)["editable"]:
                raise AISettingsError(409, "configuration_not_writable")
            for name, incoming in (("MEMORY_OS_AI_ENABLED", payload.enabled),
                                   ("MEMORY_OS_AI_DEFAULT_PROFILE", payload.default_profile)):
                current = snapshot["enabled"] if name.endswith("ENABLED") else snapshot["default"]
                if name in snapshot["environment"] and incoming != current:
                    raise AISettingsError(409, "environment_managed_field")
            try:
                profiles = {}
                for profile in payload.profiles:
                    if profile.id in profiles:
                        raise ValueError()
                    profiles[profile.id] = {**snapshot["profiles"].get(profile.id, {}),
                                           **profile.model_dump(exclude={"id"}, exclude_unset=True)}
                document = _validated({"schema_version": 1, "default_profile": payload.default_profile, "profiles": profiles})
                _hash(document.model_dump())
                updates = {"MEMORY_OS_AI_ENABLED": str(payload.enabled).lower(),
                           "MEMORY_OS_AI_DEFAULT_PROFILE": payload.default_profile or ""}
                refs = set()
                for update in payload.key_updates:
                    ref, value = update.ref.casefold(), update.value.get_secret_value()
                    if ref in refs:
                        raise ValueError()
                    refs.add(ref)
                    if not value.strip():
                        continue
                    if ref in snapshot["managed"]:
                        raise AISettingsError(409, "environment_managed_key")
                    updates["MEMORY_OS_AI_KEYS__" + ref.upper()] = value
                dotenv = env.rewrite(snapshot["dotenv"], updates)
                yaml_bytes = yaml.safe_dump(document.model_dump(), allow_unicode=True, sort_keys=False).encode("utf-8")
                # Check process-level overrides again before the first disk mutation.
                if self._snapshot()["revision"] != snapshot["revision"]:
                    raise AISettingsError(409, "configuration_changed")
                write_configuration(self.root, {self.env_file: dotenv, self.config_file: yaml_bytes},
                    {self.env_file: digest(snapshot["dotenv"]), self.config_file: digest(snapshot["yaml"])},
                    protected_paths=self.protected_paths)
                return self._describe(self._snapshot())
            except AISettingsError:
                raise
            except ConfigurationFileError as error:
                raise AISettingsError(409 if error.code == "configuration_changed" else 503, error.code) from None
            except (ValueError, ValidationError, UnicodeError, yaml.YAMLError, RecursionError):
                raise AISettingsError(422, "configuration_invalid") from None
