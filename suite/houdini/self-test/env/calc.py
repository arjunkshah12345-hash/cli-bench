"""Tiny calculator (bug to be caught by the agent's test).

Known bug: divide() raises ZeroDivisionError for a zero divisor instead of
the documented ValueError.
"""


def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b
