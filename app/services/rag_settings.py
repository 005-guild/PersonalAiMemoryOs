"""Persist next-start RAG settings without starting indexing or model calls."""

import secrets

from pydantic import ValidationError
import yaml

from app.api.rag_settings_schemas import RAGSettingsWrite
from app.services import configuration_env as env
from app.services.configuration_files import CONFIGURATION_LOCK, ConfigurationFileError, digest, write_configuration
from app.services.rag_settings_state import FIELDS, RAGSettingsError, RAGSettingsState, preflight, semantic, signature, validate_document
from app.vector.configuration import EmbeddingRegistry


class RAGSettingsService(RAGSettingsState):
    def __init__(self, settings, *, registry=None, csrf_token=None, environ=None, embedding_client=None, qdrant_transport=None):
        super().__init__(settings, environ=environ)
        self.csrf_token = csrf_token or secrets.token_urlsafe(32)
        self.registry = registry if registry is not None else EmbeddingRegistry(settings)
        active = {"enabled": settings.rag_enabled, "qdrant_url": settings.rag_qdrant_url,
            "default": self.registry.default_profile, "profiles": {key: profile.model_dump() for key, profile in self.registry.profiles.items()},
            "keys": {ref: value.get_secret_value() for ref, value in settings.ai_keys.items()}}
        self._active_signature, self._active_semantic = signature(active), semantic(active)
        self._active = {"enabled": active["enabled"], "qdrant_url": active["qdrant_url"], "default_profile": active["default"]}
        from app.services.rag_settings_probes import RAGSettingsProbes
        self.probes = RAGSettingsProbes(self, embedding_client=embedding_client, qdrant_transport=qdrant_transport)

    def _describe(self, snapshot):
        refs = set(snapshot["keys"]) | {profile["api_key_ref"].casefold() for profile in snapshot["profiles"].values() if profile["api_key_ref"]}
        reason = self.editable()
        check = preflight(snapshot)
        check["rebuild_required"] = self._active_semantic is not None and self._active_semantic != semantic(snapshot)
        check["qdrant_changed"] = self._active["qdrant_url"] != snapshot["qdrant_url"]
        return {"revision": snapshot["revision"], "editable": reason is None, "read_only_reason": reason,
            "restart_required": self._active_signature != signature(snapshot), "csrf_token": self.csrf_token,
            "enabled": snapshot["enabled"], "qdrant_url": snapshot["qdrant_url"], "default_profile": snapshot["default"],
            "profiles": [{"id": name, **profile} for name, profile in snapshot["profiles"].items()],
            "keys": [{"ref": ref, "configured": bool(snapshot["keys"].get(ref, "").strip()), "environment_managed": ref in snapshot["managed"]} for ref in sorted(refs)],
            "environment_overrides": sorted(snapshot["environment"]), "active": dict(self._active), "preflight": check,
            "locations": {"runtime_root": str(self.root), "config_directory": str(self.config_file.parent),
                "embedding_config_file": str(self.config_file), "env_file": str(self.env_file)}}

    def describe(self):
        with CONFIGURATION_LOCK:
            return self._describe(self.snapshot())

    def _updates(self, payload, snapshot):
        updates = {FIELDS["enabled"]: str(payload.enabled).lower(), FIELDS["qdrant_url"]: payload.qdrant_url,
                   FIELDS["default"]: payload.default_profile or ""}
        for field, current in (("enabled", snapshot["enabled"]), ("qdrant_url", snapshot["qdrant_url"]), ("default", snapshot["default"])):
            incoming = {"enabled": payload.enabled, "qdrant_url": payload.qdrant_url, "default": payload.default_profile}[field]
            if FIELDS[field] in snapshot["environment"] and current != incoming:
                raise RAGSettingsError(409, "environment_managed_field")
        refs = set()
        for update in payload.key_updates:
            ref, value = update.ref.casefold(), update.value.get_secret_value()
            if ref in refs:
                raise ValueError()
            refs.add(ref)
            if not value.strip():
                continue
            if ref in snapshot["managed"]:
                raise RAGSettingsError(409, "environment_managed_key")
            updates["MEMORY_OS_AI_KEYS__" + ref.upper()] = value
        return updates

    def save(self, payload: RAGSettingsWrite):
        with CONFIGURATION_LOCK:
            if self.settings.configuration_read_only:
                raise RAGSettingsError(409, "configuration_read_only")
            snapshot = self.snapshot()
            if payload.expected_revision != snapshot["revision"]:
                raise RAGSettingsError(409, "configuration_changed")
            if self.editable() is not None:
                raise RAGSettingsError(409, "configuration_not_writable")
            try:
                profiles = {}
                for profile in payload.profiles:
                    if profile.id in profiles:
                        raise ValueError()
                    profiles[profile.id] = {**snapshot["profiles"].get(profile.id, {}), **profile.model_dump(exclude={"id"}, exclude_unset=True)}
                document = validate_document({"schema_version": 1, "default_profile": payload.default_profile, "profiles": profiles})
                qdrant = self.settings.validate_qdrant_url(payload.qdrant_url)
                updates = self._updates(payload.model_copy(update={"qdrant_url": qdrant}), snapshot)
                dotenv = env.rewrite(snapshot["dotenv"], updates)
                next_keys = {**snapshot["keys"], **env.keys_from(updates)}
                check = preflight({**snapshot, "default": document.default_profile, "profiles": {name: profile.model_dump() for name, profile in document.profiles.items()}, "keys": next_keys})
                if payload.enabled and not check["ready"]:
                    raise RAGSettingsError(422, "rag_configuration_not_ready")
                raw_yaml = yaml.safe_dump(document.model_dump(), allow_unicode=True, sort_keys=False).encode("utf-8")
                if self.snapshot()["revision"] != snapshot["revision"]:
                    raise RAGSettingsError(409, "configuration_changed")
                write_configuration(self.root, {self.env_file: dotenv, self.config_file: raw_yaml},
                    {self.env_file: digest(snapshot["dotenv"]), self.config_file: digest(snapshot["yaml"])}, protected_paths=self.protected_paths)
                return self._describe(self.snapshot())
            except RAGSettingsError:
                raise
            except ConfigurationFileError as error:
                raise RAGSettingsError(409 if error.code == "configuration_changed" else 503, error.code) from None
            except (ValueError, ValidationError, UnicodeError, yaml.YAMLError, RecursionError):
                raise RAGSettingsError(422, "configuration_invalid") from None
