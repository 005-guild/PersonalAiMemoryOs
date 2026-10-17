"""Provider configuration stays local, strict, and independent of credentials."""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
import yaml

from app.agents.configuration import AIProfile, AIRegistry
from app.agents.errors import AIError
from app.config import Settings


def write_profiles(root: Path, profiles: dict | None = None, **outer) -> Path:
    path = root / "config" / "ai-providers.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": 1, "default_profile": "deepseek",
        "profiles": profiles or {"deepseek": {
            "protocol": "openai_chat", "base_url": "https://api.deepseek.com",
            "model": "test-model", "api_key_ref": "deepseek", "response_format": "json_object",
            "extra_body": {"thinking": {"type": "disabled"}},
        }},
    }
    document.update(outer)
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_safe_defaults_and_missing_config():
    registry = AIRegistry(Settings(_env_file=None))
    assert registry.settings.ai_max_input_chars == 20_000
    assert registry.describe() == {
        "enabled": False, "default_profile": None, "items": [],
        "max_input_chars": 20000,
        "error_code": "ai_configuration_missing",
    }
    with pytest.raises(AIError) as caught:
        registry.resolve()
    assert (caught.value.status_code, caught.value.code) == (503, "ai_disabled")


def test_nested_dotenv_keys_and_environment_override(isolated_project: Path, monkeypatch):
    write_profiles(isolated_project)
    (isolated_project / ".env").write_text(
        "MEMORY_OS_AI_ENABLED=true\nMEMORY_OS_AI_KEYS__DEEPSEEK=dotenv-secret\n", encoding="utf-8"
    )
    monkeypatch.setenv("MEMORY_OS_AI_KEYS__DEEPSEEK", "environment-secret")
    settings = Settings()
    assert settings.ai_keys["deepseek"].get_secret_value() == "environment-secret"
    registry = AIRegistry(settings)
    selected = registry.resolve()
    assert selected.profile_id == "deepseek"
    assert selected.api_key.get_secret_value() == "environment-secret"
    assert len(selected.fingerprint) == 64
    serialized = json.dumps(registry.describe()) + repr(settings) + repr(selected)
    assert "environment-secret" not in serialized
    assert "dotenv-secret" not in serialized


def test_key_changes_do_not_change_nonsecret_fingerprint(isolated_project: Path):
    write_profiles(isolated_project)
    first = AIRegistry(Settings(_env_file=None, ai_enabled=True, ai_keys={"DEEPSEEK": "first"})).resolve()
    second = AIRegistry(Settings(_env_file=None, ai_enabled=True, ai_keys={"deepseek": "second"})).resolve()
    assert first.fingerprint == second.fingerprint


def test_configuration_readiness_does_not_return_secrets(isolated_project: Path):
    write_profiles(isolated_project)
    registry = AIRegistry(Settings(_env_file=None, ai_enabled=True))
    assert registry.describe()["items"][0]["configured"] is False
    with pytest.raises(AIError) as caught:
        registry.resolve()
    assert (caught.value.status_code, caught.value.code) == (503, "ai_api_key_missing")


def test_profile_override_disabled_unknown_and_anonymous(isolated_project: Path):
    profiles = {
        "disabled": {"protocol": "openai_chat", "base_url": "https://example.com/v1", "model": "m", "enabled": False},
        "anonymous": {"protocol": "openai_chat", "base_url": "http://localhost:10000/v1", "model": "m", "auth": "none"},
    }
    write_profiles(isolated_project, profiles, default_profile="disabled")
    registry = AIRegistry(Settings(_env_file=None, ai_enabled=True, ai_default_profile="anonymous"))
    assert registry.resolve().profile.auth == "none"
    assert registry.resolve().api_key is None
    with pytest.raises(AIError) as disabled:
        registry.resolve("disabled")
    assert disabled.value.status_code == 409
    with pytest.raises(AIError) as missing:
        registry.resolve("unknown")
    assert missing.value.status_code == 422


