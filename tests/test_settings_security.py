"""Configuration editing is limited to same-origin loopback requests with a token."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.settings_security import ConfigurationNoStoreMiddleware, configuration_guard


TOKEN = "synthetic-session-token"


@pytest.fixture
def guarded_client():
    app = FastAPI()
    app.add_middleware(ConfigurationNoStoreMiddleware)

    @app.api_route("/api/v1/settings/probe", methods=["GET", "PUT"])
    def probe(request: Request):
        configuration_guard(request, csrf_token=TOKEN, mutation=request.method == "PUT")
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok", "database": "ok"}

    with TestClient(app, base_url="http://127.0.0.1:18000") as client:
        yield client


@pytest.mark.parametrize("origin", ["http://127.0.0.1:18000", "http://localhost:8000", "http://[::1]:8300"])
def test_same_origin_write_with_session_token_is_accepted(guarded_client, origin):
    from urllib.parse import urlsplit
    response = guarded_client.put("/api/v1/settings/probe", json={}, headers={
        "Host": urlsplit(origin).netloc, "Origin": origin, "X-Configuration-Token": TOKEN,
    })
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers", [
    {}, {"Origin": "http://127.0.0.1:18000"},
    {"X-Configuration-Token": TOKEN},
    {"Origin": "null", "X-Configuration-Token": TOKEN},
    {"Origin": "https://evil.invalid", "X-Configuration-Token": TOKEN},
    {"Origin": "http://127.0.0.1:18001", "X-Configuration-Token": TOKEN},
    {"Origin": "http://localhost:18000", "X-Configuration-Token": TOKEN},
    {"Origin": "http://127.0.0.1:18000/path", "X-Configuration-Token": TOKEN},
    {"Origin": "http://name@127.0.0.1:18000", "X-Configuration-Token": TOKEN},
    {"Origin": "http://127.0.0.1:18000", "X-Configuration-Token": "wrong"},
    {"Origin": "http://127.0.0.1:18000", "X-Configuration-Token": TOKEN, "Sec-Fetch-Site": "cross-site"},
    {"Host": "evil.invalid", "Origin": "http://evil.invalid", "X-Configuration-Token": TOKEN},
    {"Host": "127.0.0.1/", "Origin": "http://127.0.0.1", "X-Configuration-Token": TOKEN},
    {"Host": "127.0.0.1:0", "Origin": "http://127.0.0.1:0", "X-Configuration-Token": TOKEN},
])
def test_invalid_origin_token_or_host_never_allows_configuration_write(guarded_client, headers):
    response = guarded_client.put("/api/v1/settings/probe", json={"value": "DO_NOT_ECHO_SECRET"}, headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "configuration_access_denied"}
    assert "DO_NOT_ECHO_SECRET" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_mutations_require_json_and_do_not_accept_query_tokens(guarded_client):
    origin = {"Origin": "http://127.0.0.1:18000", "X-Configuration-Token": TOKEN}
    assert guarded_client.put("/api/v1/settings/probe", content="{}", headers=origin).status_code == 403
    assert guarded_client.put("/api/v1/settings/probe?token=" + TOKEN, json={},
                              headers={"Origin": "http://127.0.0.1:18000"}).status_code == 403


@pytest.mark.parametrize("header,values", [
    ("Origin", ["http://127.0.0.1:18000", "https://evil.invalid"]),
    ("Host", ["127.0.0.1:18000", "evil.invalid"]),
    ("X-Configuration-Token", [TOKEN, TOKEN]),
])
def test_duplicate_security_headers_are_rejected(guarded_client, header, values):
    headers = [("Origin", "http://127.0.0.1:18000"), ("X-Configuration-Token", TOKEN)]
    headers = [(name, value) for name, value in headers if name.lower() != header.lower()]
    headers.extend((header, value) for value in values)
    assert guarded_client.put("/api/v1/settings/probe", json={}, headers=headers).status_code == 403


def test_configuration_reads_block_cross_origin_and_rebinding_and_errors_are_not_cached(guarded_client):
    assert guarded_client.get("/api/v1/settings/probe").status_code == 200
    for headers in ({"Host": "evil.invalid"}, {"Origin": "https://evil.invalid"}, {"Sec-Fetch-Site": "cross-site"}):
        response = guarded_client.get("/api/v1/settings/probe", headers=headers)
        assert response.status_code == 403 and response.headers["cache-control"] == "no-store"
    response = guarded_client.get("/api/v1/settings/missing")
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store"
    response = guarded_client.get("/health")
    assert response.json() == {"status": "ok", "database": "ok"}
    assert "cache-control" not in response.headers
