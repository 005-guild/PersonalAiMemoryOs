"""Opt-in host preparation is bounded, secret-free and safe on failed starts."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
import yaml

from app.config import Settings
from app.desktop import local_service_process as host
from app.desktop import local_services as services


@pytest.fixture
def setup_local_startup(tmp_path, monkeypatch):
    root = tmp_path / "中文 便携目录"
    project = tmp_path / "本地模型 运行目录"
    resources = tmp_path / "打包 资源"
    for directory in (root / "config", project / ".tools/ollama", resources / "scripts"):
        directory.mkdir(parents=True)
    (project / ".tools/ollama/ollama.exe").write_bytes(b"not executed")
    (project / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    (resources / "scripts/start_local_rag.ps1").write_text("# bundled", encoding="utf-8")
    configuration = {"schema_version": 1, "enabled": True, "project_root": os.path.relpath(project, root)}
    path = root / services.CONFIGURATION
    path.write_text(json.dumps(configuration), encoding="utf-8")
    embedding = {"schema_version": 1, "default_profile": "local", "profiles": {
        "local": {"base_url": "http://127.0.0.1:11434/v1", "model": "bge-m3", "dimension": 1024,
                  "auth": "none"}}}
    embedding_path = root / "config/embedding-providers.yml"
    embedding_path.write_text(yaml.safe_dump(embedding), encoding="utf-8")
    settings = Settings(_env_file=None, runtime_root=root, rag_enabled=True)
    monkeypatch.setattr(services.sys, "platform", "win32")
    monkeypatch.setattr(services, "resource_root", lambda: resources)
    monkeypatch.setattr(services, "powershell_path", lambda: Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"))
    calls = []

    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(wait=lambda timeout: 0)

    monkeypatch.setattr(services.subprocess, "Popen", spawn)
    return SimpleNamespace(root=root, project=project, resources=resources, configuration=configuration,
                           path=path, embedding=embedding, embedding_path=embedding_path,
                           settings=settings, calls=calls)


@pytest.mark.parametrize("mode", ["rag_off", "absent", "disabled"])
def test_inactive_startup_has_no_child_log_or_proxy_changes(setup_local_startup, monkeypatch, mode):
    value = setup_local_startup
    settings = value.settings
    if mode == "rag_off":
        settings = settings.model_copy(update={"rag_enabled": False})
        monkeypatch.setattr(services, "_configuration", lambda *_: pytest.fail("RAG off read configuration"))
    elif mode == "absent":
        value.path.unlink()
    else:
        value.configuration["enabled"] = False
        value.path.write_text(json.dumps(value.configuration), encoding="utf-8")
    monkeypatch.setattr(services, "merge_local_proxy_bypass", lambda: pytest.fail("Inactive startup changed proxy"))
    services.start_local_services(value.root, settings)
    assert not value.calls
    assert not (value.root / "logs").exists()


@pytest.mark.parametrize("invalid", [
    [], {"schema_version": True, "enabled": True, "project_root": ".."},
    {"schema_version": 1.0, "enabled": True, "project_root": ".."},
    {"schema_version": 1, "enabled": 1, "project_root": ".."},
    {"schema_version": 1, "enabled": True, "project_root": " "},
    {"schema_version": 1, "enabled": True, "project_root": [".."]},
    {"schema_version": 1, "enabled": True, "project_root": "..", "command": "dangerous"},
])
def test_invalid_configuration_cannot_start_a_command(setup_local_startup, invalid):
    value = setup_local_startup
    value.path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(services.LocalServicesError, match="配置或运行环境无效"):
        services.start_local_services(value.root, value.settings)
    assert not value.calls
    assert not (value.root / "logs").exists()


@pytest.mark.parametrize("raw", [
    b'{"schema_version":1,"enabled":true,"enabled":false,"project_root":".."}',
    b"x" * (services.MAX_CONFIGURATION_BYTES + 1), b"\xff\xfe", b"{",
])
def test_duplicate_oversized_and_malformed_configurations_are_rejected(setup_local_startup, raw):
    value = setup_local_startup
    value.path.write_bytes(raw)
    with pytest.raises(services.LocalServicesError):
        services.start_local_services(value.root, value.settings)
    assert not value.calls


@pytest.mark.parametrize("endpoint", ["embedding", "qdrant", "other_loopback", "ipv6"])
def test_remote_configuration_is_skipped_without_starting_local_services(setup_local_startup, monkeypatch, caplog, endpoint):
    value = setup_local_startup
    settings = value.settings
    if endpoint == "embedding":
        value.embedding["profiles"]["local"]["base_url"] = "https://embedding.example.test/v1"
        value.embedding_path.write_text(yaml.safe_dump(value.embedding), encoding="utf-8")
    elif endpoint == "qdrant":
        settings = settings.model_copy(update={"rag_qdrant_url": "https://qdrant.example.test"})
    else:
        address = "127.0.0.2" if endpoint == "other_loopback" else "[::1]"
        value.embedding["profiles"]["local"]["base_url"] = f"http://{address}:11434/v1"
        value.embedding_path.write_text(yaml.safe_dump(value.embedding), encoding="utf-8")
    monkeypatch.setattr(services, "merge_local_proxy_bypass", lambda: pytest.fail("External endpoints changed proxy"))
    with caplog.at_level("INFO", logger=services.__name__):
        services.start_local_services(value.root, settings)
    assert "external services" in caplog.text
    assert not value.calls


@pytest.mark.parametrize("project_path", ["\\\\server\\share", "//server/share", "missing-project"])
def test_network_and_missing_project_directories_are_rejected(setup_local_startup, project_path):
    value = setup_local_startup
    value.configuration["project_root"] = project_path
    value.path.write_text(json.dumps(value.configuration), encoding="utf-8")
    with pytest.raises(services.LocalServicesError):
        services.start_local_services(value.root, value.settings)
    assert not value.calls


def test_runtime_links_are_rejected_before_resolving_project_paths(setup_local_startup, monkeypatch):
    value = setup_local_startup
    checked = []
    original = services.portable_path

    def check(root, path):
        checked.append(path)
        if path == value.project / ".tools/ollama/ollama.exe":
            raise ValueError("simulated reparse point")
        return original(root, path)

    monkeypatch.setattr(services, "portable_path", check)
    with pytest.raises(services.LocalServicesError):
        services.start_local_services(value.root, value.settings)
    assert value.project in checked
    assert value.project / ".tools/ollama/ollama.exe" in checked
    assert not value.calls


def test_bundled_script_and_project_with_spaces_are_distinct_arguments(setup_local_startup, monkeypatch):
    value = setup_local_startup
    monkeypatch.setenv("MEMORY_OS_AI_KEYS__DEEPSEEK", "should-not-reach-host-tool")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:17890")
    services.start_local_services(value.root, value.settings)
    command, arguments = value.calls[0]
    assert command == [str(services.powershell_path()), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                       "-File", str(value.resources / "scripts/start_local_rag.ps1"), "-ProjectRoot", str(value.project)]
    assert arguments["cwd"] == str(value.project)
    assert arguments["stdin"] == subprocess.DEVNULL
    assert arguments["stderr"] == subprocess.STDOUT
    assert not arguments["shell"]
    assert arguments["close_fds"]
    assert all(not name.upper().startswith("MEMORY_OS_") for name in arguments["env"])
    assert arguments["env"]["HTTPS_PROXY"] == "http://127.0.0.1:17890"
    assert "127.0.0.1" in os.environ["NO_PROXY"].split(",")
    assert (value.root / "logs/local-rag-startup.log").is_file()


@pytest.mark.parametrize("failure", ["timeout", "exit", "spawn"])
def test_failed_start_does_not_kill_services_or_expose_exception_details(setup_local_startup, monkeypatch, caplog, failure):
    value = setup_local_startup
    waits = []

    def wait(timeout):
        waits.append(timeout)
        if failure == "timeout":
            raise subprocess.TimeoutExpired("secret-value", timeout)
        return 7

    def spawn(*args, **kwargs):
        if failure == "spawn":
            raise OSError("secret-value")
        # Intentionally no terminate()/kill(): timeout must leave helpers alone.
        return SimpleNamespace(wait=wait)

    monkeypatch.setattr(services.subprocess, "Popen", spawn)
    with pytest.raises(services.LocalServicesError) as result:
        services.start_local_services(value.root, value.settings)
    assert "secret-value" not in str(result.value)
    assert "secret-value" not in caplog.text
    assert str(value.root / "logs/local-rag-startup.log") in str(result.value)
    assert waits == ([] if failure == "spawn" else [150])


def test_proxy_bypass_preserves_both_cases_and_external_environment_excludes_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "_internal"
    system = tmp_path / "system-tools"
    environment = {"NO_PROXY": "example.test,localhost", "no_proxy": "Other.test",
                   "PATH": os.pathsep.join((str(bundle), str(bundle / "pythonnet"), str(system))),
                   "MEMORY_OS_AI_KEYS__PRIVATE": "secret", "LD_LIBRARY_PATH": str(bundle),
                   "LD_LIBRARY_PATH_ORIG": "original-libraries"}
    monkeypatch.setattr(host, "os", SimpleNamespace(environ=environment, pathsep=os.pathsep))
    monkeypatch.setattr(host.sys, "_MEIPASS", str(bundle), raising=False)
    host.merge_local_proxy_bypass()
    assert environment["NO_PROXY"] == environment["no_proxy"] == "example.test,localhost,Other.test,127.0.0.1,::1"
    child = host.external_environment()
    assert child["PATH"] == str(system)
    assert child["LD_LIBRARY_PATH"] == "original-libraries"
    assert "MEMORY_OS_AI_KEYS__PRIVATE" not in child
    assert environment["MEMORY_OS_AI_KEYS__PRIVATE"] == "secret"


def test_frozen_dll_directory_is_restored_even_if_spawn_fails(monkeypatch):
    changes = []

    class Function:
        def __init__(self, call):
            self.call = call

        def __call__(self, *args):
            return self.call(*args)

    def get_directory(size, buffer):
        buffer.value = "C:/bundle/_internal"
        return len(buffer.value)

    kernel = SimpleNamespace(GetDllDirectoryW=Function(get_directory),
                             SetDllDirectoryW=Function(lambda path: changes.append(path) or 1))
    monkeypatch.setattr(host.sys, "platform", "win32")
    monkeypatch.setattr(host.sys, "frozen", True, raising=False)
    monkeypatch.setattr(host.ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    with pytest.raises(OSError):
        with host.host_dll_search():
            raise OSError("simulated spawn failure")
    assert changes == [None, "C:/bundle/_internal"]
