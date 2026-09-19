"""Tests for CBZ filename stem sanitization."""

from comicdesk.utils.comic_filename import safe_comic_stem


def test_preserves_spaces_and_punctuation():
    assert safe_comic_stem("Avengers - 1 (2020)") == "Avengers - 1 (2020)"


def test_strips_path_separators_and_invalid_chars():
    assert safe_comic_stem("Serie/Name: test?") == "Serie - Name - test"


def test_series_colon_replaced_not_removed():
    assert safe_comic_stem("Fantastic Four: House of M") == "Fantastic Four - House of M"


def test_series_colon_spaced_dash_single_spaces():
    assert safe_comic_stem("Avengers: Ejemplo") == "Avengers - Ejemplo"
    assert safe_comic_stem("Avengers:  Ejemplo") == "Avengers - Ejemplo"


def test_literal_hyphen_in_metadata_unchanged():
    assert safe_comic_stem("Spider-Man") == "Spider-Man"
