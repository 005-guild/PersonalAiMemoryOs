"""Small Windows checks and native dialogs, without importing the GUI engine."""

import ctypes
import os
from pathlib import Path
import sys

TITLE = "Personal AI Memory OS"
WEBVIEW_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


class DesktopPlatformError(RuntimeError):
    pass


def prerequisites() -> None:
    if sys.platform != "win32" or sys.maxsize < 2**32:
        raise DesktopPlatformError("此便携版需要 Windows 10/11 64 位系统。")
    import winreg
    found = False
    key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                    version = str(winreg.QueryValueEx(handle, "pv")[0])
                    found |= any(int(part) > 0 for part in version.split("."))
            except (OSError, ValueError):
                pass
    if not found:
        raise DesktopPlatformError("未检测到 Microsoft Edge WebView2 运行库。\n请从微软官网安装后重试：\n" + WEBVIEW_URL)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as handle:
            release = int(winreg.QueryValueEx(handle, "Release")[0])
        if release < 528040:
            raise OSError()
    except (OSError, TypeError, ValueError):
        raise DesktopPlatformError("需要 .NET Framework 4.8 或更高版本，请通过 Windows 更新安装。") from None


def message(text: str, *, question: bool = False) -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    user32.MessageBoxW.restype = ctypes.c_int
    return user32.MessageBoxW(None, text, TITLE, 0x10000 | (0x21 if question else 0x10)) == 1


def open_directory(path: Path) -> None:
    os.startfile(str(path))
