"""Request interceptor: threaded and async TCP servers + policy evaluation.

Chapter 3 builds the threaded interceptor. Chapter 5 rewrites it using
asyncio: same protocol, same evaluator, same audit store, dramatically
better throughput under concurrent connections.
"""
from chronoguard_lite.interceptor.protocol import (
    InterceptRequest,
    InterceptResponse,
    read_message,
    write_message,
)
from chronoguard_lite.interceptor.evaluator import PolicyEvaluator, EvaluationResult
from chronoguard_lite.interceptor.threaded import ThreadedInterceptor
from chronoguard_lite.interceptor.async_interceptor import AsyncInterceptor
from chronoguard_lite.interceptor.async_protocol import (
    async_read_message,
    async_write_message,
)

__all__ = [
    "InterceptRequest",
    "InterceptResponse",
    "read_message",
    "write_message",
    "PolicyEvaluator",
    "EvaluationResult",
    "ThreadedInterceptor",
    "AsyncInterceptor",
    "async_read_message",
    "async_write_message",
]
