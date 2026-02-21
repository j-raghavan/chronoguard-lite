"""Thread-safe policy cache backed by striped hash maps.

Two StripedMap instances:
  - _policies: PolicyId -> Policy (the policies themselves)
  - _agent_policies: AgentId -> list[PolicyId] (which policies each agent has)

Thread safety strategy: copy-on-write. The update functions in
assign/remove return a NEW list rather than mutating in place. This
means a reader that called get() and received the old list can safely
iterate it without seeing partial mutations from a concurrent writer.
Copying a short list (typically < 10 items) is cheap compared to the
bug-hunting cost of shared mutable references leaking across threads.

Mapped from full ChronoGuard: infrastructure/persistence/redis/cache_service.py
The full version uses Redis GET/SET with TTL-based expiry. Here we build
the concurrency primitives from scratch so the reader understands what
Redis abstracts away.
"""
from __future__ import annotations

from uuid import UUID

from chronoguard_lite.concurrency.striped_map import StripedMap
from chronoguard_lite.domain.policy import Policy
from chronoguard_lite.domain.types import AgentId, PolicyId


class ConcurrentPolicyCache:
    """Thread-safe policy cache with striped locking.

    Args:
        num_stripes: Number of lock stripes for each internal map.
    """

    def __init__(self, num_stripes: int = 16) -> None:
        self._policies: StripedMap = StripedMap(num_stripes)
        self._agent_policies: StripedMap = StripedMap(num_stripes)

    def add_policy(self, policy: Policy) -> None:
        """Store a policy. Overwrites if policy_id already exists."""
        self._policies.put(policy.policy_id, policy)

    def get_policy(self, policy_id: PolicyId) -> Policy | None:
        """Retrieve a single policy by ID."""
        return self._policies.get(policy_id)

    def remove_policy(self, policy_id: PolicyId) -> bool:
        """Remove a policy. Returns True if it existed."""
        return self._policies.delete(policy_id)

    def assign_policy_to_agent(self, agent_id: AgentId, policy_id: PolicyId) -> None:
        """Add a policy to an agent's assignment list.

        Creates the assignment list if this is the agent's first policy.
        Silently ignores duplicates (idempotent).

        Uses StripedMap.update() to make the read-modify-write atomic:
        the write lock on the agent_id's stripe is held for the entire
        get-append-put sequence, preventing two threads from seeing
        the same list and each losing the other's append.
        """
        def _add(current):
            if policy_id not in current:
                return list(current) + [policy_id]  # copy-on-write: new list
            return current

        self._agent_policies.update(agent_id, _add, default=[])

    def remove_policy_from_agent(self, agent_id: AgentId, policy_id: PolicyId) -> bool:
        """Remove a policy from an agent's assignment list.

        Returns True if the policy was actually assigned.
        Uses atomic update to avoid read-modify-write races.
        """
        removed = [False]  # mutable container for closure

        def _remove(current):
            if policy_id in current:
                new = [pid for pid in current if pid != policy_id]  # copy-on-write
                removed[0] = True
                return new
            return current

        result_list = self._agent_policies.update(agent_id, _remove, default=[])
        if not result_list:
            self._agent_policies.delete(agent_id)
        return removed[0]

    def get_policies_for_agent(self, agent_id: AgentId) -> list[Policy]:
        """Get all policies assigned to an agent.

        Takes a snapshot of the policy ID list immediately after get()
        returns. Combined with copy-on-write in assign/remove, this
        ensures the reader iterates a stable list even if a writer
        replaces the mapping concurrently.
        """
        policy_ids = self._agent_policies.get(agent_id)
        if policy_ids is None:
            return []
        policy_ids = list(policy_ids)  # snapshot: safe to iterate outside lock
        result = []
        for pid in policy_ids:
            p = self._policies.get(pid)
            if p is not None:
                result.append(p)
        return result

    def policy_count(self) -> int:
        """Total number of cached policies."""
        return self._policies.size()

    def agent_count(self) -> int:
        """Total number of agents with policy assignments."""
        return self._agent_policies.size()
