import json
from pathlib import Path

import pytest

from scripts.prepare_quality_review import ROOT, validate_corpus
from scripts.storage_inventory import inventory, retention_class
from scripts.rotate_external_logs import rotate


def test_fixed_quality_labels_resolve_and_duplicate_cases_fail():
    document = json.loads((ROOT / "examples/quality/retrieval-cn.json").read_text(encoding="utf-8"))
    validate_corpus(document)
    document["queries"][0]["relevant"] = ["missing"]
    with pytest.raises(ValueError, match="label"):
        validate_corpus(document)


def test_inventory_counts_bytes_without_reading_or_deleting_contents(tmp_path, monkeypatch):
    folder = tmp_path / ".cache/ollama/models"
    folder.mkdir(parents=True)
    (folder / "weights").write_bytes(b"12345")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/personal.db").write_bytes(b"123")
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("Inventory read contents"))
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: pytest.fail("Inventory read secrets"))
    value = inventory(tmp_path)
    assert value["deleted_files"] == 0
    assert sum(row["bytes"] for row in value["rows"]) == 8
    assert all(row["category"].startswith("protected") for row in value["rows"])
    assert (folder / "weights").stat().st_size == 5


def test_unknown_cache_is_preserved_and_models_are_protected():
    assert retention_class(".cache/ollama")[0] == "protected_runtime"
    assert retention_class(".cache/unknown")[0] == "unclassified_keep"


def test_stopped_log_rotation_is_explicit_bounded_and_preserves_active_logs(tmp_path):
    log = tmp_path / "service.log"
    log.write_bytes(b"first contents")
    assert rotate(tmp_path, log, active=True, apply=True, max_bytes=4)["status"] == "skipped_active_or_locked"
    assert rotate(tmp_path, log, active=False, apply=False, max_bytes=4)["status"] == "would_rotate_when_applied"
    for index in range(4):
        log.write_bytes(f"round {index}".encode())
        assert rotate(tmp_path, log, active=False, apply=True, max_bytes=4, backups=2)["status"] == "rotated"
    assert log.read_bytes() == b""
    assert (tmp_path / "service.log.1").read_bytes() == b"round 3"
    assert (tmp_path / "service.log.2").read_bytes() == b"round 2"
    assert not (tmp_path / "service.log.3").exists()
    with pytest.raises(ValueError):
        rotate(tmp_path, tmp_path / "../outside.log", active=False, apply=True)


