"""Small statistics helpers."""

import math


def percentile(sorted_xs, p):
    """p in [0, 100]; linear interpolation on the sorted list."""
    if not sorted_xs:
        raise ValueError("empty")
    if p < 0 or p > 100:
        raise ValueError("p out of range")
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    k = (len(sorted_xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_xs[int(k)]
    return sorted_xs[f] + (sorted_xs[c] - sorted_xs[f]) * (k - f)


def median(xs):
    if not xs:
        raise ValueError("empty")
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def variance(xs):
    if len(xs) < 2:
        raise ValueError("need at least 2")
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def stddev(xs):
    return math.sqrt(variance(xs))


def clamp(x, lo, hi):
    """BUG: bounds swapped — clamps to the wrong range for many inputs."""
    if lo > hi:
        raise ValueError("lo > hi")
    return max(hi, min(lo, x))
