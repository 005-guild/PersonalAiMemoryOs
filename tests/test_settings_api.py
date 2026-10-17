"""Wire contract and validation redaction without any network model calls."""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.settings import MAX_REQUEST_BYTES, router
from app.api.settings_security import configuration_guard
from app.services.ai_settings import AISettingsService

from test_ai_settings import SECRET, configuration


@pytest.fixture
def api(configuration):
    _, _, service = configuration
    app = FastAPI()
    app.state.ai_settings = service
    app.state.configuration_guard = configuration_guard
    app.include_router(router)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def payload(client):
    response = client.get("/api/v1/settings/ai")
    assert response.status_code == 200
    value = response.json()
    return {"expected_revision": value["revision"], "enabled": value["enabled"],
            "default_profile": value["default_profile"], "profiles": value["profiles"], "key_updates": []}, {
        "Origin": "http://127.0.0.1", "X-Configuration-Token": value["csrf_token"], "Content-Type": "application/json"}


def test_success_returns_safe_configuration_with_no_provider_requests(api):
    body, headers = payload(api)
    body["key_updates"] = [{"ref": "demo", "value": SECRET}]
    saved = api.put("/api/v1/settings/ai", json=body, headers=headers)
    assert saved.status_code == 200
    assert SECRET not in saved.text
    assert saved.json()["restart_required"]
    assert saved.json()["locations"]["env_file"].endswith(".env")


@pytest.mark.parametrize("change", ["bad_ref", "secret_type", "secret_value", "credentials_url", "extra_secret", "extra_secret_field"])
def test_validation_never_echoes_invalid_credentials(api, change):
    body, headers = payload(api)
    if change == "bad_ref":
        body["key_updates"] = [{"ref": "foo__bar", "value": SECRET}]
    elif change == "secret_type":
        body["key_updates"] = [{"ref": "demo", "value": {"private": SECRET}}]
    elif change == "secret_value":
        body["key_updates"] = [{"ref": "demo", "value": SECRET + "\nINJECT=true"}]
    elif change == "credentials_url":
        body["profiles"][0]["base_url"] = "http://user:" + SECRET + "@127.0.0.1/v1"
    elif change == "extra_secret":
        body["profiles"][0]["unknown"] = SECRET
    else:
        body[SECRET] = 123
    response = api.put("/api/v1/settings/ai", json=body, headers=headers)
    assert response.status_code == 422
    assert SECRET not in response.text
    for error in response.json()["detail"]:
        assert "input" not in error and "ctx" not in error


@pytest.mark.parametrize("body", [b'{"enabled":true,"enabled":false}', b'{"value":NaN}', b"[" * 1100 + b"]" * 1100])
def test_invalid_json_is_generic_and_bounded(api, body):
    _, headers = payload(api)
    response = api.put("/api/v1/settings/ai", content=body, headers=headers)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "configuration_invalid"}}


def test_request_limit_and_early_origin_rejection(api):
    _, headers = payload(api)
    response = api.put("/api/v1/settings/ai", content=b" " * (MAX_REQUEST_BYTES + 1), headers=headers)
    assert response.status_code == 413
    assert api.put("/api/v1/settings/ai", content=b"not-json").status_code == 403
