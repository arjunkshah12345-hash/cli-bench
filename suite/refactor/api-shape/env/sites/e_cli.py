"""Call site E: tiny CLI."""

import sys

from pkg.geometry import calc_rect_area, calc_rect_perimeter


def main():
    if len(sys.argv) != 3:
        print("usage: python e_cli.py WIDTH HEIGHT")
        return 1
    w, h = float(sys.argv[1]), float(sys.argv[2])
    print(f"area={calc_rect_area(w, h)} perimeter={calc_rect_perimeter(w, h)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
