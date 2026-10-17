"""Check browser JavaScript as ESM without installing a frontend build system."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "app" / "web"


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("Node.js is required only for this development check; add node to PATH.", file=sys.stderr)
        return 2
    files = sorted(path for path in WEB_ROOT.rglob("*") if path.suffix in {".js", ".mjs"})
    if not files:
        print("No browser JavaScript modules found.", file=sys.stderr)
        return 2
    failed = 0
    for path in files:
        # Filename-based --check can infer CommonJS from the enclosing directory.
        # Explicit ESM on stdin matches <script type="module"> in the browser.
        try:
            result = subprocess.run(
                [node, "--input-type=module", "--check"],
                input=path.read_text(encoding="utf-8"),
                text=True, encoding="utf-8", capture_output=True,
                cwd=PROJECT_ROOT, timeout=15, check=False,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
            failed += 1
            print(f"FAIL {path.relative_to(PROJECT_ROOT)}: {error}", file=sys.stderr)
            continue
        if result.returncode:
            failed += 1
            print(f"FAIL {path.relative_to(PROJECT_ROOT)}", file=sys.stderr)
            print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
    print(f"Checked {len(files)} browser modules (including vendor): {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
