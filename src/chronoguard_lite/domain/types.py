"""Shared type aliases and constants used across the domain."""
from __future__ import annotations

from typing import TypeAlias
from uuid import UUID

AgentId: TypeAlias = UUID
PolicyId: TypeAlias = UUID
EntryId: TypeAlias = UUID
DomainName: TypeAlias = str
Timestamp: TypeAlias = float  # Unix epoch seconds
