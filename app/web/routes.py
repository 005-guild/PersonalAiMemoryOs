"""Expose only packaged browser assets, never project data or configuration."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_ROOT = Path(__file__).resolve().parent


class WebAssets(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def install_web(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def workbench():
        return FileResponse(WEB_ROOT / "index.html", headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self'; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ),
        })

    # Explicit directories keep Python source and index headers out of the mount.
    for directory in ("js", "vendor", "css"):
        app.mount(f"/assets/{directory}", WebAssets(directory=WEB_ROOT / directory),
                  name=f"web-{directory}")