@pytest.mark.parametrize("raw", [
    "schema_version: 1\nschema_version: 1\nprofiles: {}",
    "schema_version: true\nprofiles: {}",
    "schema_version: 2\nprofiles: {}",
    "schema_version: 1\nprofiles: []",
    "schema_version: 1\nprofiles:\n  x:\n    api_key: SECRET-CONTENT",
    "[not-a-document]",
    "invalid: [unterminated",
])
def test_invalid_documents_are_safe_and_lazy(isolated_project: Path, raw: str):
    path = write_profiles(isolated_project)
    path.write_text(raw, encoding="utf-8")
    registry = AIRegistry(Settings(_env_file=None, ai_enabled=True))
    assert registry.describe()["error_code"] == "ai_configuration_invalid"
    with pytest.raises(AIError) as caught:
        registry.resolve()
    assert caught.value.status_code == 503
    assert "SECRET-CONTENT" not in str(caught.value)


@pytest.mark.parametrize("changes", [
    {"base_url": "https://username:SECRET-CONTENT@example.com/v1"},
    {"base_url": "https://example.com/v1?key=SECRET-CONTENT"},
    {"base_url": "https://example.com/v1#fragment"},
    {"base_url": "file:///etc/passwd"},
    {"base_url": "https://example.com:wrong"},
    {"base_url": "https://example.com\\evil"},
    {"base_url": "https://example.com/\n"},
    {"model": "  "},
    {"api_key": "SECRET-CONTENT"},
    {"max_output_tokens": True},
])
def test_profile_validation_hides_sensitive_inputs(changes: dict):
    values = {"protocol": "openai_chat", "base_url": "https://example.com/v1", "model": "m", **changes}
    with pytest.raises(ValidationError) as caught:
        AIProfile.model_validate(values)
    assert "SECRET-CONTENT" not in str(caught.value)


@pytest.mark.parametrize("extra", [
    {"model": "other"}, {"messages": []}, {"stream": True}, {"response_format": {}},
    {"generationConfig": {"maxOutputTokens": 100000}},
    {"generationConfig": {"candidateCount": 10}},
    {"generationConfig": {"nested": {"max_tokens": 100000}}},
    {"tools": []}, {"headers": {"authorization": "secret"}},
    {"text": {"format": {"type": "json_schema"}}}, {"max_completion_tokens": 999999},
    {"generationConfig": {"responseMimeType": "application/json"}},
    {"generationConfig": {"responseSchema": {"type": "OBJECT"}}},
    {"generationConfig": {"responseJsonSchema": {"type": "object"}}},
    {"generationConfig": None}, {"generationConfig": []}, {"generationConfig": "disabled"},
    {"generation_config": {"temperature": 0.5}},
    {"background": True}, {"store": True}, {"temperature": float("nan")},
])
def test_extensions_cannot_bypass_reserved_settings(extra: dict):
    with pytest.raises(ValidationError):
        AIProfile(protocol="openai_chat", base_url="https://example.com", model="m", extra_body=extra)


def test_json_mode_only_supported_for_chat(isolated_project: Path):
    write_profiles(isolated_project, {"deepseek": {
        "protocol": "openai_responses", "base_url": "https://example.com", "model": "m",
        "response_format": "json_object",
    }})
    assert AIRegistry(Settings(_env_file=None)).error_code == "ai_configuration_invalid"


def test_read_utf8_bom_and_blank_default_override(isolated_project: Path):
    path = write_profiles(isolated_project)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    settings = Settings(_env_file=None, ai_enabled=True, ai_default_profile="", ai_keys={"deepseek": SecretStr("secret")})
    assert AIRegistry(settings).resolve().profile_id == "deepseek"


def test_config_path_stays_inside_project(isolated_project: Path):
    with pytest.raises(ValidationError, match="inside the project"):
        Settings(_env_file=None, ai_config_file=str(isolated_project.parent / "outside.yml"))


def test_overlarge_configuration_is_rejected_without_reading_all(isolated_project: Path):
    path = write_profiles(isolated_project)
    path.write_bytes(b" " * (1024 * 1024 + 1))
    assert AIRegistry(Settings(_env_file=None)).error_code == "ai_configuration_invalid"


def test_unauthenticated_profiles_require_explicit_none_auth(isolated_project: Path):
    write_profiles(isolated_project, {"deepseek": {
        "protocol": "openai_chat", "base_url": "https://example.com/v1", "model": "m",
    }})
    registry = AIRegistry(Settings(_env_file=None, ai_enabled=True))
    assert registry.describe()["items"][0]["configured"] is False
    with pytest.raises(AIError) as caught:
        registry.resolve()
    assert caught.value.code == "ai_api_key_missing"
