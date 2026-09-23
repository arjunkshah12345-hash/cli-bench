"""Geometry helpers (internal module, public API used across the project)."""


def calc_rect_area(width, height):
    if width < 0 or height < 0:
        raise ValueError("negative dimension")
    return width * height


def calc_rect_perimeter(width, height):
    if width < 0 or height < 0:
        raise ValueError("negative dimension")
    return 2 * (width + height)


def calc_circle_area(radius):
    if radius < 0:
        raise ValueError("negative radius")
    return 3.141592653589793 * radius * radius


def calc_circle_circumference(radius):
    if radius < 0:
        raise ValueError("negative radius")
    return 2 * 3.141592653589793 * radius
