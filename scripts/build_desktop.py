"""Reproducible Windows desktop bundle; all intermediate state stays in .cache."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "PersonalAiMemoryOs"
BUILD_ENV = ROOT / ".cache" / "desktop-build-venv"


def portable_directory_name(value: str) -> str:
    """Accept one safe Windows basename, never a path or reserved device name."""
    devices = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
               *[f"LPT{i}" for i in range(1, 10)]}
    if (not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,78}[A-Za-z0-9])?", value)
            or value.split(".", 1)[0].upper() in devices):
        raise argparse.ArgumentTypeError("Output name must be a safe directory basename (letters, digits, dot, dash, underscore).")
    return value


def run(command: list[str], environment: dict[str, str]) -> None:
    # PyInstaller writes progress to stderr; merge it before PowerShell can turn
    # ordinary progress into NativeCommandError records in a redirected build log.
    process = subprocess.Popen(command, cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            print(line, end="", flush=True)
    if process.wait():
        raise subprocess.CalledProcessError(process.returncode, command)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_fingerprint() -> str:
    files = []
    for relative in ("app", "migrations", "packaging"):
        files.extend(path for path in (ROOT / relative).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    files.extend(ROOT / name for name in ("pyproject.toml", "uv.lock", "alembic.ini", ".env.example",
                 "config/ai-providers.example.yml", "config/embedding-providers.example.yml",
                 "scripts/desktop_entry.py", "scripts/build_desktop.py"))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def inspect_bundle(bundle: Path) -> dict:
    expected = ["PersonalAiMemoryOs.exe", "_internal/python312.dll", "_internal/alembic.ini",
                "_internal/.env.example", "_internal/migrations/versions/0004_rag_index.py",
                "_internal/migrations/versions/0005_prompts_batches_sources.py",
                "_internal/app/prompts/zhihu_deep_analysis_v1.md", "_internal/app/prompts/knowledge_v2_contract.md",
                "_internal/app/web/index.html", "_internal/config/ai-providers.example.yml",
                "_internal/config/embedding-providers.example.yml",
                "_internal/webview/lib/Microsoft.Web.WebView2.Core.dll",
                "_internal/pythonnet/runtime/Python.Runtime.dll"]
    expected.extend("_internal/" + path.relative_to(ROOT).as_posix()
                    for folder in (ROOT / "migrations/versions", ROOT / "app/prompts")
                    for path in folder.glob("*") if path.is_file() and path.suffix in {".py", ".md"})
    for file in bundle.rglob("*"):
        lowered = {part.lower() for part in file.relative_to(bundle).parts}
        if (lowered & {"playwright", "pytest", ".env", "memory.db", "ai-providers.yml",
                       "embedding-providers.yml", ".memory-os-config-transactions"}
                or any(part.startswith(".memory-os-ai-") and part.endswith(".tmp") for part in lowered)):
            raise RuntimeError(f"Private or development-only resource in distribution: {file}")
        if file.is_file() and file.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            raise RuntimeError(f"Database in distribution: {file}")
    for relative in expected:
        if not (bundle / relative).is_file():
            raise RuntimeError(f"Required bundle resource missing: {relative}")
    return {"files": sum(item.is_file() for item in bundle.rglob("*")),
            "bytes": sum(item.stat().st_size for item in bundle.rglob("*") if item.is_file())}


def publish(bundle: Path, version: str, report: dict, output_name: str = NAME) -> Path:
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    target = destination / portable_directory_name(output_name)
    if target.exists():
        # Never overwrite a folder that has been used as a portable installation.
        if any((target / name).exists() for name in ("data", "knowledge", "config", ".env", "logs")):
            raise RuntimeError(f"{target} contains runtime data. Preserve it and choose a new --output-name.")
        previous = ROOT / ".cache" / "desktop-build" / f"previous-{uuid4().hex}"
        target.rename(previous)
    # Keep the staging tree as evidence. Windows scanners can temporarily hold
    # its directory handles after PyInstaller exits; copying avoids that rename
    # race without deleting or modifying files in a used portable installation.
    shutil.copytree(bundle, target)
    archive = destination / f"{NAME}-{version}-windows-x64.zip"
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(target.rglob("*")):
            if file.is_file():
                output.write(file, file.relative_to(destination).as_posix())
    temporary.replace(archive)
    executable = target / f"{NAME}.exe"
    checksums = f"{sha256(archive)}  {archive.name}\n{sha256(executable)}  {target.name}/{executable.name}\n"
    (destination / f"{archive.name}.sha256").write_text(checksums, encoding="ascii")
    report.update({"directory": str(target), "archive": str(archive),
                   "archive_sha256": sha256(archive), "executable_sha256": sha256(executable)})
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-sync", action="store_true", help="Reuse the already synchronized isolated build environment")
    parser.add_argument("--staging-only", action="store_true", help="Keep the clean bundle in .cache and publish only a pristine ZIP")
    parser.add_argument("--output-name", type=portable_directory_name, default=NAME,
                        help="New directory basename beneath dist; existing runtime data is never overwritten")
    arguments = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("This build must run on Windows x64.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    workspace = ROOT / ".cache" / "desktop-build" / uuid4().hex
    workspace.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update({"UV_PROJECT_ENVIRONMENT": str(BUILD_ENV), "UV_CACHE_DIR": str(ROOT / ".cache" / "uv"),
                        "UV_LINK_MODE": "copy", "PYINSTALLER_CONFIG_DIR": str(workspace / "pyinstaller-cache"),
                        "MEMORY_OS_DESKTOP_BUILD_ASSETS": str(workspace / "assets")})
    # The build never evaluates personal application configuration or keys.
    for key in list(environment):
        if key.startswith("MEMORY_OS_") and key != "MEMORY_OS_DESKTOP_BUILD_ASSETS":
            del environment[key]
    if not arguments.skip_sync:
        uv = shutil.which("uv")
        if not uv:
            raise RuntimeError("uv is required to create the isolated build environment.")
        run([uv, "sync", "--locked", "--no-dev", "--group", "desktop", "--group", "build"], environment)
    python = BUILD_ENV / "Scripts" / "python.exe"
    if not python.is_file():
        raise RuntimeError("The isolated build environment is missing; rerun without --skip-sync.")
    if not (ROOT / "app" / "desktop" / "launcher.py").is_file():
        raise RuntimeError("Desktop launcher is not present.")
    input_fingerprint = source_fingerprint()
    run([str(python), str(ROOT / "packaging" / "desktop_assets.py"),
         "--output", str(workspace / "assets"), "--version", version], environment)
    run([str(python), "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(workspace / "dist"), "--workpath", str(workspace / "work"),
         str(ROOT / "packaging" / "desktop.spec")], environment)
    bundle = workspace / "dist" / NAME
    shutil.copyfile(ROOT / "packaging" / "使用说明.txt", bundle / "使用说明.txt")
    sys.path.insert(0, str(ROOT))
    from app.desktop.update_resources import create_manifest
    from alembic.script import ScriptDirectory
    from app.repositories.migrations import migration_config
    schema = ScriptDirectory.from_config(migration_config()).get_current_head()
    create_manifest(bundle, version, schema)
    if input_fingerprint != source_fingerprint():
        raise RuntimeError("Build inputs changed during packaging; rerun after edits finish.")
    report = {"version": version, "architecture": "windows-x64", "schema": schema,
              "built_at": datetime.now(timezone.utc).isoformat(), "signed": False,
              "manifest": inspect_bundle(bundle), "workspace": str(workspace),
              "source_fingerprint": input_fingerprint}
    if arguments.staging_only:
        destination = ROOT / "dist"
        destination.mkdir(exist_ok=True)
        archive = destination / f"{NAME}-windows-x64.zip"
        temporary = archive.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for file in sorted(bundle.rglob("*")):
                if file.is_file():
                    output.write(file, Path("PersonalAiMemoryOs-0.6.6") / file.relative_to(bundle))
        temporary.replace(archive)
        executable = bundle / f"{NAME}.exe"
        checksums = f"{sha256(archive)}  {archive.name}\n{sha256(executable)}  PersonalAiMemoryOs-0.6.6/{executable.name}\n"
        archive.with_suffix(".zip.sha256").write_text(checksums, encoding="ascii")
        report.update(directory=str(bundle), archive=str(archive), archive_sha256=sha256(archive), executable_sha256=sha256(executable))
        target = bundle
    else:
        target = publish(bundle, version, report, arguments.output_name)
    (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / ".cache" / "desktop-build-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Portable bundle: {target}\nArchive: {report['archive']}\nReport: {workspace / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
