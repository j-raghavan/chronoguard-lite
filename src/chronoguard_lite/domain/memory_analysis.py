"""Memory measurement utilities for comparing object representations.

This module is a teaching tool — it shows readers exactly how much memory
different Python object representations consume and why.

Usage:
    from chronoguard_lite.domain.memory_analysis import compare_representations
    compare_representations()  # Prints comparison table
"""
from __future__ import annotations

import gc
import sys
import tracemalloc
from typing import Any, Callable


def deep_sizeof(obj: Any, seen: set[int] | None = None) -> int:
    """Recursively calculate the total memory of an object and its referents.

    Handles: dicts, lists, sets, tuples, dataclass fields.
    Does NOT follow weak references or module-level objects.

    Algorithm:
        1. sys.getsizeof(obj) for the object header + immediate data
        2. Recurse into __dict__ values (if no __slots__)
        3. Recurse into __slots__ attribute values
        4. Recurse into list/tuple/set/dict contents
        5. Track seen object IDs to avoid cycles
    """
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        size += sum(deep_sizeof(k, seen) + deep_sizeof(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(deep_sizeof(item, seen) for item in obj)
    elif hasattr(obj, "__dict__"):
        size += deep_sizeof(obj.__dict__, seen)
    elif hasattr(obj, "__slots__"):
        for slot in obj.__slots__:
            try:
                val = getattr(obj, slot)
                size += deep_sizeof(val, seen)
            except AttributeError:
                pass

    return size


def measure_batch_memory(
    factory: Callable[[], Any], count: int = 100_000
) -> dict[str, float]:
    """Create `count` objects using `factory` and measure total memory.

    Methodology:
        1. gc.collect() to clean up
        2. tracemalloc.start()
        3. Create objects in a list
        4. Take tracemalloc snapshot
        5. Compute per-object average

    Returns:
        {
            "total_bytes": <float>,
            "per_object_bytes": <float>,
            "tracemalloc_peak_mb": <float>,
        }
    """
    gc.collect()
    tracemalloc.start()

    # Measure baseline
    snapshot_before = tracemalloc.take_snapshot()
    baseline = sum(stat.size for stat in snapshot_before.statistics("filename"))

    # Create objects
    objects = [factory() for _ in range(count)]

    # Measure after
    snapshot_after = tracemalloc.take_snapshot()
    total_after = sum(stat.size for stat in snapshot_after.statistics("filename"))
    peak = tracemalloc.get_traced_memory()[1]

    tracemalloc.stop()

    total_bytes = total_after - baseline
    per_object = total_bytes / count if count > 0 else 0

    # Keep reference to prevent GC
    _ = len(objects)

    return {
        "total_bytes": float(total_bytes),
        "per_object_bytes": float(per_object),
        "tracemalloc_peak_mb": float(peak / (1024 * 1024)),
    }


def compare_representations(count: int = 100_000) -> dict[str, dict[str, float]]:
    """Compare memory usage of AgentDataclass vs AgentSlots vs Agent.

    Returns dict mapping representation name to measurement results.

    Output example:
        Representation       Per-Object (bytes)   100K Total (MB)
        ─────────────────────────────────────────────────────────
        AgentDataclass       412                  39.3
        AgentSlots           216                  20.6
        Agent (__slots__)    216                  20.6
    """
    import uuid
    from datetime import datetime, timezone

    from chronoguard_lite.domain.agent import (
        Agent,
        AgentDataclass,
        AgentSlots,
        AgentStatus,
    )

    now = datetime.now(timezone.utc)

    def make_dataclass() -> AgentDataclass:
        return AgentDataclass(
            agent_id=uuid.uuid4(),
            name="test-agent",
            status=AgentStatus.ACTIVE,
            policy_ids=[],
            created_at=now,
            updated_at=now,
        )

    def make_slots() -> AgentSlots:
        return AgentSlots(
            agent_id=uuid.uuid4(),
            name="test-agent",
            status=AgentStatus.ACTIVE,
            policy_ids=[],
            created_at=now,
            updated_at=now,
        )

    def make_agent() -> Agent:
        return Agent(
            agent_id=uuid.uuid4(),
            name="test-agent",
            status=AgentStatus.ACTIVE,
            policy_ids=[],
            created_at=now,
            updated_at=now,
        )

    results: dict[str, dict[str, float]] = {}

    for name, factory in [
        ("AgentDataclass", make_dataclass),
        ("AgentSlots", make_slots),
        ("Agent (__slots__)", make_agent),
    ]:
        results[name] = measure_batch_memory(factory, count)

    # Print comparison table
    print(f"\n{'Representation':<25} {'Per-Object (bytes)':<22} {f'{count // 1000}K Total (MB)':<18}")
    print("─" * 65)
    for name, data in results.items():
        per_obj = data["per_object_bytes"]
        total_mb = data["total_bytes"] / (1024 * 1024)
        print(f"{name:<25} {per_obj:<22.0f} {total_mb:<18.1f}")
    print()

    return results
