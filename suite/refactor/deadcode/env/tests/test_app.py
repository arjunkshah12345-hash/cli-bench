import math

import pytest
from app import add, circle_area, mean, mul, stddev, sub


def test_add():
    assert add(2, 3) == 5


def test_sub():
    assert sub(5, 2) == 3


def test_mul():
    assert mul(3, 4) == 12


def test_circle_area():
    assert abs(circle_area(1.0) - math.pi) < 1e-9


def test_mean():
    assert mean([1, 2, 3]) == 2.0


def test_mean_empty():
    with pytest.raises(ValueError):
        mean([])


def test_stddev():
    assert abs(stddev([2, 4, 4, 4, 5, 5, 7, 9]) - 2.0) < 1e-9
