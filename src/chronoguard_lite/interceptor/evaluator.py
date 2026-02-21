"""Policy evaluator: given a request and policies, produce an access decision.

The central decision-making logic:
  1. Look up whether the agent can make requests
  2. Sort the agent's assigned policies by priority
  3. Evaluate each ACTIVE policy against the request domain + time
  4. Return the first match, or NO_MATCHING_POLICY if nothing matches

Mapped from full ChronoGuard: domain/policy/service.py (PolicyService.evaluate)
Simplified: no OPA integration, no Rego compilation -- pure Python evaluation.

Thread safety: PolicyEvaluator has no mutable state. The evaluate() method
is a pure function of its arguments. Safe to share one instance across all
worker threads in the ThreadedInterceptor.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from chronoguard_lite.domain.agent import Agent
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import Policy, PolicyStatus, RuleAction
from chronoguard_lite.domain.types import PolicyId
from chronoguard_lite.interceptor.protocol import InterceptRequest


@dataclass(slots=True)
class EvaluationResult:
    """Result of evaluating a request against policies."""
    decision: AccessDecision
    reason: str
    policy_id: PolicyId | None = None
    rule_id: uuid.UUID | None = None


class PolicyEvaluator:
    """Stateless policy evaluator.

    Thread-safe: no mutable state. Can be shared across threads.

    Usage:
        evaluator = PolicyEvaluator()
        result = evaluator.evaluate(request, agent, policies)
    """

    def evaluate(
        self,
        request: InterceptRequest,
        agent: Agent,
        policies: list[Policy],
    ) -> EvaluationResult:
        """Evaluate request against the agent's assigned policies.

        Algorithm:
        1. If not agent.can_make_requests() -> DENY
        2. Sort policies by priority (lowest number = highest priority)
        3. For each ACTIVE policy, call policy.evaluate(domain, now)
        4. Map RuleAction.ALLOW/DENY to AccessDecision
        5. If nothing matched -> NO_MATCHING_POLICY
        """
        if not agent.can_make_requests():
            return EvaluationResult(
                decision=AccessDecision.DENY,
                reason=f"Agent {agent.name} is {agent.status.name}, not ACTIVE",
            )

        now = datetime.now(timezone.utc)
        sorted_policies = sorted(policies, key=lambda p: p.priority)

        for policy in sorted_policies:
            if policy.status != PolicyStatus.ACTIVE:
                continue

            action = policy.evaluate(request.domain, now)
            if action is None:
                continue

            # Find the specific rule that matched (for audit trail)
            matched_rule_id = self._find_matched_rule(policy, request.domain)

            decision = (
                AccessDecision.ALLOW
                if action == RuleAction.ALLOW
                else AccessDecision.DENY
            )
            return EvaluationResult(
                decision=decision,
                reason=f"Matched policy: {policy.name}",
                policy_id=policy.policy_id,
                rule_id=matched_rule_id,
            )

        return EvaluationResult(
            decision=AccessDecision.NO_MATCHING_POLICY,
            reason=f"No policy matched domain {request.domain}",
        )

    @staticmethod
    def _find_matched_rule(policy: Policy, domain: str) -> uuid.UUID | None:
        """Walk rules in priority order to find which one matched.

        We re-check here because policy.evaluate() doesn't tell us
        which rule fired. Slight duplication, but keeps Policy clean.
        """
        for rule in sorted(policy.rules, key=lambda r: r.priority):
            if rule.matches(domain):
                return rule.rule_id
        return None
