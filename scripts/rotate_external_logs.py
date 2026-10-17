"""Explicit stopped-log rotation; never stops a desktop, helper or model server."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.paths import portable_path


def process_alive(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return True  # Unknown ownership is not permission to rotate.
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such PID
    try:
        return kernel.WaitForSingleObject(handle, 0) != 0
    finally:
        kernel.CloseHandle(handle)


def exclusively_available(path: Path) -> bool:
    if sys.platform != "win32":
        return True
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                  ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        return False
    kernel.CloseHandle(handle)
    return True


def rotate(root: Path, path: Path, *, active: bool, apply: bool, max_bytes=8 * 1024 * 1024, backups=3) -> dict:
    path = portable_path(root, path)
    if max_bytes < 1 or backups < 1:
        raise ValueError("Invalid log retention limits")
    archives = [portable_path(root, path.with_name(path.name + f".{i}")) for i in range(1, backups + 1)]
    row = {"path": path.relative_to(root).as_posix(), "status": "missing"}
    if not path.exists():
        return row
    if not path.is_file() or any(p.exists() and not p.is_file() for p in archives):
        raise ValueError("Log path is not an ordinary file")
    row["bytes"] = path.stat().st_size
    if row["bytes"] <= max_bytes:
        row["status"] = "within_limit"
    elif active or not exclusively_available(path):
        row["status"] = "skipped_active_or_locked"
    elif not apply:
        row["status"] = "would_rotate_when_applied"
    else:
        # Only these individually checked ordinary log files are changed.
        if archives[-1].exists():
            archives[-1].unlink()
        for index in range(backups - 1, 0, -1):
            if archives[index - 1].exists():
                archives[index - 1].rename(archives[index])
        path.rename(archives[0])
        path.touch(exist_ok=False)
        row["status"] = "rotated"
    return row


def recorded_active(record: Path) -> bool:
    if not record.exists():
        return True
    try:
        return process_alive(json.loads(record.read_text(encoding="utf-8-sig"))["pid"])
    except (OSError, ValueError, KeyError):
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Rotate only eligible logs; otherwise preview")
    args = parser.parse_args()
    portable = ROOT / "dist/PersonalAiMemoryOs-0.6.6"
    ollama_active = recorded_active(ROOT / ".cache/ollama/service.json")
    desktop_active = recorded_active(portable / ".cache/desktop/runtime.json")
    # A timed-out helper can outlive the app. Exclusive-open probing is also
    # mandatory, so a saved inactive desktop PID alone cannot authorize rotation.
    rows = [rotate(ROOT, ROOT / ".cache/ollama" / name, active=ollama_active, apply=args.apply)
            for name in ["server.stdout.log", "server.stderr.log"]]
    rows.append(rotate(ROOT, portable / "logs/local-rag-startup.log", active=desktop_active, apply=args.apply))
    output = ROOT / ".cache/storage-inventory/log-rotation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"mode": "apply" if args.apply else "preview", "max_bytes": 8388608, "archives": 3, "logs": rows,
              "services_stopped": 0, "model_calls": 0, "scope": "Stopped logs only; live external logs are not continuously capped"}
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
