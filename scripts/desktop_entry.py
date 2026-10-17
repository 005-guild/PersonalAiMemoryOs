"""Windowed frozen entry point; application lifecycle lives in app.desktop."""

from app.desktop.launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
