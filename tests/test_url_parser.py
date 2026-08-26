"""Tests for URL parser module."""

import pytest
from cbl_maker.utils.url_parser import extract_comicvine_ids, extract_all_cv_ids


class TestExtractComicvineIds:
    """Tests for extract_comicvine_ids function."""

    def test_issue_url_with_trailing_slash(self):
        url = "https://comicvine.gamespot.com/doctor-strange/4000-139720/"
        result = extract_comicvine_ids(url)
        assert result["issue_id"] == "139720"
        assert result["series_id"] is None

    def test_issue_url_without_trailing_slash(self):
        url = "https://comicvine.gamespot.com/doctor-strange/4000-139720"
        result = extract_comicvine_ids(url)
        assert result["issue_id"] == "139720"

    def test_series_url(self):
        url = "https://comicvine.gamespot.com/avengers/4050-150431/"
        result = extract_comicvine_ids(url)
        assert result["series_id"] == "150431"
        assert result["issue_id"] is None

    def test_url_without_www(self):
        url = "https://comicvine.gamespot.com/batman/4000-12345"
        result = extract_comicvine_ids(url)
        assert result["issue_id"] == "12345"

    def test_invalid_url(self):
        url = "https://example.com/not-cv"
        result = extract_comicvine_ids(url)
        assert result["series_id"] is None
        assert result["issue_id"] is None

    def test_empty_string(self):
        result = extract_comicvine_ids("")
        assert result["series_id"] is None
        assert result["issue_id"] is None


class TestExtractAllCvIds:
    """Tests for extract_all_cv_ids function."""

    def test_single_url(self):
        text = "https://comicvine.gamespot.com/doctor-strange/4000-139720/"
        results = extract_all_cv_ids(text)
        assert len(results) == 1
        assert results[0]["issue_id"] == "139720"

    def test_multiple_urls(self):
        text = """
        https://comicvine.gamespot.com/dr-strange/4000-139720/
        https://comicvine.gamespot.com/avengers/4050-150431/
        """
        results = extract_all_cv_ids(text)
        assert len(results) == 2

    def test_no_urls(self):
        text = "No comic vine links here"
        results = extract_all_cv_ids(text)
        assert len(results) == 0
