"""Tests for the lightweight platform health-check listener."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app import health
from app.health import start_health_server


async def _get(port: int, path: str) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode("ascii"))
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    return response


def test_health_endpoint_returns_json_ok():
    async def exercise() -> None:
        server = await start_health_server(port=0)
        try:
            port = server.sockets[0].getsockname()[1]
            response = await _get(port, "/healthz")
            headers, body = response.split(b"\r\n\r\n", maxsplit=1)

            assert response.startswith(b"HTTP/1.1 200 OK\r\n")
            assert b"Content-Type: application/json\r\n" in headers + b"\r\n"
            assert body == b'{"status":"ok"}'
            assert f"Content-Length: {len(body)}".encode("ascii") in headers
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_root_alias_also_returns_json_ok():
    async def exercise() -> None:
        server = await start_health_server(port=0)
        try:
            port = server.sockets[0].getsockname()[1]
            response = await _get(port, "/")
            assert response.startswith(b"HTTP/1.1 200 OK\r\n")
            assert response.endswith(b'{"status":"ok"}')
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_health_endpoint_returns_not_found_for_unknown_route():
    async def exercise() -> None:
        server = await start_health_server(port=0)
        try:
            port = server.sockets[0].getsockname()[1]
            response = await _get(port, "/unknown")
            assert response.startswith(b"HTTP/1.1 404 Not Found\r\n")
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_health_server_uses_port_environment_and_default(monkeypatch):
    async def exercise(port_env: str | None, expected_port: int) -> None:
        if port_env is None:
            monkeypatch.delenv("PORT", raising=False)
        else:
            monkeypatch.setenv("PORT", port_env)

        captured: dict[str, object] = {}

        async def fake_start_server(_handler, *, host: str, port: int):
            captured.update(host=host, port=port)
            return SimpleNamespace(sockets=[])

        monkeypatch.setattr(health.asyncio, "start_server", fake_start_server)
        await start_health_server()

        assert captured == {"host": "0.0.0.0", "port": expected_port}

    asyncio.run(exercise("12345", 12345))
    asyncio.run(exercise(None, 10000))


def test_invalid_port_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 65535"):
        asyncio.run(start_health_server(port=65536))


def test_invalid_port_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(ValueError, match="PORT must be an integer"):
        asyncio.run(start_health_server())
