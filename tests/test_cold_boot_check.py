from copy import deepcopy

from scripts.cold_boot_check import compare


def test_same_boot_never_counts_as_cold_boot():
    assert compare({"boot_time": "one"}, {"boot_time": "one"})["status"] == "pending"


def test_new_boot_requires_services_and_original_ready_generation():
    before = {"boot_time": "one", "model_digest": "fixed", "index": {"generation": {"id": "same"}}}
    current = {"boot_time": "two", "model_digest": "fixed", "ollama": {"version": "test"},
        "qdrant": {"version": "test"}, "desktop_health": {"status": "ok"},
        "index": {"generation": {"id": "same", "status": "ready"}, "counts": {"failed": 0, "pending": 0}}}
    assert compare(before, current)["status"] == "services_checked"
    changed = deepcopy(current)
    changed["index"]["generation"]["id"] = "different"
    assert compare(before, changed)["status"] == "failed"
    changed = deepcopy(current)
    changed["errors"] = {"ollama": "error"}
    assert compare(before, changed)["status"] == "failed"
