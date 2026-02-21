"""Tests for TimeRange query objects."""
import pytest

from chronoguard_lite.store.queries import TimeRange


def test_create_time_range():
    tr = TimeRange(start=100.0, end=200.0)
    assert tr.start == 100.0
    assert tr.end == 200.0


def test_invalid_range_raises():
    with pytest.raises(ValueError, match="start.*must be <= end"):
        TimeRange(start=200.0, end=100.0)


def test_contains_inside():
    tr = TimeRange(start=100.0, end=200.0)
    assert tr.contains(150.0) is True


def test_contains_boundaries():
    tr = TimeRange(start=100.0, end=200.0)
    assert tr.contains(100.0) is True   # inclusive start
    assert tr.contains(200.0) is True   # inclusive end


def test_contains_outside():
    tr = TimeRange(start=100.0, end=200.0)
    assert tr.contains(99.99) is False
    assert tr.contains(200.01) is False


def test_duration():
    tr = TimeRange(start=100.0, end=200.0)
    assert tr.duration_seconds == 100.0


def test_zero_width_range():
    """A range where start == end should contain exactly that point."""
    tr = TimeRange(start=150.0, end=150.0)
    assert tr.contains(150.0) is True
    assert tr.contains(150.1) is False
    assert tr.duration_seconds == 0.0


def test_frozen():
    tr = TimeRange(start=100.0, end=200.0)
    with pytest.raises(AttributeError):
        tr.start = 50.0  # type: ignore[misc]
