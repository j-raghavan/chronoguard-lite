"""Async TCP interceptor -- same logic as ThreadedInterceptor, no threads.

Architecture:
    Single thread, single event loop.
    asyncio.start_server() accepts connections.
    Each connection is a coroutine on the event loop.
    An asyncio.Queue buffers audit entries for a background flush task.

Why this is faster than the threaded version:
    - No thread creation/destruction overhead per connection
    - No GIL contention (only one thread, so the GIL is never contested)
    - No context-switch overhead from the OS scheduler
    - Coroutine switching is ~100ns vs ~10us for OS thread switches
    - The event loop handles thousands of idle connections with zero cost

The threaded version plateaued because the GIL serialized CPU-bound
evaluation work across threads. The async version runs the same
evaluation code on one thread, but spends almost zero time waiting:
while one coroutine awaits a socket read, others run their evaluation
logic. The bottleneck shifts from "GIL contention" to "actual CPU
work on one core."

Mapped from full ChronoGuard: infrastructure/envoy/ (proxy concept).
The production version uses Envoy with ext_authz gRPC, which is
internally async. This is the Python equivalent.
"""
from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

from chronoguard_lite.domain.agent import Agent
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import Policy
from chronoguard_lite.interceptor.async_protocol import (
    async_read_message,
    async_write_message,
)
from chronoguard_lite.interceptor.evaluator import PolicyEvaluator, EvaluationResult
from chronoguard_lite.interceptor.protocol import InterceptRequest, InterceptResponse
from chronoguard_lite.store.columnar_store import ColumnarAuditStore

log = logging.getLogger(__name__)

# Flush at most this many entries per cycle
_FLUSH_BATCH_SIZE = 1_000


class AsyncInterceptor:
    """Asyncio TCP server that intercepts agent requests.

    Args:
        host: Bind address (default "127.0.0.1").
        port: Bind port (default 0 = OS picks a free port).
        agents: mapping of agent_id string -> Agent.
        policies: mapping of policy_id string -> Policy.
        audit_store: where to log decisions.
        queue_maxsize: bounded audit queue size for backpressure.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        agents: dict[str, Agent] | None = None,
        policies: dict[str, Policy] | None = None,
        audit_store: ColumnarAuditStore | None = None,
        queue_maxsize: int = 50_000,
    ) -> None:
        self._host = host
        self._port = port
        self._agents = agents or {}
        self._policies = policies or {}
        self._audit_store = audit_store or ColumnarAuditStore()
        self._evaluator = PolicyEvaluator()
        self._queue: asyncio.Queue[AuditEntry | None] = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self._server: asyncio.AbstractServer | None = None
        self._flush_task: asyncio.Task | None = None
        self._requests_processed: int = 0
        self._queue_full_count: int = 0
        self._ready = asyncio.Event()
        self._bound_port: int = 0

    @property
    def address(self) -> tuple[str, int]:
        """Return (host, port) the server is bound to."""
        return (self._host, self._bound_port)

    @property
    def requests_processed(self) -> int:
        return self._requests_processed

    @property
    def queue_full_count(self) -> int:
        """Number of times a handler had to wait for queue space."""
        return self._queue_full_count

    @property
    def audit_store(self) -> ColumnarAuditStore:
        return self._audit_store

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        """Start the TCP server and background flush task."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self._host,
            self._port,
        )
        # Grab the actual bound port (important when port=0)
        socks = self._server.sockets
        if socks:
            self._bound_port = socks[0].getsockname()[1]

        self._flush_task = asyncio.ensure_future(self._flush_loop())
        self._ready.set()

    async def stop(self) -> None:
        """Graceful shutdown: stop accepting, drain audit queue, close."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Signal the flush task to drain and exit
        await self._queue.put(None)  # sentinel
        if self._flush_task is not None:
            await self._flush_task
            self._flush_task = None

    async def wait_ready(self, timeout: float = 5.0) -> None:
        """Wait until the server is accepting connections."""
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection.

        Same 10-step flow as ThreadedInterceptor._handle_connection,
        but every socket operation is an await instead of a blocking call.
        The policy evaluation is synchronous (fast CPU work, no await).
        """
        try:
            start_ns = time.perf_counter_ns()

            # 1-2: read and parse
            raw = await async_read_message(reader)
            req = InterceptRequest.from_bytes(raw)

            # 3: look up agent
            agent = self._agents.get(req.agent_id)
            if agent is None:
                result = EvaluationResult(
                    decision=AccessDecision.DENY,
                    reason=f"Unknown agent: {req.agent_id}",
                )
            else:
                # 4: gather policies for this agent
                agent_policies = [
                    self._policies[str(pid)]
                    for pid in agent.policy_ids
                    if str(pid) in self._policies
                ]
                # 5: evaluate (synchronous, fast, no await)
                result = self._evaluator.evaluate(req, agent, agent_policies)

            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

            # 6: create audit entry
            entry = AuditEntry.create(
                agent_id=UUID(req.agent_id) if agent is None else agent.agent_id,
                domain=req.domain,
                decision=result.decision,
                reason=result.reason,
                policy_id=result.policy_id,
                rule_id=result.rule_id,
                request_method=req.method,
                request_path=req.path,
                source_ip=req.source_ip,
                processing_time_ms=elapsed_ms,
            )

            # 7: queue audit entry (backpressure if queue is full)
            if self._queue.full():
                self._queue_full_count += 1
            await self._queue.put(entry)

            # 8: respond
            resp = InterceptResponse(
                decision=result.decision.name,
                reason=result.reason,
                processing_time_ms=elapsed_ms,
            )
            resp_bytes = resp.to_bytes()[4:]  # strip length prefix
            await async_write_message(writer, resp_bytes)

        except asyncio.IncompleteReadError:
            log.debug("Client disconnected mid-read")
        except ConnectionError:
            log.debug("Client connection reset")
        except Exception:
            log.exception("Error handling connection")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            self._requests_processed += 1

    async def _flush_loop(self) -> None:
        """Background task: drain the audit queue into the columnar store.

        Batches up to _FLUSH_BATCH_SIZE entries per cycle, or flushes
        every _FLUSH_INTERVAL_S seconds, whichever comes first.

        On shutdown, a None sentinel is pushed onto the queue. The loop
        drains all remaining entries before exiting.
        """
        while True:
            batch: list[AuditEntry] = []
            try:
                # Block until at least one entry arrives
                item = await self._queue.get()
                if item is None:
                    # Sentinel: drain remaining and exit
                    self._drain_remaining()
                    return
                batch.append(item)

                # Grab more without blocking, up to batch size
                while len(batch) < _FLUSH_BATCH_SIZE:
                    try:
                        item = self._queue.get_nowait()
                        if item is None:
                            self._flush_batch(batch)
                            self._drain_remaining()
                            return
                        batch.append(item)
                    except asyncio.QueueEmpty:
                        break

                self._flush_batch(batch)

            except Exception:
                log.exception("Error in audit flush loop")
                # Sleep briefly to avoid tight error loops
                await asyncio.sleep(0.5)

    def _flush_batch(self, batch: list[AuditEntry]) -> None:
        """Write a batch of entries to the columnar store."""
        for entry in batch:
            try:
                self._audit_store.append(entry)
            except ValueError:
                # Out-of-order timestamp: drop (same as ConcurrentAuditLog)
                pass

    def _drain_remaining(self) -> None:
        """Drain any entries left in the queue after the sentinel."""
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item is not None:
                    try:
                        self._audit_store.append(item)
                    except ValueError:
                        pass
            except asyncio.QueueEmpty:
                break
