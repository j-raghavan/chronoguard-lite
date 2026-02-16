"""Domain model for chronoguard-lite.

Re-exports all public types for convenient access:
    from chronoguard_lite.domain import Agent, Policy, AuditEntry, AccessDecision
"""
from chronoguard_lite.domain.agent import (
    Agent,
    AgentDataclass,
    AgentSlots,
    AgentStatus,
    InvalidTransition,
    VALID_TRANSITIONS,
)
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
    RateLimit,
    RuleAction,
    TimeWindow,
)
from chronoguard_lite.domain.types import (
    AgentId,
    DomainName,
    EntryId,
    PolicyId,
    Timestamp,
)

__all__ = [
    "Agent",
    "AgentDataclass",
    "AgentSlots",
    "AgentStatus",
    "InvalidTransition",
    "VALID_TRANSITIONS",
    "AuditEntry",
    "AccessDecision",
    "Policy",
    "PolicyRule",
    "PolicyStatus",
    "RateLimit",
    "RuleAction",
    "TimeWindow",
    "AgentId",
    "DomainName",
    "EntryId",
    "PolicyId",
    "Timestamp",
]
