"""Simulate realistic agent traffic for profiling.

Traffic pattern:
  - num_agents agents with varied policy assignments (2-8 policies each)
  - num_domains target domains with Zipf-like distribution
    (top 10% of domains generate ~80% of traffic)
  - 60% of rules ALLOW, 30% DENY, 10% wildcard
  - total_requests requests with timestamps spread over a simulated
    24-hour window

The generator produces InterceptRequest-like tuples so the profiling
harness can feed them through the full evaluation pipeline without
needing a running TCP server.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from chronoguard_lite.domain.agent import Agent
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import (
    Policy,
    PolicyRule,
    PolicyStatus,
    RuleAction,
    TimeWindow,
)
from chronoguard_lite.domain.types import AgentId, PolicyId

# Domain pools
_TLD = ["com", "org", "io", "net", "ai"]
_PROVIDERS = [
    "openai", "anthropic", "google", "stripe", "github",
    "aws", "azure", "internal", "corp", "staging",
    "datadog", "sentry", "pagerduty", "slack", "notion",
    "huggingface", "replicate", "cohere", "mistral", "deepmind",
]
_SUBDOMAINS = ["api", "chat", "admin", "dashboard", "ws", "cdn", "auth", "data"]


@dataclass(slots=True)
class LoadRequest:
    """A synthetic request for the profiling pipeline."""
    agent_id: AgentId
    domain: str
    timestamp: datetime


class LoadGenerator:
    """Generate realistic request workloads for profiling."""

    __slots__ = (
        "_rng", "_agents", "_policies", "_domains",
        "_agent_policies", "_total_requests",
        "_zipf_weights",
    )

    def __init__(
        self,
        num_agents: int = 50,
        num_domains: int = 200,
        num_policies: int = 20,
        total_requests: int = 10_000,
        seed: int = 42,
    ) -> None:
        self._rng = random.Random(seed)
        self._total_requests = total_requests
        self._domains = self._generate_domains(num_domains)
        self._agents = self._generate_agents(num_agents)
        self._policies = self._generate_policies(num_policies)
        self._agent_policies = self._assign_policies(num_agents, num_policies)
        # Zipf weights: domain i has weight 1/(i+1)
        self._zipf_weights = [1.0 / (i + 1) for i in range(num_domains)]

    def _generate_domains(self, n: int) -> list[str]:
        domains = []
        for i in range(n):
            sub = self._rng.choice(_SUBDOMAINS)
            provider = self._rng.choice(_PROVIDERS)
            tld = self._rng.choice(_TLD)
            domains.append(f"{sub}.{provider}.{tld}")
        return domains

    def _generate_agents(self, n: int) -> list[Agent]:
        agents = []
        for i in range(n):
            a = Agent.create(f"agent-{i:03d}")
            a.activate()
            agents.append(a)
        return agents

    def _generate_policies(self, n: int) -> list[Policy]:
        policies = []
        for i in range(n):
            p = Policy.create(f"policy-{i:03d}", priority=self._rng.randint(1, 500))

            # each policy gets 3-10 rules
            n_rules = self._rng.randint(3, 10)
            for _ in range(n_rules):
                roll = self._rng.random()
                if roll < 0.6:
                    action = RuleAction.ALLOW
                elif roll < 0.9:
                    action = RuleAction.DENY
                else:
                    action = RuleAction.ALLOW

                # mix of exact and wildcard patterns
                provider = self._rng.choice(_PROVIDERS)
                tld = self._rng.choice(_TLD)
                if self._rng.random() < 0.4:
                    pattern = f"*.{provider}.{tld}"
                else:
                    sub = self._rng.choice(_SUBDOMAINS)
                    pattern = f"{sub}.{provider}.{tld}"

                p.add_rule(PolicyRule(
                    rule_id=uuid.uuid4(),
                    domain_pattern=pattern,
                    action=action,
                    priority=self._rng.randint(1, 200),
                ))

            p.activate()
            policies.append(p)
        return policies

    def _assign_policies(self, n_agents: int, n_policies: int) -> dict[int, list[int]]:
        """Map agent index -> list of policy indices."""
        mapping: dict[int, list[int]] = {}
        for i in range(n_agents):
            k = self._rng.randint(2, min(8, n_policies))
            mapping[i] = self._rng.sample(range(n_policies), k)
        return mapping

    @property
    def agents(self) -> list[Agent]:
        return self._agents

    @property
    def policies(self) -> list[Policy]:
        return self._policies

    @property
    def domains(self) -> list[str]:
        return self._domains

    def policies_for_agent(self, agent_idx: int) -> list[Policy]:
        """Get assigned policies for an agent by index."""
        return [self._policies[pi] for pi in self._agent_policies[agent_idx]]

    def generate(self) -> list[LoadRequest]:
        """Generate all requests as a list (not iterator, for profiling)."""
        base_time = datetime(2025, 6, 15, 0, 0, tzinfo=timezone.utc)
        requests = []

        for _ in range(self._total_requests):
            agent_idx = self._rng.randint(0, len(self._agents) - 1)
            domain_idx = self._rng.choices(
                range(len(self._domains)),
                weights=self._zipf_weights,
                k=1,
            )[0]
            offset_seconds = self._rng.uniform(0, 86400)

            requests.append(LoadRequest(
                agent_id=self._agents[agent_idx].agent_id,
                domain=self._domains[domain_idx],
                timestamp=base_time + timedelta(seconds=offset_seconds),
            ))

        return requests
