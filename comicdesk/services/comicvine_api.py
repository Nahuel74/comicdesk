"""Comic Vine API client with caching and rate limiting."""

import time
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from comicdesk.models import ComicVineIssue, ComicVineVolume
from comicdesk.config import CONFIG_DIR

logger = logging.getLogger(__name__)

API_BASE = "https://comicvine.gamespot.com/api"
CACHE_DIR = CONFIG_DIR / "cache"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"


class ComicVineError(Exception):
    """Base exception for Comic Vine API errors."""
    pass


class RateLimitError(ComicVineError):
    """Raised when rate limit is exceeded."""
    pass


class InvalidAPIKeyError(ComicVineError):
    """Raised when API key is invalid."""
    pass


def _image_url_from_result(result: dict) -> str:
    image = result.get("image")
    if not isinstance(image, dict):
        return ""
    for key in ("thumb_url", "small_url", "medium_url", "icon_url", "super_url"):
        url = str(image.get(key) or "").strip()
        if url and "no-image" not in url.casefold():
            return url.replace("http://", "https://", 1)
    return ""


def _parse_issue_response(result: dict) -> ComicVineIssue:
    """Parse API response into ComicVineIssue."""
    if not isinstance(result, dict):
        raise ComicVineError("Comic Vine returned an invalid issue")
    volume = result.get("volume") or {}
    if not isinstance(volume, dict):
        volume = {}
    return ComicVineIssue(
        id=str(result.get("id", "")),
        series_id=str(volume.get("id", "")),
        series_name=volume.get("name", ""),
        volume=str(volume.get("volume_number", "")),
        issue_number=str(result.get("issue_number", "")),
        cover_date=result.get("cover_date", ""),
        store_date=result.get("store_date") or "",
        web_url=result.get("site_detail_url", ""),
        name=result.get("name") or "",
        description=result.get("description") or "",
        publisher=(result.get("publisher") or {}).get("name", "") if isinstance(result.get("publisher"), dict) else "",
        genres=_names(result.get("genres")),
        character_credits=_names(result.get("character_credits")),
        concept_credits=_names(result.get("concept_credits")),
        location_credits=_names(result.get("location_credits")),
        person_credits=result.get("person_credits") or [],
        story_arc_credits=_names(result.get("story_arc_credits")),
        team_credits=_names(result.get("team_credits")),
        age_rating=result.get("age_rating") or "",
        volume_start_year=str(volume.get("start_year") or ""),
        volume_count_of_issues=str(volume.get("count_of_issues") or ""),
        image_url=_image_url_from_result(result),
    )


def _parse_volume_response(result: dict) -> ComicVineVolume:
    """Parse API response into ComicVineVolume."""
    if not isinstance(result, dict):
        raise ComicVineError("Comic Vine returned an invalid volume")
    return ComicVineVolume(
        id=str(result.get("id", "")),
        name=result.get("name") or "",
        start_year=str(result.get("start_year") or ""),
        web_url=result.get("site_detail_url") or "",
        count_of_issues=str(result.get("count_of_issues") or ""),
        description=result.get("description") or "",
        publisher=(result.get("publisher") or {}).get("name", "") if isinstance(result.get("publisher"), dict) else "",
        genres=_names(result.get("genres")),
        character_credits=_names(result.get("character_credits")),
        concept_credits=_names(result.get("concept_credits")),
        location_credits=_names(result.get("location_credits")),
        person_credits=result.get("person_credits") or [],
        team_credits=_names(result.get("team_credits")),
        age_rating=result.get("age_rating") or "",
        image_url=_image_url_from_result(result),
    )


def _names(values) -> list[str]:
    return [str(item.get("name", "")).strip() for item in (values or [])
            if isinstance(item, dict) and item.get("name")]


ISSUE_FIELDS = ("id,volume,issue_number,name,cover_date,store_date,site_detail_url,description,"
                "publisher,genres,character_credits,concept_credits,location_credits,"
                "person_credits,story_arc_credits,team_credits,age_rating,image")
VOLUME_FIELDS = ("id,name,start_year,count_of_issues,site_detail_url,description,"
                 "publisher,genres,character_credits,concept_credits,location_credits,"
                 "person_credits,team_credits,age_rating,image")


