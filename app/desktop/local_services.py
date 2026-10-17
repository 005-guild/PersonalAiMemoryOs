"""Optional portable-desktop preparation of existing local RAG services."""

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from app.config import Settings
from app.desktop.local_service_process import (
    external_environment, host_dll_search, merge_local_proxy_bypass, powershell_path,
)
from app.paths import portable_path, resource_root
from app.vector.configuration import EmbeddingRegistry

logger = logging.getLogger(__name__)
CONFIGURATION = "config/local-rag-startup.json"
MAX_CONFIGURATION_BYTES = 16 * 1024
STARTUP_TIMEOUT = 150


class LocalServicesError(RuntimeError):
    """Safe Chinese text for a startup dialog, without environment/provider data."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key.")
        result[key] = value
    return result


def _configuration(root: Path) -> dict | None:
    path = portable_path(root, root / CONFIGURATION)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONFIGURATION_BYTES + 1)
    if len(raw) > MAX_CONFIGURATION_BYTES:
        raise ValueError("Startup configuration too large.")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    if (not isinstance(value, dict) or set(value) != {"schema_version", "enabled", "project_root"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["enabled"]) is not bool or not isinstance(value["project_root"], str)
            or not value["project_root"].strip()
            or any(ord(character) < 32 for character in value["project_root"])):
        raise ValueError("Invalid startup configuration.")
    return value


def _loopback_endpoint(value: str, port: int, path: str) -> bool:
    parsed = urlsplit(value)
    # The helper binds IPv4 127.0.0.1 only. Other loopback interfaces remain
    # externally managed instead of launching a service at the wrong address.
    return (parsed.hostname in {"localhost", "127.0.0.1"}
            and parsed.scheme == "http" and parsed.port == port
            and parsed.path.rstrip("/") == path and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment)


def _managed_endpoints(settings: Settings) -> bool:
    registry = EmbeddingRegistry(settings)
    profile = registry.profiles.get(registry.default_profile)
    if registry.error_code or profile is None or not profile.enabled:
        raise LocalServicesError("默认向量配置未就绪，请检查 RAG 设置后重试。")
    return (_loopback_endpoint(profile.base_url, 11434, "/v1")
            and _loopback_endpoint(settings.rag_qdrant_url, 6333, ""))


def _project_directory(root: Path, configured: str) -> Path:
    if configured.startswith(("\\\\", "//")):
        raise ValueError("Network directories are not supported.")
    path = Path(configured)
    path = Path(os.path.abspath(path if path.is_absolute() else root / path))
    # Validate the original path before resolving: resolution alone can hide a
    # junction in the project directory or one of its ancestors.
    portable_path(Path(path.anchor), path)
    path = path.resolve(strict=True)
    if str(path).startswith(("\\\\", "//")) or not path.is_dir():
        raise ValueError("Project directory must be local.")
    executable = portable_path(path, path / ".tools/ollama/ollama.exe")
    compose = portable_path(path, path / "docker-compose.yml")
    if not executable.is_file() or not compose.is_file():
        raise ValueError("Local runtime files missing.")
    return path


def start_local_services(root: Path, settings: Settings) -> None:
    """Run only the bundled startup helper for an explicitly opted-in profile.

    This never downloads models, calls an embedding/generation endpoint, changes
    saved settings, or stops shared services. A timed-out helper is left running.
    """
    if not settings.rag_enabled:
        return
    root = Path(root).absolute()
    try:
        configuration = _configuration(root)
        if configuration is None or not configuration["enabled"]:
            return
        if sys.platform != "win32":
            logger.info("Local RAG startup skipped: Windows host tools required.")
            return
        if not _managed_endpoints(settings):
            logger.info("Local RAG startup skipped: configured endpoints use external services.")
            return
        project = _project_directory(root, configuration["project_root"])
        script = resource_root() / "scripts/start_local_rag.ps1"
        if not script.is_file():
            raise LocalServicesError("程序缺少本地 RAG 启动资源，请完整更新便携程序。")
        command = [str(powershell_path()), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-File", str(script), "-ProjectRoot", str(project)]
        log_path = portable_path(root, root / "logs/local-rag-startup.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        merge_local_proxy_bypass()
        with log_path.open("ab") as output:
            with host_dll_search():
                process = subprocess.Popen(command, cwd=str(project), env=external_environment(),
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                    shell=False, close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                result = process.wait(timeout=STARTUP_TIMEOUT)
            except subprocess.TimeoutExpired:
                raise LocalServicesError("本地 RAG 服务准备超过 150 秒，后台仍可能继续启动。"
                    "请稍后重试，不会强制停止服务。\n日志位置：" + str(log_path)) from None
        if result != 0:
            raise LocalServicesError("本地 RAG 服务启动失败，请检查 Ollama、Docker 和本地运行目录。"
                "\n日志位置：" + str(log_path))
        logger.info("Local RAG services are ready.")
    except LocalServicesError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        logger.warning("Local RAG service preparation failed (%s).", type(error).__name__)
        raise LocalServicesError("本地 RAG 自动启动配置或运行环境无效，请检查配置和日志。"
            "\n日志位置：" + str(root / "logs/local-rag-startup.log")) from None
