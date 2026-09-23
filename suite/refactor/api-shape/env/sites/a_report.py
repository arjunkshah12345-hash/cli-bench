"""Call site A: report generation."""

from pkg.geometry import calc_circle_area, calc_rect_area


def build_report(rects, circles):
    lines = []
    for w, h in rects:
        lines.append(f"rect area={calc_rect_area(w, h)}")
    for r in circles:
        lines.append(f"circle area={calc_circle_area(r):.2f}")
    return "\n".join(lines)
