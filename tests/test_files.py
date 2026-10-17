"""Safety boundaries, complete scans, and optimistic atomic file operations."""

import os
import subprocess
from pathlib import Path

import pytest

from app.services import files
from app.services.files import (
    FileChangedError,
    FileSafetyError,
    atomic_write,
    read_file,
    remove_file,
    safe_path,
    scan_files,
)
from app.services.markdown import raw_hash


@pytest.fixture
def knowledge_root(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    return root


def test_scan_recurses_and_preserves_raw_utf8_content(knowledge_root: Path) -> None:
    (knowledge_root / "nested").mkdir()
    (knowledge_root / "nested" / "笔记.md").write_bytes("正文\r\n末尾".encode("utf-8"))
    (knowledge_root / "a.MD").write_text("first", encoding="utf-8")
    (knowledge_root / ".note.md.edit.tmp").write_text("unfinished", encoding="utf-8")
    (knowledge_root / "other.txt").write_text("ignored", encoding="utf-8")

    scanned = scan_files(knowledge_root)

    assert [item.path for item in scanned] == ["a.MD", "nested/笔记.md"]
    assert scanned[1].content == "正文\r\n末尾"
    assert scanned[1].hash == raw_hash("正文\r\n末尾")


@pytest.mark.parametrize(
    "relative",
    [
        "", ".", "..", "../outside.md", "nested/../note.md", "./note.md",
        "/outside.md", "C:/outside.md", "C:outside.md", "nested\\note.md",
        "nested//note.md", "note.md:alternate-stream", "nul.md", "bad\x00.md",
    ],
)
def test_unsafe_paths_are_rejected(knowledge_root: Path, relative: str) -> None:
    with pytest.raises(FileSafetyError):
        safe_path(knowledge_root, relative)


def test_missing_target_is_the_only_none_result(knowledge_root: Path) -> None:
    assert read_file(knowledge_root, "missing/note.md") is None
    (knowledge_root / "missing").mkdir()
    with pytest.raises(FileSafetyError):
        read_file(knowledge_root, "missing")


def test_missing_root_is_not_treated_as_an_empty_scan_or_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "not-created"
    with pytest.raises(FileNotFoundError):
        scan_files(root)
    with pytest.raises(FileNotFoundError):
        read_file(root, "note.md")
    assert not root.exists()


def test_scan_propagates_decode_errors(knowledge_root: Path) -> None:
    (knowledge_root / "bad.md").write_bytes(b"\xff\xfe")

    with pytest.raises(UnicodeDecodeError):
        scan_files(knowledge_root)


def test_scan_propagates_directory_errors(
    knowledge_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = knowledge_root / "blocked"
    blocked.mkdir()
    original_scandir = os.scandir

    def denied(path):
        if Path(path) == blocked:
            raise PermissionError("blocked directory")
        return original_scandir(path)

    monkeypatch.setattr(files.os, "scandir", denied)

    with pytest.raises(PermissionError):
        scan_files(knowledge_root)


def test_scan_does_not_silently_drop_a_disappearing_file(
    knowledge_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (knowledge_root / "note.md").write_text("old", encoding="utf-8")
    monkeypatch.setattr(files, "read_file", lambda *args: None)

    with pytest.raises(FileChangedError):
        scan_files(knowledge_root)


def _make_symlink(target: Path, link: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        pytest.skip(f"Symbolic link creation is unavailable: {type(exc).__name__}")


def test_symlink_parent_is_rejected_by_all_operations(
    knowledge_root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("external", encoding="utf-8")
    _make_symlink(outside, knowledge_root / "linked")

    for action in (
        lambda: safe_path(knowledge_root, "linked/note.md"),
        lambda: read_file(knowledge_root, "linked/note.md"),
        lambda: atomic_write(knowledge_root, "linked/new.md", "overwrite", None),
        lambda: remove_file(knowledge_root, "linked/note.md", raw_hash("external")),
        lambda: scan_files(knowledge_root),
    ):
        with pytest.raises(FileSafetyError):
            action()
    assert (outside / "note.md").read_text(encoding="utf-8") == "external"
    assert not (outside / "new.md").exists()


def test_symlink_root_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    link = tmp_path / "link"
    _make_symlink(real_root, link)

    with pytest.raises(FileSafetyError):
        scan_files(link)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_windows_junction_is_rejected(knowledge_root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("external", encoding="utf-8")
    junction = knowledge_root / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Junction creation is unavailable on this volume.")
    try:
        for action in (
            lambda: scan_files(knowledge_root),
            lambda: scan_files(junction),
            lambda: safe_path(knowledge_root, "junction/new.md"),
            lambda: read_file(knowledge_root, "junction/note.md"),
            lambda: atomic_write(knowledge_root, "junction/new.md", "new", None),
            lambda: remove_file(knowledge_root, "junction/note.md", raw_hash("external")),
        ):
            with pytest.raises(FileSafetyError):
                action()
        assert (outside / "note.md").read_text(encoding="utf-8") == "external"
        assert not (outside / "new.md").exists()
    finally:
        junction.rmdir()


def test_atomic_create_replace_and_delete(knowledge_root: Path) -> None:
    atomic_write(knowledge_root, "nested/note.md", "first\r\n", None)
    created = read_file(knowledge_root, "nested/note.md")
    assert created.content == "first\r\n"
    assert created.hash == raw_hash("first\r\n")

    atomic_write(knowledge_root, "nested/note.md", "second", created.hash)
    assert read_file(knowledge_root, "nested/note.md").content == "second"
    assert list((knowledge_root / "nested").glob("*.tmp")) == []

    remove_file(knowledge_root, "nested/note.md", raw_hash("second"))
    assert read_file(knowledge_root, "nested/note.md") is None
    remove_file(knowledge_root, "nested/note.md", None)


def test_stale_hash_never_overwrites_or_removes_a_file(knowledge_root: Path) -> None:
    (knowledge_root / "note.md").write_text("external", encoding="utf-8")

    for expected_hash in (None, raw_hash("stale")):
        with pytest.raises(FileChangedError):
            atomic_write(knowledge_root, "note.md", "new", expected_hash)
        with pytest.raises(FileChangedError):
            remove_file(knowledge_root, "note.md", expected_hash)

    assert read_file(knowledge_root, "note.md").content == "external"
    assert list(knowledge_root.glob("*.tmp")) == []


def test_missing_file_with_expected_hash_is_a_conflict(knowledge_root: Path) -> None:
    with pytest.raises(FileChangedError):
        atomic_write(knowledge_root, "note.md", "new", raw_hash("missing"))
    with pytest.raises(FileChangedError):
        remove_file(knowledge_root, "note.md", raw_hash("missing"))
    assert not (knowledge_root / "note.md").exists()


def test_atomic_create_does_not_overwrite_a_file_created_during_commit(
    knowledge_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_link = os.link

    def racing_link(source, target):
        Path(target).write_text("concurrent", encoding="utf-8")
        return original_link(source, target)

    monkeypatch.setattr(files.os, "link", racing_link)

    with pytest.raises(FileChangedError):
        atomic_write(knowledge_root, "note.md", "new", None)
    assert read_file(knowledge_root, "note.md").content == "concurrent"
    assert list(knowledge_root.glob("*.tmp")) == []


def test_atomic_replace_rechecks_content_after_preparing_temporary_file(
    knowledge_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = knowledge_root / "note.md"
    target.write_text("old", encoding="utf-8")
    original_fsync = os.fsync

    def racing_fsync(descriptor):
        original_fsync(descriptor)
        target.write_text("concurrent", encoding="utf-8")

    monkeypatch.setattr(files.os, "fsync", racing_fsync)

    with pytest.raises(FileChangedError):
        atomic_write(knowledge_root, "note.md", "new", raw_hash("old"))
    assert read_file(knowledge_root, "note.md").content == "concurrent"
    assert list(knowledge_root.glob("*.tmp")) == []


def test_replace_failure_cleans_only_its_own_temporary_file(
    knowledge_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (knowledge_root / "note.md").write_text("old", encoding="utf-8")
    unrelated = knowledge_root / ".unrelated.tmp"
    unrelated.write_text("keep", encoding="utf-8")

    def denied(*args):
        raise PermissionError("replace denied")

    monkeypatch.setattr(files.os, "replace", denied)

    with pytest.raises(PermissionError):
        atomic_write(knowledge_root, "note.md", "new", raw_hash("old"))
    assert read_file(knowledge_root, "note.md").content == "old"
    assert list(knowledge_root.glob("*.tmp")) == [unrelated]
