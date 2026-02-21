"""Analytics engine combining HyperLogLog, Count-Min Sketch, and Bloom filter.

Processes AuditEntry objects and maintains three probabilistic data
structures that answer common audit queries in O(1):

    1. "How many distinct agents accessed domain X?" -- HyperLogLog
    2. "How many times was domain X accessed?" -- Count-Min Sketch
    3. "Has agent Y ever accessed domain X?" -- Bloom filter

Each query would normally require scanning the full audit log or
maintaining exact data structures that grow linearly with the number
of entries. The probabilistic versions use a fixed amount of memory
regardless of how many entries are processed, at the cost of bounded
approximation error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chronoguard_lite.analytics.bloom import BloomFilter
from chronoguard_lite.analytics.countmin import CountMinSketch
from chronoguard_lite.analytics.hyperloglog import HyperLogLog

if TYPE_CHECKING:
    from chronoguard_lite.domain.audit import AuditEntry


class AnalyticsEngine:
    """Probabilistic analytics engine for audit entries.

    Parameters:
        hll_precision: HyperLogLog precision (default 11, ~2 KB per domain).
        cms_width: Count-Min Sketch width (default 2048).
        cms_depth: Count-Min Sketch depth (default 5).
        bloom_expected: Expected number of (agent, domain) pairs for Bloom filter.
        bloom_fp_rate: Bloom filter target false positive rate.
    """

    def __init__(
        self,
        hll_precision: int = 11,
        cms_width: int = 2048,
        cms_depth: int = 5,
        bloom_expected: int = 1_000_000,
        bloom_fp_rate: float = 0.01,
    ) -> None:
        self._hll_precision = hll_precision
        self._domain_hlls: dict[str, HyperLogLog] = {}
        self._cms = CountMinSketch(width=cms_width, depth=cms_depth)
        self._bloom = BloomFilter(
            expected_elements=bloom_expected,
            fp_rate=bloom_fp_rate,
        )
        self._entries_processed = 0

    def process_entry(self, entry: AuditEntry) -> None:
        """Update all three structures from an AuditEntry.

        This is the main ingestion path. Call it once per entry.
        """
        domain = entry.domain
        agent_str = str(entry.agent_id)

        # HyperLogLog: count unique agents per domain
        if domain not in self._domain_hlls:
            self._domain_hlls[domain] = HyperLogLog(p=self._hll_precision)
        self._domain_hlls[domain].add(agent_str)

        # Count-Min Sketch: track domain access frequency
        self._cms.add(domain)

        # Bloom filter: record (agent, domain) pair
        pair_key = f"{agent_str}:{domain}"
        self._bloom.add(pair_key)

        self._entries_processed += 1

    def unique_agents(self, domain: str) -> int:
        """Estimate the number of distinct agents that accessed a domain.

        Returns 0 if the domain has never been seen.
        """
        hll = self._domain_hlls.get(domain)
        if hll is None:
            return 0
        return hll.count()

    def domain_frequency(self, domain: str) -> int:
        """Estimate how many times a domain has been accessed.

        The Count-Min Sketch never underestimates, so this is always
        >= the true count.
        """
        return self._cms.estimate(domain)

    def has_accessed(self, agent_id: str, domain: str) -> bool:
        """Check if an agent has ever accessed a domain.

        Returns True if the agent probably accessed the domain (could
        be a false positive). Returns False if the agent definitely
        never accessed it.
        """
        pair_key = f"{agent_id}:{domain}"
        return self._bloom.might_contain(pair_key)

    @property
    def entries_processed(self) -> int:
        return self._entries_processed

    def memory_report(self) -> dict[str, int]:
        """Report approximate memory usage per component."""
        hll_total = sum(h.memory_bytes() for h in self._domain_hlls.values())
        return {
            "hyperloglog_bytes": hll_total,
            "hyperloglog_domains": len(self._domain_hlls),
            "countmin_bytes": self._cms.memory_bytes(),
            "bloom_bytes": self._bloom.memory_bytes(),
            "total_bytes": hll_total + self._cms.memory_bytes() + self._bloom.memory_bytes(),
        }
