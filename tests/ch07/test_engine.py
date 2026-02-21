"""Tests for the combined AnalyticsEngine."""
from __future__ import annotations

import uuid

from chronoguard_lite.analytics.engine import AnalyticsEngine
from chronoguard_lite.domain.decisions import AccessDecision

from .conftest import make_entry, AGENT_POOL, DOMAIN_POOL


class TestEngineBasics:
    def test_empty_engine(self):
        engine = AnalyticsEngine()
        assert engine.entries_processed == 0
        assert engine.unique_agents("api.openai.com") == 0
        assert engine.domain_frequency("api.openai.com") == 0
        assert not engine.has_accessed("agent-1", "api.openai.com")

    def test_process_single_entry(self):
        engine = AnalyticsEngine()
        agent = uuid.UUID(int=1)
        entry = make_entry(ts=1.0, agent_id=agent, domain="api.openai.com")
        engine.process_entry(entry)

        assert engine.entries_processed == 1
        assert engine.unique_agents("api.openai.com") >= 1
        assert engine.domain_frequency("api.openai.com") >= 1
        assert engine.has_accessed(str(agent), "api.openai.com")
        assert not engine.has_accessed(str(agent), "api.github.com")

    def test_multiple_agents_one_domain(self):
        engine = AnalyticsEngine()
        for i in range(20):
            entry = make_entry(
                ts=float(i),
                agent_id=uuid.UUID(int=i),
                domain="api.openai.com",
            )
            engine.process_entry(entry)

        assert engine.unique_agents("api.openai.com") >= 15  # allow some HLL error
        assert engine.domain_frequency("api.openai.com") >= 20

    def test_one_agent_multiple_domains(self):
        engine = AnalyticsEngine()
        agent = uuid.UUID(int=1)
        for domain in DOMAIN_POOL[:10]:
            entry = make_entry(ts=1.0, agent_id=agent, domain=domain)
            engine.process_entry(entry)

        agent_str = str(agent)
        for domain in DOMAIN_POOL[:10]:
            assert engine.has_accessed(agent_str, domain)
        # Domains not visited should return False (with high probability)
        assert not engine.has_accessed(agent_str, "never.visited.com")

    def test_memory_report(self):
        engine = AnalyticsEngine()
        for i in range(100):
            entry = make_entry(
                ts=float(i),
                agent_id=AGENT_POOL[i % len(AGENT_POOL)],
                domain=DOMAIN_POOL[i % len(DOMAIN_POOL)],
            )
            engine.process_entry(entry)

        report = engine.memory_report()
        assert report["hyperloglog_domains"] > 0
        assert report["countmin_bytes"] > 0
        assert report["bloom_bytes"] > 0
        assert report["total_bytes"] == (
            report["hyperloglog_bytes"]
            + report["countmin_bytes"]
            + report["bloom_bytes"]
        )
