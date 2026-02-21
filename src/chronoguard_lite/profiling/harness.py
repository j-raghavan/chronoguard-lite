"""Profiling harness for the ChronoGuard Lite pipeline.

Runs a full request pipeline (policy evaluation, audit chain append,
chain verification, domain matching) under cProfile and reports the
top functions by cumulative time.

The harness is designed to be profiled, not to be fast. It exercises
every module built across Chapters 1-9 in a realistic sequence so
the profiler can identify real hotspots.
"""
from __future__ import annotations

import cProfile
import io
import pstats
import time
from dataclasses import dataclass

from chronoguard_lite.crypto.chain import AuditChain
from chronoguard_lite.crypto.hasher import generate_secret_key
from chronoguard_lite.crypto.verifier import ChainVerifier
from chronoguard_lite.domain.audit import AuditEntry
from chronoguard_lite.domain.decisions import AccessDecision
from chronoguard_lite.interceptor.evaluator import PolicyEvaluator
from chronoguard_lite.interceptor.protocol import InterceptRequest
from chronoguard_lite.profiling.load_generator import LoadGenerator, LoadRequest
from chronoguard_lite.strings.domain_matcher import DomainMatcher


@dataclass(slots=True)
class PipelineResult:
    """Timing results from a single pipeline run."""
    total_requests: int
    eval_time_ms: float
    chain_append_time_ms: float
    chain_verify_time_ms: float
    domain_match_time_ms: float
    total_time_ms: float
    requests_per_sec: float
    entries_in_chain: int
    cprofile_stats: str | None = None


def run_pipeline(
    total_requests: int = 10_000,
    num_agents: int = 50,
    num_policies: int = 20,
    num_domains: int = 200,
    verify_every: int = 1000,
    seed: int = 42,
    profile: bool = False,
) -> PipelineResult:
    """Run the full ChronoGuard Lite pipeline and return timing data.

    The pipeline for each request:
      1. Look up the agent and its assigned policies
      2. Evaluate policies against the request domain
      3. Create an AuditEntry and append it to the hash chain
      4. Every verify_every requests, run verify_full() on the chain

    If profile=True, wraps the entire run in cProfile and includes
    the stats in the result.
    """
    gen = LoadGenerator(
        num_agents=num_agents,
        num_domains=num_domains,
        num_policies=num_policies,
        total_requests=total_requests,
        seed=seed,
    )
    requests = gen.generate()

    # set up the pipeline components
    evaluator = PolicyEvaluator()
    secret = generate_secret_key()
    chain = AuditChain(secret_key=secret)

    # build a domain matcher from all policy rules for benchmarking
    patterns = set()
    for p in gen.policies:
        for rule in p.rules:
            patterns.add(rule.domain_pattern)
    matcher = DomainMatcher()
    for pat in patterns:
        matcher.add_pattern(pat)
    matcher.build()

    # agent index lookup
    agent_by_id = {a.agent_id: (i, a) for i, a in enumerate(gen.agents)}

    def _run():
        nonlocal eval_ms, chain_ms, verify_ms, match_ms
        for req_idx, req in enumerate(requests):
            info = agent_by_id.get(req.agent_id)
            if info is None:
                continue
            agent_idx, agent = info
            agent_policies = gen.policies_for_agent(agent_idx)

            # 1. policy evaluation
            t0 = time.perf_counter()
            fake_request = InterceptRequest(
                agent_id=str(req.agent_id),
                domain=req.domain,
                method="GET",
                path="/",
            )
            result = evaluator.evaluate(fake_request, agent, agent_policies)
            eval_ms += (time.perf_counter() - t0) * 1000

            # 2. domain match (trie-based)
            t0 = time.perf_counter()
            matcher.match(req.domain)
            match_ms += (time.perf_counter() - t0) * 1000

            # 3. audit chain append
            t0 = time.perf_counter()
            entry = AuditEntry.create(
                agent_id=req.agent_id,
                domain=req.domain,
                decision=result.decision,
                reason=result.reason,
            )
            chain.append(entry)
            chain_ms += (time.perf_counter() - t0) * 1000

            # 4. periodic verification
            if (req_idx + 1) % verify_every == 0:
                t0 = time.perf_counter()
                verifier = ChainVerifier(chain)
                verifier.verify_full()
                verify_ms += (time.perf_counter() - t0) * 1000

    eval_ms = 0.0
    chain_ms = 0.0
    verify_ms = 0.0
    match_ms = 0.0
    cprofile_text = None

    t_total_start = time.perf_counter()
    if profile:
        pr = cProfile.Profile()
        pr.enable()
        _run()
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(30)
        cprofile_text = s.getvalue()
    else:
        _run()
    total_ms = (time.perf_counter() - t_total_start) * 1000

    rps = total_requests / (total_ms / 1000) if total_ms > 0 else 0

    return PipelineResult(
        total_requests=total_requests,
        eval_time_ms=eval_ms,
        chain_append_time_ms=chain_ms,
        chain_verify_time_ms=verify_ms,
        domain_match_time_ms=match_ms,
        total_time_ms=total_ms,
        requests_per_sec=rps,
        entries_in_chain=len(chain),
        cprofile_stats=cprofile_text,
    )


