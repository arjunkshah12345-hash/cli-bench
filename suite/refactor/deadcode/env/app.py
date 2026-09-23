import math


def add(a, b):
    """Add two numbers."""
    return a + b


def sub(a, b):
    """Subtract b from a."""
    return a - b


def mul(a, b):
    """Multiply two numbers."""
    return a * b


def legacy_multiply(a, b):
    """Old helper kept around 'just in case'. Should be pruned."""
    result = 0
    for _ in range(abs(int(b))):
        result += a
    if b < 0:
        result = -result
    return result


def circle_area(radius):
    """Area of a circle."""
    return math.pi * radius * radius


def circle_area_v2(radius):
    """Experimental variant, superseded by circle_area. Should be pruned."""
    return 3.14159 * radius * radius


def mean(xs):
    if not xs:
        raise ValueError("empty")
    return sum(xs) / len(xs)


def stddev(xs):
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def unused_util(x):
    """Never called anywhere. Should be pruned."""
    return x * 2 + 1
