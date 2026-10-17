"""Portable publishing must preserve installations that already contain data."""

import argparse
import importlib.util
from pathlib import Path
import zipfile

import pytest


@pytest.fixture
def builder(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parents[1] / "scripts/build_desktop.py"
    spec = importlib.util.spec_from_file_location("desktop_build_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


@pytest.mark.parametrize("name", ["../outside", r"..\outside", "D:/outside", "CON", "aux.txt", "NUL",
                                  "COM1", "LPT9.txt", ".", "..", "trailing.", "bad:name"])
def test_output_name_cannot_escape_dist_or_use_windows_devices(builder, name):
    with pytest.raises(argparse.ArgumentTypeError):
        builder.portable_directory_name(name)


def test_versioned_output_preserves_previous_runtime_and_old_archive(builder, tmp_path):
    previous = tmp_path / "dist/PersonalAiMemoryOs"
    previous.mkdir(parents=True)
    (previous / ".env").write_text("private sentinel", encoding="utf-8")
    archive = previous.parent / "PersonalAiMemoryOs-0.6.1-windows-x64.zip"
    archive.write_bytes(b"previous archive sentinel")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "PersonalAiMemoryOs.exe").write_bytes(b"synthetic build fixture")

    with pytest.raises(RuntimeError, match="contains runtime data"):
        builder.publish(staging, "0.6.2", {})
    report = {}
    target = builder.publish(staging, "0.6.2", report, "PersonalAiMemoryOs-0.6.2")

    assert target == tmp_path / "dist/PersonalAiMemoryOs-0.6.2"
    assert (previous / ".env").read_text(encoding="utf-8") == "private sentinel"
    assert archive.read_bytes() == b"previous archive sentinel"
    with zipfile.ZipFile(report["archive"]) as output:
        assert output.namelist() == ["PersonalAiMemoryOs-0.6.2/PersonalAiMemoryOs.exe"]
    checksums = Path(report["archive"] + ".sha256").read_text(encoding="ascii")
    assert "PersonalAiMemoryOs-0.6.2/PersonalAiMemoryOs.exe" in checksums


@pytest.mark.parametrize("private_path", [
    ".memory-os-config-transactions/pending/old-0",
    ".memory-os-ai-pending-0.tmp",
    "config/.memory-os-ai-pending-1.tmp",
])
def test_bundle_rejects_interrupted_configuration_secrets(builder, tmp_path, private_path):
    bundle = tmp_path / "bundle"
    for relative in ("PersonalAiMemoryOs.exe", "_internal/python312.dll", "_internal/alembic.ini",
                     "_internal/.env.example", "_internal/migrations/versions/0004_rag_index.py",
                     "_internal/app/web/index.html", "_internal/config/ai-providers.example.yml",
                     "_internal/config/embedding-providers.example.yml",
                     "_internal/webview/lib/Microsoft.Web.WebView2.Core.dll",
                     "_internal/pythonnet/runtime/Python.Runtime.dll", private_path):
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"synthetic resource")
    with pytest.raises(RuntimeError, match="Private or development-only"):
        builder.inspect_bundle(bundle)
