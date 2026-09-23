"""Input validation helpers."""


def validate_username(u):
    """3-20 chars, letters/digits/underscore, must start with a letter."""
    if not isinstance(u, str):
        return False
    if not (3 <= len(u) <= 20):
        return False
    if not u[0].isalpha():
        return False
    return u.isidentifier()


def validate_email(e):
    """Rough shape: non-empty local part, '@', dotted domain."""
    if not isinstance(e, str):
        return False
    if e.count("@") != 1:
        return False
    local, domain = e.split("@")
    if not local or not domain:
        return False
    return "." in domain and " " not in e
