"""Submit a project-local JSON batch to the Zhihu import API using the stdlib."""

from __future__ import annotations

import argparse
from http.client import HTTPException
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 10 * 1024 * 1024
DEFAULT_BASE_URL = "http://127.0.0.1:18000"
COUNTERS = ("total", "processed", "created", "skipped", "invalid", "would_create", "failed")


class InputError(ValueError):
    """The command or its local input cannot be submitted safely."""


class RequestError(RuntimeError):
    """The import service could not be reached."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="JSON file inside the project; relative paths use the project root.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Import API origin (default: %(default)s).")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without creating Sources.")
    return parser.parse_args(argv)


def _read_input(filename: str) -> bytes:
    root = PROJECT_ROOT.resolve()
    candidate = Path(filename)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise InputError("--file must refer to a regular file inside the project.")
        with candidate.open("rb") as source:
            payload = source.read(MAX_FILE_BYTES + 1)
    except InputError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise InputError(f"Cannot read the import file ({type(exc).__name__}).") from None
    if len(payload) > MAX_FILE_BYTES:
        raise InputError("The import file exceeds the 10 MiB limit.")
    try:
        payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("The import file must use UTF-8 encoding; a UTF-8 BOM is allowed.") from None
    return payload


def _endpoint(base_url: str, dry_run: bool) -> str:
    try:
        parsed = urlsplit(base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError
        parsed.port  # Validate a supplied port without printing its input.
    except ValueError:
        raise InputError("--base-url must be an HTTP(S) URL without credentials, query, or fragment.") from None
    path = parsed.path.rstrip("/") + "/api/v1/imports/zhihu"
    return urlunsplit((parsed.scheme, parsed.netloc, path, f"dry_run={str(dry_run).lower()}", ""))


def _post(endpoint: str, payload: bytes) -> tuple[int, dict]:
    request = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            status, raw = response.status, response.read()
    except HTTPError as exc:
        try:
            status, raw = exc.code, exc.read()
        finally:
            exc.close()
    except (URLError, OSError, ValueError, HTTPException) as exc:
        raise RequestError(f"Cannot reach the import service ({type(exc).__name__}).") from None
    try:
        result = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {
            "error": {"type": "ResponseError", "message": "The server returned a non-JSON response."},
            "http_status": status,
            "response_text": raw.decode("utf-8", errors="replace"),
        }
    if not isinstance(result, dict):
        return status, {
            "error": {"type": "ResponseError", "message": "The server returned an unexpected response shape."},
            "http_status": status, "response": result,
        }
    if status == 200 and not (
        type(result.get("dry_run")) is bool
        and all(type(result.get(key)) is int and result[key] >= 0 for key in COUNTERS)
        and isinstance(result.get("items"), list)
    ):
        return status, {
            "error": {"type": "ResponseError", "message": "The import report is incomplete."},
            "http_status": status, "response": result,
        }
    return status, result


def _save_report(report: dict) -> Path:
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    root = PROJECT_ROOT.resolve()
    directory = root / ".cache" / "import-reports"
    if not directory.resolve().is_relative_to(root):
        raise InputError("The report directory must remain inside the project.")
    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve()
    if not directory.is_relative_to(root):
        raise InputError("The report directory must remain inside the project.")
    path = directory / f"{uuid4()}.json"
    with path.open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(serialized)
    return path


def main(argv: list[str] | None = None) -> int:
    status = None
    try:
        arguments = _arguments(argv)
        payload = _read_input(arguments.file)
        status, report = _post(_endpoint(arguments.base_url, arguments.dry_run), payload)
    except (InputError, RequestError) as exc:
        report = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    try:
        saved = _save_report(report)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Cannot save the import report ({type(exc).__name__}).", file=sys.stderr)
        return 1

    print(f"Report: {saved}")
    summary = report.get("report", report)
    if isinstance(summary, dict) and all(type(summary.get(key)) is int for key in COUNTERS):
        print(" ".join(f"{key}={summary[key]}" for key in COUNTERS))
    if "error" in report:
        error = report["error"]
        message = error.get("message") if isinstance(error, dict) else None
        print(message or "Import failed; inspect the saved report.", file=sys.stderr)
        return 1
    if status != 200:
        print(f"Import request failed (HTTP {status}).", file=sys.stderr)
        return 1
    return 1 if report["invalid"] or report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
