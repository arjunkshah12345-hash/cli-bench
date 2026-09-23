"""Feature code with a dependency used but not declared."""

import math


def compound_growth(principal, rate, periods):
    """Compound growth; uses stdlib math only."""
    return principal * (1 + rate) ** periods


def area_circle(radius):
    return math.pi * radius * radius