def run_pipeline_optimized(
    total_requests: int = 10_000,
    num_agents: int = 50,
    num_policies: int = 20,
    num_domains: int = 200,
    verify_every: int = 1000,
    seed: int = 42,
    profile: bool = False,
) -> PipelineResult:
    """Run the pipeline with three optimizations applied.

    Optimization 1: Checkpoint verification
      Instead of verify_full() from genesis every time, verify only
      from the last checkpoint.

    Optimization 2: Cached policy evaluation
      Cache (agent_id, domain) -> decision to skip redundant evaluation
      for repeated requests.

    Optimization 3: Pre-sorted policies
      Sort policies once at setup, not on every evaluate() call.
    """
    gen = LoadGenerator(
        num_agents=num_agents,
        num_domains=num_domains,
        num_policies=num_policies,
        total_requests=total_requests,
        seed=seed,
    )
    requests = gen.generate()

    evaluator = PolicyEvaluator()
    secret = generate_secret_key()
    chain = AuditChain(secret_key=secret)

    patterns = set()
    for p in gen.policies:
        for rule in p.rules:
            patterns.add(rule.domain_pattern)
    matcher = DomainMatcher()
    for pat in patterns:
        matcher.add_pattern(pat)
    matcher.build()

    agent_by_id = {a.agent_id: (i, a) for i, a in enumerate(gen.agents)}

    # Optimization 2: result cache
    eval_cache: dict[tuple, AccessDecision] = {}

    # Optimization 3: pre-sort policies per agent
    sorted_agent_policies: dict[int, list] = {}
    for idx in range(len(gen.agents)):
        pols = gen.policies_for_agent(idx)
        sorted_agent_policies[idx] = sorted(pols, key=lambda p: p.priority)

    # Optimization 1: checkpoint tracking
    last_verified_seq = 0

    def _run():
        nonlocal eval_ms, chain_ms, verify_ms, match_ms, last_verified_seq
        for req_idx, req in enumerate(requests):
            info = agent_by_id.get(req.agent_id)
            if info is None:
                continue
            agent_idx, agent = info

            # 1. policy evaluation with cache
            t0 = time.perf_counter()
            cache_key = (req.agent_id, req.domain)
            cached = eval_cache.get(cache_key)
            if cached is not None:
                decision = cached
                reason = "cached"
            else:
                fake_request = InterceptRequest(
                    agent_id=str(req.agent_id),
                    domain=req.domain,
                    method="GET",
                    path="/",
                )
                result = evaluator.evaluate(
                    fake_request, agent, sorted_agent_policies[agent_idx]
                )
                decision = result.decision
                reason = result.reason
                eval_cache[cache_key] = decision
            eval_ms += (time.perf_counter() - t0) * 1000

            # 2. domain match (same as unoptimized)
            t0 = time.perf_counter()
            matcher.match(req.domain)
            match_ms += (time.perf_counter() - t0) * 1000

            # 3. audit chain append
            t0 = time.perf_counter()
            entry = AuditEntry.create(
                agent_id=req.agent_id,
                domain=req.domain,
                decision=decision,
                reason=reason,
            )
            chain.append(entry)
            chain_ms += (time.perf_counter() - t0) * 1000

            # 4. checkpoint verification (only verify from last checkpoint)
            if (req_idx + 1) % verify_every == 0:
                t0 = time.perf_counter()
                verifier = ChainVerifier(chain)
                current_len = len(chain)
                if last_verified_seq < current_len:
                    verifier.verify_range(last_verified_seq, current_len)
                    last_verified_seq = current_len
                verify_ms += (time.perf_counter() - t0) * 1000

    eval_ms = 0.0
    chain_ms = 0.0
    verify_ms = 0.0
    match_ms = 0.0
    cprofile_text = None

    t_total_start = time.perf_counter()
    if profile:
        pr = cProfile.Profile()
        pr.enable()
        _run()
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(30)
        cprofile_text = s.getvalue()
    else:
        _run()
    total_ms = (time.perf_counter() - t_total_start) * 1000

    rps = total_requests / (total_ms / 1000) if total_ms > 0 else 0

    return PipelineResult(
        total_requests=total_requests,
        eval_time_ms=eval_ms,
        chain_append_time_ms=chain_ms,
        chain_verify_time_ms=verify_ms,
        domain_match_time_ms=match_ms,
        total_time_ms=total_ms,
        requests_per_sec=rps,
        entries_in_chain=len(chain),
        cprofile_stats=cprofile_text,
    )
