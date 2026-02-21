"""Async version of the JSON-over-TCP protocol.

Same wire format as protocol.py (4-byte big-endian length prefix + JSON),
but uses asyncio.StreamReader/StreamWriter instead of raw sockets.

Why a separate module? The blocking socket calls in protocol.py
(sock.recv, sock.sendall) would block the event loop if called from
a coroutine. asyncio.StreamReader.readexactly() suspends the coroutine
and lets the event loop serve other connections while waiting for bytes.
The wire format is identical, so sync and async clients can talk to
either server.
"""
from __future__ import annotations

import asyncio
import struct

from chronoguard_lite.interceptor.protocol import HEADER_SIZE, MAX_MESSAGE_SIZE


async def async_read_message(reader: asyncio.StreamReader) -> bytes:
    """Read a length-prefixed message from an async stream.

    Same framing as the sync version:
        1. Read 4 bytes -> big-endian uint32 -> message length
        2. Validate length <= MAX_MESSAGE_SIZE
        3. Read exactly that many bytes -> payload

    Raises:
        asyncio.IncompleteReadError: if the stream closes mid-read
        ValueError: if message_length > MAX_MESSAGE_SIZE
    """
    header = await reader.readexactly(HEADER_SIZE)
    (msg_len,) = struct.unpack("!I", header)
    if msg_len > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message size {msg_len} exceeds limit {MAX_MESSAGE_SIZE}"
        )
    return await reader.readexactly(msg_len)


async def async_write_message(
    writer: asyncio.StreamWriter, payload: bytes
) -> None:
    """Write a length-prefixed message to an async stream.

    Packs header + payload and writes in one call. The await drain()
    applies backpressure: if the OS send buffer is full, the coroutine
    suspends instead of buffering unboundedly in userspace.
    """
    header = struct.pack("!I", len(payload))
    writer.write(header + payload)
    await writer.drain()
