"""Tiny HTTP liveness endpoint for platforms that require a bound web port."""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("yorinetflix.health")


async def _handle_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Serve a minimal HTTP response without adding a web-framework dependency."""
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5)
        parts = request_line.decode("ascii", errors="replace").strip().split()
        # Consume headers, with a limit to avoid unbounded reads from clients.
        header_bytes = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            header_bytes += len(line)
            if not line or line in (b"\r\n", b"\n") or header_bytes > 8192:
                break

        if len(parts) >= 2 and parts[0] == "GET" and parts[1].split("?", 1)[0] in ("/", "/healthz"):
            status, body = "200 OK", b"ok\n"
        else:
            status, body = "404 Not Found", b"not found\n"

        writer.write(
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n".encode("ascii")
            + body
        )
        await writer.drain()
    except (asyncio.TimeoutError, ConnectionError):
        # Health probes and scanners may disconnect without sending a full request.
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


async def start_health_server(port: int | None = None) -> asyncio.AbstractServer:
    """Bind the platform-provided port on all interfaces and return the server."""
    if port is None:
        try:
            port = int(os.environ.get("PORT", "10000"))
        except ValueError as exc:
            raise ValueError("PORT must be an integer") from exc
    if not 0 <= port <= 65535:
        raise ValueError("PORT must be between 0 and 65535")

    server = await asyncio.start_server(_handle_request, host="0.0.0.0", port=port)
    bound_port = server.sockets[0].getsockname()[1] if server.sockets else port
    log.info("Health check server listening on 0.0.0.0:%d (/healthz)", bound_port)
    return server
