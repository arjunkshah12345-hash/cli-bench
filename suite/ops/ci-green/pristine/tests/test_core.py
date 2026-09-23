import math

import pytest
from src.pkg_with_deps import area_circle, compound_growth

pytestmark = [pytest.mark.unit, pytest.mark.api]


def test_growth():
    assert compound_growth(100, 0.1, 2) == pytest.approx(121.0)


def test_growth_zero_periods():
    assert compound_growth(100, 0.1, 0) == 100


def test_area():
    assert area_circle(1) == pytest.approx(math.pi)
