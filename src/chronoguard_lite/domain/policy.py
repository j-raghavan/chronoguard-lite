"""Policy entity — access control rules for agents.

A policy contains:
  - A list of PolicyRule objects (domain allow/deny rules)
  - Optional TimeWindow restrictions (business hours only, etc.)
  - Optional RateLimit (requests per minute/hour/day)
  - Priority for evaluation ordering

Mapped from full ChronoGuard: domain/policy/entity.py
Simplified: no Pydantic, no multi-tenancy, no RuleCondition operators.
Domain matching is exact or wildcard (*.domain.com) only.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum, auto

from chronoguard_lite.domain.types import PolicyId


class PolicyStatus(Enum):
    DRAFT = auto()
    ACTIVE = auto()
    SUSPENDED = auto()
    ARCHIVED = auto()


class RuleAction(Enum):
    ALLOW = auto()
    DENY = auto()


@dataclass(slots=True)
class TimeWindow:
    """Time-of-day restriction. All times in UTC."""
    start_time: time       # e.g., time(9, 0) for 9 AM
    end_time: time         # e.g., time(17, 0) for 5 PM
    days_of_week: set[int]  # 0=Monday, 6=Sunday

    def contains(self, dt: datetime) -> bool:
        """Check if a datetime falls within this window.

        Handle overnight windows where start_time > end_time.
        Example: start=22:00, end=06:00 means "10 PM to 6 AM".
        """
        if dt.weekday() not in self.days_of_week:
            return False
        t = dt.time()
        if self.start_time <= self.end_time:
            # Normal window: e.g., 09:00 - 17:00
            return self.start_time <= t <= self.end_time
        else:
            # Overnight window: e.g., 22:00 - 06:00
            return t >= self.start_time or t <= self.end_time


@dataclass(slots=True)
class RateLimit:
    """Rate limiting configuration."""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_limit: int = 10

    def __post_init__(self) -> None:
        """Validate: per_minute <= per_hour <= per_day, all positive."""
        if not (0 < self.requests_per_minute <= self.requests_per_hour <= self.requests_per_day):
            raise ValueError(
                "Rate limits must satisfy: 0 < per_minute <= per_hour <= per_day"
            )
        if self.burst_limit < 1 or self.burst_limit > 1000:
            raise ValueError("burst_limit must be between 1 and 1000")


@dataclass(slots=True)
class PolicyRule:
    """A single rule within a policy.

    domain_pattern supports:
      - Exact match: "api.openai.com"
      - Wildcard prefix: "*.openai.com" (matches any subdomain)
      - Wildcard segment: "api.*.internal" (matches any middle segment)
    """
    rule_id: uuid.UUID
    domain_pattern: str
    action: RuleAction
    priority: int = 100      # Lower number = higher priority (1-1000)

    @classmethod
    def allow(cls, domain_pattern: str, priority: int = 100) -> PolicyRule:
        """Factory: create an ALLOW rule."""
        return cls(
            rule_id=uuid.uuid4(),
            domain_pattern=domain_pattern,
            action=RuleAction.ALLOW,
            priority=priority,
        )

    @classmethod
    def deny(cls, domain_pattern: str, priority: int = 100) -> PolicyRule:
        """Factory: create a DENY rule."""
        return cls(
            rule_id=uuid.uuid4(),
            domain_pattern=domain_pattern,
            action=RuleAction.DENY,
            priority=priority,
        )

    def matches(self, domain: str) -> bool:
        """Check if domain matches this rule's pattern.

        Matching rules:
          - "api.openai.com" matches only "api.openai.com"
          - "*.openai.com" matches "api.openai.com", "chat.openai.com"
          - "api.*.internal" matches "api.staging.internal", "api.prod.internal"

        Implementation: split on '.', compare segment by segment,
        '*' matches any single segment.
        """
        pattern_parts = self.domain_pattern.split(".")
        domain_parts = domain.split(".")
        if len(pattern_parts) != len(domain_parts):
            return False
        return all(
            pp == "*" or pp == dp
            for pp, dp in zip(pattern_parts, domain_parts)
        )


@dataclass(slots=True)
class Policy:
    """Access control policy with rules, time windows, and rate limits."""
    policy_id: PolicyId
    name: str
    description: str
    rules: list[PolicyRule]
    status: PolicyStatus
    priority: int                           # Policy-level priority (1-1000)
    time_window: TimeWindow | None = None
    rate_limit: RateLimit | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(cls, name: str, description: str = "", priority: int = 100) -> Policy:
        """Factory: create a new policy in DRAFT state."""
        return cls(
            policy_id=uuid.uuid4(),
            name=name,
            description=description,
            rules=[],
            status=PolicyStatus.DRAFT,
            priority=priority,
        )

    def activate(self) -> None:
        """Move from DRAFT → ACTIVE. Must have at least one rule."""
        if self.status != PolicyStatus.DRAFT:
            raise ValueError(f"Can only activate DRAFT policies, current: {self.status.name}")
        if not self.rules:
            raise ValueError("Cannot activate a policy with no rules")
        self.status = PolicyStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)

    def suspend(self) -> None:
        """ACTIVE → SUSPENDED."""
        if self.status != PolicyStatus.ACTIVE:
            raise ValueError(f"Can only suspend ACTIVE policies, current: {self.status.name}")
        self.status = PolicyStatus.SUSPENDED
        self.updated_at = datetime.now(timezone.utc)

    def archive(self) -> None:
        """Any non-ARCHIVED state → ARCHIVED (terminal)."""
        if self.status == PolicyStatus.ARCHIVED:
            raise ValueError("Policy is already archived")
        self.status = PolicyStatus.ARCHIVED
        self.updated_at = datetime.now(timezone.utc)

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a rule. Max 100 rules per policy."""
        if len(self.rules) >= 100:
            raise ValueError("Maximum 100 rules per policy")
        self.rules.append(rule)
        self.updated_at = datetime.now(timezone.utc)

    def remove_rule(self, rule_id: uuid.UUID) -> None:
        """Remove a rule by ID. Raises ValueError if not found."""
        for i, rule in enumerate(self.rules):
            if rule.rule_id == rule_id:
                self.rules.pop(i)
                self.updated_at = datetime.now(timezone.utc)
                return
        raise ValueError(f"Rule {rule_id} not found in policy {self.policy_id}")

    def evaluate(self, domain: str, request_time: datetime) -> RuleAction | None:
        """Evaluate this policy against a domain and time.

        Returns:
            RuleAction if a rule matches, None if no rules match.
            Rules are evaluated in priority order (lowest number first).
            Time window is checked first — if outside window, returns None.
        """
        # 1. Check time window (if configured)
        if self.time_window and not self.time_window.contains(request_time):
            return None

        # 2. Sort rules by priority (stable sort — preserve insertion order for ties)
        sorted_rules = sorted(self.rules, key=lambda r: r.priority)

        # 3. Evaluate rules in order
        for rule in sorted_rules:
            if rule.matches(domain):
                return rule.action

        return None

    def check_rate_limit(self, current_count: int, window: str) -> bool:
        """Check if current_count exceeds the rate limit for the given window.

        Args:
            current_count: Number of requests in the current window.
            window: One of "minute", "hour", "day".

        Returns:
            True if within limit, False if exceeded.
        """
        if self.rate_limit is None:
            return True
        limit_map = {
            "minute": self.rate_limit.requests_per_minute,
            "hour": self.rate_limit.requests_per_hour,
            "day": self.rate_limit.requests_per_day,
        }
        limit = limit_map.get(window)
        if limit is None:
            raise ValueError(f"Unknown window: {window}. Use 'minute', 'hour', or 'day'.")
        return current_count <= limit
