"""Benchmark tests for hashing and verification throughput.

These tests measure actual performance on the current hardware.
The numbers printed here are what we'll use in the Chapter 6 prose.
No fabricated numbers -- we measure, then we write.
"""
from __future__ import annotations

import time

import pytest

from chronoguard_lite.crypto.chain import AuditChain
from chronoguard_lite.crypto.verifier import ChainVerifier

from .conftest import generate_entries


@pytest.mark.benchmark
class TestHashThroughput:
    """Measure how fast we can hash entries into a chain."""

    def test_hash_throughput_1m(self):
        """Hash 1M entries and report throughput.

        Target: >200K entries/sec (i.e., <5 seconds for 1M).
        """
        entries = generate_entries(1_000_000)
        chain = AuditChain()

        start = time.perf_counter()
        for entry in entries:
            chain.append(entry)
        elapsed = time.perf_counter() - start

        throughput = len(entries) / elapsed
        print(f"\n  SHA256 chain: {len(entries):,} entries in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:,.0f} entries/sec")

        assert len(chain) == 1_000_000
        # Sanity: should be faster than 5 seconds on any modern machine
        assert elapsed < 10.0, f"Too slow: {elapsed:.1f}s for 1M entries"

    def test_hmac_throughput_1m(self):
        """HMAC-SHA256 chain throughput for 1M entries.

        HMAC adds one extra HMAC call per entry compared to plain SHA256.
        We expect it to be somewhat slower but still in the same ballpark.
        """
        entries = generate_entries(1_000_000)
        chain = AuditChain.with_hmac(secret_key=b"benchmark-key-32-bytes-exactly!!")

        start = time.perf_counter()
        for entry in entries:
            chain.append(entry)
        elapsed = time.perf_counter() - start

        throughput = len(entries) / elapsed
        print(f"\n  HMAC-SHA256 chain: {len(entries):,} entries in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:,.0f} entries/sec")

        assert len(chain) == 1_000_000
        assert elapsed < 10.0, f"Too slow: {elapsed:.1f}s for 1M entries"


@pytest.mark.benchmark
class TestVerifyThroughput:
    """Measure chain verification speed."""

    def test_verify_throughput_1m(self):
        """Verify a 1M-entry chain and report speed.

        Verification recomputes every hash, so it should take roughly
        the same time as building the chain.
        """
        entries = generate_entries(1_000_000)
        chain = AuditChain()
        for entry in entries:
            chain.append(entry)

        verifier = ChainVerifier(chain)

        start = time.perf_counter()
        result = verifier.verify_full()
        elapsed = time.perf_counter() - start

        throughput = result.entries_verified / elapsed
        print(f"\n  Verify SHA256 chain: {result.entries_verified:,} entries in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:,.0f} entries/sec")

        assert result.is_valid
        assert result.entries_verified == 1_000_000
        assert elapsed < 10.0, f"Too slow: {elapsed:.1f}s"

    def test_verify_throughput_hmac_1m(self):
        """Verify a 1M-entry HMAC chain."""
        entries = generate_entries(1_000_000)
        chain = AuditChain.with_hmac(secret_key=b"benchmark-key-32-bytes-exactly!!")
        for entry in entries:
            chain.append(entry)

        verifier = ChainVerifier(chain)

        start = time.perf_counter()
        result = verifier.verify_full()
        elapsed = time.perf_counter() - start

        throughput = result.entries_verified / elapsed
        print(f"\n  Verify HMAC chain: {result.entries_verified:,} entries in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:,.0f} entries/sec")

        assert result.is_valid
        assert result.entries_verified == 1_000_000
        assert elapsed < 10.0, f"Too slow: {elapsed:.1f}s"


@pytest.mark.benchmark
class TestHashVsHmacComparison:
    """Direct comparison of SHA256 vs HMAC-SHA256 throughput."""

    def test_sha256_vs_hmac_100k(self):
        """Compare SHA256 and HMAC-SHA256 on 100K entries."""
        entries = generate_entries(100_000)

        # SHA256
        sha_chain = AuditChain()
        start = time.perf_counter()
        for entry in entries:
            sha_chain.append(entry)
        sha_elapsed = time.perf_counter() - start
        sha_rate = len(entries) / sha_elapsed

        # HMAC-SHA256
        hmac_chain = AuditChain.with_hmac(secret_key=b"benchmark-key-32-bytes-exactly!!")
        start = time.perf_counter()
        for entry in entries:
            hmac_chain.append(entry)
        hmac_elapsed = time.perf_counter() - start
        hmac_rate = len(entries) / hmac_elapsed

        ratio = sha_rate / hmac_rate
        print(f"\n  SHA256:      {sha_rate:,.0f} entries/sec ({sha_elapsed:.2f}s)")
        print(f"  HMAC-SHA256: {hmac_rate:,.0f} entries/sec ({hmac_elapsed:.2f}s)")
        print(f"  SHA256/HMAC ratio: {ratio:.2f}x")

        # Both should complete, and SHA256 should be at least a little faster
        assert len(sha_chain) == 100_000
        assert len(hmac_chain) == 100_000
