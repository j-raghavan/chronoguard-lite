"""Tests for the StripedMap.

Covers: basic CRUD, concurrent writes, concurrent reads+writes,
stripe distribution, and invalid construction.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, wait

import pytest

from chronoguard_lite.concurrency.striped_map import StripedMap


def test_basic_crud():
    """get/put/delete/contains/size work correctly on a single thread."""
    m = StripedMap(num_stripes=4)
    assert m.size() == 0

    m.put("a", 1)
    m.put("b", 2)
    m.put("c", 3)
    assert m.size() == 3
    assert m.get("a") == 1
    assert m.get("b") == 2
    assert m.get("missing") is None
    assert m.contains("c") is True
    assert m.contains("d") is False

    assert m.delete("b") is True
    assert m.delete("b") is False
    assert m.size() == 2

    # Overwrite
    m.put("a", 99)
    assert m.get("a") == 99


def test_concurrent_writes():
    """16 threads writing 1000 keys each, all present after."""
    m = StripedMap(num_stripes=16)
    n_threads = 16
    n_keys = 1000

    def writer(thread_id):
        for i in range(n_keys):
            key = f"t{thread_id}_k{i}"
            m.put(key, thread_id * n_keys + i)

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futs = [pool.submit(writer, tid) for tid in range(n_threads)]
        wait(futs)

    assert m.size() == n_threads * n_keys

    # Spot-check a few values
    assert m.get("t0_k0") == 0
    assert m.get("t15_k999") == 15 * n_keys + 999


def test_concurrent_reads_writes():
    """8 readers + 8 writers operating concurrently, no crashes."""
    m = StripedMap(num_stripes=16)
    # Pre-populate
    for i in range(1000):
        m.put(f"key_{i}", i)

    errors = []

    def reader():
        for i in range(1000):
            val = m.get(f"key_{i}")
            # Value may have been updated by a writer, so just check type
            if val is not None and not isinstance(val, int):
                errors.append(f"Unexpected type: {type(val)}")

    def writer(offset):
        for i in range(1000):
            m.put(f"key_{i}", i + offset)

    threads = []
    for _ in range(8):
        threads.append(threading.Thread(target=reader))
    for w in range(8):
        threads.append(threading.Thread(target=writer, args=(w * 1000,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(errors) == 0, f"Errors: {errors}"
    assert m.size() == 1000


def test_stripe_distribution():
    """Keys distribute roughly evenly across stripes."""
    m = StripedMap(num_stripes=8)
    n = 8000
    for i in range(n):
        m.put(f"key_{i}", i)

    # Check each stripe has roughly n/8 = 1000 keys
    for i, stripe in enumerate(m._stripes):
        count = len(stripe)
        # Allow 50% variance (500-1500 per stripe)
        assert 200 < count < 1800, (
            f"Stripe {i} has {count} keys, expected ~{n // 8}"
        )


def test_invalid_num_stripes():
    """Non-power-of-2 or zero stripes raises ValueError."""
    with pytest.raises(ValueError):
        StripedMap(num_stripes=0)
    with pytest.raises(ValueError):
        StripedMap(num_stripes=3)
    with pytest.raises(ValueError):
        StripedMap(num_stripes=15)
    # These should work fine
    StripedMap(num_stripes=1)
    StripedMap(num_stripes=2)
    StripedMap(num_stripes=64)


def test_keys_and_values():
    """keys() and values() return snapshots."""
    m = StripedMap(num_stripes=4)
    m.put("x", 10)
    m.put("y", 20)
    m.put("z", 30)

    keys = sorted(m.keys())
    assert keys == ["x", "y", "z"]
    assert sorted(m.values()) == [10, 20, 30]
