"""DAG-based policy evaluation engine.

The PolicyEngine wraps a Graph of policy dependencies and evaluates
them in topological order.  Each policy node can depend on other
policies, meaning "only evaluate me if all my prerequisites returned
ALLOW".  If any prerequisite returns DENY, the dependent policy is
short-circuited to DENY without running its own rules.

This replaces flat linear evaluation (check all 50 policies every time)
with dependency-aware evaluation (skip branches early when a prerequisite
denies).

Comparison to full ChronoGuard: the production system uses OPA (Open
Policy Agent) with Rego policy files and a separate policy compiler.
We replace that with a hand-built DAG evaluator so the reader sees
the graph algorithms directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Hashable
from uuid import UUID

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import Policy, RuleAction
from chronoguard_lite.domain.types import PolicyId
from chronoguard_lite.graph.adjacency import Graph
from chronoguard_lite.graph.cycle_detector import CycleResult, detect_cycle
from chronoguard_lite.graph.topological import CyclicDependencyError, topological_sort


@dataclass(slots=True)
class EvalResult:
    """Result of evaluating a single policy."""
    policy_id: PolicyId
    decision: AccessDecision
    eval_time_ms: float       # wall-clock time to evaluate this policy
    short_circuited: bool     # True if skipped because a prerequisite denied


@dataclass(slots=True)
class EvalReport:
    """Full evaluation report for a request."""
    results: list[EvalResult]
    final_decision: AccessDecision
    total_time_ms: float
    policies_evaluated: int
    policies_skipped: int


class PolicyEngine:
    """DAG-based policy evaluator.

    Usage:
        engine = PolicyEngine()
        engine.register(policy_a)
        engine.register(policy_b)
        engine.add_dependency(policy_b.policy_id, depends_on=policy_a.policy_id)
        engine.build()   # topological sort, cycle check
        report = engine.evaluate("api.openai.com", request_time)
    """

    __slots__ = ("_policies", "_graph", "_order", "_built")

    def __init__(self) -> None:
        self._policies: dict[PolicyId, Policy] = {}
        self._graph: Graph[PolicyId] = Graph()
        self._order: list[PolicyId] | None = None
        self._built = False

    def register(self, policy: Policy) -> None:
        """Register a policy.  Must call build() again after."""
        self._policies[policy.policy_id] = policy
        self._graph.add_node(policy.policy_id)
        self._built = False

    def add_dependency(self, policy_id: PolicyId, depends_on: PolicyId) -> None:
        """Declare that *policy_id* depends on *depends_on*.

        This means *depends_on* must be evaluated (and return ALLOW)
        before *policy_id* is evaluated.  The edge direction is
        depends_on -> policy_id (prerequisite points to dependent).
        """
        if policy_id not in self._policies:
            raise ValueError(f"Unknown policy: {policy_id}")
        if depends_on not in self._policies:
            raise ValueError(f"Unknown dependency: {depends_on}")
        self._graph.add_edge(depends_on, policy_id)
        self._built = False

    def validate(self) -> CycleResult[PolicyId]:
        """Check for circular dependencies without building."""
        return detect_cycle(self._graph)

    def build(self) -> list[PolicyId]:
        """Topologically sort the policy graph.

        Raises CyclicDependencyError if circular dependencies exist.
        Returns the evaluation order.
        """
        self._order = topological_sort(self._graph)
        self._built = True
        return list(self._order)

    @property
    def evaluation_order(self) -> list[PolicyId]:
        if self._order is None:
            raise RuntimeError("Call build() before accessing evaluation_order")
        return list(self._order)

    @property
    def graph(self) -> Graph[PolicyId]:
        return self._graph

    def evaluate(
        self, domain: str, request_time: datetime
    ) -> EvalReport:
        """Evaluate all policies in dependency order for *domain*.

        Short-circuit: if a prerequisite returned DENY or RATE_LIMITED,
        all policies that depend on it are skipped and marked DENY.
        A prerequisite that returned NO_MATCHING_POLICY does *not*
        trigger short-circuit -- "no rules matched" is not a denial.

        Returns an EvalReport with per-policy results and the final
        decision.
        """
        if not self._built or self._order is None:
            raise RuntimeError("Call build() before evaluate()")

        _DENY_DECISIONS = frozenset({
            AccessDecision.DENY,
            AccessDecision.RATE_LIMITED,
        })

        results: list[EvalResult] = []
        decided: dict[PolicyId, AccessDecision] = {}
        skipped = 0
        t_start = time.perf_counter()

        for pid in self._order:
            # check prerequisites
            prereqs = self._graph.predecessors(pid)
            prereq_denied = False
            for pre_id in prereqs:
                pre_dec = decided.get(pre_id)
                if pre_dec is not None and pre_dec in _DENY_DECISIONS:
                    prereq_denied = True
                    break

            if prereq_denied:
                decided[pid] = AccessDecision.DENY
                results.append(EvalResult(
                    policy_id=pid,
                    decision=AccessDecision.DENY,
                    eval_time_ms=0.0,
                    short_circuited=True,
                ))
                skipped += 1
                continue

            # actually evaluate this policy
            policy = self._policies[pid]
            t0 = time.perf_counter()
            action = policy.evaluate(domain, request_time)
            elapsed = (time.perf_counter() - t0) * 1000.0

            if action is None:
                dec = AccessDecision.NO_MATCHING_POLICY
            elif action == RuleAction.ALLOW:
                dec = AccessDecision.ALLOW
            else:
                dec = AccessDecision.DENY

            decided[pid] = dec
            results.append(EvalResult(
                policy_id=pid,
                decision=dec,
                eval_time_ms=elapsed,
                short_circuited=False,
            ))

        total_ms = (time.perf_counter() - t_start) * 1000.0

        # final decision: DENY if any policy denied, otherwise ALLOW if any
        # allowed, otherwise NO_MATCHING_POLICY
        has_deny = any(r.decision == AccessDecision.DENY for r in results)
        has_allow = any(r.decision == AccessDecision.ALLOW for r in results)

        if has_deny:
            final = AccessDecision.DENY
        elif has_allow:
            final = AccessDecision.ALLOW
        else:
            final = AccessDecision.NO_MATCHING_POLICY

        return EvalReport(
            results=results,
            final_decision=final,
            total_time_ms=total_ms,
            policies_evaluated=len(results) - skipped,
            policies_skipped=skipped,
        )

    def evaluate_flat(
        self, domain: str, request_time: datetime
    ) -> EvalReport:
        """Flat linear evaluation: no dependency ordering, no short-circuit.

        Evaluates every registered policy regardless of dependency
        relationships.  Used as a baseline for benchmarking the DAG
        evaluator.
        """
        results: list[EvalResult] = []
        t_start = time.perf_counter()

        for pid, policy in self._policies.items():
            t0 = time.perf_counter()
            action = policy.evaluate(domain, request_time)
            elapsed = (time.perf_counter() - t0) * 1000.0

            if action is None:
                dec = AccessDecision.NO_MATCHING_POLICY
            elif action == RuleAction.ALLOW:
                dec = AccessDecision.ALLOW
            else:
                dec = AccessDecision.DENY

            results.append(EvalResult(
                policy_id=pid,
                decision=dec,
                eval_time_ms=elapsed,
                short_circuited=False,
            ))

        total_ms = (time.perf_counter() - t_start) * 1000.0

        has_deny = any(r.decision == AccessDecision.DENY for r in results)
        has_allow = any(r.decision == AccessDecision.ALLOW for r in results)

        if has_deny:
            final = AccessDecision.DENY
        elif has_allow:
            final = AccessDecision.ALLOW
        else:
            final = AccessDecision.NO_MATCHING_POLICY

        return EvalReport(
            results=results,
            final_decision=final,
            total_time_ms=total_ms,
            policies_evaluated=len(results),
            policies_skipped=0,
        )
