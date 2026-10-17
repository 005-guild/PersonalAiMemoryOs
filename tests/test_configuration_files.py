"""Process-crash recovery and fail-closed portable configuration journals."""

import json

import pytest

from app.services import configuration_files as files


class SimulatedProcessCrash(BaseException):
    pass


@pytest.fixture
def pair(isolated_project):
    root = isolated_project
    (root / "config").mkdir()
    paths = [root / ".env", root / "config/ai.yml"]
    original = [b"OLD_ENV=synthetic\n", b"old: synthetic\n"]
    for path, value in zip(paths, original):
        path.write_bytes(value)
    return root, paths, original


def commit(pair):
    root, paths, original = pair
    files.write_configuration(root, dict(zip(paths, [b"NEW_ENV=synthetic\n", b"new: synthetic\n"])),
                              {path: files.digest(value) for path, value in zip(paths, original)})


def crash_after_first_replace(pair, monkeypatch):
    replace = files._replace
    called = 0
    def crashing(*args):
        nonlocal called
        replace(*args)
        called += 1
        if called == 1:
            raise SimulatedProcessCrash()
    with monkeypatch.context() as patch:
        patch.setattr(files, "_replace", crashing)
        with pytest.raises(SimulatedProcessCrash):
            commit(pair)
    return next((pair[0] / files.JOURNAL_DIRECTORY).iterdir())


def test_partial_failure_rolls_back_both_files(pair, monkeypatch):
    root, paths, original = pair
    replace = files._replace
    called = 0
    def failure(*args):
        nonlocal called
        called += 1
        if called == 2:
            raise PermissionError("synthetic-secret-not-for-response")
        replace(*args)
    monkeypatch.setattr(files, "_replace", failure)
    with pytest.raises(files.ConfigurationFileError) as error:
        commit(pair)
    assert "synthetic-secret" not in str(error.value)
    assert [path.read_bytes() for path in paths] == original
    assert not list((root / files.JOURNAL_DIRECTORY).iterdir())


def test_crash_recovers_before_configuration_is_loaded(pair, monkeypatch):
    root, paths, original = pair
    crash_after_first_replace(pair, monkeypatch)
    assert paths[0].read_bytes() != original[0]
    assert files.recover_ai_settings(root)
    assert [path.read_bytes() for path in paths] == original
    assert not files.recover_ai_settings(root)
    assert not list((root / files.JOURNAL_DIRECTORY).iterdir())


def test_manual_change_after_crash_is_not_overwritten(pair, monkeypatch):
    root, paths, _ = pair
    directory = crash_after_first_replace(pair, monkeypatch)
    paths[1].write_bytes(b"manual: later-change\n")
    before = [path.read_bytes() for path in paths]
    with pytest.raises(files.ConfigurationFileError, match="AI") as error:
        files.recover_ai_settings(root)
    assert error.value.code == "configuration_recovery_conflict"
    assert [path.read_bytes() for path in paths] == before
    assert directory.exists()


@pytest.mark.parametrize("attack", ["outside", "database", "oversized", "bad_hash", "missing_new"])
def test_corrupt_journal_fails_closed(pair, monkeypatch, attack):
    root, paths, _ = pair
    directory = crash_after_first_replace(pair, monkeypatch)
    manifest = directory / "manifest.json"
    data = json.loads(manifest.read_bytes())
    if attack == "outside":
        data["files"][1]["path"] = "../outside.yml"
    elif attack == "database":
        data["files"][1]["path"] = "data/accidental.yml"
    elif attack == "oversized":
        (directory / "old-0").write_bytes(b"x" * (files.MAX_FILE_BYTES + 1))
    elif attack == "bad_hash":
        data["files"][1]["after"] = None
    else:
        (directory / "new-1").unlink()
    manifest.write_text(json.dumps(data), encoding="utf-8")
    before = [path.read_bytes() for path in paths]
    with pytest.raises(files.ConfigurationFileError) as error:
        files.recover_ai_settings(root)
    assert error.value.code == "configuration_recovery_conflict"
    assert [path.read_bytes() for path in paths] == before
    assert directory.exists()


def test_committed_cleanup_can_resume_after_artifact_removal(pair, monkeypatch):
    root, paths, _ = pair
    with monkeypatch.context() as patch:
        def interrupted_cleanup(root, directory, entries=()):
            (directory / "old-0").unlink()
            raise SimulatedProcessCrash()
        patch.setattr(files, "_clean", interrupted_cleanup)
        with pytest.raises(SimulatedProcessCrash):
            commit(pair)
    assert not files.recover_ai_settings(root)
    assert paths[0].read_bytes().startswith(b"NEW_ENV")
    assert not list((root / files.JOURNAL_DIRECTORY).iterdir())


def test_external_change_rejects_before_staging(pair):
    root, paths, _ = pair
    paths[0].write_bytes(b"external")
    with pytest.raises(files.ConfigurationFileError) as error:
        commit(pair)
    assert error.value.code == "configuration_changed"
    assert not (root / files.JOURNAL_DIRECTORY).exists()
