"""Request interceptor: threaded TCP server + policy evaluation.

Chapter 3 builds the first interceptor -- a threaded TCP server that
receives agent requests, evaluates them against policies, and logs
audit entries. Under load, the GIL bottleneck becomes visible:
throughput plateaus no matter how many threads you add.
"""
from chronoguard_lite.interceptor.protocol import (
    InterceptRequest,
    InterceptResponse,
    read_message,
    write_message,
)
from chronoguard_lite.interceptor.evaluator import PolicyEvaluator, EvaluationResult
from chronoguard_lite.interceptor.threaded import ThreadedInterceptor

__all__ = [
    "InterceptRequest",
    "InterceptResponse",
    "read_message",
    "write_message",
    "PolicyEvaluator",
    "EvaluationResult",
    "ThreadedInterceptor",
]
