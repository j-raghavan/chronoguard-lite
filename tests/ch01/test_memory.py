"""Tests for memory analysis utilities — deep_sizeof, measure_batch_memory, compare_representations."""
import sys
import uuid
from datetime import datetime, timezone

from chronoguard_lite.domain.agent import Agent, AgentDataclass, AgentSlots, AgentStatus
from chronoguard_lite.domain.memory_analysis import (
    compare_representations,
    deep_sizeof,
    measure_batch_memory,
)


# ── deep_sizeof ──

def test_deep_sizeof_basic():
    """deep_sizeof should return at least sys.getsizeof for simple objects."""
    x = 42
    assert deep_sizeof(x) >= sys.getsizeof(x)


def test_deep_sizeof_dict():
    """deep_sizeof of a dict should exceed the dict shell itself."""
    d = {"key": "value", "number": 12345}
    assert deep_sizeof(d) > sys.getsizeof(d)


def test_deep_sizeof_no_double_count():
    """Shared references should only be counted once."""
    shared = [1, 2, 3]
    container = [shared, shared]
    size = deep_sizeof(container)
    # Should not count `shared` twice
    naive = deep_sizeof([shared]) + deep_sizeof([shared])
    assert size < naive


# ── Dataclass vs __slots__ comparison ──

def test_slots_smaller_than_dataclass():
    """AgentSlots (with __slots__) should use less memory than AgentDataclass (with __dict__)."""
    now = datetime.now(timezone.utc)
    dc = AgentDataclass(
        agent_id=uuid.uuid4(),
        name="test-agent",
        status=AgentStatus.ACTIVE,
        policy_ids=[],
        created_at=now,
        updated_at=now,
    )
    sl = AgentSlots(
        agent_id=uuid.uuid4(),
        name="test-agent",
        status=AgentStatus.ACTIVE,
        policy_ids=[],
        created_at=now,
        updated_at=now,
    )
    dc_size = deep_sizeof(dc)
    sl_size = deep_sizeof(sl)
    # __slots__ version should be noticeably smaller
    assert sl_size < dc_size, f"Slots ({sl_size}) should be smaller than dataclass ({dc_size})"


def test_agent_has_no_dict():
    """Agent (production class) should not have __dict__."""
    agent = Agent.create("test-agent")
    assert not hasattr(agent, "__dict__"), "Agent should use __slots__, not __dict__"


# ── measure_batch_memory ──

def test_measure_batch_memory():
    """measure_batch_memory should return sensible measurements for a small batch."""
    now = datetime.now(timezone.utc)

    def factory() -> AgentSlots:
        return AgentSlots(
            agent_id=uuid.uuid4(),
            name="bench-agent",
            status=AgentStatus.ACTIVE,
            policy_ids=[],
            created_at=now,
            updated_at=now,
        )

    result = measure_batch_memory(factory, count=1000)
    assert "total_bytes" in result
    assert "per_object_bytes" in result
    assert "tracemalloc_peak_mb" in result
    assert result["total_bytes"] > 0
    assert result["per_object_bytes"] > 0


# ── compare_representations ──

def test_compare_representations():
    """compare_representations should return data for all three representations."""
    results = compare_representations(count=1000)
    assert "AgentDataclass" in results
    assert "AgentSlots" in results
    assert "Agent (__slots__)" in results
    # Dataclass should use more memory per object than slots
    assert (
        results["AgentDataclass"]["per_object_bytes"]
        > results["AgentSlots"]["per_object_bytes"]
    )
