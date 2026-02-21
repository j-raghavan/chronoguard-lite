"""Simple JSON-over-TCP protocol for agent requests.

Message format:
    4 bytes: message length (big-endian uint32)
    N bytes: JSON payload (UTF-8)

Request payload:
    {
        "agent_id": "uuid-string",
        "domain": "api.openai.com",
        "method": "GET",
        "path": "/v1/chat/completions",
        "source_ip": "10.0.0.5"
    }

Response payload:
    {
        "decision": "ALLOW" | "DENY" | "RATE_LIMITED" | "NO_MATCHING_POLICY",
        "reason": "Matched policy: production-ai-access, rule: allow-openai",
        "processing_time_ms": 0.45
    }

Why not HTTP? Because HTTP adds layers of abstraction that hide what
we want to teach: raw socket I/O, thread scheduling, and the GIL.
The wire protocol is intentionally minimal so that serialization cost
is negligible compared to the evaluation and audit-logging work.
"""
from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass


HEADER_SIZE = 4          # 4 bytes, big-endian uint32
MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MB safety limit


@dataclass(frozen=True, slots=True)
class InterceptRequest:
    """Deserialized agent request."""
    agent_id: str
    domain: str
    method: str
    path: str
    source_ip: str = "0.0.0.0"

    def to_bytes(self) -> bytes:
        """Serialize to wire format: 4-byte length prefix + JSON payload."""
        payload = json.dumps(
            {
                "agent_id": self.agent_id,
                "domain": self.domain,
                "method": self.method,
                "path": self.path,
                "source_ip": self.source_ip,
            },
            separators=(",", ":"),  # compact JSON, less wire bytes
        ).encode("utf-8")
        return struct.pack("!I", len(payload)) + payload

    @classmethod
    def from_bytes(cls, data: bytes) -> InterceptRequest:
        """Deserialize from JSON bytes (without length prefix)."""
        obj = json.loads(data.decode("utf-8"))
        return cls(
            agent_id=obj["agent_id"],
            domain=obj["domain"],
            method=obj["method"],
            path=obj["path"],
            source_ip=obj.get("source_ip", "0.0.0.0"),
        )


@dataclass(frozen=True, slots=True)
class InterceptResponse:
    """Serialized response back to the agent."""
    decision: str
    reason: str
    processing_time_ms: float

    def to_bytes(self) -> bytes:
        """Serialize to wire format: 4-byte length prefix + JSON payload."""
        payload = json.dumps(
            {
                "decision": self.decision,
                "reason": self.reason,
                "processing_time_ms": self.processing_time_ms,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        return struct.pack("!I", len(payload)) + payload

    @classmethod
    def from_bytes(cls, data: bytes) -> InterceptResponse:
        """Deserialize from JSON bytes (without length prefix)."""
        obj = json.loads(data.decode("utf-8"))
        return cls(
            decision=obj["decision"],
            reason=obj["reason"],
            processing_time_ms=obj["processing_time_ms"],
        )


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from a socket, or raise ConnectionError."""
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError(
                f"Socket closed with {remaining} bytes still expected"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_message(sock: socket.socket) -> bytes:
    """Read a length-prefixed message from a socket.

    Steps:
        1. Read exactly 4 bytes -> big-endian uint32 -> message length
        2. Validate length <= MAX_MESSAGE_SIZE
        3. Read exactly that many bytes -> payload
        4. Return the payload bytes (caller decides how to deserialize)

    Raises:
        ConnectionError: if the socket closes mid-read
        ValueError: if message_length > MAX_MESSAGE_SIZE
    """
    header = _recv_exactly(sock, HEADER_SIZE)
    (msg_len,) = struct.unpack("!I", header)
    if msg_len > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message size {msg_len} exceeds limit {MAX_MESSAGE_SIZE}"
        )
    return _recv_exactly(sock, msg_len)


def write_message(sock: socket.socket, payload: bytes) -> None:
    """Write a length-prefixed message to a socket.

    Packs len(payload) as big-endian uint32, then sends header + payload
    in one sendall call so the OS can coalesce into a single TCP segment.
    """
    header = struct.pack("!I", len(payload))
    sock.sendall(header + payload)
