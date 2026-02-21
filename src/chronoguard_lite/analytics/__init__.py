"""Probabilistic analytics engine for audit data.

Public API:
    HyperLogLog: cardinality estimation (~2 KB per counter)
    CountMinSketch: frequency estimation (~40 KB total)
    BloomFilter: membership testing (auto-sized)
    AnalyticsEngine: combines all three for AuditEntry processing
"""

from chronoguard_lite.analytics.bloom import BloomFilter
from chronoguard_lite.analytics.countmin import CountMinSketch
from chronoguard_lite.analytics.engine import AnalyticsEngine
from chronoguard_lite.analytics.hyperloglog import HyperLogLog

__all__ = [
    "AnalyticsEngine",
    "BloomFilter",
    "CountMinSketch",
    "HyperLogLog",
]
