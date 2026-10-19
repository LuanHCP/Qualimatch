import asyncio
import io
import json
from contextlib import contextmanager
from datetime import datetime, timedelta

from starlette.requests import Request
from fastapi import FastAPI

import app as app_module
import qualimatch.auth as auth
from qualimatch.uploads import UploadTooLarge, read_upload_limited, save_upload_limited
from qualimatch.version import APP_VERSION
from qualimatch.manual_measurement_link import install_manual_measurement_frontend


class FakeUpload:
    def __init__(self, content: bytes):
        self.stream = io.BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


async def _asgi_get(path: str):
    sent_request = False
    messages = []

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    await app_module.app(scope, receive, send)
    status = next(x["status"] for x in messages if x["type"] == "http.response.start")
    body = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
    return status, body


def test_health_and_index_use_the_canonical_version():
    health_status, health_body = asyncio.run(_asgi_get("/api/health"))
    assert health_status == 200
    assert json.loads(health_body)["version"] == APP_VERSION

    index_status, index_body = asyncio.run(_asgi_get("/"))
    assert index_status == 200
    html = index_body.decode("utf-8")
    assert "__QUALIMATCH_VERSION__" not in html
    assert f"/static/app.js?v={APP_VERSION}" in html
    assert f"v{APP_VERSION}<br>Desenvolvido por Luan" in html


def test_launcher_frontend_route_uses_the_same_version():
    application = FastAPI()
    install_manual_measurement_frontend(application)
    route = application.router.routes[0]
    response = asyncio.run(route.endpoint(None))
    html = response.body.decode("utf-8")
    assert "__QUALIMATCH_VERSION__" not in html
    assert f"/static/app.js?v={APP_VERSION}" in html
    assert f"/static/manual_measurement_link.js?v={APP_VERSION}" in html


def test_protected_api_rejects_anonymous_request():
    status, body = asyncio.run(_asgi_get("/api/admin/users"))
    assert status == 401
    assert "autenticação necessária" in body.decode("utf-8")


def test_upload_read_and_stream_limits(tmp_path):
    assert asyncio.run(read_upload_limited(FakeUpload(b"1234"), 4, 2)) == b"1234"
    try:
        asyncio.run(read_upload_limited(FakeUpload(b"12345"), 4, 2))
    except UploadTooLarge:
        pass
    else:
        raise AssertionError("Upload acima do limite deveria ser rejeitado.")

    target = tmp_path / "upload.pdf"
    try:
        asyncio.run(save_upload_limited(FakeUpload(b"12345"), target, 4, 2))
    except UploadTooLarge:
        pass
    else:
        raise AssertionError("Upload acima do limite deveria ser rejeitado.")
    assert not target.exists()


def test_forwarded_ip_is_used_only_when_proxy_is_trusted(monkeypatch):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
        "client": ("10.0.0.5", 1234),
    }
    request = Request(scope)
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    assert app_module._client_ip(request) == "10.0.0.5"
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    assert app_module._client_ip(request) == "203.0.113.9"


def test_session_last_seen_is_throttled(monkeypatch):
    writes = []
    current = datetime.now().isoformat(timespec="seconds")

    monkeypatch.setattr(auth, "row", lambda *args, **kwargs: {"id": 1, "last_seen_at": current})

    @contextmanager
    def fake_transaction(path=None):
        class Connection:
            def execute(self, sql, params=()):
                writes.append((sql, params))

        yield Connection()

    monkeypatch.setattr(auth, "transaction", fake_transaction)
    assert auth.user_from_session("token")
    assert writes == []

    old = (datetime.now() - timedelta(minutes=6)).isoformat(timespec="seconds")
    monkeypatch.setattr(auth, "row", lambda *args, **kwargs: {"id": 1, "last_seen_at": old})
    assert auth.user_from_session("token")
    assert len(writes) == 1
