import pytest
from stats import clamp, median, percentile, stddev, variance


def test_percentile_basic():
    xs = list(range(1, 101))
    assert percentile(xs, 0) == 1
    assert percentile(xs, 100) == 100
    assert percentile(xs, 50) == 50.5
    assert percentile(xs, 25) == 25.75


def test_percentile_single():
    assert percentile([5], 42) == 5


def test_median():
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5


def test_variance_stddev():
    assert variance([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(4.5714, abs=1e-3)
    assert stddev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.1381, abs=1e-3)


def test_clamp_within():
    assert clamp(5, 0, 10) == 5


def test_clamp_below():
    assert clamp(-5, 0, 10) == 0


def test_clamp_above():
    assert clamp(15, 0, 10) == 10


def test_clamp_edges():
    assert clamp(0, 0, 10) == 0
    assert clamp(10, 0, 10) == 10
