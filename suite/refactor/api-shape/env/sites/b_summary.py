"""Call site B: summary stats."""

from pkg.geometry import calc_circle_circumference, calc_rect_perimeter


def summarize(rects, circles):
    per = sum(calc_rect_perimeter(w, h) for w, h in rects)
    cir = sum(calc_circle_circumference(r) for r in circles)
    return {"total_rect_perimeter": per, "total_circle_circumference": cir}
