"""Verify a real old-to-new EXE upgrade in one isolated portable directory."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import traceback
from uuid import uuid4
import zipfile

import yaml

from desktop_verification_support import FrozenDesktop
from v05_acceptance import storage_fingerprint
from verification_support import PROJECT_ROOT, PROJECT_VERSION, eventually, note_path

sys.path.insert(0, str(PROJECT_ROOT))

from app.desktop.update import upgrade_portable
from app.desktop.update_resources import digest, read_manifest, resource_name
from app.paths import portable_path


def extract_previous(archive: Path, target: Path) -> None:
    """Validate every ZIP member before extracting only its program resources."""
    devices = {"CON", "PRN", "AUX", "NUL", *[f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)]}
    with zipfile.ZipFile(archive) as source:
        entries, names, roots = [], set(), set()
        if len(source.infolist()) > 10000:
            raise ValueError("Previous release archive has too many entries.")
        if sum(entry.file_size for entry in source.infolist()) > 2 * 1024**3:
            raise ValueError("Previous release archive is too large.")
        for entry in source.infolist():
            name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
            parts = name.split("/")
            if (len(parts) < 1 or any(part in {"", ".", ".."} or ":" in part
                                      or "\\" in part or "\x00" in part for part in parts)
                    or any(part.endswith((".", " ")) for part in parts)
                    or any(part.split(".", 1)[0].upper() in devices for part in parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Unsafe path or link in previous release archive.")
            roots.add(parts[0])
            if len(parts) == 1:
                if not entry.is_dir():
                    raise ValueError("Previous archive must contain one portable root directory.")
                continue
            relative = "/".join(parts[1:])
            if entry.is_dir():
                if relative != "_internal":
                    resource_name(relative)
                continue
            resource_name(relative)
            if relative.casefold() in names:
                raise ValueError("Duplicate release path in previous archive.")
            names.add(relative.casefold())
            entries.append((entry, portable_path(target, target / relative)))
        if len(roots) != 1:
            raise ValueError("Previous release archive has inconsistent root paths.")
        if "personalaimemoryos.exe" not in names:
            raise ValueError("Previous release archive has no portable executable.")
        target.mkdir()
        for entry, destination in entries:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as incoming, destination.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)


@contextmanager
def isolated_settings_environment():
    """An upgrader must never inherit the caller's personal MEMORY_OS settings."""
    original = {key: value for key, value in os.environ.items() if key.startswith("MEMORY_OS_")}
    try:
        for key in original:
            del os.environ[key]
        yield
    finally:
        for key in tuple(os.environ):
            if key.startswith("MEMORY_OS_"):
                del os.environ[key]
        os.environ.update(original)


def database_snapshot(path: Path, columns=None):
    """Keep old row values in memory; the public report contains only their hash."""
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        if columns is None:
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if row[0] != "alembic_version" and not row[0].startswith("sqlite_")]
            columns = {name: [row[1] for row in connection.execute('PRAGMA table_info("' + name.replace('"', '""') + '")')]
                       for name in tables}
        quote = lambda name: '"' + name.replace('"', '""') + '"'
        rows = {name: sorted(json.dumps(row, ensure_ascii=False) for row in connection.execute(
            "SELECT " + ",".join(map(quote, fields)) + " FROM " + quote(name)))
            for name, fields in columns.items()}
    return columns, rows


def digest_json(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def formal_storage_fingerprint() -> dict:
    """Hash project storage plus existing installed desktop databases/vaults."""
    result = storage_fingerprint()
    for installation in (PROJECT_ROOT / "dist").glob("*"):
        if not installation.is_dir():
            continue
        paths = [installation / "data/memory.db", *(installation / "knowledge").rglob("*")]
        result.update({path.relative_to(PROJECT_ROOT).as_posix(): digest(path)
                       for path in paths if path.is_file()})
    return result


def configuration_snapshot(root: Path):
    paths = [root / ".env", *(root / "config").rglob("*")]
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in paths if path.is_file()}


def frozen(root: Path, evidence: Path) -> FrozenDesktop:
    application = FrozenDesktop(root, evidence)
    application.environment.update({"MEMORY_OS_AI_ENABLED": "false", "MEMORY_OS_RAG_ENABLED": "false"})
    return application


def assert_disabled(application: FrozenDesktop) -> None:
    assert application.request("GET", "/api/v1/ai/profiles")["enabled"] is False
    assert application.request("GET", "/api/v1/rag/index/status")["enabled"] is False


