import textproc


def test_importable():
    assert hasattr(textproc, "slugify")
    assert hasattr(textproc, "word_frequencies")
    assert hasattr(textproc, "truncate")
    assert hasattr(textproc, "camel_to_snake")
