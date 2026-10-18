"""Tests for the lightweight platform health-check listener."""

from __future__ import annotations

import asyncio

import pytest

from app.health import start_health_server


def test_health_endpoint_returns_ok():
    async def exercise() -> None:
        server = await start_health_server(port=0)
        try:
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()

            assert response.startswith(b"HTTP/1.1 200 OK\r\n")
            assert response.endswith(b"ok\n")
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_health_endpoint_returns_not_found_for_unknown_route():
    async def exercise() -> None:
        server = await start_health_server(port=0)
        try:
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /unknown HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()

            assert response.startswith(b"HTTP/1.1 404 Not Found\r\n")
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_invalid_port_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 65535"):
        asyncio.run(start_health_server(port=65536))
