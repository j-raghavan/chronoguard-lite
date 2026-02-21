"""Tests for the DAG-based PolicyEngine."""
from __future__ import annotations

import pytest

from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import RuleAction
from chronoguard_lite.graph.policy_engine import PolicyEngine
from chronoguard_lite.graph.topological import CyclicDependencyError

from .conftest import REQUEST_TIME, make_policy


class TestPolicyEngineBasics:
    def test_single_policy_allow(self) -> None:
        engine = PolicyEngine()
        p = make_policy("base", "*.example.com", RuleAction.ALLOW)
        engine.register(p)
        engine.build()
        report = engine.evaluate("api.example.com", REQUEST_TIME)
        assert report.final_decision == AccessDecision.ALLOW
        assert report.policies_evaluated == 1
        assert report.policies_skipped == 0

    def test_single_policy_deny(self) -> None:
        engine = PolicyEngine()
        p = make_policy("blocker", "*.evil.com", RuleAction.DENY)
        engine.register(p)
        engine.build()
        report = engine.evaluate("api.evil.com", REQUEST_TIME)
        assert report.final_decision == AccessDecision.DENY

    def test_no_matching_policy(self) -> None:
        engine = PolicyEngine()
        p = make_policy("narrow", "api.specific.com", RuleAction.ALLOW)
        engine.register(p)
        engine.build()
        report = engine.evaluate("totally.different.com", REQUEST_TIME)
        assert report.final_decision == AccessDecision.NO_MATCHING_POLICY


class TestDependencyOrdering:
    def test_dependency_order(self) -> None:
        """Prerequisites must be evaluated before dependents."""
        engine = PolicyEngine()
        base = make_policy("base-rate-limit", "*.example.com", RuleAction.ALLOW)
        trust = make_policy("agent-trust", "*.example.com", RuleAction.ALLOW)
        final = make_policy("final-access", "*.example.com", RuleAction.ALLOW)

        engine.register(base)
        engine.register(trust)
        engine.register(final)
        engine.add_dependency(final.policy_id, depends_on=base.policy_id)
        engine.add_dependency(final.policy_id, depends_on=trust.policy_id)
        order = engine.build()

        pos = {pid: i for i, pid in enumerate(order)}
        assert pos[base.policy_id] < pos[final.policy_id]
        assert pos[trust.policy_id] < pos[final.policy_id]

    def test_deep_chain_ordering(self) -> None:
        """Chain of 5 policies: p0 -> p1 -> p2 -> p3 -> p4."""
        engine = PolicyEngine()
        policies = [
            make_policy(f"p{i}", "*.example.com", RuleAction.ALLOW)
            for i in range(5)
        ]
        for p in policies:
            engine.register(p)
        for i in range(4):
            engine.add_dependency(
                policies[i + 1].policy_id,
                depends_on=policies[i].policy_id,
            )
        order = engine.build()
        pos = {pid: i for i, pid in enumerate(order)}
        for i in range(4):
            assert pos[policies[i].policy_id] < pos[policies[i + 1].policy_id]


class TestShortCircuit:
    def test_deny_short_circuits_dependents(self) -> None:
        """If base denies, dependent should be skipped."""
        engine = PolicyEngine()
        base = make_policy("base", "*.example.com", RuleAction.DENY)
        dependent = make_policy("dependent", "*.example.com", RuleAction.ALLOW)

        engine.register(base)
        engine.register(dependent)
        engine.add_dependency(dependent.policy_id, depends_on=base.policy_id)
        engine.build()

        report = engine.evaluate("api.example.com", REQUEST_TIME)
        assert report.final_decision == AccessDecision.DENY
        assert report.policies_skipped == 1

        # check that dependent was short-circuited
        dep_result = [r for r in report.results if r.policy_id == dependent.policy_id]
        assert len(dep_result) == 1
        assert dep_result[0].short_circuited is True
        assert dep_result[0].eval_time_ms == 0.0

    def test_allow_does_not_short_circuit(self) -> None:
        engine = PolicyEngine()
        base = make_policy("base", "*.example.com", RuleAction.ALLOW)
        dependent = make_policy("dependent", "*.example.com", RuleAction.ALLOW)

        engine.register(base)
        engine.register(dependent)
        engine.add_dependency(dependent.policy_id, depends_on=base.policy_id)
        engine.build()

        report = engine.evaluate("api.example.com", REQUEST_TIME)
        assert report.final_decision == AccessDecision.ALLOW
        assert report.policies_skipped == 0
        assert report.policies_evaluated == 2

    def test_deep_short_circuit_cascades(self) -> None:
        """Deny at depth 0 should cascade through all descendants."""
        engine = PolicyEngine()
        p0 = make_policy("root", "*.example.com", RuleAction.DENY)
        p1 = make_policy("mid", "*.example.com", RuleAction.ALLOW)
        p2 = make_policy("leaf", "*.example.com", RuleAction.ALLOW)

        engine.register(p0)
        engine.register(p1)
        engine.register(p2)
        engine.add_dependency(p1.policy_id, depends_on=p0.policy_id)
        engine.add_dependency(p2.policy_id, depends_on=p1.policy_id)
        engine.build()

        report = engine.evaluate("api.example.com", REQUEST_TIME)
        assert report.policies_skipped == 2  # both p1 and p2 skipped
        assert report.policies_evaluated == 1  # only p0 ran


