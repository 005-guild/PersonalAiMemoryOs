"""Prepare generated icon, Windows metadata and dependency license notices."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import struct
import sys


def icon_file(path: Path) -> None:
    """Rasterize the existing favicon's vector outline without an image dependency."""
    outline = [(9, 29), (9, 13), (14, 13), (14, 15)]

    def curve(first, second, end):
        start = outline[-1]
        for step in range(1, 21):
            t = step / 20
            outline.append(tuple((1-t)**3*start[i] + 3*(1-t)**2*t*first[i]
                                 + 3*(1-t)*t*t*second[i] + t**3*end[i] for i in (0, 1)))

    curve((16, 12), (20, 12), (22, 15))
    curve((26, 11), (31, 13), (31, 18))
    outline.extend([(31, 29), (26, 29), (26, 19)])
    curve((26, 16), (22, 16), (22, 19))
    outline.extend([(22, 29), (17, 29), (17, 19)])
    curve((17, 16), (14, 16), (14, 19))
    outline.append((14, 29))

    def in_letter(x, y):
        result = False
        last = outline[-1]
        for current in outline:
            if (current[1] > y) != (last[1] > y):
                crossing = (last[0]-current[0])*(y-current[1])/(last[1]-current[1])+current[0]
                if x < crossing:
                    result = not result
            last = current
        return result

    frames, entries = [], []
    offset = 6 + 16 * 5
    for size in (16, 32, 48, 128, 256):
        pixels = bytearray()
        for row in range(size - 1, -1, -1):
            for column in range(size):
                x, y = (column + .5) * 40 / size, (row + .5) * 40 / size
                distance = max(11-x, 0, x-29)**2 + max(11-y, 0, y-29)**2
                if distance > 121:
                    pixels.extend((0, 0, 0, 0))
                else:
                    pixels.extend((255, 255, 255, 255) if in_letter(x, y) else (220, 102, 52, 255))
        mask = bytes(((size + 31) // 32) * 4 * size)
        header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                             len(pixels) + len(mask), 0, 0, 0, 0)
        frame = header + pixels + mask
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(frame), offset))
        frames.append(frame)
        offset += len(frame)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(frames)) + b"".join(entries) + b"".join(frames))


def collect_licenses(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    notices = []
    for distribution in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = distribution.metadata["Name"]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        copied = []
        for file in distribution.files or []:
            normalized = str(file).replace("\\", "/")
            if any(word in file.name.lower() for word in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(file))
                if not source.is_file():
                    continue
                relative = Path(safe_name) / normalized.replace("../", "").replace(":", "_")
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                copied.append(relative.as_posix())
        notices.append({"name": name, "version": distribution.version,
                        "license": distribution.metadata.get("License-Expression")
                                   or distribution.metadata.get("License", "See package notices"),
                        "license_files": copied})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, destination / "Python-LICENSE.txt")
    (destination / "dependencies.json").write_text(json.dumps(notices, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "README.txt").write_text(
        "Third-party license texts are retained in package-named subdirectories.\n"
        "dependencies.json lists the isolated build environment, including build-only tools.\n"
        "Build-only tools are not application runtime modules.\n"
        "Browser assets retain their own license files under app/web/vendor.\n"
        "WebView2 and .NET Framework are separately installed Microsoft system components.\n", encoding="utf-8")


def windows_version(path: Path, version: str) -> None:
    numbers = tuple(int(number) for number in version.split(".")) + (0,)
    path.write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'Personal AI Memory OS'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'PersonalAiMemoryOs'),
    StringStruct('OriginalFilename', 'PersonalAiMemoryOs.exe'),
    StringStruct('ProductName', 'Personal AI Memory OS'),
    StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    icon_file(args.output / "desktop.ico")
    collect_licenses(args.output / "licenses")
    windows_version(args.output / "windows-version.txt", args.version)
