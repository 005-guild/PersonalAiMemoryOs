"""Offline release consistency checks; no build, publication or private settings."""

import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check(root: Path = ROOT) -> dict:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", project["version"]):
        raise ValueError("Application version must use major.minor.patch")
    tree = ast.parse((root / "app/main.py").read_text(encoding="utf-8"))
    versions = [keyword.value.value for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == "FastAPI"
                for keyword in node.keywords if keyword.arg == "version" and isinstance(keyword.value, ast.Constant)]
    if versions != [project["version"]]:
        raise ValueError("FastAPI and project versions differ")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = [p for p in lock["package"] if p["name"] == project["name"]]
    if len(packages) != 1 or packages[0]["version"] != project["version"]:
        raise ValueError("Lock project version differs")
    vendor_root = root / "app/web/vendor"
    manifest = json.loads((vendor_root / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["files"].items():
        path = vendor_root / name
        if not path.resolve().is_relative_to(vendor_root.resolve()):
            raise ValueError("Vendor manifest path escapes resource directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Vendor integrity mismatch: {name}")
    # Importing migrations/config does not instantiate Settings or open SQLite.
    from alembic.script import ScriptDirectory
    from app.repositories.migrations import migration_config
    scripts = ScriptDirectory.from_config(migration_config())
    return {"status": "passed", "application_version": project["version"], "schema": scripts.get_current_head(),
            "lock_packages": len(lock["package"]), "verified_vendor_files": len(manifest["files"]),
            "lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
            "project_license": "declared" if (root / "LICENSE").is_file() else "not selected; no open-source license grant",
            "vulnerability_scan": "separate online audit required", "model_calls": 0}


if __name__ == "__main__":
    try:
        result = check()
    except Exception as error:
        result = {"status": "failed", "error": str(error)}
    output = ROOT / ".cache/release-check/report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
