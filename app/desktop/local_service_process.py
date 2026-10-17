"""Launch trusted host tools without inheriting bundled DLL search paths."""

from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys


def powershell_path() -> Path:
    """Select Windows' own executable, never a PATH/configuration command."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel32.GetSystemDirectoryW
    function.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
    function.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32_768)
    length = function(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise OSError("Windows system directory unavailable.")
    result = Path(buffer.value) / "WindowsPowerShell/v1.0/powershell.exe"
    if not result.is_file():
        raise OSError("Windows PowerShell unavailable.")
    return result


def merge_local_proxy_bypass() -> None:
    """HTTPX in the desktop itself must bypass proxies for these services."""
    values = []
    for value in (os.environ.get("NO_PROXY", ""), os.environ.get("no_proxy", ""),
                  "localhost,127.0.0.1,::1"):
        for item in value.split(","):
            item = item.strip()
            if item and item.casefold() not in {entry.casefold() for entry in values}:
                values.append(item)
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(values)


def external_environment() -> dict[str, str]:
    """Host tools need proxies, not application credentials or bundled DLLs."""
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("MEMORY_OS_")}
    for name in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        if name + "_ORIG" in environment:
            environment[name] = environment[name + "_ORIG"]
        else:
            environment.pop(name, None)
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        directory = Path(bundled).resolve()
        entries = []
        for entry in environment.get("PATH", "").split(os.pathsep):
            try:
                belongs_to_bundle = bool(entry) and Path(entry.strip('"')).resolve().is_relative_to(directory)
            except (OSError, ValueError):
                belongs_to_bundle = False
            if not belongs_to_bundle:
                entries.append(entry)
        environment["PATH"] = os.pathsep.join(entries)
    return environment


@contextmanager
def host_dll_search():
    """PyInstaller modifies the process DLL directory; restore it after spawn."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_directory = kernel32.GetDllDirectoryW
    get_directory.argtypes = [ctypes.c_uint, ctypes.c_wchar_p]
    get_directory.restype = ctypes.c_uint
    set_directory = kernel32.SetDllDirectoryW
    set_directory.argtypes = [ctypes.c_wchar_p]
    set_directory.restype = ctypes.c_int
    buffer = ctypes.create_unicode_buffer(32_768)
    length = get_directory(len(buffer), buffer)
    if length >= len(buffer):
        raise OSError("DLL search directory unavailable.")
    previous = buffer.value if length else None
    if not set_directory(None):
        raise OSError("Cannot prepare host DLL search.")
    try:
        yield
    finally:
        if not set_directory(previous):
            raise OSError("Cannot restore bundled DLL search.")
