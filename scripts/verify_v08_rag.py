"""Real isolated Qdrant plus synthetic models; v0.8 local/Docker HTTP acceptance."""

import argparse
from contextlib import closing
import json
import sqlite3
import sys
import traceback
from uuid import uuid4

from v05_acceptance import QDRANT_IMAGE, Runtime, json_file, storage_fingerprint
from v08_rag_workflow import check_restart, run_workflow
from verification_support import PROJECT_ROOT, PROJECT_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "docker", "all"], default="local")
    parser.add_argument("--image", default="memory-os-v08-validation:latest")
    args = parser.parse_args()
    evidence = PROJECT_ROOT / ".cache/v08-rag" / uuid4().hex
    evidence.mkdir(parents=True)
    before = storage_fingerprint()
    report = {"version": PROJECT_VERSION, "schema": "0006", "qdrant_image": QDRANT_IMAGE,
        "real_model_calls": 0, "real_quality": "pending", "modes": {}, "formal_before": before}
    print(f"Evidence: {evidence}", flush=True)
    try:
        for mode in (["local", "docker"] if args.mode == "all" else [args.mode]):
            runtime = Runtime(evidence / f"{mode}-{uuid4().hex[:12]}", mode, args.image,
                              mock_script=PROJECT_ROOT / "scripts/v08_rag_mock_server.py")
            try:
                app = runtime.start()
                state = run_workflow(app, runtime.workspace)
                app = runtime.restart()
                check_restart(app, state, runtime.workspace)
                with closing(sqlite3.connect(runtime.database)) as database:
                    assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    assert database.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006"
                    assert database.execute("SELECT count(*) FROM sources").fetchone()[0] == 1
                    assert database.execute("SELECT count(*) FROM knowledge").fetchone()[0] == 1
                    assert database.execute("SELECT count(*) FROM processing_runs").fetchone()[0] == 0
                report["modes"][mode] = {"status": "passed", "evidence": str(runtime.workspace), "checks": state["checks"] + ["restart persistence", "SQLite integrity/schema"]}
                print(mode + ": passed", flush=True)
            finally:
                runtime.stop()
                leftovers = {}
                for resource, arguments in {
                    "containers": ["ps", "-aq"], "networks": ["network", "ls", "-q"],
                    "volumes": ["volume", "ls", "-q"],
                }.items():
                    leftovers[resource] = runtime.command(["docker", *arguments, "--filter",
                        "label=com.docker.compose.project=" + runtime.project]).splitlines()
                assert not any(leftovers.values()), leftovers
                cleanup = json.loads((runtime.workspace / "cleanup.json").read_text(encoding="utf-8"))
                report["modes"].setdefault(mode, {"status": "failed", "evidence": str(runtime.workspace)})["cleanup"] = {
                    **cleanup, "owned_resources_remaining": leftovers}
        report["status"] = "engineering_passed"
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Verification failed: {error}", file=sys.stderr, flush=True)
    finally:
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        json_file(evidence / "report.json", report)
    print(f"Report: {evidence / 'report.json'}", flush=True)
    return 0 if report["status"] == "engineering_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
