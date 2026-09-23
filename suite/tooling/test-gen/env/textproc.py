"""Text processing utilities (currently untested)."""


def slugify(s, sep="-"):
    """Lowercase, strip, collapse non-alphanumerics into sep, collapse repeats."""
    out = []
    prev_sep = True
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
        else:
            if not prev_sep:
                out.append(sep)
            prev_sep = True
    res = "".join(out)
    if res.endswith(sep):
        res = res[:-1]
    return res


def word_frequencies(text):
    """Case-insensitive word counts; words are alphanumerics possibly with internal apostrophes."""
    import re

    words = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq


def truncate(s, n, ellipsis="..."):
    """Truncate to n chars; if truncated, end with ellipsis (ellipsis counts within n)."""
    if n < 0:
        raise ValueError("n must be >= 0")
    if n == 0:
        return ""
    if len(s) <= n:
        return s
    if n <= len(ellipsis):
        return ellipsis[:n]
    return s[: n - len(ellipsis)] + ellipsis


def camel_to_snake(name):
    """Convert CamelCase / camelCase to snake_case; acronym runs split sensibly."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            prev = name[i - 1]
            if (
                prev.islower()
                or prev.isdigit()
                or (prev.isupper() and i + 1 < len(name) and name[i + 1].islower())
            ):
                out.append("_")
        out.append(ch.lower())
    return "".join(out)
