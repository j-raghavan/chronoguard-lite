"""Tests for the ReadWriteLock.

Covers: concurrent readers, writer exclusion, writer preference,
and no-deadlock under stress.
"""
from __future__ import annotations

import threading
import time

import pytest

from chronoguard_lite.concurrency.rwlock import ReadWriteLock


def test_multiple_readers():
    """10 threads can hold the read lock concurrently."""
    lock = ReadWriteLock()
    inside = threading.Event()
    count = 0
    count_lock = threading.Lock()
    barrier = threading.Barrier(10)

    def reader():
        nonlocal count
        with lock.read():
            barrier.wait(timeout=5.0)
            with count_lock:
                count += 1
            time.sleep(0.05)  # hold the read lock briefly

    threads = [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert count == 10, f"Only {count} readers got in, expected 10"


def test_writer_excludes_readers():
    """While a writer holds the lock, readers block."""
    lock = ReadWriteLock()
    writer_entered = threading.Event()
    writer_done = threading.Event()
    reader_entered = threading.Event()

    def writer():
        with lock.write():
            writer_entered.set()
            # Hold the write lock until we're told to release
            writer_done.wait(timeout=5.0)

    def reader():
        # Wait until writer has the lock
        writer_entered.wait(timeout=5.0)
        with lock.read():
            reader_entered.set()

    wt = threading.Thread(target=writer)
    rt = threading.Thread(target=reader)
    wt.start()
    writer_entered.wait(timeout=5.0)

    rt.start()
    # Reader should NOT be able to enter while writer holds the lock
    entered = reader_entered.wait(timeout=0.2)
    assert not entered, "Reader entered while writer held the lock"

    # Release the writer
    writer_done.set()
    wt.join(timeout=5.0)

    # Now reader should enter quickly
    entered = reader_entered.wait(timeout=5.0)
    assert entered, "Reader never entered after writer released"
    rt.join(timeout=5.0)


def test_writer_preference():
    """Once a writer is waiting, new readers block (no writer starvation)."""
    lock = ReadWriteLock()
    reader1_entered = threading.Event()
    writer_waiting = threading.Event()
    reader2_entered = threading.Event()
    reader1_release = threading.Event()

    def reader1():
        with lock.read():
            reader1_entered.set()
            reader1_release.wait(timeout=5.0)

    def writer():
        reader1_entered.wait(timeout=5.0)
        writer_waiting.set()
        with lock.write():
            pass  # just need to acquire and release

    def reader2():
        writer_waiting.wait(timeout=5.0)
        time.sleep(0.05)  # give writer time to actually block
        with lock.read():
            reader2_entered.set()

    t1 = threading.Thread(target=reader1)
    tw = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader2)

    t1.start()
    reader1_entered.wait(timeout=5.0)

    tw.start()
    writer_waiting.wait(timeout=5.0)
    time.sleep(0.05)

    t2.start()
    # reader2 should NOT enter while writer is waiting
    entered = reader2_entered.wait(timeout=0.2)
    assert not entered, "New reader entered while writer was waiting (starvation risk)"

    # Release reader1, writer gets in, then reader2
    reader1_release.set()
    tw.join(timeout=5.0)
    t2.join(timeout=5.0)
    t1.join(timeout=5.0)

    assert reader2_entered.is_set(), "Reader2 never entered"


def test_no_deadlock():
    """100 threads alternating read/write complete within 5 seconds."""
    lock = ReadWriteLock()
    counter = 0
    counter_lock = threading.Lock()

    def worker(n):
        nonlocal counter
        for _ in range(50):
            if n % 2 == 0:
                with lock.read():
                    _ = counter  # read
            else:
                with lock.write():
                    with counter_lock:
                        counter += 1

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"Took {elapsed:.1f}s, possible deadlock"
    assert counter == 50 * 50, f"Counter={counter}, expected {50*50}"
