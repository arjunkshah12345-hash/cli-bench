"""Spatial utilities. count_pairs_within is the hot function."""

import math


def count_pairs_within(points, r):
    """Count unordered pairs (i, j), i < j, with dist(points[i], points[j]) <= r.

    (Deliberately naive — this is the function to optimize.)
    """
    n = len(points)
    count = 0
    r2 = r * r
    for i in range(n):
        xi, yi = points[i]
        for j in range(i + 1, n):
            dx = points[j][0] - xi
            dy = points[j][1] - yi
            if dx * dx + dy * dy <= r2:
                count += 1
    return count


def total_path_length(points):
    """Sum of distances of a closed path (used elsewhere; leave as-is)."""
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points)):
        a, b = points[i], points[(i + 1) % len(points)]
        total += math.dist(a, b)
    return total
