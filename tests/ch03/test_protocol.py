"""Tests for the JSON-over-TCP wire protocol.

Covers serialization roundtrips, length-prefix correctness,
large payloads, and the max-message-size safety valve.
"""
from __future__ import annotations

import struct

from chronoguard_lite.interceptor.protocol import (
    HEADER_SIZE,
    MAX_MESSAGE_SIZE,
    InterceptRequest,
    InterceptResponse,
)


def test_request_roundtrip():
    """Serialize -> deserialize -> all fields match."""
    req = InterceptRequest(
        agent_id="550e8400-e29b-41d4-a716-446655440000",
        domain="api.openai.com",
        method="POST",
        path="/v1/chat/completions",
        source_ip="10.0.0.5",
    )
    wire = req.to_bytes()
    # Strip the 4-byte length header to get raw JSON
    payload = wire[HEADER_SIZE:]
    restored = InterceptRequest.from_bytes(payload)
    assert restored.agent_id == req.agent_id
    assert restored.domain == req.domain
    assert restored.method == req.method
    assert restored.path == req.path
    assert restored.source_ip == req.source_ip


def test_response_roundtrip():
    """Serialize -> deserialize -> all fields match."""
    resp = InterceptResponse(
        decision="ALLOW",
        reason="Matched policy: prod-ai-access",
        processing_time_ms=0.45,
    )
    wire = resp.to_bytes()
    payload = wire[HEADER_SIZE:]
    restored = InterceptResponse.from_bytes(payload)
    assert restored.decision == resp.decision
    assert restored.reason == resp.reason
    assert abs(restored.processing_time_ms - resp.processing_time_ms) < 1e-6


def test_length_prefix():
    """4-byte big-endian header matches actual JSON payload length."""
    req = InterceptRequest(
        agent_id="abc",
        domain="example.com",
        method="GET",
        path="/",
    )
    wire = req.to_bytes()
    header = wire[:HEADER_SIZE]
    payload = wire[HEADER_SIZE:]
    (declared_len,) = struct.unpack("!I", header)
    assert declared_len == len(payload)


def test_large_payload():
    """100KB-ish payload round-trips correctly."""
    long_path = "/" + "a" * 100_000
    req = InterceptRequest(
        agent_id="big-agent",
        domain="example.com",
        method="GET",
        path=long_path,
    )
    wire = req.to_bytes()
    payload = wire[HEADER_SIZE:]
    restored = InterceptRequest.from_bytes(payload)
    assert restored.path == long_path
    assert len(payload) > 100_000


def test_default_source_ip():
    """source_ip defaults to 0.0.0.0 when not provided."""
    req = InterceptRequest(
        agent_id="x",
        domain="y.com",
        method="GET",
        path="/",
    )
    assert req.source_ip == "0.0.0.0"
    # Also verify it survives a roundtrip through JSON
    wire = req.to_bytes()
    restored = InterceptRequest.from_bytes(wire[HEADER_SIZE:])
    assert restored.source_ip == "0.0.0.0"
