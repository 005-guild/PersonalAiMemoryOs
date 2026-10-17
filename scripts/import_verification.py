"""Verify API/CLI imports against an existing isolated local Uvicorn process."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import UUID

from verification_support import PROJECT_ROOT, RunningApp


def _counts(app: RunningApp) -> tuple[int, int, int]:
    with closing(sqlite3.connect(app.database)) as database:
        return tuple(database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("sources", "source_origins", "knowledge"))


def check_zhihu_import(app: RunningApp) -> None:
    """Keep every submitted input and every touched database inside test storage."""
    print("Checking isolated Zhihu API/CLI dry run, creation, deduplication and partial errors...", flush=True)
    input_path = app.workspace / "zhihu-import.json"
    reports = []
    report_directory = (PROJECT_ROOT / ".cache" / "import-reports").resolve()
    original_counts = _counts(app)
    original_markdown = sorted(path.relative_to(app.vault).as_posix() for path in app.vault.rglob("*.md"))

    def run_cli(payload: dict, *, dry_run=False, exit_code=0) -> dict:
        # A BOM exercises the exact bytes accepted by real user-created JSON files.
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig")
        command = [sys.executable, str(PROJECT_ROOT / "scripts" / "import_zhihu.py"),
                   "--file", str(input_path), "--base-url", f"http://127.0.0.1:{app.port}"]
        if dry_run:
            command.append("--dry-run")
        result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=45)
        lines = [line.removeprefix("Report: ") for line in result.stdout.splitlines()
                 if line.startswith("Report: ")]
        assert len(lines) == 1, f"CLI did not preserve a report: {result.stdout}\n{result.stderr}"
        report_path = Path(lines[0]).resolve()
        if report_path.parent != report_directory or report_path.suffix != ".json":
            raise RuntimeError("Refusing a CLI report outside its expected project cache.")
        UUID(report_path.stem)
        reports.append(report_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert result.returncode == exit_code, f"CLI exit {result.returncode}: {result.stdout}\n{result.stderr}"
        return report

    try:
        sample = json.loads((PROJECT_ROOT / "examples" / "zhihu-import.sample.json").read_text(encoding="utf-8"))
        preview = run_cli(sample, dry_run=True)
        assert preview["dry_run"] is True
        assert preview["would_create"] == 2 and preview["created"] == 0
        assert _counts(app) == original_counts

        created = run_cli(sample)
        assert created["created"] == 2 and created["processed"] == 2
        assert all(item["status"] == "created" for item in created["items"])
        first_source_id = created["items"][0]["source_id"]
        first_source = app.api("GET", f"/api/v1/sources/{first_source_id}")
        assert first_source["content"] == sample["items"][0]["content"]

        repeated = json.loads(json.dumps(sample))
        repeated["items"][1]["title"] = "Changed incoming title; existing Source must remain unchanged"
        repeated["items"][0]["url"] += "?utm_source=verification#ignored-fragment"
        skipped = run_cli(repeated)
        assert skipped["skipped"] == 2 and skipped["created"] == 0
        assert "title" in skipped["items"][1]["differing_fields"]

        mixed = {"schema_version": 1, "items": [
            sample["items"][0],
            {"url": "https://www.zhihu.com/answer/920000002", "title": "Missing required content"},
            {"url": "https://zhuanlan.zhihu.com/p/930000002", "title": "Additional original sample",
             "author": None, "content": "This synthetic text verifies that valid items survive another item's error."},
        ]}
        partial = run_cli(mixed, exit_code=1)
        assert (partial["created"], partial["skipped"], partial["invalid"], partial["failed"]) == (1, 1, 1, 0)

        deleted = app.api("DELETE", f"/api/v1/sources/{first_source_id}?expected_version={first_source['version']}")
        deleted_repeat = run_cli({"schema_version": 1, "items": [sample["items"][0]]})
        assert deleted_repeat["skipped"] == 1 and deleted_repeat["created"] == 0
        unchanged = app.api("GET", f"/api/v1/sources/{first_source_id}?include_deleted=true")
        assert unchanged["deleted_at"] == deleted["deleted_at"]
        assert unchanged["version"] == deleted["version"]
        assert unchanged["content"] == first_source["content"]

        protocol_error = run_cli({"schema_version": 999, "items": []}, exit_code=1)
        assert isinstance(protocol_error["detail"], str)
        assert _counts(app) == (original_counts[0] + 3, original_counts[1] + 3, original_counts[2])
        assert sorted(path.relative_to(app.vault).as_posix() for path in app.vault.rglob("*.md")) == original_markdown
    finally:
        # These UUID paths were created by this invocation, never enumerate/delete user reports.
        for path in reports:
            if path.parent != report_directory or not path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
                raise RuntimeError("Refusing cleanup outside the known import report directory.")
            path.unlink(missing_ok=True)

    print("Zhihu CLI/API verification passed without creating Knowledge or Markdown files.", flush=True)
