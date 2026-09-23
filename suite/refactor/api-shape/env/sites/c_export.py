"""Call site C: JSON export."""

import json

from pkg.geometry import calc_rect_area


def export_shapes(rects, path):
    data = [{"width": w, "height": h, "area": calc_rect_area(w, h)} for w, h in rects]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return data
