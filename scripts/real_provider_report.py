"""Non-secret evidence and a durable, bounded ledger for live acceptance."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

MAX_CALLS = 3


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict | list) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def new_workspace(project_root: Path) -> Path:
    root = project_root.resolve()
    cache = root / ".cache" / "real-provider-validation"
    if not cache.resolve().is_relative_to(root):
        raise ValueError("Acceptance evidence must remain inside the project.")
    cache.mkdir(parents=True, exist_ok=True)
    workspace = cache / uuid4().hex
    workspace.mkdir()
    return workspace


def storage_fingerprint(project_root: Path) -> dict[str, str]:
    root = project_root.resolve()
    files = [root / "data/memory.db", *sorted((root / "knowledge").rglob("*"))]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if p.is_file()}


class LiveBudgetGuard:
    """A new CLI invocation must not retry an earlier possibly charged request."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.lock = workspace.parent / ".live.lock"
        self.owned = False

    def acquire(self) -> None:
        try:
            descriptor = os.open(self.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise RuntimeError("A live acceptance execution requires review before starting another.") from None
        self.owned = True
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"owner": self.workspace.name}, handle)
            for path in self.workspace.parent.glob("*/report.json"):
                if path.parent == self.workspace:
                    continue
                with path.open("rb") as report:
                    raw = report.read(2_000_001)
                if len(raw) > 2_000_000 or json.loads(raw).get("attempts"):
                    raise RuntimeError("Earlier live-call intents require review; do not automatically retry.")
        except Exception:
            self.release()
            raise

    def release(self) -> None:
        if self.owned:
            owner = json.loads(self.lock.read_text(encoding="utf-8"))
            if owner.get("owner") != self.workspace.name:
                raise RuntimeError("The live acceptance lock changed ownership.")
            self.lock.unlink()
            self.owned = False


class Evidence:
    def __init__(self, workspace: Path, profile: dict, formal_before: dict,
                 secrets: tuple[str, ...] = ()) -> None:
        self.workspace = workspace
        self._secrets = tuple(secret for secret in secrets if secret)
        self.path = workspace / "report.json"
        self.data = {
            "schema_version": 1, "created_at": timestamp(), "status": "prepared",
            "profile": profile, "max_model_calls": MAX_CALLS, "attempts": [],
            "cases": [], "formal_before": formal_before, "quality_accepted": False,
        }
        self.save()

    def save(self) -> None:
        self.artifact(self.path.name, self.data)

    def artifact(self, filename: str, value: dict | list) -> None:
        path = self.workspace / filename
        if path.parent != self.workspace or path.name != filename:
            raise ValueError("Evidence files must remain inside the acceptance directory.")

        def redact(item):
            if isinstance(item, str):
                for secret in self._secrets:
                    item = item.replace(secret, "[REDACTED]")
                return item
            if isinstance(item, dict):
                return {redact(key): redact(nested) for key, nested in item.items()}
            if isinstance(item, list):
                return [redact(nested) for nested in item]
            return item

        write_json(path, redact(value))

    def reserve(self, case_id: str, environment: str, source_id: str) -> None:
        if len(self.data["attempts"]) >= MAX_CALLS:
            raise RuntimeError("The three-call acceptance budget is exhausted.")
        self.data["attempts"].append({
            "case_id": case_id, "environment": environment, "source_id": source_id,
            "reserved_at": timestamp(), "status": "outcome_unknown",
        })
        # Persist intent BEFORE sending: a timeout or disconnect consumes a call.
        self.save()

    def generation_result(self, status: int, body: dict) -> None:
        attempt = self.data["attempts"][-1]
        attempt["http_status"] = status
        attempt["status"] = "ready" if status == 201 else "failed"
        if status == 201:
            attempt["run_id"] = body.get("id")
            attempt["usage"] = body.get("usage")
        else:
            detail = body.get("detail")
            if isinstance(detail, dict):
                attempt["run_id"] = detail.get("run_id")
                attempt["error_code"] = detail.get("code")
        self.save()

    def quality_template(self, cases: list[dict]) -> None:
        self.artifact("quality-review.json", {
            "schema_version": 1, "reviewed_by": "", "reviewed_at": None,
            "cases": [{"id": case["id"], "review_focus": case["review_focus"],
                       "summary_faithful": None, "category_appropriate": None,
                       "viewpoints_grounded": None, "analysis_separated": None,
                       "instructions_treated_as_data": None, "passed": None, "notes": ""}
                      for case in cases],
            "all_passed": False,
        })
