"""Project-local CLI input, exact HTTP submission, durable reports and exits."""

from io import BytesIO
from http.client import IncompleteRead
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest

from scripts import import_zhihu


@pytest.fixture
def cli_root(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = isolated_project / "cli-project"
    root.mkdir()
    monkeypatch.setattr(import_zhihu, "PROJECT_ROOT", root)
    return root


def input_file(root: Path, payload: bytes | None = None) -> Path:
    path = root / "imports" / "batch.json"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(payload if payload is not None else b'{"schema_version":1,"items":[]}')
    return path


def response_report(**changes) -> dict:
    return {"dry_run": False, "total": 1, "processed": 1, "created": 1,
            "skipped": 0, "invalid": 0, "would_create": 0, "failed": 0,
            "items": [], **changes}


class Response:
    def __init__(self, report, status=200):
        self.report, self.status = report, status

    def read(self):
        return self.report if isinstance(self.report, bytes) else json.dumps(self.report).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def saved_report(root: Path) -> tuple[Path, dict]:
    reports = list((root / ".cache" / "import-reports").glob("*.json"))
    assert len(reports) == 1
    return reports[0], json.loads(reports[0].read_text(encoding="utf-8"))


def test_cli_submits_original_bom_bytes_and_saves_exact_report(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    payload = '\ufeff{"schema_version":1,"items":[],"演示":"原始文本"}'.encode("utf-8")
    path = input_file(cli_root, payload)
    report = response_report()
    observed = []

    def post(request, timeout):
        observed.append(request)
        assert timeout == 30
        return Response(report)

    monkeypatch.setattr(import_zhihu, "urlopen", post)

    assert import_zhihu.main(["--file", str(path)]) == 0

    request = observed[0]
    assert request.full_url == "http://127.0.0.1:18000/api/v1/imports/zhihu?dry_run=false"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.data == payload
    saved, content = saved_report(cli_root)
    assert content == report
    assert str(saved) in capsys.readouterr().out


def test_dry_run_uses_custom_base_url_and_project_relative_file_from_other_cwd(
    cli_root: Path, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_file(cli_root)
    monkeypatch.chdir(isolated_project)

    def post(request, timeout):
        assert request.full_url == "http://127.0.0.1:12345/api/v1/imports/zhihu?dry_run=true"
        return Response(response_report(dry_run=True, created=0, would_create=1))

    monkeypatch.setattr(import_zhihu, "urlopen", post)

    assert import_zhihu.main(["--file", "imports/batch.json", "--base-url", "http://127.0.0.1:12345/", "--dry-run"]) == 0
    assert saved_report(cli_root)[1]["would_create"] == 1


@pytest.mark.parametrize("counter", ["invalid", "failed"])
def test_partial_item_errors_have_nonzero_exit_and_preserve_report(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch, counter: str
) -> None:
    path = input_file(cli_root)
    report = response_report(created=0, **{counter: 1})
    monkeypatch.setattr(import_zhihu, "urlopen", lambda *args, **kwargs: Response(report))

    assert import_zhihu.main(["--file", str(path)]) != 0
    assert saved_report(cli_root)[1] == report


def test_skipped_differing_source_is_a_successful_import_attempt(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = input_file(cli_root)
    report = response_report(created=0, skipped=1, items=[{
        "index": 0, "status": "skipped", "reason": "skipped_different", "resource_type": "answer",
        "external_id": "123", "source_id": str(uuid4()), "version": 2,
        "differing_fields": ["title"], "matched_source_ids": [], "errors": [],
    }])
    monkeypatch.setattr(import_zhihu, "urlopen", lambda *args, **kwargs: Response(report))

    assert import_zhihu.main(["--file", str(path)]) == 0
    assert saved_report(cli_root)[1] == report


@pytest.mark.parametrize("status", [400, 413, 422, 503])
def test_http_errors_preserve_server_json_and_partial_report(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    path = input_file(cli_root)
    report = {"detail": "Request rejected."}
    if status == 503:
        report = {"detail": "Database temporarily unavailable.", "report": response_report(created=0, failed=1)}

    def rejected(request, timeout):
        raise HTTPError(request.full_url, status, "Rejected", {}, BytesIO(json.dumps(report).encode("utf-8")))

    monkeypatch.setattr(import_zhihu, "urlopen", rejected)

    assert import_zhihu.main(["--file", str(path)]) != 0
    assert saved_report(cli_root)[1] == report


def test_network_failure_saves_error_without_dumping_underlying_details(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    path = input_file(cli_root)

    def unavailable(*args, **kwargs):
        raise URLError("private-transport-error-sentinel")

    monkeypatch.setattr(import_zhihu, "urlopen", unavailable)

    assert import_zhihu.main(["--file", str(path)]) != 0
    report = saved_report(cli_root)[1]
    assert report["error"]["type"] == "RequestError"
    assert "private-transport-error-sentinel" not in json.dumps(report)
    assert "private-transport-error-sentinel" not in capsys.readouterr().err


def test_interrupted_http_response_creates_error_report(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = input_file(cli_root)

    def interrupted(*args, **kwargs):
        raise IncompleteRead(b"partial", 100)

    monkeypatch.setattr(import_zhihu, "urlopen", interrupted)

    assert import_zhihu.main(["--file", str(path)]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "RequestError"


@pytest.mark.parametrize(
    "payload", [b"\xff\xfe", b" " * (import_zhihu.MAX_FILE_BYTES + 1)],
    ids=["invalid-utf8", "over-10-mib"],
)
def test_invalid_encoding_or_oversized_file_is_reported_before_request(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    path = input_file(cli_root, payload)

    def unexpected_request(*args, **kwargs):
        pytest.fail("Unsafe input must not be submitted.")

    monkeypatch.setattr(import_zhihu, "urlopen", unexpected_request)

    assert import_zhihu.main(["--file", str(path)]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "InputError"


@pytest.mark.parametrize("kind", ["outside", "missing", "directory"])
def test_only_real_files_inside_project_are_accepted(
    cli_root: Path, isolated_project: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    if kind == "outside":
        path = isolated_project / "outside.json"
        path.write_text("{}", encoding="utf-8")
    elif kind == "missing":
        path = cli_root / "missing.json"
    else:
        path = cli_root

    def unexpected_request(*args, **kwargs):
        pytest.fail("Invalid input paths must not be submitted.")

    monkeypatch.setattr(import_zhihu, "urlopen", unexpected_request)

    assert import_zhihu.main(["--file", str(path)]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "InputError"


@pytest.mark.parametrize("base_url", ["file:///private", "http://", "http://localhost:bad", "http://user:secret@localhost", "http://localhost?query=x"])
def test_invalid_api_endpoint_is_reported(cli_root: Path, base_url: str) -> None:
    path = input_file(cli_root)

    assert import_zhihu.main(["--file", str(path), "--base-url", base_url]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "InputError"


@pytest.mark.parametrize("response", [b"<html>Bad gateway</html>", [], {}, {"dry_run": False, "items": []}])
def test_unexpected_server_response_still_creates_inspectable_report(
    cli_root: Path, monkeypatch: pytest.MonkeyPatch, response
) -> None:
    path = input_file(cli_root)
    monkeypatch.setattr(import_zhihu, "urlopen", lambda *args, **kwargs: Response(response))

    assert import_zhihu.main(["--file", str(path)]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "ResponseError"


def test_missing_required_argument_creates_error_report(cli_root: Path) -> None:
    assert import_zhihu.main([]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "InputError"


def test_invalid_path_text_creates_error_report(cli_root: Path) -> None:
    assert import_zhihu.main(["--file", "invalid\x00.json"]) != 0
    assert saved_report(cli_root)[1]["error"]["type"] == "InputError"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction path containment")
def test_linked_external_input_is_rejected(cli_root: Path, isolated_project: Path) -> None:
    outside = isolated_project / "outside"
    outside.mkdir()
    (outside / "batch.json").write_text("{}", encoding="utf-8")
    link = cli_root / "linked"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=False)
    if result.returncode:
        pytest.skip("Junction creation is unavailable on this volume.")
    try:
        assert import_zhihu.main(["--file", "linked/batch.json"]) != 0
        assert saved_report(cli_root)[1]["error"]["type"] == "InputError"
    finally:
        link.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction path containment")
def test_report_directory_cannot_write_outside_project(
    cli_root: Path, isolated_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = input_file(cli_root)
    outside = isolated_project / "outside-reports"
    outside.mkdir()
    link = cli_root / ".cache"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=False)
    if result.returncode:
        pytest.skip("Junction creation is unavailable on this volume.")
    monkeypatch.setattr(import_zhihu, "urlopen", lambda *args, **kwargs: Response(response_report()))
    try:
        assert import_zhihu.main(["--file", str(path)]) != 0
        assert list(outside.iterdir()) == []
    finally:
        link.rmdir()
