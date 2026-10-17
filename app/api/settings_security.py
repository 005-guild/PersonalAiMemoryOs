"""Same-origin configuration editing for the loopback-only workbench."""

from secrets import compare_digest
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.datastructures import MutableHeaders


_LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1"}


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOOPBACK_NAMES
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or any(character.isspace() or ord(character) < 32 for character in value)):
        raise ValueError("Invalid configuration origin.")
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    if port < 1:
        raise ValueError("Invalid configuration origin.")
    return parsed.scheme, parsed.hostname, port


def configuration_guard(request: Request, *, csrf_token: str, mutation: bool = False) -> None:
    """Do not expose settings through DNS rebinding or cross-origin requests."""
    try:
        hosts = request.headers.getlist("host")
        origins = request.headers.getlist("origin")
        if len(hosts) != 1 or len(origins) > 1 or "/" in hosts[0]:
            raise ValueError()
        expected = _origin(f"{request.url.scheme}://{hosts[0]}")
        if request.headers.get("sec-fetch-site", "").strip().lower() == "cross-site":
            raise ValueError()
        if origins and _origin(origins[0]) != expected:
            raise ValueError()
        if mutation:
            tokens = request.headers.getlist("x-configuration-token")
            if not origins or len(tokens) != 1 or not csrf_token:
                raise ValueError()
            if not compare_digest(tokens[0].encode("utf-8"), csrf_token.encode("utf-8")):
                raise ValueError()
            if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(status_code=403, detail="configuration_access_denied") from None


class ConfigurationNoStoreMiddleware:
    """Keep setting metadata and session tokens out of HTTP caches, including errors."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope.get("type") != "http" or not any(path == prefix or path.startswith(prefix + "/")
                                                for prefix in ("/api/v1/settings", "/api/v1/desktop")):
            return await self.app(scope, receive, send)

        async def no_store(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Pragma"] = "no-cache"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        await self.app(scope, receive, no_store)