class ComicVineClient:
    """Client for Comic Vine API with rate limiting and caching."""

    def __init__(self, api_key: str, cache_enabled: bool = True):
        self.api_key = api_key
        self.cache_enabled = cache_enabled
        self._last_request_time = 0.0
        self._cache: dict[str, dict] = {}
        self._cookies: dict[str, str] = {}
        
        if cache_enabled:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = CACHE_DIR / "api_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    value = json.load(f)
                    self._cache = value if isinstance(value, dict) else {}
            except (json.JSONDecodeError, IOError, OSError):
                self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self.cache_enabled:
            return
        cache_file = CACHE_DIR / "api_cache.json"
        tmp_path = None
        try:
            fd, name = tempfile.mkstemp(dir=CACHE_DIR, suffix=".json")
            os.close(fd)
            tmp_path = Path(name)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
            os.replace(tmp_path, cache_file)
        except (IOError, OSError) as e:
            logger.warning(f"Failed to save cache: {e}")
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def _rate_limit(self) -> None:
        """Enforce rate limiting (1 request per second)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request with rate limiting and caching."""
        cache_key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        
        if self.cache_enabled and cache_key in self._cache:
            logger.debug("comicvine_request cache_hit endpoint=%s", endpoint)
            return self._cache[cache_key]
        
        self._rate_limit()
        started = time.monotonic()
        logger.info("comicvine_request_started endpoint=%s", endpoint)
        
        request_params = {**params}
        request_params["api_key"] = self.api_key
        request_params["format"] = "json"
        
        url = f"{API_BASE}/{endpoint}"
        
        try:
            # HTTP/1.1 keeps the optional h2 package out of the runtime
            # requirements and is sufficient for Comic Vine requests.
            with httpx.Client(
                http2=False,
                follow_redirects=True,
                cookies=self._cookies
            ) as client:
                response = client.get(
                    url,
                    params=request_params,
                    timeout=30,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Connection": "keep-alive",
                        "X-Requested-With": "XMLHttpRequest",
                    }
                )
                
                self._cookies.update(dict(response.cookies))
                
                if response.status_code == 403:
                    raise ComicVineError("Blocked by Cloudflare - try again later")
                
                response.raise_for_status()
                try:
                    data = response.json()
                except (ValueError, json.JSONDecodeError) as exc:
                    raise ComicVineError("Comic Vine returned invalid JSON") from exc
                
        except httpx.HTTPStatusError as e:
            logger.warning("comicvine_request_http_error endpoint=%s status_code=%s",
                           endpoint, e.response.status_code)
            if e.response.status_code == 420:
                raise RateLimitError("Rate limit exceeded")
            raise ComicVineError(f"HTTP error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.exception("comicvine_request_network_error endpoint=%s error_type=%s",
                             endpoint, type(e).__name__)
            raise ComicVineError(f"Request failed: {e}")
        except Exception as e:
            # This also exposes missing optional transports such as h2 while
            # keeping credentials and request parameters out of the log.
            logger.exception("comicvine_request_failed endpoint=%s error_type=%s",
                             endpoint, type(e).__name__)
            raise
        
        if not isinstance(data, dict):
            raise ComicVineError("Comic Vine returned an invalid response")
        status_code = data.get("status_code")
        if status_code == 100:
            raise InvalidAPIKeyError("Invalid API key")
        elif status_code != 1:
            raise ComicVineError(f"API error: {data.get('error', 'Unknown')}")
        
        if self.cache_enabled:
            self._cache[cache_key] = data
            self._save_cache()

        logger.info("comicvine_request_finished endpoint=%s duration_ms=%d result_count=%d",
                    endpoint, int((time.monotonic() - started) * 1000),
                    len(data.get("results") or []) if isinstance(data.get("results"), list) else 1)
        
        return data

    def get_issue(self, issue_id: str) -> ComicVineIssue:
        """Get issue details by ID."""
        data = self._request(f"issue/4000-{issue_id}", {
            "field_list": ISSUE_FIELDS
        })
        issue = _parse_issue_response(data.get("results") or {})
        # Comic Vine's issue payload identifies the parent volume but does not
        # reliably include its start year. Resolve it explicitly so the local
        # Comic.volume is the real volume year, never the volume's database ID.
        if issue.series_id:
            try:
                volume = self.get_volume(issue.series_id)
                issue.volume = volume.start_year
                issue.volume_start_year = volume.start_year
                issue.volume_count_of_issues = volume.count_of_issues
                logger.info("comicvine_volume_resolved series_id=%s start_year=%s",
                            issue.series_id, issue.volume_start_year)
            except ComicVineError:
                logger.warning("comicvine_volume_lookup_failed series_id=%s", issue.series_id)
        return issue

    def get_volume(self, volume_id: str) -> dict:
        """Get volume details by ID."""
        data = self._request(f"volume/4050-{volume_id}", {
            "field_list": VOLUME_FIELDS
        })
        return _parse_volume_response(data.get("results") or {})

    def search_issue(self, query: str) -> list[ComicVineIssue]:
        """Search for issues by name."""
        data = self._request("search", {
            "query": query,
            "resources": "issue",
            "limit": 10
        })
        results = data.get("results") or []
        if not isinstance(results, list):
            raise ComicVineError("Comic Vine returned invalid issue results")
        return [_parse_issue_response(r) for r in results]

    def search_volume(self, query: str) -> list[ComicVineVolume]:
        """Search for volumes/series by name."""
        data = self._request("search", {
            "query": query,
            "resources": "volume",
            "limit": 10,
        })
        results = data.get("results") or []
        if not isinstance(results, list):
            raise ComicVineError("Comic Vine returned invalid volume results")
        return [_parse_volume_response(r) for r in results]

    def list_issues(
        self, volume_id: str, issue_number: str | None = None
    ) -> list[ComicVineIssue]:
        """List issues for a volume, optionally filtered by issue number."""
        volume_id = str(volume_id).strip()
        filter_parts = [f"volume:{volume_id}"]
        if issue_number:
            filter_parts.append(f"issue_number:{issue_number}")
        data = self._request("issues/", {
            "filter": ",".join(filter_parts),
            "field_list": ISSUE_FIELDS,
            "limit": 100,
        })
        results = data.get("results") or []
        if isinstance(results, dict):
            results = [results]
        if not isinstance(results, list):
            raise ComicVineError("Comic Vine returned invalid issue results")
        return [_parse_issue_response(r) for r in results]

    def validate_api_key(self) -> bool:
        """Validate the API key by making a test request."""
        try:
            self._request("search", {"query": "batman", "limit": 1, "resources": "issue"})
            return True
        except InvalidAPIKeyError:
            return False
