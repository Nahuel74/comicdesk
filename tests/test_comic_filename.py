"""Tests for CBZ filename stem sanitization."""

from comicdesk.utils.comic_filename import safe_comic_stem


def test_preserves_spaces_and_punctuation():
    assert safe_comic_stem("Avengers - 1 (2020)") == "Avengers - 1 (2020)"


def test_strips_path_separators_and_invalid_chars():
    assert safe_comic_stem("Serie/Name: test?") == "SerieName test"
