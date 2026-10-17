"""Workbench assets are local, reproducible and isolated from project data."""

import hashlib
import json
from pathlib import Path
import tomllib

import pytest

from app.web.routes import WEB_ROOT


def test_root_serves_packaged_chinese_shell_with_revalidation_and_csp(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    for policy in ("script-src 'self'", "connect-src 'self'", "object-src 'none'",
                   "base-uri 'none'", "frame-ancestors 'none'"):
        assert policy in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert '<html lang="zh-CN">' in response.text
    assert '<script type="module" src="/assets/js/app.js">' in response.text
    assert 'href="/assets/css/styles.css"' in response.text


@pytest.mark.parametrize("path", [
    "/.env", "/data/memory.db", "/knowledge/private.md", "/config/ai-providers.yml",
    "/app/main.py", "/assets/routes.py", "/assets/index.html", "/assets/js/",
    "/assets/js/%2e%2e%2f%2e%2e%2froutes.py", "/assets/vendor/%2e%2e%2f%2e%2e%2froutes.py",
])
def test_static_routes_do_not_publish_project_or_python_files(client, isolated_project, path):
    (isolated_project / ".env").write_text("PRIVATE_WEB_SENTINEL=secret", encoding="utf-8")
    response = client.get(path)
    assert response.status_code == 404
    assert "PRIVATE_WEB_SENTINEL" not in response.text
    assert "def install_web" not in response.text


@pytest.mark.parametrize("path,content_type", [
    ("/assets/js/app.js", "javascript"),
    ("/assets/js/ui.js", "javascript"),
    ("/assets/js/pages/editor.js", "javascript"),
    ("/assets/vendor/marked.js", "javascript"),
    ("/assets/vendor/purify.js", "javascript"),
    ("/assets/css/styles.css", "text/css"),
])
def test_packaged_assets_are_available_without_cdn(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200 and content_type in response.headers["content-type"]
    assert len(response.content) > 100
    assert "etag" in response.headers
    repeated = client.get(path, headers={"If-None-Match": response.headers["etag"]})
    assert repeated.status_code == 304


def test_vendored_renderer_and_sanitizer_match_recorded_checksums():
    manifest = json.loads((WEB_ROOT / "vendor" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["marked"] and manifest["dompurify"]
    assert {"marked.js", "marked.LICENSE", "purify.js", "DOMPurify.LICENSE"} == set(manifest["files"])
    for name, evidence in manifest["files"].items():
        path = WEB_ROOT / "vendor" / name
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"]
        assert evidence["source"].startswith("https://")


def test_ui_routes_preserve_health_docs_and_version_contract(client):
    project = Path(__file__).resolve().parents[1]
    version = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == version
    for path in ("/api/v1/knowledge", "/api/v1/sources", "/api/v1/ui/overview"):
        assert path in schema["paths"]
    assert f"v{version}" in client.get("/").text
