"""Restart requests must preserve dirty guards, revisions and local-only access."""

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.desktop import router
from app.api.settings_security import configuration_guard, ConfigurationNoStoreMiddleware
from app.desktop.restart import DesktopRestarter
from app.desktop.window import DesktopWindow

REVISION = "a" * 64


@pytest.fixture
def client():
    app = FastAPI()
    app.state.ai_settings = SimpleNamespace(csrf_token="test-nonce", describe=lambda: {"revision": REVISION})
    app.state.configuration_guard = configuration_guard
    app.state.desktop_restarter = Mock()
    app.state.desktop_restarter.request.return_value = True
    app.include_router(router)
    app.add_middleware(ConfigurationNoStoreMiddleware)
    with TestClient(app, base_url="http://127.0.0.1:9000") as current:
        yield current


def headers():
    return {"Origin": "http://127.0.0.1:9000", "X-Configuration-Token": "test-nonce"}


def test_restart_queues_once_and_has_no_store(client):
    response = client.post("/api/v1/desktop/restart", json={"expected_revision": REVISION}, headers=headers())
    assert response.status_code == 202 and response.json() == {"status": "restarting"}
    assert response.headers["cache-control"] == "no-store"
    client.app.state.desktop_restarter.request.assert_called_once()


@pytest.mark.parametrize("case,status", [("stale", 409), ("web", 409), ("busy", 409), ("origin", 403), ("token", 403)])
def test_restart_rejects_without_effect(client, case, status):
    payload, values = {"expected_revision": REVISION}, headers()
    restarter = client.app.state.desktop_restarter
    if case == "stale": payload["expected_revision"] = "b" * 64
    if case == "web": client.app.state.desktop_restarter = None
    if case == "busy": restarter.request.return_value = False
    if case == "origin": values["Origin"] = "https://attacker.invalid"
    if case == "token": values["X-Configuration-Token"] = "wrong"
    assert client.post("/api/v1/desktop/restart", json=payload, headers=values).status_code == status
    if case != "busy": restarter.request.assert_not_called()


def test_repeat_request_does_not_start_second_restart(tmp_path):
    controller = Mock()
    controller.request_restart.return_value = True
    restarter = DesktopRestarter(tmp_path, controller)
    assert restarter.request() is True
    assert restarter.request() is False
    controller.request_restart.assert_called_once_with(restarter)
    restarter.cancel()
    assert restarter.request() is True


def test_dirty_cancel_keeps_application_and_cancels_restart(tmp_path):
    controller = DesktopWindow(tmp_path, Mock())
    controller.window = Mock()
    controller.window.run_js.side_effect = [True, None, False]
    controller.shutdown = Mock()
    restarter = Mock()
    controller._ask(restarter)
    restarter.cancel.assert_called_once()
    restarter.prepare.assert_not_called()
    controller.shutdown.assert_not_called()


def test_helper_failure_keeps_old_window(tmp_path, monkeypatch):
    controller = DesktopWindow(tmp_path, Mock())
    controller.window = Mock()
    controller.window.run_js.side_effect = [True, None, True]
    controller.shutdown = Mock()
    monkeypatch.setattr("app.desktop.window.message", Mock())
    restarter = Mock()
    restarter.prepare.side_effect = RuntimeError("helper unavailable")
    controller._ask(restarter)
    controller.shutdown.assert_not_called()
    assert not controller.asking


def test_restart_prepares_successor_before_draining(tmp_path):
    controller = DesktopWindow(tmp_path, Mock())
    controller.window = Mock()
    controller.window.run_js.side_effect = [True, None, True]
    order = []
    controller.shutdown = lambda: order.append("drain")
    controller._ask(SimpleNamespace(prepare=lambda: order.append("prepare")))
    assert order == ["prepare", "drain"]
