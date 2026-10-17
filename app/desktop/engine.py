"""Configure EdgeChromium without broad JS bridges or weaker page CSP."""

import os
from pathlib import Path
import re
from uuid import uuid4

from app.paths import portable_path


def configure_engine(webview, root):
    testing = os.environ.get("MEMORY_OS_DESKTOP_TEST_MODE") == "1"
    # Do not inherit arbitrary browser flags or a redirected browser profile.
    for key in ("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "WEBVIEW2_BROWSER_EXECUTABLE_FOLDER",
                "WEBVIEW2_USER_DATA_FOLDER", "PYWEBVIEW_GUI", "PYWEBVIEW_LOG"):
        os.environ.pop(key, None)
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    webview.settings["REMOTE_DEBUGGING_PORT"] = None
    if testing:
        port = int(os.environ.get("MEMORY_OS_DESKTOP_DEBUG_PORT", "0"))
        if not 1024 <= port <= 65535:
            raise ValueError("Desktop test debugging port is invalid.")
        webview.settings["REMOTE_DEBUGGING_PORT"] = port
    return testing


def install_native_hooks(window, root: Path, testing: bool):
    """Use an explicit portable download directory and prevent main-view escapes."""
    from System import Action
    import System.Windows.Forms as Forms
    import webbrowser
    from urllib.parse import urlsplit

    root_url = urlsplit(window.get_current_url())
    origin = (root_url.scheme, root_url.netloc)
    exports = portable_path(root, root / "exports")
    exports.mkdir(exist_ok=True)

    def download(sender, args):
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(str(args.ResultFilePath)).name).strip(' .') or 'report.json'
        if testing:
            destination = portable_path(root, exports / name)
            if destination.exists():
                destination = destination.with_name(uuid4().hex[:8] + '-' + name)
            args.ResultFilePath = str(destination)
            args.Handled = True
            return
        dialog = Forms.SaveFileDialog()
        try:
            dialog.InitialDirectory = str(exports)
            dialog.FileName = name
            dialog.Filter = 'JSON 报告 (*.json)|*.json|所有文件 (*.*)|*.*'
            dialog.RestoreDirectory = True
            if dialog.ShowDialog(window.native) == Forms.DialogResult.OK:
                args.ResultFilePath = dialog.FileName
                args.Handled = True
            else:
                args.Cancel = True
        finally:
            dialog.Dispose()

    def navigate(sender, args):
        target = urlsplit(str(args.Uri))
        if (target.scheme, target.netloc) != origin:
            args.Cancel = True
            if target.scheme in {"http", "https", "mailto"}:
                webbrowser.open(str(args.Uri))

    def attach():
        browser = window.native.browser
        core = window.native.webview.CoreWebView2
        core.DownloadStarting -= browser.on_download_starting
        core.DownloadStarting += download
        core.NavigationStarting += navigate
    # Retain delegates for the full native window lifetime.
    window._memory_os_hooks = (download, navigate)
    window.native.Invoke(Action(attach))
