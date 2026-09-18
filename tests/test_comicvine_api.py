"""Tests for Comic Vine API client."""

import pytest
from unittest.mock import patch, MagicMock

from comicdesk.services.comicvine_api import (
    ComicVineClient,
    InvalidAPIKeyError,
    RateLimitError
)


@pytest.fixture
def client():
    """Create a test client."""
    return ComicVineClient(api_key="test-key", cache_enabled=False)


class TestComicVineClient:
    """Tests for ComicVineClient."""

    @patch("comicdesk.services.comicvine_api.httpx.Client")
    def test_get_issue_success(self, mock_client_cls, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status_code": 1,
            "results": {
                "id": 139720,
                "volume": {"id": 23227, "name": "Doctor Strange"},
                "issue_number": "1",
                "cover_date": "1989-10-01",
                "site_detail_url": "https://comicvine.gamespot.com/doctor-strange/4000-139720/"
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_response

        issue = client.get_issue("139720")
        
        assert issue.id == "139720"
        assert issue.series_id == "23227"
        assert issue.series_name == "Doctor Strange"

    @patch("comicdesk.services.comicvine_api.httpx.Client")
    def test_invalid_api_key(self, mock_client_cls, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status_code": 100,
            "error": "Invalid API Key"
        }
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_response

        # validate_api_key should return False for invalid key
        result = client.validate_api_key()
        assert result is False

    def test_rate_limiting(self, client):
        """Test that rate limiting is enforced."""
        import time
        client._last_request_time = time.time()
        
        # Should not sleep if enough time has passed
        client._last_request_time = time.time() - 2
        client._rate_limit()  # Should not block

    @patch("comicdesk.services.comicvine_api.httpx.Client")
    def test_get_issue_parses_store_date(self, mock_client_cls, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status_code": 1,
            "results": {
                "id": 1143298,
                "volume": {"id": 162531, "name": "Red Hulk"},
                "issue_number": "10",
                "cover_date": "2026-01-01",
                "store_date": "2025-11-12",
                "site_detail_url": "https://comicvine.gamespot.com/red-hulk-10-red-flag/4000-1143298/"
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_response

        issue = client.get_issue("1143298")

        assert issue.cover_date == "2026-01-01"
        assert issue.store_date == "2025-11-12"

    @patch("comicdesk.services.comicvine_api.httpx.Client")
    def test_get_issue_store_date_defaults_to_empty(self, mock_client_cls, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status_code": 1,
            "results": {
                "id": 100,
                "volume": {"id": 200, "name": "Test"},
                "issue_number": "1",
                "cover_date": "2020-01-01",
                "site_detail_url": "https://comicvine.test/4000-100/"
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_response

        issue = client.get_issue("100")

        assert issue.store_date == ""

    @patch("comicdesk.services.comicvine_api.httpx.Client")
    def test_search_issue_uses_expanded_result_limit(self, mock_client_cls, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status_code": 1, "results": []}
        mock_response.raise_for_status = MagicMock()
        mock_get = mock_client_cls.return_value.__enter__.return_value.get
        mock_get.return_value = mock_response

        client.search_issue("Batman #1")

        params = mock_get.call_args.kwargs.get("params") or mock_get.call_args[0][1]
        assert params["limit"] == 20

    @patch("comicdesk.services.comicvine_api.httpx.Client")
    def test_invalid_json_is_reported_as_api_error(self, mock_client_cls, client):
        from comicdesk.services.comicvine_api import ComicVineError

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("not json")
        mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_response

        with pytest.raises(ComicVineError, match="invalid JSON"):
            client.search_issue("Batman #1")
