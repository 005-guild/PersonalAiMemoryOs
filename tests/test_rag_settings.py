"""Portable RAG settings use synthetic local profiles and never real credentials."""

import json

import pytest
import yaml

from app.api.rag_settings_schemas import RAGSettingsWrite
from app.config import Settings
from app.services.ai_settings import AISettingsError, AISettingsService
from app.services.rag_settings import RAGSettingsService

SECRET = "synthetic-embedding-test-secret"


@pytest.fixture
def rag_configuration(isolated_project):
    root = isolated_project
    (root / "config").mkdir()
    (root / ".env").write_text("# keep unrelated values\nMEMORY_OS_AI_ENABLED=false\nOTHER=retained\n", encoding="utf-8")
    profile = {"base_url": "http://127.0.0.1:9/v1", "model": "synthetic-embedding", "dimension": 3, "api_key_ref": "embed"}
    (root / "config/embedding-providers.yml").write_text(yaml.safe_dump(
        {"schema_version": 1, "default_profile": "demo", "profiles": {"demo": profile}}), encoding="utf-8")
    settings = Settings(runtime_root=root, _env_file=root / ".env", sync_enabled=False)
    return root, settings, RAGSettingsService(settings, environ={}, csrf_token="shared-test-token")


def write_request(service, **changes):
    current = service.describe()
    data = {"expected_revision": current["revision"], "enabled": current["enabled"],
        "qdrant_url": current["qdrant_url"], "default_profile": current["default_profile"], "profiles": current["profiles"]}
    data.update(changes)
    return RAGSettingsWrite.model_validate(data)


def test_save_is_next_start_only_redacted_and_preserves_ai(rag_configuration):
    root, settings, service = rag_configuration
    before = service.describe()
    assert not before["restart_required"]
    assert not before["preflight"]["ready"] and not before["preflight"]["network_checked"]
    result = service.save(write_request(service, enabled=True, key_updates=[{"ref": "embed", "value": SECRET}]))
    assert SECRET not in json.dumps(result)
    assert result["csrf_token"] == "shared-test-token"
    assert result["enabled"] and result["restart_required"] and result["preflight"]["ready"]
    assert result["active"]["enabled"] is False
    assert "OTHER=retained" in (root / ".env").read_text()
    assert "MEMORY_OS_AI_ENABLED=false" in (root / ".env").read_text()
    assert not settings.rag_enabled
    restarted = Settings(runtime_root=root, _env_file=root / ".env")
    assert restarted.rag_enabled and restarted.ai_keys["embed"].get_secret_value() == SECRET
    assert not RAGSettingsService(restarted, environ={}).describe()["restart_required"]
    with pytest.raises(AISettingsError, match="configuration_changed"):
        service.save(write_request(service).model_copy(update={"expected_revision": before["revision"]}))


def test_save_invalid_or_enable_unready_writes_nothing(rag_configuration):
    root, _, service = rag_configuration
    before = (root / ".env").read_bytes()
    with pytest.raises(AISettingsError, match="rag_configuration_not_ready"):
        service.save(write_request(service, enabled=True))
    with pytest.raises(AISettingsError, match="configuration_invalid"):
        service.save(write_request(service, qdrant_url="http://user:password@host"))
    assert (root / ".env").read_bytes() == before


def test_blank_key_keep_and_semantic_change_requires_rebuild(rag_configuration):
    root, _, service = rag_configuration
    service.save(write_request(service, key_updates=[{"ref": "embed", "value": SECRET}]))
    profiles = service.describe()["profiles"]
    profiles[0]["model"] = "new-model"
    result = service.save(write_request(service, profiles=profiles, key_updates=[{"ref": "embed", "value": "  "}]))
    assert result["preflight"]["rebuild_required"]
    assert Settings(runtime_root=root, _env_file=root / ".env").ai_keys["embed"].get_secret_value() == SECRET


