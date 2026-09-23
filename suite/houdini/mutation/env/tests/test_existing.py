from validator import validate_email, validate_username


def test_username_basic():
    assert validate_username("alice") is True


def test_email_basic():
    assert validate_email("a@b.c") is True
