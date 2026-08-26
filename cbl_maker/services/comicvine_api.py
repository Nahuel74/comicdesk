"""Comic Vine API client with caching and rate limiting."""

import time
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from cbl_maker.models import ComicVineIssue
from cbl_maker.config import CONFIG_DIR

logger = logging.getLogger(__name__)

API_BASE = "https://comicvine.gamespot.com/api"
CACHE_DIR = CONFIG_DIR / "cache"


class ComicVineError(Exception):
    """Base exception for Comic Vine API errors."""
    pass


class RateLimitError(ComicVineError):
    """Raised when rate limit is exceeded."""
    pass


class InvalidAPIKeyError(ComicVineError):
    """Raised when API key is invalid."""
    pass


class ComicVineClient:
    """Client for Comic Vine API with rate limiting and caching."""

    def __init__(self, api_key: str, cache_enabled: bool = True):
        self.api_key = api_key
        self.cache_enabled = cache_enabled
        self._last_request_time = 0.0
        self._cache: dict[str, dict] = {}
        
        if cache_enabled:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = CACHE_DIR / "api_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.cache_enabled:
            return
        cache_file = CACHE_DIR / "api_cache.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(self._cache, f)
        except IOError as e:
            logger.warning(f"Failed to save cache: {e}")

    def _rate_limit(self) -> None:
        """Enforce rate limiting (1 request per second)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request with rate limiting and caching."""
        # Build cache key
        cache_key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        
        # Check cache
        if self.cache_enabled and cache_key in self._cache:
            logger.debug(f"Cache hit: {cache_key}")
            return self._cache[cache_key]
        
        # Rate limit
        self._rate_limit()
        
        # Make request
        params["api_key"] = self.api_key
        params["format"] = "json"
        
        url = f"{API_BASE}/{endpoint}"
        
        try:
            with httpx.Client() as client:
                response = client.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 420:
                raise RateLimitError("Rate limit exceeded")
            raise ComicVineError(f"HTTP error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise ComicVineError(f"Request failed: {e}")
        
        # Check for API errors
        status_code = data.get("status_code")
        if status_code == 100:
            raise InvalidAPIKeyError("Invalid API key")
        elif status_code != 1:
            raise ComicVineError(f"API error: {data.get('error', 'Unknown')}")
        
        # Cache response
        if self.cache_enabled:
            self._cache[cache_key] = data
            self._save_cache()
        
        return data

    def get_issue(self, issue_id: str) -> ComicVineIssue:
        """
        Get issue details by ID.
        
        Args:
            issue_id: Comic Vine issue ID (e.g., "139720")
            
        Returns:
            ComicVineIssue with issue details
        """
        data = self._request(f"issue/4000-{issue_id}", {
            "field_list": "id,volume,issue_number,name,cover_date,site_detail_url"
        })
        
        result = data.get("results", {})
        volume = result.get("volume", {})
        
        return ComicVineIssue(
            id=str(result.get("id", issue_id)),
            series_id=str(volume.get("id", "")),
            series_name=volume.get("name", ""),
            volume=str(volume.get("volume_number", "")),
            issue_number=str(result.get("issue_number", "")),
            cover_date=result.get("cover_date", ""),
            web_url=result.get("site_detail_url", "")
        )

    def get_volume(self, volume_id: str) -> dict:
        """
        Get volume details by ID.
        
        Args:
            volume_id: Comic Vine volume ID (e.g., "23227")
            
        Returns:
            Dict with volume details
        """
        data = self._request(f"volume/4050-{volume_id}", {
            "field_list": "id,name,start_year,site_detail_url"
        })
        return data.get("results", {})

    def search_issue(self, query: str) -> list[ComicVineIssue]:
        """
        Search for issues by name.
        
        Args:
            query: Search query
            
        Returns:
            List of matching ComicVineIssue objects
        """
        data = self._request("search", {
            "query": query,
            "resources": "issue",
            "limit": 10
        })
        
        issues = []
        for result in data.get("results", []):
            volume = result.get("volume", {})
            issues.append(ComicVineIssue(
                id=str(result.get("id", "")),
                series_id=str(volume.get("id", "")),
                series_name=volume.get("name", ""),
                volume=str(volume.get("volume_number", "")),
                issue_number=str(result.get("issue_number", "")),
                cover_date=result.get("cover_date", ""),
                web_url=result.get("site_detail_url", "")
            ))
        
        return issues

    def validate_api_key(self) -> bool:
        """Validate the API key by making a test request."""
        try:
            self._request("genres", {"limit": 1})
            return True
        except InvalidAPIKeyError:
            return False
        except ComicVineError:
            return False
