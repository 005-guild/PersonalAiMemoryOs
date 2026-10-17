"""Verified in-place update of the fixed, normally closed desktop installation."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.desktop.update import upgrade_portable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="Pristine, tested .cache build directory")
    parser.add_argument("--target", type=Path, default=ROOT / "dist/PersonalAiMemoryOs-0.6.6")
    parser.add_argument("--previous-archive", type=Path, default=ROOT / "dist/PersonalAiMemoryOs-0.6.6-windows-x64.zip")
    args = parser.parse_args()
    try:
        result = upgrade_portable(args.bundle.resolve(), args.target.resolve(), args.previous_archive)
    except Exception as error:
        print("升级停止（" + type(error).__name__ + "）。请检查目录、运行状态和备份清单。", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