def verify_backup(backup: Path, root: Path, columns, old_rows, configs, vault_files):
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_revision"] == "0004"
    for entry in manifest["files"]:
        assert digest(portable_path(backup, backup / entry["path"])) == entry["sha256"]
    assert database_snapshot(backup / "memory.db", columns)[1] == old_rows
    assert {path.relative_to(backup / "knowledge").as_posix(): path.read_bytes()
            for path in (backup / "knowledge").rglob("*") if path.is_file()} == vault_files
    for relative, content in configs.items():
        assert (backup / "configuration" / relative).read_bytes() == content
    program = json.loads((backup / "program-update.json").read_text(encoding="utf-8"))
    assert program["phase"] == "installed"
    for entry in program["files"]:
        if entry["before"] is not None:
            assert digest(portable_path(backup, backup / entry["backup"])) == entry["before"]
        assert digest(portable_path(root, root / entry["path"])) == entry["after"]
    assert backup.resolve().is_relative_to((root / "backups").resolve())


def run_upgrade(bundle: Path, archive: Path, evidence: Path, report: dict):
    root = evidence / "PersonalAiMemoryOs-0.6.6"
    extract_previous(archive, root)
    report["checks"] = ["safe_previous_zip_extraction"]
    application = frozen(root, evidence)
    report["portable_directory"] = str(root)
    try:
        application.start()
        eventually(application.window, timeout=20)
        assert application.request("GET", "/openapi.json")["info"]["version"] == "0.6.6"
        assert_disabled(application)
        assert application.request("GET", "/api/v1/sources")["total"] == 0
        assert application.request("GET", "/api/v1/knowledge")["total"] == 0
        report["checks"].append("old_real_exe_empty_start")
        sources = [application.request("POST", "/api/v1/sources", {
            "title": f"原地升级合成资料 {position}", "author": "离线验收", "source_type": "manual",
            "content": f"只用于缓存目录的第 {position} 份资料。\n不调用任何模型。"}) for position in (1, 2)]
        note = application.request("POST", "/api/v1/knowledge", {"source_id": sources[0]["id"],
            "title": "保留原字节的 v1 笔记", "body": "# 中文笔记\n\n```python\nprint('unchanged')\n```\n",
            "summary": "原地升级验收", "category": "工程", "tags": ["中文", "升级"], "concepts": ["持久化"]})
        note_route = "/api/v1/knowledge/" + note["id"]
        eventually(lambda: application.request("GET", note_route)["sync_status"] == "synced")
        markdown = eventually(lambda: note_path(root / "knowledge", note["id"]))
        note = application.request("GET", note_route)
        for path in (root / ".env", root / "config/ai-providers.yml", root / "config/embedding-providers.yml"):
            with path.open("ab") as stream:
                stream.write(b"\n# isolated upgrade acceptance: preserve this exact configuration\n")
        sentinel = root / "unmanaged-user-sentinel.bin"
        sentinel.write_bytes(b"Unknown user file must survive an in-place resource update.\r\n\x00\xff")
        configs = configuration_snapshot(root)
        markdown_bytes, sentinel_bytes = markdown.read_bytes(), sentinel.read_bytes()
        assert yaml.safe_load(markdown_bytes.decode("utf-8").split("---", 2)[1])["schema_version"] == 1
        report["checks"] += ["source_and_linked_note_creation", "v1_markdown_synced"]
        old_exe = digest(root / "PersonalAiMemoryOs.exe")
        old_live_database = digest(root / "data/memory.db")
        try:
            with isolated_settings_environment():
                upgrade_portable(bundle, root, archive)
        except RuntimeError as error:
            assert "仍在运行" in str(error), "Running-upgrade rejection must come from the instance lease."
        else:
            raise AssertionError("An upgrade unexpectedly replaced a running installation.")
        assert application.process.poll() is None
        assert application.request("GET", "/health")["status"] == "ok"
        assert digest(root / "PersonalAiMemoryOs.exe") == old_exe
        assert digest(root / "data/memory.db") == old_live_database
        assert not (root / "backups").exists() and not (root / ".memory-os-upgrade.json").exists()
        assert markdown.read_bytes() == markdown_bytes and configuration_snapshot(root) == configs
        report["checks"].append("running_upgrade_refused_without_writes")
        application.request_close()
        application.wait_closed()
        report["checks"].append("old_exe_graceful_close_and_port_release")
        columns, old_rows = database_snapshot(root / "data/memory.db")
        with sqlite3.connect((root / "data/memory.db").as_uri() + "?mode=ro", uri=True) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0004"
        vault_files = {path.relative_to(root / "knowledge").as_posix(): path.read_bytes()
                       for path in (root / "knowledge").rglob("*") if path.is_file()}
        with isolated_settings_environment():
            result = upgrade_portable(bundle, root, archive)
        assert result["status"] == "upgraded" and result["schema"] == "0005"
        assert digest(root / "PersonalAiMemoryOs.exe") == digest(bundle / "PersonalAiMemoryOs.exe")
        assert database_snapshot(root / "data/memory.db", columns)[1] == old_rows
        verify_backup(Path(result["backup"]), root, columns, old_rows, configs, vault_files)
        report["checks"] += ["verified_backup", "all_legacy_columns_and_rows_preserved"]
        assert not (root / ".memory-os-upgrade.json").exists()
        assert markdown.read_bytes() == markdown_bytes and configuration_snapshot(root) == configs
        assert sentinel.read_bytes() == sentinel_bytes
        application = frozen(root, evidence)
        application.start()
        eventually(application.window, timeout=20)
        assert application.request("GET", "/openapi.json")["info"]["version"] == PROJECT_VERSION
        assert_disabled(application)
        for source in sources:
            assert application.request("GET", "/api/v1/sources/" + source["id"]) == source
        current_note = application.request("GET", note_route)
        assert {key: current_note[key] for key in note} == note
        assert current_note["source_ids"] == [sources[0]["id"]]
        assert application.request("GET", "/api/v1/sources")["total"] == 2
        assert application.request("GET", "/api/v1/knowledge")["total"] == 1
        templates = application.request("GET", "/api/v1/prompt-templates")
        assert templates["total"] == 2 and sum(item["is_default"] for item in templates["items"]) == 1
        assert {item["output_schema_version"] for item in templates["items"]} == {1, 2}
        assert application.request("GET", "/api/v1/processing/runs")["total"] == 0
        assert application.request("GET", "/api/v1/processing/batches")["total"] == 0
        application.request_close()
        application.wait_closed()
        with sqlite3.connect((root / "data/memory.db").as_uri() + "?mode=ro", uri=True) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005"
            assert connection.execute("SELECT knowledge_id, source_id, position FROM knowledge_sources").fetchall() == [(note["id"], sources[0]["id"], 0)]
            assert all(connection.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0 for table in (
                "processing_runs", "processing_batches", "processing_batch_items", "rag_index_generations",
                "rag_note_index_states", "rag_index_jobs"))
        assert markdown.read_bytes() == markdown_bytes and configuration_snapshot(root) == configs
        assert sentinel.read_bytes() == sentinel_bytes
        assert database_snapshot(root / "data/memory.db", columns)[1] == old_rows
        report.update(backup=result["backup"], old_columns_and_rows_sha256=digest_json(old_rows),
            markdown_sha256=hashlib.sha256(markdown_bytes).hexdigest(), configuration_files=len(configs),
            old_version="0.6.6", old_schema="0004", new_schema="0005", source_count=2, knowledge_count=1,
            prompt_template_count=2, checks=["safe_previous_zip_extraction", "old_real_exe_empty_start",
            "source_and_linked_note_creation", "v1_markdown_synced", "running_upgrade_refused_without_writes",
            "old_exe_graceful_close_and_port_release", "verified_backup", "all_legacy_columns_and_rows_preserved",
            "configuration_and_unknown_file_preserved", "same_directory_new_real_exe_start", "source_link_backfill",
            "v1_markdown_original_bytes", "built_in_templates", "zero_processing_and_rag_jobs", "new_exe_port_release"])
    finally:
        application.stop()
        report["owned_process_released"] = application.process is None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="Pristine new clean staging bundle")
    parser.add_argument("--previous-archive", type=Path,
                        default=PROJECT_ROOT / "dist/PersonalAiMemoryOs-0.6.6-windows-x64.zip")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Real portable EXE upgrade verification requires Windows.")
    bundle, archive = args.bundle.resolve(), args.previous_archive.resolve()
    if not archive.is_file():
        parser.error("The original previous release ZIP does not exist.")
    if any((bundle / name).exists() for name in (".env", "data", "knowledge", "config/ai-providers.yml")):
        parser.error("The new bundle must be pristine and contain no private/runtime data.")
    manifest = read_manifest(bundle)
    if manifest["version"] != PROJECT_VERSION or manifest["schema"] != "0005":
        parser.error("The bundle version/schema does not match this v0.7 upgrade verifier.")
    cache = (PROJECT_ROOT / ".cache/v07-upgrade").resolve()
    if not cache.is_relative_to(PROJECT_ROOT.resolve()):
        parser.error("Verification data must remain inside this project workspace.")
    evidence = cache / uuid4().hex
    evidence.mkdir(parents=True)
    before = formal_storage_fingerprint()
    report = {"version": PROJECT_VERSION, "bundle": str(bundle), "previous_archive": str(archive),
              "previous_archive_sha256": digest(archive), "formal_before": before, "real_model_calls": 0,
              "evidence": str(evidence), "clean_second_pc_tested": False}
    print("Upgrade evidence: " + str(evidence), flush=True)
    try:
        run_upgrade(bundle, archive, evidence, report)
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        report["formal_storage_unchanged"] = before == formal_storage_fingerprint()
        if not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(evidence / "report.json")}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
