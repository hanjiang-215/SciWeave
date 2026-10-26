import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from email_service.ports import EmailServiceError
from email_service.registry_client import RegistryRecipientResolver


class _FakeSession:
    def __init__(self, result):
        self.result = result
        self.initialized = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def initialize(self):
        self.initialized = True

    async def call_tool(self, name, arguments):
        assert self.initialized
        assert name == "get_principal_contact"
        assert arguments == {"principal_id": "person:owner"}
        return self.result


class _FakeSessionContext:
    def __init__(self, result):
        self.result = result

    async def __aenter__(self):
        return ("read", "write", "session-id")

    async def __aexit__(self, *_):
        return False


class _FakeClientSessionFactory:
    def __init__(self, result):
        self.result = result

    def __call__(self, read, write):
        return _FakeSession(self.result)


def _run(coro):
    return asyncio.run(coro)


def _text_result(payload, *, is_error=False):
    return SimpleNamespace(
        isError=is_error,
        structuredContent=None,
        content=[SimpleNamespace(text=json.dumps(payload))],
    )


def test_registry_resolver_returns_contact_and_sends_bearer_token(monkeypatch):
    result = _text_result(
        {
            "principal_id": "person:owner",
            "contact_email": "owner@example.test",
            "status": "active",
            "contact_version": "contact:person:owner:1",
        }
    )
    monkeypatch.setattr("email_service.registry_client.ClientSession", _FakeClientSessionFactory(result))

    def streamable(url, *, http_client):
        assert url == "http://registry.test/mcp"
        assert http_client.headers["authorization"] == "Bearer registry-token"
        return _FakeSessionContext(result)

    monkeypatch.setattr("email_service.registry_client.streamable_http_client", streamable)
    resolver = RegistryRecipientResolver("http://registry.test/mcp", "registry-token", 1)

    assert _run(resolver.resolve("person:owner")) == "owner@example.test"


def test_registry_resolver_preserves_stable_registry_errors(monkeypatch):
    result = _text_result({"error": {"code": "contact_disabled"}}, is_error=True)
    monkeypatch.setattr("email_service.registry_client.ClientSession", _FakeClientSessionFactory(result))
    monkeypatch.setattr(
        "email_service.registry_client.streamable_http_client",
        lambda url, *, http_client: _FakeSessionContext(result),
    )
    resolver = RegistryRecipientResolver("http://registry.test/mcp", "registry-token", 1)

    with pytest.raises(EmailServiceError, match="contact_disabled"):
        _run(resolver.resolve("person:owner"))


def test_registry_resolver_maps_transport_failures_to_unavailable(monkeypatch):
    def streamable(url, *, http_client):
        raise TimeoutError("timed out")

    monkeypatch.setattr("email_service.registry_client.streamable_http_client", streamable)
    resolver = RegistryRecipientResolver("http://registry.test/mcp", "registry-token", 1)

    with pytest.raises(EmailServiceError, match="registry_unavailable"):
        _run(resolver.resolve("person:owner"))


@pytest.mark.parametrize(
    "status_code, expected",
    [(401, "registry_denied"), (403, "registry_denied"), (429, "registry_unavailable"), (503, "registry_unavailable")],
)
def test_registry_resolver_maps_http_status_errors(monkeypatch, status_code, expected):
    request = httpx.Request("POST", "http://registry.test/mcp")
    response = httpx.Response(status_code, request=request)

    def streamable(url, *, http_client):
        raise httpx.HTTPStatusError("registry response", request=request, response=response)

    monkeypatch.setattr("email_service.registry_client.streamable_http_client", streamable)
    resolver = RegistryRecipientResolver("http://registry.test/mcp", "registry-token", 1)

    with pytest.raises(EmailServiceError, match=expected):
        _run(resolver.resolve("person:owner"))


def test_registry_resolver_uses_temporary_streamable_http_mcp_server():
    import threading
    import time

    import uvicorn
    from mcp.server.fastmcp import FastMCP

    class _Server(uvicorn.Server):
        def install_signal_handlers(self):
            return

    server_app = FastMCP(
        name="temporary-registry",
        host="127.0.0.1",
        port=0,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @server_app.tool()
    def get_principal_contact(principal_id: str) -> dict[str, str]:
        return {
            "principal_id": principal_id,
            "contact_email": "owner@example.test",
            "status": "active",
            "contact_version": "contact:person:owner:1",
        }

    server = _Server(uvicorn.Config(server_app.streamable_http_app(), host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("temporary Registry MCP did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        resolver = RegistryRecipientResolver(f"http://127.0.0.1:{port}/mcp", "registry-token", 1)
        assert _run(resolver.resolve("person:owner")) == "owner@example.test"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
