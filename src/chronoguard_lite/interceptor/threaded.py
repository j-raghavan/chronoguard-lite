"""Threaded TCP interceptor -- the first version, deliberately GIL-bound.

Architecture:
    Main thread: socket.accept() in a loop
    Worker threads: ThreadPoolExecutor handles each connection
    Per-connection flow: read -> evaluate -> log -> respond -> close

This version works correctly but under load you'll observe:
    - Throughput plateaus regardless of thread count
    - CPU pins to ~100% of ONE core (GIL serializes Python bytecode)
    - Adding threads past a point only adds context-switch overhead

The plateau motivates Chapter 4 (better locking) and Chapter 5
(async rewrite that sidesteps the GIL for I/O).

Mapped from full ChronoGuard: infrastructure/envoy/ (proxy concept).
The full version uses Envoy proxy with ext_authz gRPC filter.
This Lite version is a raw TCP server -- no HTTP, no TLS, no proxy.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from chronoguard_lite.domain.agent import Agent
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.domain.policy import Policy
from chronoguard_lite.interceptor.evaluator import PolicyEvaluator, EvaluationResult
from chronoguard_lite.interceptor.protocol import (
    InterceptRequest,
    InterceptResponse,
    read_message,
    write_message,
)
from chronoguard_lite.store.columnar_store import ColumnarAuditStore

log = logging.getLogger(__name__)


class ThreadedInterceptor:
    """TCP server that intercepts agent requests using a thread pool.

    Args:
        host: Bind address (default "127.0.0.1")
        port: Bind port (default 0 = OS picks a free port)
        max_workers: Thread pool size (default 16)
        agents: mapping of agent_id string -> Agent
        policies: mapping of policy_id string -> Policy
        audit_store: where to log decisions
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        max_workers: int = 16,
        agents: dict[str, Agent] | None = None,
        policies: dict[str, Policy] | None = None,
        audit_store: ColumnarAuditStore | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._max_workers = max_workers
        self._agents = agents or {}
        self._policies = policies or {}
        self._audit_store = audit_store or ColumnarAuditStore()
        self._evaluator = PolicyEvaluator()
        self._server_socket: socket.socket | None = None
        self._running = False
        self._executor: ThreadPoolExecutor | None = None
        self._requests_processed = 0
        self._lock = threading.Lock()
        self._ready = threading.Event()  # signals when accept loop is running

    @property
    def address(self) -> tuple[str, int]:
        """Return (host, port) the server is bound to.

        Useful when port=0 (OS-assigned). Only valid after start().
        """
        if self._server_socket is None:
            raise RuntimeError("Server not started")
        return self._server_socket.getsockname()

    def start(self) -> None:
        """Bind socket and start accept loop. Blocks until stop() is called."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self._host, self._port))
        self._server_socket.listen(128)
        self._server_socket.settimeout(0.5)
        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        self._ready.set()
        self._accept_loop()

    def stop(self) -> None:
        """Graceful shutdown: stop accepting, drain thread pool, close socket."""
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

    def wait_ready(self, timeout: float = 5.0) -> None:
        """Block until the accept loop is running. For test setup."""
        self._ready.wait(timeout=timeout)

    def _accept_loop(self) -> None:
        """Accept connections and submit to thread pool.

        Uses socket timeout (0.5s) to periodically check self._running.
        """
        while self._running:
            try:
                client_sock, addr = self._server_socket.accept()
                self._executor.submit(self._handle_connection, client_sock, addr)
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed by stop()

    def _handle_connection(
        self, client_sock: socket.socket, addr: tuple[str, int]
    ) -> None:
        """Handle a single client connection.

        Steps:
        1. Read request via length-prefixed protocol
        2. Parse InterceptRequest from JSON
        3. Look up agent in self._agents
        4. Gather agent's policies from self._policies
        5. Evaluate with PolicyEvaluator
        6. Create AuditEntry from the result
        7. Append entry to the audit store
        8. Send InterceptResponse back to client
        9. Close the connection
        10. Bump the requests_processed counter

        Every step except the socket read/write is CPU work that
        holds the GIL. This is why adding threads doesn't help.
        """
        try:
            start_ns = time.perf_counter_ns()

            # 1-2: read and parse
            raw = read_message(client_sock)
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
                # 5: evaluate
                result = self._evaluator.evaluate(req, agent, agent_policies)

            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

            # 6-7: audit entry
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
            self._audit_store.append(entry)

            # 8: respond
            resp = InterceptResponse(
                decision=result.decision.name,
                reason=result.reason,
                processing_time_ms=elapsed_ms,
            )
            resp_payload = resp.to_bytes()[4:]  # strip length prefix, write_message adds its own
            write_message(client_sock, resp_payload)

        except ConnectionError:
            log.debug("Client %s disconnected", addr)
        except Exception:
            log.exception("Error handling %s", addr)
        finally:
            try:
                client_sock.close()
            except OSError:
                pass
            # 10: bump counter
            with self._lock:
                self._requests_processed += 1

    @property
    def requests_processed(self) -> int:
        """Total requests handled (thread-safe read)."""
        with self._lock:
            return self._requests_processed

    @property
    def audit_store(self) -> ColumnarAuditStore:
        """Access the audit store (for test assertions)."""
        return self._audit_store
