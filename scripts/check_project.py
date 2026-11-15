"""One non-paid verification entry; external acceptance is deliberately separate."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-node", action="store_true")
    args = parser.parse_args()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORY_OS_")}
    steps = [("lock", ["uv", "lock", "--check", "--offline"]),
             ("docs", [sys.executable, "scripts/check_docs.py"]),
             ("release", [sys.executable, "scripts/check_release.py"]),
             ("tests", [sys.executable, "-m", "pytest"])]
    records = []
    node = shutil.which("node")
    if node or args.require_node:
        steps.append(("web", [sys.executable, "scripts/check_web_modules.py"]))
    else:
        records.append({"name": "web", "status": "skipped", "reason": "Node.js not on PATH"})
    output = ROOT / ".cache/project-check"
    output.mkdir(parents=True, exist_ok=True)
    for name, command in steps:
        started = time.monotonic()
        print(f"Checking {name}...", flush=True)
        try:
            with (output / f"{name}.log").open("w", encoding="utf-8") as stream:
                result = subprocess.run(command, cwd=ROOT, env=environment, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=600, check=False)
            records.append({"name": name, "status": "passed" if result.returncode == 0 else "failed",
                            "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 3)})
        except (OSError, subprocess.TimeoutExpired) as error:
            records.append({"name": name, "status": "failed", "reason": type(error).__name__})
        if records[-1]["status"] == "failed":
            log = output / f"{name}.log"
            if log.is_file():
                print(f"Failed {name}; final 12000 characters of {log.name}:", flush=True)
                print(log.read_text(encoding="utf-8", errors="replace")[-12000:], flush=True)
    report = {"status": "failed" if any(r["status"] == "failed" for r in records) else "passed",
              "checks": records, "real_model_calls": 0, "external_acceptance": "not run"}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