class TestCycleRejection:
    def test_cycle_rejected_on_build(self) -> None:
        engine = PolicyEngine()
        a = make_policy("a", "*.example.com", RuleAction.ALLOW)
        b = make_policy("b", "*.example.com", RuleAction.ALLOW)

        engine.register(a)
        engine.register(b)
        engine.add_dependency(b.policy_id, depends_on=a.policy_id)
        engine.add_dependency(a.policy_id, depends_on=b.policy_id)

        with pytest.raises(CyclicDependencyError):
            engine.build()

    def test_validate_detects_cycle(self) -> None:
        engine = PolicyEngine()
        a = make_policy("a", "*.example.com", RuleAction.ALLOW)
        b = make_policy("b", "*.example.com", RuleAction.ALLOW)

        engine.register(a)
        engine.register(b)
        engine.add_dependency(b.policy_id, depends_on=a.policy_id)
        engine.add_dependency(a.policy_id, depends_on=b.policy_id)

        result = engine.validate()
        assert result.has_cycle


class TestFlatEvaluation:
    def test_flat_evaluates_all(self) -> None:
        """Flat evaluation does not skip anything."""
        engine = PolicyEngine()
        base = make_policy("base", "*.example.com", RuleAction.DENY)
        dependent = make_policy("dependent", "*.example.com", RuleAction.ALLOW)

        engine.register(base)
        engine.register(dependent)
        engine.add_dependency(dependent.policy_id, depends_on=base.policy_id)
        engine.build()

        report = engine.evaluate_flat("api.example.com", REQUEST_TIME)
        assert report.policies_evaluated == 2
        assert report.policies_skipped == 0

    def test_flat_no_short_circuit_changes_nothing_for_all_allow(self) -> None:
        engine = PolicyEngine()
        for i in range(5):
            engine.register(
                make_policy(f"p{i}", "*.example.com", RuleAction.ALLOW)
            )
        engine.build()
        dag_report = engine.evaluate("api.example.com", REQUEST_TIME)
        flat_report = engine.evaluate_flat("api.example.com", REQUEST_TIME)
        assert dag_report.final_decision == flat_report.final_decision


class TestEdgeCases:
    def test_evaluate_before_build_raises(self) -> None:
        engine = PolicyEngine()
        p = make_policy("p", "*.example.com", RuleAction.ALLOW)
        engine.register(p)
        with pytest.raises(RuntimeError, match="build"):
            engine.evaluate("api.example.com", REQUEST_TIME)

    def test_unknown_policy_in_dependency(self) -> None:
        import uuid
        engine = PolicyEngine()
        p = make_policy("p", "*.example.com", RuleAction.ALLOW)
        engine.register(p)
        with pytest.raises(ValueError, match="Unknown"):
            engine.add_dependency(p.policy_id, depends_on=uuid.uuid4())

    def test_evaluation_order_property(self) -> None:
        engine = PolicyEngine()
        p = make_policy("p", "*.example.com", RuleAction.ALLOW)
        engine.register(p)
        with pytest.raises(RuntimeError):
            _ = engine.evaluation_order
        engine.build()
        assert engine.evaluation_order == [p.policy_id]
