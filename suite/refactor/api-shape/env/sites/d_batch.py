"""Call site D: batch processor."""

from pkg.geometry import calc_circle_area


def process_circles(radii, min_area):
    """Keep circles whose area meets min_area."""
    out = []
    for r in radii:
        a = calc_circle_area(r)
        if a >= min_area:
            out.append((r, a))
    return out