def test_missing_yaml_can_be_configured_with_rag_disabled(rag_configuration):
    root, settings, _ = rag_configuration
    (root / "config/embedding-providers.yml").unlink()
    service = RAGSettingsService(settings, environ={})
    assert service.describe()["profiles"] == []
    result = service.save(write_request(service))
    assert not result["enabled"]
    assert (root / "config/embedding-providers.yml").exists()


def test_environment_fields_keys_and_readonly_are_enforced(rag_configuration):
    root, settings, _ = rag_configuration
    service = RAGSettingsService(settings, environ={"MEMORY_OS_RAG_ENABLED": "true", "MEMORY_OS_AI_KEYS__EMBED": SECRET})
    assert service.describe()["keys"][0]["environment_managed"]
    before = (root / ".env").read_bytes()
    with pytest.raises(AISettingsError, match="environment_managed_field"):
        service.save(write_request(service, enabled=False))
    with pytest.raises(AISettingsError, match="environment_managed_key"):
        service.save(write_request(service, key_updates=[{"ref": "embed", "value": "another"}]))
    settings.configuration_read_only = True
    with pytest.raises(AISettingsError, match="configuration_read_only"):
        service.save(write_request(service))
    assert (root / ".env").read_bytes() == before


@pytest.mark.parametrize("path", ["config/ai-providers.yml", "data/misplaced.yml", "knowledge/config.yaml", ".env"])
def test_rag_config_cannot_overwrite_ai_or_data(rag_configuration, path):
    _, settings, _ = rag_configuration
    settings.embedding_config_file = path
    service = RAGSettingsService(settings, environ={})
    with pytest.raises(AISettingsError, match="configuration_path_invalid"):
        service.describe()


def test_ai_config_cannot_overwrite_embedding_yaml(rag_configuration):
    _, settings, _ = rag_configuration
    settings.ai_config_file = settings.embedding_config_file
    with pytest.raises(AISettingsError, match="configuration_path_invalid"):
        AISettingsService(settings, environ={}).describe()


def test_concurrent_ai_save_invalidates_rag_revision_and_preserves_embedding(rag_configuration):
    root, settings, service = rag_configuration
    from app.api.settings_schemas import AISettingsWrite
    ai = AISettingsService(settings, environ={})
    old = write_request(service)
    before_embedding = (root / "config/embedding-providers.yml").read_bytes()
    described = ai.describe()
    ai.save(AISettingsWrite(expected_revision=described["revision"], enabled=False, profiles=[], key_updates=[]))
    with pytest.raises(AISettingsError, match="configuration_changed"):
        service.save(old)
    assert (root / "config/embedding-providers.yml").read_bytes() == before_embedding


def test_two_file_failure_restores_env_and_yaml(rag_configuration, monkeypatch):
    root, _, service = rag_configuration
    from app.services import configuration_files
    original = configuration_files._replace
    before = {(root / ".env"): (root / ".env").read_bytes(), service.config_file: service.config_file.read_bytes()}
    failed = False
    def broken(root_arg, path, content, temporary):
        nonlocal failed
        if path == service.config_file and not failed:
            failed = True
            raise OSError("synthetic one-time replace failure")
        return original(root_arg, path, content, temporary)
    monkeypatch.setattr(configuration_files, "_replace", broken)
    with pytest.raises(AISettingsError, match="configuration_io_error"):
        service.save(write_request(service, key_updates=[{"ref": "embed", "value": SECRET}]))
    assert all(path.read_bytes() == content for path, content in before.items())


def test_next_config_path_requires_restart_instead_of_editing_previous_yaml(rag_configuration):
    root, _, service = rag_configuration
    with (root / ".env").open("a", encoding="utf-8") as stream:
        stream.write("MEMORY_OS_EMBEDDING_CONFIG_FILE=config/different.yml\n")
    with pytest.raises(AISettingsError, match="configuration_path_changed"):
        service.describe()
