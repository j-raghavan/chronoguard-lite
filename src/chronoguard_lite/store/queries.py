"""Query objects for the audit store.

TimeRange wraps a start/end pair of Unix timestamps.
Nothing fancy here, but it gives us a named type instead of
passing bare floats around, and a .contains() method the
prose examples can reference.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Closed time interval [start, end] in Unix epoch seconds.

    Both endpoints are inclusive to match the store's query_time_range
    semantics: start <= timestamp <= end.
    """
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(
                f"start ({self.start}) must be <= end ({self.end})"
            )

    def contains(self, timestamp: float) -> bool:
        """Check whether a timestamp falls within this range (inclusive)."""
        return self.start <= timestamp <= self.end

    @property
    def duration_seconds(self) -> float:
        """Length of the range in seconds."""
        return self.end - self.start
