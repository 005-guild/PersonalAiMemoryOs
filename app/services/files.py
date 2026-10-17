"""Guarded Markdown file IO with optimistic checks and atomic commits.

Static symlinks and Windows reparse points are rejected. Revalidation narrows,
but does not eliminate, races with arbitrary editors between a check and replace.
"""

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from app.services.markdown import raw_hash


class FileSafetyError(RuntimeError):
    """A path could escape the real knowledge directory or is not a plain file."""


class FileChangedError(RuntimeError):
    """A file no longer matches the version checked by the caller."""


@dataclass(frozen=True)
class ScannedFile:
    path: str
    content: str
    hash: str


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _check_entry(path: Path, info: os.stat_result, *, directory: bool) -> None:
    if _is_link(info):
        raise FileSafetyError("Symbolic links and reparse points are not supported.")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode):
        raise FileSafetyError(f"Expected a regular {'directory' if directory else 'file'}: {path.name}")


def _real_root(root: Path) -> Path:
    path = Path(os.path.abspath(root))
    for ancestor in (*reversed(path.parents), path):
        _check_entry(ancestor, ancestor.lstat(), directory=True)
    return path


def _relative_parts(relative: str) -> list[str]:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise FileSafetyError("A plain relative POSIX path is required.")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts) or any(
        "\x00" in part or PureWindowsPath(part).is_reserved() for part in parts
    ):
        raise FileSafetyError("Unsafe relative path.")
    return parts


def safe_path(root: Path, relative: str) -> Path:
    """Validate root and every existing component without following links."""
    root_path = _real_root(root)
    parts = _relative_parts(relative)
    current = root_path
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        _check_entry(current, info, directory=index < len(parts) - 1)
    return current


def read_file(root: Path, relative: str) -> ScannedFile | None:
    """Read exact UTF-8 text; only a missing target is represented by None."""
    path = safe_path(root, relative)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        _real_root(root)
        return None
    with os.fdopen(descriptor, "rb") as stream:
        _check_entry(path, os.fstat(stream.fileno()), directory=False)
        safe_path(root, relative)
        content = stream.read().decode("utf-8")
    return ScannedFile(path=relative, content=content, hash=raw_hash(content))


def scan_files(root: Path) -> list[ScannedFile]:
    """Complete a deterministic scan or fail the whole round on any IO error."""
    root_path = _real_root(root)
    files = []

    def visit(directory: Path) -> None:
        _real_root(directory)
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            path = Path(entry.path)
            info = entry.stat(follow_symlinks=False)
            if _is_link(info):
                raise FileSafetyError("Symbolic links and reparse points are not supported.")
            if stat.S_ISDIR(info.st_mode):
                visit(path)
            elif stat.S_ISREG(info.st_mode):
                if path.suffix.lower() == ".md":
                    relative = path.relative_to(root_path).as_posix()
                    scanned = read_file(root_path, relative)
                    if scanned is None:
                        raise FileChangedError("A Markdown file disappeared during scanning.")
                    files.append(scanned)
            else:
                raise FileSafetyError("Only regular files and directories are supported.")

    visit(root_path)
    _real_root(root)
    return files


def _assert_expected(current: ScannedFile | None, expected_hash: str | None) -> None:
    if (current.hash if current is not None else None) != expected_hash:
        raise FileChangedError("The file changed after it was read.")


def _create_parents(root: Path, relative: str) -> None:
    current = _real_root(root)
    for part in _relative_parts(relative)[:-1]:
        current = current / part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        _check_entry(current, current.lstat(), directory=True)


def _cleanup_temporary(root: Path, path: Path, identity: os.stat_result) -> None:
    try:
        # Revalidate the parent chain before removing only the file we created.
        safe_path(root, path.relative_to(_real_root(root)).as_posix())
        current = path.lstat()
    except (FileNotFoundError, FileSafetyError):
        return
    if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
        path.unlink()


def atomic_write(
    root: Path, relative: str, content: str, expected_hash: str | None
) -> None:
    """Commit a checked replacement or exclusive creation using a sibling temp."""
    _assert_expected(read_file(root, relative), expected_hash)
    _create_parents(root, relative)
    target = safe_path(root, relative)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    identity = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        target = safe_path(root, relative)
        _assert_expected(read_file(root, relative), expected_hash)
        if expected_hash is None:
            try:
                os.link(temporary, target)
            except FileExistsError:
                raise FileChangedError("A file appeared before creation could commit.") from None
        else:
            os.replace(temporary, target)
    finally:
        _cleanup_temporary(root, temporary, identity)


def remove_file(root: Path, relative: str, expected_hash: str | None) -> None:
    """Remove the checked file; a missing expected target is a conflict."""
    current = read_file(root, relative)
    _assert_expected(current, expected_hash)
    if current is None:
        return
    target = safe_path(root, relative)
    try:
        target.unlink()
    except FileNotFoundError:
        raise FileChangedError("The file disappeared before removal could commit.") from None
