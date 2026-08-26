"""Tests for Comic Vine enrichment flow."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cbl_maker.models import Comic, ComicVineIssue
from cbl_maker.ui.comic_list import EnrichWorker


def _make_comic(**kwargs) -> Comic:
    """Create a Comic with defaults."""
    defaults = {
        "path": Path("/fake/comic.cbz"),
        "title": "Test Comic",
        "series_name": "",
        "volume": "",
        "issue_number": "",
        "year": "",
        "web_links": [],
        "cv_series_id": None,
        "cv_issue_id": None,
    }
    defaults.update(kwargs)
    return Comic(**defaults)


def _mock_issue(issue_id="100", series_id="200", series_name="Test Series",
                volume="1", issue_number="1", cover_date="2020-01-01"):
    """Create a mock ComicVineIssue."""
    return ComicVineIssue(
        id=issue_id,
        series_id=series_id,
        series_name=series_name,
        volume=volume,
        issue_number=issue_number,
        cover_date=cover_date,
        web_url=f"https://comicvine.gamespot.com/test/4000-{issue_id}/"
    )


class TestEnrichWorker:
    """Tests for EnrichWorker enrichment logic."""

    def _run_worker(self, comics, api_key="test-key"):
        """Run EnrichWorker synchronously for testing."""
        worker = EnrichWorker(comics, api_key)
        worker.run()
        return worker

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_with_issue_id_fetches_series(self, mock_client_cls):
        """Comic with cv_issue_id should fetch series_id via get_issue."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_issue.return_value = _mock_issue(
            issue_id="139720", series_id="23227", series_name="Doctor Strange"
        )

        comic = _make_comic(cv_issue_id="139720")
        self._run_worker([comic])

        assert comic.cv_series_id == "23227"
        assert comic.series_name == "Doctor Strange"
        mock_client.get_issue.assert_called_once_with("139720")

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_with_url_parse_then_fetch(self, mock_client_cls):
        """Comic with web_link but no IDs should parse URL then fetch issue."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_issue.return_value = _mock_issue(
            issue_id="139720", series_id="23227"
        )

        comic = _make_comic(
            web_links=["https://comicvine.gamespot.com/doctor-strange/4000-139720/"]
        )
        self._run_worker([comic])

        assert comic.cv_issue_id == "139720"
        assert comic.cv_series_id == "23227"
        mock_client.get_issue.assert_called_once_with("139720")

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_search_by_title_and_issue(self, mock_client_cls):
        """Comic with no IDs should search by title + issue number."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search_issue.return_value = [_mock_issue(
            issue_id="500", series_id="600", series_name="Batman"
        )]

        comic = _make_comic(series_name="Batman", issue_number="1")
        self._run_worker([comic])

        assert comic.cv_issue_id == "500"
        assert comic.cv_series_id == "600"
        mock_client.search_issue.assert_called_once_with("Batman #1")

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_skips_comic_with_both_ids(self, mock_client_cls):
        """Comic with both IDs should be skipped."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        comic = _make_comic(cv_series_id="100", cv_issue_id="200")
        self._run_worker([comic])

        mock_client.get_issue.assert_not_called()
        mock_client.search_issue.assert_not_called()

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_fills_missing_metadata(self, mock_client_cls):
        """Enrichment should persist all missing normalized issue metadata."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_issue.return_value = _mock_issue(
            series_name="X-Men", volume="3", issue_number="5", cover_date="2019-06-15"
        )

        comic = _make_comic(cv_issue_id="999")
        self._run_worker([comic])

        assert comic.series_name == "X-Men"
        assert comic.volume == "3"
        assert comic.issue_number == "5"
        assert comic.year == "2019"
        assert comic.month == "06"
        assert comic.day == "15"
        assert comic.web_links == [
            "https://comicvine.gamespot.com/test/4000-999/"
        ]

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_does_not_overwrite_existing_fields(self, mock_client_cls):
        """Enrichment should NOT overwrite manual fields or links."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_issue.return_value = _mock_issue(
            series_name="New Name", volume="99", issue_number="99"
        )

        comic = _make_comic(
            cv_issue_id="999",
            series_name="Existing Name",
            volume="1",
            issue_number="10",
            year="2001",
            month="02",
            day="03",
            web_links=["https://example.test/manual"],
        )
        self._run_worker([comic])

        assert comic.series_name == "Existing Name"
        assert comic.volume == "1"
        assert comic.issue_number == "10"
        assert comic.year == "2001"
        assert comic.month == "02"
        assert comic.day == "03"
        assert comic.web_links == [
            "https://example.test/manual",
            "https://comicvine.gamespot.com/test/4000-999/",
        ]

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_skips_already_enriched_issue(self, mock_client_cls):
        """A comic with both Comic Vine IDs must not trigger another lookup."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        comic = _make_comic(
            cv_issue_id="999",
            cv_series_id="888",
            series_name="Persisted Series",
            year="2019",
        )

        self._run_worker([comic])

        mock_client.get_issue.assert_not_called()
        mock_client.search_issue.assert_not_called()
        assert comic.series_name == "Persisted Series"
        assert comic.year == "2019"

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_handles_no_search_results(self, mock_client_cls):
        """Enrichment should handle empty search results gracefully."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search_issue.return_value = []

        comic = _make_comic(series_name="Unknown", issue_number="1")
        self._run_worker([comic])

        assert comic.cv_issue_id is None
        assert comic.cv_series_id is None

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_handles_api_error(self, mock_client_cls):
        """Enrichment should handle ComicVineError without crashing."""
        from cbl_maker.services.comicvine_api import ComicVineError

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_issue.side_effect = ComicVineError("API down")

        comic = _make_comic(cv_issue_id="139720")
        # Should not raise
        self._run_worker([comic])

        # comic should remain unchanged
        assert comic.cv_series_id is None

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_cancellation(self, mock_client_cls):
        """Enrichment should stop when cancelled."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_issue.return_value = _mock_issue()

        comics = [_make_comic(cv_issue_id=str(i)) for i in range(10)]
        worker = EnrichWorker(comics, "test-key")

        # Cancel after first comic
        original_enrich = worker._enrich_comic
        call_count = 0

        def counting_enrich(comic, client):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                worker._cancelled = True
            original_enrich(comic, client)

        worker._enrich_comic = counting_enrich
        worker.run()

        # Should not have processed all comics
        assert call_count < 10

    @patch("cbl_maker.ui.comic_list.ComicVineClient")
    def test_enrich_search_no_series_name_skips(self, mock_client_cls):
        """Comic with no series_name and no IDs should be skipped (no search possible)."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        comic = _make_comic()  # no series_name, no issue_number, no IDs
        self._run_worker([comic])

        mock_client.search_issue.assert_not_called()
        mock_client.get_issue.assert_not_called()
