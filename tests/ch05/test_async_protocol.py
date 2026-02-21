"""Tests for async_protocol.py: async read/write message over streams."""
from __future__ import annotations

import asyncio
import struct

import pytest

from chronoguard_lite.interceptor.async_protocol import (
    async_read_message,
    async_write_message,
)
from chronoguard_lite.interceptor.protocol import (
    HEADER_SIZE,
    MAX_MESSAGE_SIZE,
    InterceptRequest,
    InterceptResponse,
)


async def _pipe() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Create an in-memory reader/writer pair via a loopback TCP connection."""
    ready = asyncio.Event()
    container: dict = {}

    async def on_connect(reader, writer):
        container["reader"] = reader
        container["writer"] = writer
        ready.set()

    server = await asyncio.start_server(on_connect, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client_reader, client_writer = await asyncio.open_connection("127.0.0.1", port)
    await ready.wait()

    # Return (client_reader receives from server_writer,
    #         server_reader receives from client_writer)
    # We'll use client_writer to send, container["reader"] to receive.
    return container["reader"], client_writer, client_reader, container["writer"], server


@pytest.mark.asyncio
async def test_roundtrip_request():
    """Send a request through async protocol, verify it arrives intact."""
    srv_reader, cli_writer, cli_reader, srv_writer, server = await _pipe()
    try:
        req = InterceptRequest(
            agent_id="abc-123",
            domain="api.openai.com",
            method="POST",
            path="/v1/chat",
            source_ip="10.0.0.1",
        )
        payload = req.to_bytes()[4:]  # strip length prefix, we'll add our own
        await async_write_message(cli_writer, payload)
        received = await async_read_message(srv_reader)
        parsed = InterceptRequest.from_bytes(received)
        assert parsed.agent_id == "abc-123"
        assert parsed.domain == "api.openai.com"
        assert parsed.method == "POST"
        assert parsed.path == "/v1/chat"
        assert parsed.source_ip == "10.0.0.1"
    finally:
        cli_writer.close()
        srv_writer.close()
        server.close()


@pytest.mark.asyncio
async def test_roundtrip_response():
    """Send a response through async protocol, verify it arrives intact."""
    srv_reader, cli_writer, cli_reader, srv_writer, server = await _pipe()
    try:
        resp = InterceptResponse(
            decision="ALLOW",
            reason="Matched policy: prod-ai",
            processing_time_ms=0.42,
        )
        payload = resp.to_bytes()[4:]
        await async_write_message(cli_writer, payload)
        received = await async_read_message(srv_reader)
        parsed = InterceptResponse.from_bytes(received)
        assert parsed.decision == "ALLOW"
        assert parsed.reason == "Matched policy: prod-ai"
        assert abs(parsed.processing_time_ms - 0.42) < 0.001
    finally:
        cli_writer.close()
        srv_writer.close()
        server.close()


@pytest.mark.asyncio
async def test_large_payload():
    """100 KB payload survives the async protocol round trip."""
    srv_reader, cli_writer, cli_reader, srv_writer, server = await _pipe()
    try:
        payload = b"x" * 100_000
        await async_write_message(cli_writer, payload)
        received = await async_read_message(srv_reader)
        assert received == payload
    finally:
        cli_writer.close()
        srv_writer.close()
        server.close()


@pytest.mark.asyncio
async def test_oversized_message_rejected():
    """Messages exceeding MAX_MESSAGE_SIZE raise ValueError."""
    srv_reader, cli_writer, cli_reader, srv_writer, server = await _pipe()
    try:
        # Write a header claiming 2 MB payload
        header = struct.pack("!I", MAX_MESSAGE_SIZE + 1)
        cli_writer.write(header)
        await cli_writer.drain()
        with pytest.raises(ValueError, match="exceeds limit"):
            await async_read_message(srv_reader)
    finally:
        cli_writer.close()
        srv_writer.close()
        server.close()


@pytest.mark.asyncio
async def test_incomplete_read_raises():
    """Closing the stream mid-message raises IncompleteReadError."""
    srv_reader, cli_writer, cli_reader, srv_writer, server = await _pipe()
    try:
        # Write only the header, then close
        header = struct.pack("!I", 100)
        cli_writer.write(header)
        await cli_writer.drain()
        cli_writer.close()
        await cli_writer.wait_closed()
        with pytest.raises(asyncio.IncompleteReadError):
            await async_read_message(srv_reader)
    finally:
        srv_writer.close()
        server.close()
