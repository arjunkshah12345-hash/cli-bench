"""library.py — a small set of text utilities (the doc target)."""


def chunk_list(items, size):
    """Split a list into chunks of at most `size` items.

    The final chunk may be shorter. Raises ValueError if size < 1.
    """
    if size < 1:
        raise ValueError("size must be >= 1")
    return [items[i : i + size] for i in range(0, len(items), size)]


def flatten(nested, max_depth=10):
    """Flatten arbitrarily nested lists up to max_depth levels.

    Non-list items are kept as-is. Cycles are broken after max_depth.
    """
    out = []

    def rec(x, depth):
        if depth > max_depth:
            out.append(x)
            return
        if isinstance(x, list):
            for item in x:
                rec(item, depth + 1)
        else:
            out.append(x)

    rec(nested, 0)
    return out


def pluralize(word, count=None):
    """Naive English plural: -s, -es after s/x/z/ch/sh, consonant+y -> -ies.

    If count is given, returns the singular for count == 1.
    """
    if count == 1:
        return word
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def truncate_chars(s, n, ellipsis="…"):
    """Truncate to n chars; if truncated, ends with the ellipsis (counted within n).

    Raises ValueError if n < 0. Returns "" for n == 0.
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    if n == 0:
        return ""
    if len(s) < n:
        return s
    if n <= len(ellipsis):
        return ellipsis[:n]
    return s[: n - len(ellipsis)] + ellipsis


def valid_identifier(s):
    """True if s is a valid Python identifier (keyword-safe).

    Returns False for keywords like 'class' — keywords are NOT valid identifiers.
    """
    import keyword

    return s.isidentifier() and not keyword.iskeyword(s)
