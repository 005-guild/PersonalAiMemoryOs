"""Synthetic portable configuration; these tests never use personal providers."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
import yaml

from app.agents.configuration import AIRegistry
from app.api.settings_schemas import AIKeyUpdate, AISettingsWrite
from app.config import Settings
from app.services.ai_settings import AISettingsError, AISettingsService
from app.services import configuration_env


SECRET = "synthetic-test-key-not-real"


@pytest.fixture
def configuration(isolated_project):
    root = isolated_project
    (root / "config").mkdir()
    (root / ".env").write_text("# unrelated comment\nOTHER=preserved\nMEMORY_OS_AI_ENABLED=false\n", encoding="utf-8")
    profile = {"protocol": "openai_chat", "base_url": "http://127.0.0.1:9/v1", "model": "synthetic-model",
               "api_key_ref": "demo", "response_format": "json_object", "extra_body": {"thinking": {"type": "disabled"}}}
    (root / "config/ai-providers.yml").write_text(yaml.safe_dump(
        {"schema_version": 1, "default_profile": "demo", "profiles": {"demo": profile}}), encoding="utf-8")
    settings = Settings(runtime_root=root, _env_file=root / ".env", sync_enabled=False)
    return root, settings, AISettingsService(settings, environ={})


def request(service, **changes):
    current = service.describe()
    data = {"expected_revision": current["revision"], "enabled": current["enabled"],
            "default_profile": current["default_profile"], "profiles": current["profiles"], "key_updates": []}
    data.update(changes)
    return AISettingsWrite.model_validate(data)


def test_save_is_redacted_and_requires_restart(configuration):
    root, settings, service = configuration
    before = service.describe()
    assert not before["restart_required"]
    assert before["locations"]["database_file"] == str(root / "data" / "memory.db")
    assert before["locations"]["data_directory"] == str(root / "data")
    assert before["locations"]["knowledge_directory"] == str(root / "knowledge")
    result = service.save(request(service, enabled=True, key_updates=[{"ref": "demo", "value": SECRET}]))
    assert SECRET not in json.dumps(result)
    assert result["revision"] != before["revision"]
    assert result["enabled"] and result["restart_required"]
    assert result["active"] == {"enabled": False, "default_profile": "demo"}
    assert result["keys"] == [{"ref": "demo", "configured": True, "environment_managed": False}]
    assert "OTHER=preserved" in (root / ".env").read_text()
    restarted = Settings(runtime_root=root, _env_file=root / ".env", sync_enabled=False)
    registry = AIRegistry(restarted)
    assert registry.describe()["items"][0]["configured"]
    assert not AISettingsService(restarted, registry=registry, environ={}).describe()["restart_required"]
    with pytest.raises(AISettingsError, match="configuration_changed"):
        service.save(AISettingsWrite.model_validate({**request(service).model_dump(), "expected_revision": before["revision"]}))


def test_locations_use_actual_configured_storage_paths(configuration):
    root, _, _ = configuration
    settings = Settings(runtime_root=root, _env_file=root / ".env", database_url="sqlite:///custom/db/store.sqlite",
                        knowledge_dir="custom/notes")
    locations = AISettingsService(settings, environ={}).describe()["locations"]
    assert locations["database_file"] == str(root / "custom/db/store.sqlite")
    assert locations["data_directory"] == str(root / "custom/db")
    assert locations["knowledge_directory"] == str(root / "custom/notes")
    assert all("sqlite:" not in value for value in locations.values())


def test_blank_key_keeps_secret_and_partial_profile_keeps_advanced_fields(configuration):
    root, _, service = configuration
    service.save(request(service, key_updates=[{"ref": "demo", "value": SECRET}]))
    minimal = {"id": "demo", "protocol": "openai_chat", "base_url": "http://127.0.0.1:9/v1", "model": "changed"}
    result = service.save(request(service, profiles=[minimal], key_updates=[{"ref": "demo", "value": "  "}]))
    assert result["profiles"][0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert result["profiles"][0]["response_format"] == "json_object"
    assert Settings(runtime_root=root, _env_file=root / ".env").ai_keys["demo"].get_secret_value() == SECRET


def test_environment_fields_and_keys_are_not_falsely_saved(configuration):
    root, settings, _ = configuration
    service = AISettingsService(settings, environ={"MEMORY_OS_AI_ENABLED": "true", "MEMORY_OS_AI_KEYS__DEMO": SECRET})
    result = service.describe()
    assert result["enabled"]
    assert result["keys"][0]["environment_managed"]
    original = (root / ".env").read_bytes()
    with pytest.raises(AISettingsError, match="environment_managed_field"):
        service.save(request(service, enabled=False))
    with pytest.raises(AISettingsError, match="environment_managed_key"):
        service.save(request(service, key_updates=[{"ref": "demo", "value": "changed"}]))
    assert (root / ".env").read_bytes() == original


def test_read_only_rejects_before_reading_files(configuration, monkeypatch):
    _, settings, service = configuration
    payload = request(service)
    settings.configuration_read_only = True
    monkeypatch.setattr(service, "_snapshot", lambda: pytest.fail("readonly save read files"))
    with pytest.raises(AISettingsError, match="configuration_read_only"):
        service.save(payload)


def test_external_change_and_invalid_profile_do_not_write(configuration):
    root, _, service = configuration
    payload = request(service)
    with (root / ".env").open("ab") as handle:
        handle.write(b"# external change\n")
    with pytest.raises(AISettingsError, match="configuration_changed"):
        service.save(payload)
    original = (root / ".env").read_bytes()
    with pytest.raises(AISettingsError, match="configuration_invalid"):
        service.save(request(service, profiles=[service.describe()["profiles"][0]] * 2))
    assert (root / ".env").read_bytes() == original


@pytest.mark.parametrize("value", ["foo__bar", "bad\nkey", "\ud800"])
def test_key_reference_cannot_create_nested_settings(value):
    with pytest.raises(ValidationError):
        AIKeyUpdate(ref=value, value=SECRET)


@pytest.mark.parametrize("value", ["a\nb", "${OTHER}", "\ud800"])
def test_key_value_rejects_injection_and_invalid_unicode(value):
    with pytest.raises(ValidationError):
        AIKeyUpdate(ref="demo", value=value)


def test_preserves_legacy_json_key_reference(configuration):
    root, _, _ = configuration
    (root / ".env").write_text('MEMORY_OS_AI_KEYS=\'{"foo__bar":"synthetic-old-key"}\'\n', encoding="utf-8")
    settings = Settings(runtime_root=root, _env_file=root / ".env")
    service = AISettingsService(settings, environ={})
    service.save(request(service))
    assert Settings(runtime_root=root, _env_file=root / ".env").ai_keys["foo__bar"].get_secret_value() == "synthetic-old-key"


def test_dotenv_multiline_bom_crlf_and_duplicate_assignments_preserved():
    unrelated = 'OTHER="first\r\nMEMORY_OS_AI_ENABLED=inside-not-a-binding\r\nlast"\r\n# outside comment\r\n'
    raw = b"\xef\xbb\xbf" + (unrelated + "MEMORY_OS_AI_ENABLED=false # managed\r\nMEMORY_OS_AI_ENABLED=true\r\n").encode()
    result = configuration_env.rewrite(raw, {"MEMORY_OS_AI_ENABLED": "false", "MEMORY_OS_AI_KEYS__DEMO": SECRET})
    assert result.startswith(b"\xef\xbb\xbf" + unrelated.encode())
    assert result.count(b'MEMORY_OS_AI_ENABLED="false"') == 1
    values = configuration_env.ai_values(result)
    assert values["MEMORY_OS_AI_ENABLED"] == "false"
    assert values["MEMORY_OS_AI_KEYS__DEMO"] == SECRET


@pytest.mark.parametrize("path", ["data/accidental.yml", "knowledge/accidental.yaml", ".env", "data/memory.db"])
def test_cannot_point_editor_at_runtime_data(configuration, path):
    root, settings, _ = configuration
    settings.ai_config_file = path
    service = AISettingsService(settings, environ={})
    with pytest.raises(AISettingsError, match="configuration_path_invalid"):
        service.describe()


def test_invalid_escaped_key_reference_fails_safely_without_crashing_base_service(configuration):
    root, _, _ = configuration
    (root / ".env").write_text('MEMORY_OS_AI_KEYS=\'{"\\ud800":"synthetic-key"}\'\n', encoding="utf-8")
    settings = Settings(runtime_root=root, _env_file=root / ".env")
    service = AISettingsService(settings, environ={})
    with pytest.raises(AISettingsError, match="configuration_invalid"):
        service.describe()
