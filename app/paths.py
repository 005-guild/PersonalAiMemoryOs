"""Read-only bundled resources and the independent persistent desktop root."""

import os
import stat
import sys
from pathlib import Path


def resource_root() -> Path:
    """PyInstaller preserves package-relative paths inside its resource folder."""
    return Path(__file__).resolve().parent.parent


def persistent_root() -> Path:
    """Portable state follows the executable, never the current working directory."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else resource_root()


def portable_path(root: Path, path: Path) -> Path:
    """Reject external paths and existing link/reparse entries before any IO."""
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("路径必须位于便携目录内。")
    for entry in (root, *[root.joinpath(*path.relative_to(root).parts[:n])
                         for n in range(1, len(path.relative_to(root).parts) + 1)]):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValueError("便携目录内不支持符号链接或目录联接。")
    return path
