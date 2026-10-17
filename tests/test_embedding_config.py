"""Embedding selection is independent from generation and does not expose keys."""

import json

from pydantic import ValidationError
import pytest
import yaml

from app.config import Settings
from app.vector.configuration import EmbeddingProfile, EmbeddingRegistry
from app.vector.errors import RagError


def write_config(root, **changes):
    profile = {"base_url": "https://example.com/v1", "model": "embedding-test", "dimension": 3,
               "api_key_ref": "embedding"}
    profile.update(changes)
    path = root / "config" / "embedding-providers.yml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump({"schema_version": 1, "default_profile": "first",
                                   "profiles": {"first": profile}}), encoding="utf-8")
    return path


def test_missing_default_disabled_and_secret_readiness(isolated_project):
    assert EmbeddingRegistry(Settings(_env_file=None)).describe()["enabled"] is False
    with pytest.raises(RagError, match="rag_disabled"):
        EmbeddingRegistry(Settings(_env_file=None)).resolve()
    write_config(isolated_project)
    registry = EmbeddingRegistry(Settings(_env_file=None, rag_enabled=True))
    assert registry.describe()["items"][0]["configured"] is False
    with pytest.raises(RagError, match="embedding_api_key_missing"):
        registry.resolve()
    registry = EmbeddingRegistry(Settings(_env_file=None, rag_enabled=True,
                                          ai_enabled=False, ai_keys={"EMBEDDING": "secret-value"}))
    assert registry.resolve().api_key.get_secret_value() == "secret-value"
    assert "secret-value" not in json.dumps(registry.describe()) + repr(registry.resolve())
    with pytest.raises(RagError) as error:
        registry.resolve("unknown")
    assert error.value.status_code == 422
    write_config(isolated_project, enabled=False)
    with pytest.raises(RagError) as disabled:
        EmbeddingRegistry(registry.settings).resolve()
    assert disabled.value.status_code == 409


def test_environment_over_dotenv_and_semantic_fingerprint(isolated_project, monkeypatch):
    write_config(isolated_project)
    (isolated_project / ".env").write_text("MEMORY_OS_AI_KEYS__EMBEDDING=dotenv-secret\n", encoding="utf-8")
    monkeypatch.setenv("MEMORY_OS_AI_KEYS__EMBEDDING", "environment-secret")
    settings = Settings(rag_enabled=True)
    original = EmbeddingRegistry(settings).resolve()
    assert original.api_key.get_secret_value() == "environment-secret"
    write_config(isolated_project, timeout_seconds=30, batch_size=2, label="Label")
    assert EmbeddingRegistry(settings).resolve().fingerprint == original.fingerprint
    write_config(isolated_project, model_revision="revision-2")
    assert EmbeddingRegistry(settings).resolve().fingerprint != original.fingerprint
    write_config(isolated_project, extra_body={"task": "retrieval"})
    assert EmbeddingRegistry(settings).resolve().fingerprint != original.fingerprint


@pytest.mark.parametrize("changes", [
    {"dimension": True}, {"dimension": 0}, {"dimension": 3.0},
    {"batch_size": 9}, {"request_dimensions": 2}, {"api_key": "secret"},
    {"base_url": "https://secret:password@example.com"}, {"base_url": "https://example.com/?key=secret"},
    {"base_url": "https://example.com/#fragment"}, {"model": "\n"},
    {"extra_body": {"input": "override"}}, {"extra_body": {"nested": {"API-KEY": "secret"}}},
    {"extra_body": {"dimensions": 3}}, {"extra_body": {"bad": float("nan")}},
])
def test_strict_profile_validation(changes):
    values = {"model": "m", "dimension": 3, "base_url": "http://localhost/v1", **changes}
    with pytest.raises(ValidationError):
        EmbeddingProfile(**values)


@pytest.mark.parametrize("raw", [
    "schema_version: true\nprofiles: {}", "schema_version: 2\nprofiles: {}",
    "schema_version: 1\nschema_version: 1\nprofiles: {}",
    "schema_version: 1\nprofiles:\n  bad id:\n    model: x\n    dimension: 3\n    base_url: http://localhost",
    "schema_version: 1\ndefault_profile: missing\nprofiles: {}",
    "schema_version: 1\nprofiles:\n  a:\n    model: one\n    model: two",
    "[invalid]", "\x00invalid",
])
def test_bad_documents_leave_core_usable(isolated_project, raw):
    path = isolated_project / "config" / "embedding-providers.yml"
    path.parent.mkdir()
    path.write_text(raw, encoding="utf-8")
    registry = EmbeddingRegistry(Settings(_env_file=None, rag_enabled=True))
    assert registry.describe()["error_code"] == "embedding_configuration_invalid"
    with pytest.raises(RagError) as error:
        registry.resolve()
    assert error.value.status_code == 503


def test_anonymous_and_explicit_dimension(isolated_project):
    write_config(isolated_project, auth="none", request_dimensions=3)
    selected = EmbeddingRegistry(Settings(_env_file=None, rag_enabled=True)).resolve()
    assert selected.api_key is None
    assert selected.profile.request_dimensions == 3


def test_key_rotation_does_not_invalidate_vectors(isolated_project):
    write_config(isolated_project)
    first = EmbeddingRegistry(Settings(_env_file=None, rag_enabled=True, ai_keys={"embedding": "first"})).resolve()
    second = EmbeddingRegistry(Settings(_env_file=None, rag_enabled=True, ai_keys={"embedding": "second"})).resolve()
    assert first.fingerprint == second.fingerprint
    assert first.api_key != second.api_key
