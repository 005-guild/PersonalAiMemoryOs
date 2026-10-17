"""Windowed portable entry point. No Docker, CLI installation or browser tab."""

import logging
import multiprocessing
import os
from pathlib import Path
import sys

from app.desktop.bootstrap import DesktopStorageError, prepare_desktop
from app.desktop.instance import SingleInstance
from app.desktop.logging import configure_logging
from app.desktop.platform import DesktopPlatformError, TITLE, message, open_directory, prerequisites
from app.paths import persistent_root, portable_path, resource_root
from app.config import resolve_database_url


def open_ai_settings(window) -> None:
    """Use the existing dirty-aware router rather than reloading the workbench."""
    try:
        window.evaluate_js("window.location.hash = '#/settings'; void 0;")
    except Exception as error:
        logging.getLogger(__name__).warning("Settings navigation unavailable (%s).", type(error).__name__)
        message("工作台尚未加载完成，请稍后再次打开设置。")


def main() -> int:
    multiprocessing.freeze_support()
    root = persistent_root() if getattr(sys, "frozen", False) else resource_root() / ".cache/desktop-dev"
    instance, backend, controller, failure = None, None, None, None
    try:
        from app.desktop.restart import WAIT_FLAG, wait_for_restart
        if len(sys.argv) > 1 and sys.argv[1] == WAIT_FLAG:
            wait_for_restart(root, sys.argv[1:])
        prerequisites()
        if not getattr(sys, "frozen", False):
            root.mkdir(parents=True, exist_ok=True)
        portable_path(root, root)
        instance = SingleInstance(root)
        if not instance.owner:
            instance.activate()
            return 0
        redaction = configure_logging(root)
        settings = prepare_desktop(root, lambda prompt: message(prompt, question=True))
        redaction.secrets = tuple(secret.get_secret_value() for secret in settings.ai_keys.values() if secret.get_secret_value())
        cache = portable_path(root, root / ".cache/desktop")
        temp = portable_path(root, cache / "tmp")
        profile = portable_path(root, cache / "webview")
        temp.mkdir(parents=True, exist_ok=True)
        profile.mkdir(exist_ok=True)
        os.environ.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), PYTHONNET_RUNTIME="netfx")

        import webview
        from webview.menu import Menu, MenuAction, MenuSeparator
        from app.desktop.engine import configure_engine, install_native_hooks
        from app.desktop.server import DesktopServer
        from app.desktop.window import DesktopWindow

        testing = configure_engine(webview, root)
        backend = DesktopServer(settings)
        backend.start()
        controller = DesktopWindow(root, backend)
        from app.desktop.restart import DesktopRestarter
        if getattr(sys, "frozen", False):
            backend.app.state.desktop_restarter = DesktopRestarter(root, controller)
        window = webview.create_window(TITLE, backend.url, width=1280, height=900,
            min_size=(960, 640), text_select=True, zoomable=True, background_color="#f5f7fb")
        controller.window = window
        window.events.closing += controller.closing
        hook_installed = False

        def loaded():
            nonlocal hook_installed
            if not hook_installed:
                install_native_hooks(window, root, testing)
                hook_installed = True

        window.events.loaded += loaded
        menu = [Menu("设置", [
            MenuAction("AI 接口设置", lambda: open_ai_settings(window)),
            MenuAction("打开配置目录", lambda: open_directory(settings.ai_config_path.parent)),
        ]), Menu("工作空间", [
            MenuAction("打开数据目录", lambda: open_directory(Path(resolve_database_url(settings.database_url).database).parent)),
            MenuAction("打开知识目录", lambda: open_directory(settings.knowledge_path)),
            MenuAction("打开配置目录", lambda: open_directory(settings.ai_config_path.parent)),
            MenuAction("查看日志", lambda: open_directory(root / "logs")),
            MenuSeparator(), MenuAction("退出", lambda: window.destroy()),
        ])]
        instance.watch(controller.activate)
        controller.state("running")
        logging.getLogger(__name__).info("Portable desktop started.")
        webview.start(gui="edgechromium", debug=False, private_mode=False,
            storage_path=str(profile), menu=menu,
            icon=str(resource_root() / "desktop.ico") if (resource_root() / "desktop.ico").exists() else None)
    except (DesktopPlatformError, DesktopStorageError) as error:
        failure = str(error)
    except PermissionError:
        failure = "便携目录不可写，请将整个程序文件夹移动到具有写入权限的本地目录后重试。"
    except Exception as error:
        logging.getLogger(__name__).error("Desktop startup failed (%s).", type(error).__name__)
        failure = "桌面程序启动失败（" + type(error).__name__ + "），请检查完整解压目录和运行环境。"
    finally:
        if backend is not None:
            backend.stop()
        if controller is not None:
            controller.state("stopped")
        if instance is not None:
            instance.close()
    if failure:
        message(failure + "\n\n日志位置：" + str(root / "logs/memory-os.log"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
