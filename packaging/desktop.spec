# -*- mode: python ; coding: utf-8 -*-
"""Windows x64 one-folder build. Execute through scripts/build_desktop.py."""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
assets = Path(os.environ["MEMORY_OS_DESKTOP_BUILD_ASSETS"])

datas = []
for directory in (root / "app" / "web", root / "app" / "prompts", root / "migrations"):
    for source in sorted(directory.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
            # Migration scripts intentionally remain real files for Alembic's loader.
            if directory.name == "web" and source.suffix == ".py":
                continue
            datas.append((str(source), str(source.relative_to(root).parent)))
for relative in ("alembic.ini", ".env.example", "config/ai-providers.example.yml",
                 "config/embedding-providers.example.yml", "config/local-rag-startup.example.json",
                 "scripts/start_local_rag.ps1"):
    source = root / relative
    datas.append((str(source), str(Path(relative).parent)))
datas += [(str(assets / "licenses"), "licenses"), (str(assets / "desktop.ico"), ".")]
datas += collect_data_files("webview", includes=["js/**", "lib/**"])
datas += collect_data_files("pythonnet")
for distribution in ("pywebview", "pythonnet", "clr_loader", "uvicorn"):
    datas += copy_metadata(distribution)

analysis = Analysis(
    [str(root / "scripts" / "desktop_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "webview.platforms.winforms", "webview.platforms.edgechromium", "clr", "pythonnet",
        "sqlalchemy.dialects.sqlite", "uvicorn.logging", "uvicorn.loops.asyncio",
        "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    ],
    excludes=[
        "playwright", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy",
        "gi", "cefpython3", "kivy", "webview.platforms.qt", "webview.platforms.gtk",
        "webview.platforms.cef", "webview.platforms.cocoa", "webview.platforms.android",
        "uvloop", "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True,
    name="PersonalAiMemoryOs", console=False, debug=False, strip=False, upx=False,
    icon=str(assets / "desktop.ico"),
    version=str(assets / "windows-version.txt"),
    uac_admin=False,
)
collection = COLLECT(
    exe, analysis.binaries, analysis.datas,
    strip=False, upx=False, name="PersonalAiMemoryOs",
)
