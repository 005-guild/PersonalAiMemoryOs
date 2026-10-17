"""Runtime acceptance safety, using fakes rather than Docker or provider traffic."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from scripts import real_provider_runtime as runtime


@pytest.fixture
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime, "VALIDATION_ROOT", tmp_path / ".cache" / "real-provider-validation")
    workspace = runtime.VALIDATION_ROOT / "test-only"
    workspace.mkdir(parents=True)
    profile = workspace / "providers.yml"
    profile.write_text("schema_version: 1\nprofiles: {}\n", encoding="utf-8")
    monkeypatch.setattr(runtime._Runtime, "_ready", lambda self, **kwargs: None)
    yield workspace, profile
    # Tests never leave a live process/container; clear fake ownership records.
    with runtime._ACTIVE_LOCK:
        runtime._ACTIVE.pop(workspace.resolve(), None)


class FakeProcess:
    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.returncode = 0
        return 0


@pytest.mark.parametrize("location", ["outside", ".cache", ".cache/real-provider-validation"])
def test_reject_nonisolated_workspace(monkeypatch, tmp_path, location):
    monkeypatch.setattr(runtime, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runtime, "VALIDATION_ROOT", tmp_path / ".cache" / "real-provider-validation")
    with pytest.raises(runtime.RuntimeFailure, match="workspace"):
        runtime.LocalRuntime(tmp_path / location, tmp_path / "profile.yml", {})


def test_reject_validation_root_outside_project(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "PROJECT_ROOT", tmp_path / "project")
    monkeypatch.setattr(runtime, "VALIDATION_ROOT", tmp_path / "junction-target")
    with pytest.raises(runtime.RuntimeFailure, match="root escaped"):
        runtime.LocalRuntime(runtime.VALIDATION_ROOT / "run", tmp_path / "profile.yml", {})


def test_profile_must_belong_to_workspace(isolated_runtime):
    workspace, profile = isolated_runtime
    with pytest.raises(runtime.RuntimeFailure, match="escaped"):
        runtime.LocalRuntime(workspace, profile.parent.parent / "personal.yml", {})


def test_missing_isolated_profile_rejected(isolated_runtime):
    workspace, _ = isolated_runtime
    with pytest.raises(runtime.RuntimeFailure, match="missing"):
        runtime.LocalRuntime(workspace, workspace / "missing.yml", {})


def test_proxy_preservation_and_loopback_merge(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    monkeypatch.setenv("HTTPS_PROXY", "http://user:private-proxy@proxy.invalid:3128")
    monkeypatch.setenv("NO_PROXY", "company.invalid")
    monkeypatch.setenv("MEMORY_OS_DATABASE_URL", "sqlite:///formal.db")
    local = runtime.LocalRuntime(workspace, profile, {
        "MEMORY_OS_AI_ENABLED": "true", "no_proxy": "other.invalid",
    })
    environment = local.environment()
    assert environment["HTTPS_PROXY"] == "http://user:private-proxy@proxy.invalid:3128"
    assert set(environment["NO_PROXY"].split(",")) == {
        "company.invalid", "other.invalid", "localhost", "127.0.0.1", "::1",
    }
    assert environment["NO_PROXY"] == environment["no_proxy"]
    assert environment["MEMORY_OS_DATABASE_URL"] == f"sqlite:///{local.database.as_posix()}"
    assert environment["MEMORY_OS_KNOWLEDGE_DIR"] == str(workspace / "knowledge")
    assert environment["MEMORY_OS_AI_CONFIG_FILE"] == str(profile)
    assert "private-proxy" not in "".join(path.read_text() for path in workspace.iterdir())


def test_unrelated_inherited_memory_settings_are_discarded(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    monkeypatch.setenv("MEMORY_OS_AI_KEYS__OTHER", "not-provided-to-runner")
    local = runtime.LocalRuntime(workspace, profile, {})
    assert "MEMORY_OS_AI_KEYS__OTHER" not in local.environment()


def test_migration_explicit_revision_connection_no_dotenv(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    calls = []
    monkeypatch.setattr(runtime.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs))
                        or SimpleNamespace(returncode=0))
    local = runtime.LocalRuntime(workspace, profile, {})
    local.migrate()
    args, kwargs = calls[0]
    assert "command.upgrade(cfg,'head')" in args[0][2]
    assert "cfg.attributes['connection']=connection" in args[0][2]
    assert "Settings(" not in args[0][2]
    assert kwargs["env"]["MEMORY_OS_DATABASE_URL"] == f"sqlite:///{local.database.as_posix()}"
    assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["timeout"] == 60
    assert not local.database.exists()


@pytest.mark.parametrize("failure", [
    OSError("provider-secret-should-not-escape"),
    subprocess.TimeoutExpired("secret-command", 60, output="provider-secret-should-not-escape"),
])
def test_migration_failures_do_not_include_subprocess_secrets(monkeypatch, isolated_runtime, failure):
    workspace, profile = isolated_runtime

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(runtime.subprocess, "run", fail)
    with pytest.raises(runtime.RuntimeFailure) as error:
        runtime.LocalRuntime(workspace, profile, {}).migrate()
    assert "secret" not in str(error.value)


def test_local_process_has_secret_only_in_environment_and_graceful_stop(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    calls = []
    process = FakeProcess()
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs:
                        calls.append((args, kwargs)) or process)
    local = runtime.LocalRuntime(workspace, profile, {"MEMORY_OS_AI_KEYS__DEEPSEEK": "api-secret"})
    local.start()
    args, kwargs = calls[0]
    assert "api-secret" not in str(args)
    assert kwargs["env"]["MEMORY_OS_AI_KEYS__DEEPSEEK"] == "api-secret"
    assert kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL
    if os.name == "nt":
        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert local.base_url.startswith("http://127.0.0.1:")
    local.stop()
    assert (workspace / ".local-stop").read_text() == "stop\n"
    assert local.process is None
    assert workspace not in runtime._ACTIVE
    assert profile.exists()


def test_local_start_failure_sanitized_and_ownership_released(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime

    def fail(*args, **kwargs):
        raise OSError("api-secret")

    monkeypatch.setattr(runtime.subprocess, "Popen", fail)
    with pytest.raises(runtime.RuntimeFailure) as error:
        runtime.LocalRuntime(workspace, profile, {}).start()
    assert "api-secret" not in str(error.value)
    assert workspace not in runtime._ACTIVE


def test_local_shutdown_timeout_does_not_force_kill_or_release_storage(isolated_runtime):
    workspace, profile = isolated_runtime
    local = runtime.LocalRuntime(workspace, profile, {})
    local._claim()

    class SlowProcess(FakeProcess):
        def wait(self, timeout):
            raise subprocess.TimeoutExpired("service", timeout)

    local.process = SlowProcess()
    with pytest.raises(runtime.RuntimeFailure, match="not force-killed"):
        local.stop()
    assert local.process is not None
    assert workspace in runtime._ACTIVE


def test_shared_storage_disallows_overlapping_local_and_docker(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    local = runtime.LocalRuntime(workspace, profile, {})
    docker = runtime.DockerRuntime(workspace, profile, {})
    local.start()
    with pytest.raises(runtime.RuntimeFailure, match="existing"):
        docker.start()
    with pytest.raises(runtime.RuntimeFailure, match="Stop"):
        local.migrate()
    local.stop()
    docker._claim()
    docker._release()


def test_docker_manifest_has_environment_names_no_secret_values(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    calls = []

    def compose(self, *args, **kwargs):
        calls.append(args)
        return "127.0.0.1:23456\n" if args[0] == "port" else ""

    monkeypatch.setattr(runtime.DockerRuntime, "_compose", compose)
    docker = runtime.DockerRuntime(workspace, profile, {
        "MEMORY_OS_AI_ENABLED": "true", "MEMORY_OS_AI_KEYS__DEEPSEEK": "api-secret",
        "HTTPS_PROXY": "http://user:proxy-secret@proxy.invalid",
    })
    docker.start()
    text = docker._manifest.read_text(encoding="utf-8")
    assert "api-secret" not in text and "proxy-secret" not in text
    service = json.loads(text)["services"]["api"]
    assert service["image"] == runtime.IMAGE
    assert service["pull_policy"] == "never"
    assert service["environment"] == sorted(set(service["environment"]))
    assert "MEMORY_OS_AI_KEYS__DEEPSEEK" in service["environment"]
    assert "HTTPS_PROXY" in service["environment"]
    assert service["volumes"][2]["read_only"] is True
    assert {volume["source"] for volume in service["volumes"]} == {
        str(workspace / "data"), str(workspace / "knowledge"), str(profile),
    }
    assert calls[0] == ("up", "-d", "--no-build", "--pull", "never", "api")
    assert docker.base_url == "http://127.0.0.1:23456"
    docker.stop()
    assert calls[-1] == ("down", "--timeout", "30")
    assert profile.is_file() and docker._manifest.is_file()


@pytest.mark.parametrize("port", ["0.0.0.0:23456", "[::]:23456", "127.0.0.1:0", "127.0.0.1:65536", "secret"])
def test_docker_rejects_unsafe_port_and_cleans_owned_resources(monkeypatch, isolated_runtime, port):
    workspace, profile = isolated_runtime
    calls = []

    def compose(self, *args, **kwargs):
        calls.append(args)
        return port if args[0] == "port" else ""

    monkeypatch.setattr(runtime.DockerRuntime, "_compose", compose)
    docker = runtime.DockerRuntime(workspace, profile, {})
    with pytest.raises(runtime.RuntimeFailure, match="loopback"):
        docker.start()
    assert calls[-1][0] == "down"
    assert workspace not in runtime._ACTIVE


def test_compose_subprocess_does_not_disclose_stdout_or_env(monkeypatch, isolated_runtime):
    workspace, profile = isolated_runtime
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=7, stdout="api-secret", stderr="proxy-secret")

    monkeypatch.setattr(runtime.subprocess, "run", run)
    docker = runtime.DockerRuntime(workspace, profile, {"MEMORY_OS_AI_KEYS__DEEPSEEK": "api-secret"})
    with pytest.raises(runtime.RuntimeFailure) as error:
        docker._compose("version")
    assert str(error.value) == "Isolated Compose failed (exit 7)."
    args, kwargs = calls[0]
    assert "api-secret" not in str(args)
    assert kwargs["env"]["MEMORY_OS_AI_KEYS__DEEPSEEK"] == "api-secret"
    assert "--env-file" in args[0] and "--project-name" in args[0]


def test_factory_explicitly_disables_dotenv(monkeypatch):
    import app.config
    import app.main

    calls = []
    marker = object()
    monkeypatch.setattr(app.config, "Settings", lambda **kwargs: calls.append(kwargs) or marker)
    monkeypatch.setattr(app.main, "create_app", lambda settings: settings)
    assert runtime.create_isolated_app() is marker
    assert calls == [{"_env_file": None}]
