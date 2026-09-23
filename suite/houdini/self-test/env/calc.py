"""Tiny calculator (bug to be caught by the agent's test)."""


def divide(a, b):
    if b == 0:
        raise ValueError("division by zero")
    return a / b
