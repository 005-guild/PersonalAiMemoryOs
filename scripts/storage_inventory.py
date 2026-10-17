"""Read-only workspace disk inventory. NEVER deletes, rotates or reads secrets."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]


def measure(path: Path) -> dict:
    result = {"bytes": 0, "files": 0, "links_skipped": 0, "errors": 0}
    def scan(current):
        try:
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                result["links_skipped"] += 1
                return
            if stat.S_ISREG(info.st_mode):
                result["bytes"] += info.st_size
                result["files"] += 1
            elif stat.S_ISDIR(info.st_mode):
                with os.scandir(current) as entries:
                    for entry in entries:
                        scan(Path(entry.path))
        except OSError:
            result["errors"] += 1
    scan(path)
    return result


def retention_class(relative: str) -> tuple[str, str]:
    name = relative.replace("\\", "/").lower()
    if name == ".cache/ollama" or name.startswith((".tools", "data", "knowledge", "config")):
        return "protected_runtime", "Models, services or business configuration; never bulk-clean"
    if name.startswith("dist"):
        return "protected_distribution", "May contain the used portable installation and its backups"
    if name.startswith(".cache/desktop-build"):
        return "review_builds", "Keep current referenced bundle and last two verified builds; preserve rollback evidence"
    if any(word in name for word in ("validation", "-rag", "-web", "-ui", "desktop-local", "recovery", "cold-boot", "quality")):
        return "review_evidence", "Keep latest passed and unresolved failures; archive after 30 days, never auto-delete"
    if name.startswith((".cache/uv", ".cache/pytest", ".cache/playwright")):
        return "reproducible_tool_cache", "Remove only explicitly when tools/tests are stopped; browsers may be needed offline"
    return "unclassified_keep", "Preserve until ownership and recovery requirements are reviewed"


def inventory(root: Path = ROOT) -> dict:
    candidates = [root / name for name in [".tools", ".venv", "data", "knowledge", "config", "imports", "dist"]]
    if (root / ".cache").is_dir():
        candidates += sorted((root / ".cache").iterdir())
    rows = []
    for path in candidates:
        if not path.exists():
            continue
        relative = path.relative_to(root).as_posix()
        category, policy = retention_class(relative)
        rows.append({"path": relative, "category": category, "policy": policy, **measure(path)})
    return {"captured_at": datetime.now(timezone.utc).isoformat(), "status": "read_only",
            "deleted_files": 0, "content_read": False, "rows": sorted(rows, key=lambda r: r["bytes"], reverse=True),
            "log_policy": {"memory-os.log": "existing 2 MiB / 3 archives",
                "local-rag-startup.log": "external; inspect size, rotate only after its helper has stopped",
                "ollama_stdout_stderr": "external; inspect size, rotate only after the tracked server has stopped"},
            "backup_policy": "Keep at least 3 verified full backups and all pending upgrade/restore evidence; no automatic purge"}


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = inventory()
    output = ROOT / ".cache/storage-inventory/report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "bytes": sum(r["bytes"] for r in result["rows"]),
        "errors": sum(r["errors"] for r in result["rows"]), "deleted_files": 0}))
