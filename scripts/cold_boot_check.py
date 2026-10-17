"""Read-only Windows cold-boot evidence; NEVER reboot, start or stop services."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.local_rag_support import get_json


def compare(previous: dict, current: dict) -> dict:
    if previous["boot_time"] == current["boot_time"]:
        return {"status": "pending", "reason": "same_windows_boot; no reboot was performed by this tool"}
    if previous.get("configuration_hashes") != current.get("configuration_hashes"):
        return {"status": "failed", "reason": "configuration_changed_between_boots"}
    missing = [key for key in ["ollama", "qdrant", "desktop_health", "index"] if not current.get(key)]
    if missing or current.get("errors"):
        return {"status": "failed", "reason": "services_or_desktop_unavailable", "missing": missing}
    old_model = previous.get("model_digest")
    if old_model and old_model != current.get("model_digest"):
        return {"status": "failed", "reason": "embedding_model_revision_changed"}
    old_generation = previous.get("index", {}).get("generation") or {}
    new_generation = current["index"].get("generation") or {}
    counts = current["index"].get("counts", {})
    if (not new_generation or new_generation.get("status") != "ready"
            or current["index"].get("last_error") or counts.get("failed") or counts.get("pending")
            or (old_generation and old_generation.get("id") != new_generation.get("id"))):
        return {"status": "failed", "reason": "index_not_ready_or_generation_changed"}
    return {"status": "services_checked", "retrieval_quality": "not executed; use explicit local query acceptance",
            "manual_confirmation_required": "EXE was opened directly after boot without preparatory commands"}


def snapshot(portable: Path) -> dict:
    if sys.platform != "win32":
        raise ValueError("Windows is required")
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command",
        "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"],
        capture_output=True, text=True, timeout=20, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    value = {"boot_time": result.stdout.strip(), "captured_at": datetime.now(timezone.utc).isoformat(),
             "portable": str(portable), "errors": {}, "model_calls": 0}
    if not value["boot_time"]:
        raise ValueError("Cannot read Windows boot identity")
    for name, base, path in [("ollama", "http://127.0.0.1:11434", "/api/version"),
                             ("qdrant", "http://127.0.0.1:6333", "/")]:
        try:
            value[name] = get_json(base, path)
        except Exception as error:
            value["errors"][name] = type(error).__name__
    try:
        tags = get_json("http://127.0.0.1:11434", "/api/tags")
        value["model_digest"] = next(m["digest"] for m in tags["models"] if m["name"] == "bge-m3:latest")
    except Exception as error:
        value["errors"]["model"] = type(error).__name__
    try:
        runtime = json.loads((portable / ".cache/desktop/runtime.json").read_text(encoding="utf-8-sig"))
        # get_json only contacts loopback here; never trust a saved arbitrary URL.
        from scripts.local_rag_support import local_url
        base = local_url(runtime["url"])
        value["desktop_pid"] = runtime["pid"]
        value["desktop_health"] = get_json(base, "/health")
        value["index"] = get_json(base, "/api/v1/rag/index/status?summary_only=true")
    except Exception as error:
        value["errors"]["desktop"] = type(error).__name__
    # Hashes only, never disclose provider secrets.
    value["configuration_hashes"] = {name: hashlib.sha256((portable / name).read_bytes()).hexdigest()
        for name in [".env", "config/ai-providers.yml", "config/embedding-providers.yml", "config/local-rag-startup.json"]
        if (portable / name).is_file()}
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", type=Path, default=ROOT / "dist/PersonalAiMemoryOs-0.6.6")
    parser.add_argument("--verify", type=Path, help="Previous snapshot; a different Windows boot is mandatory")
    args = parser.parse_args()
    value = snapshot(args.portable.resolve())
    if args.verify:
        previous = json.loads(args.verify.read_text(encoding="utf-8"))
        value["comparison"] = compare(previous, value)
        value["configuration_unchanged"] = previous["configuration_hashes"] == value["configuration_hashes"]
    evidence = ROOT / ".cache/cold-boot" / uuid4().hex
    evidence.mkdir(parents=True)
    path = evidence / "report.json"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(path), "comparison": value.get("comparison", {"status": "baseline_only"})}))
    raise SystemExit(1 if value.get("comparison", {}).get("status") == "failed" else 0)
