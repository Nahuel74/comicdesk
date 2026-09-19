"""Comic Vine API client with caching and rate limiting."""

import gzip
import time
import json
import logging
import os
import re
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
SEARCH_RESULT_LIMIT = 20


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


def _norm_issue_number(value: str) -> str:
    text = (value or "").strip().lstrip("#").casefold()
    if not text:
        return ""
    if text.isdigit():
        return str(int(text))
    return text


def _response_json(response: httpx.Response) -> dict:
    """Parse a Comic Vine JSON body, including gzip when httpx did not decode it."""
    try:
        data = response.json()
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        body = response.content
        if len(body) >= 2 and body[:2] == b"\x1f\x8b":
            try:
                data = json.loads(gzip.decompress(body))
            except (OSError, ValueError, json.JSONDecodeError) as gzip_exc:
                raise ComicVineError("Comic Vine returned invalid JSON") from gzip_exc
        else:
            encoding = (response.headers.get("content-encoding") or "").casefold()
            if "br" in encoding:
                raise ComicVineError(
                    "Comic Vine returned brotli-compressed data that could not be decoded"
                ) from exc
            raise ComicVineError("Comic Vine returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ComicVineError("Comic Vine returned an invalid response")
    return data


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
        self._volume_cache: dict[str, ComicVineVolume] = {}
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

    @staticmethod
    def _should_cache_response(endpoint: str, data: dict) -> bool:
        results = data.get("results")
        if endpoint in ("search", "issues/", "volumes/") and isinstance(results, list) and not results:
            return False
        return True

    def _rate_limit(self) -> None:
        """Enforce rate limiting (1 request per second)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def _request(self, endpoint: str, params: dict, *, _attempt: int = 0) -> dict:
        """Make API request with rate limiting and caching."""
        cache_key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        
        if self.cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            results = cached.get("results") if isinstance(cached, dict) else None
            if endpoint in ("search", "issues/", "volumes/") and isinstance(results, list) and not results:
                pass
            else:
                logger.debug("comicvine_request cache_hit endpoint=%s", endpoint)
                return cached
        
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
                        # Do not set Accept-Encoding here: advertising brotli (br) without
                        # a decoder leaves compressed bytes that break response.json().
                        "Connection": "keep-alive",
                        "X-Requested-With": "XMLHttpRequest",
                    }
                )
                
                self._cookies.update(dict(response.cookies))
                
                if response.status_code == 403:
                    raise ComicVineError("Blocked by Cloudflare - try again later")
                
                response.raise_for_status()
                data = _response_json(response)
                
        except httpx.HTTPStatusError as e:
            logger.warning("comicvine_request_http_error endpoint=%s status_code=%s",
                           endpoint, e.response.status_code)
            if e.response.status_code == 420 and _attempt < 3:
                delay = 2.0 * (2 ** _attempt)
                logger.info(
                    "comicvine_rate_limit_retry endpoint=%s attempt=%s delay_s=%s",
                    endpoint,
                    _attempt + 1,
                    delay,
                )
                time.sleep(delay)
                return self._request(endpoint, params, _attempt=_attempt + 1)
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
        
        if self.cache_enabled and self._should_cache_response(endpoint, data):
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
        start_year = (issue.volume_start_year or "").strip()
        if re.fullmatch(r"(19|20)\d{2}", start_year):
            issue.volume = start_year
        elif issue.series_id:
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

    def get_volume(self, volume_id: str) -> ComicVineVolume:
        """Get volume details by ID."""
        volume_id = str(volume_id or "").strip()
        cached = self._volume_cache.get(volume_id)
        if cached is not None:
            return cached
        data = self._request(f"volume/4050-{volume_id}", {
            "field_list": VOLUME_FIELDS
        })
        volume = _parse_volume_response(data.get("results") or {})
        self._volume_cache[volume_id] = volume
        return volume

    def search_issue(self, query: str) -> list[ComicVineIssue]:
        """Search for issues by name."""
        data = self._request("search", {
            "query": query,
            "resources": "issue",
            "limit": SEARCH_RESULT_LIMIT
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
            "limit": SEARCH_RESULT_LIMIT,
        })
        results = data.get("results") or []
        if not isinstance(results, list):
            raise ComicVineError("Comic Vine returned invalid volume results")
        return [_parse_volume_response(r) for r in results]

    def filter_volumes(
        self, *, name: str = "", start_year: str = ""
    ) -> list[ComicVineVolume]:
        """List volumes using Comic Vine filter (more precise than ranked search)."""
        # Comic Vine treats comma-separated filters loosely; apply start_year locally.
        if (name or "").strip():
            filter_value = f"name:{name.strip()}"
        elif (start_year or "").strip():
            filter_value = f"start_year:{start_year.strip()}"
        else:
            return []
        data = self._request("volumes/", {
            "filter": filter_value,
            "field_list": VOLUME_FIELDS,
            "limit": 100,
        })
        results = data.get("results") or []
        if isinstance(results, dict):
            results = [results]
        if not isinstance(results, list):
            raise ComicVineError("Comic Vine returned invalid volume results")
        volumes = [_parse_volume_response(r) for r in results]
        year = (start_year or "").strip()
        if year and (name or "").strip():
            volumes = [
                volume for volume in volumes
                if (volume.start_year or "").strip() == year
            ]
        return volumes

    def search_issues_by_number(self, issue_number: str) -> list[ComicVineIssue]:
        """Find issues with an exact issue number, preferring the search API."""
        number = str(issue_number or "").strip().lstrip("#")
        if not number:
            return []
        for query in (f"issue_number:{number}", number):
            data = self._request("search", {
                "query": query,
                "resources": "issue",
                "limit": 100,
            })
            results = data.get("results") or []
            if not isinstance(results, list):
                continue
            parsed = [_parse_issue_response(r) for r in results]
            exact = [
                item
                for item in parsed
                if _norm_issue_number(item.issue_number) == _norm_issue_number(number)
            ]
            if exact:
                return exact
        return []

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
