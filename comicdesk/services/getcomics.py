"""GetComics.org search, parsing, link resolution and file download."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urljoin, urlparse

import cloudscraper
import httpx
from bs4 import BeautifulSoup

from comicdesk.models import CBLBook

logger = logging.getLogger(__name__)

BASE_URL = "https://getcomics.org"


def _format_bytes(size: int | None) -> str:
    if size is None:
        return "unknown"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _format_speed(bytes_per_second: float) -> str:
    if bytes_per_second < 1024 * 1024:
        return f"{bytes_per_second / 1024:.1f} KB/s"
    return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)
ARCHIVE_EXTENSIONS = (".cbz", ".cbr", ".zip", ".rar", ".7z", ".pdf")
DOWNLOAD_CHUNK_SIZE = 1024 * 256
DIRECT_PROVIDER_KEYWORDS = (
    "main server",
    "mirror",
    "direct",
    "download now",
    "server 1",
    "server #1",
    "getcomics",
)
MANUAL_PROVIDER_KEYWORDS = (
    "mega",
    "pixeldrain",
    "mediafire",
    "zippyshare",
    "torrent",
    "dropbox",
    "googledrive",
    "google drive",
    "onedrive",
    "uptobox",
    "rapidgator",
    "nitroflare",
    "katfile",
    "uploaded",
    "turbobit",
)


class GetComicsError(Exception):
    """Base exception for GetComics operations."""


class GetComicsNetworkError(GetComicsError):
    """Network or HTTP failure."""


class GetComicsParseError(GetComicsError):
    """HTML structure could not be parsed."""


class GetComicsDownloadError(GetComicsError):
    """File download failed."""


class CloudflareChallengeError(GetComicsError):
    """Cloudflare blocked the request."""


@dataclass
class GetComicsSearchResult:
    title: str
    url: str
    thumbnail_url: str = ""
    date: str = ""
    excerpt: str = ""


@dataclass
class GetComicsDownloadLink:
    label: str
    provider: str
    url: str
    is_auto_downloadable: bool = False
    resolved_url: str = ""


@dataclass
class GetComicsIssue:
    title: str
    url: str
    date: str = ""
    excerpt: str = ""
    thumbnail_url: str = ""
    download_links: list[GetComicsDownloadLink] = field(default_factory=list)
    series_name: str = ""
    issue_number: str = ""
    year: str = ""


@dataclass(frozen=True)
class ParsedTitleMetadata:
    series_name: str = ""
    issue_number: str = ""
    year: str = ""


def _normalize_provider(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).upper()


def _provider_from_link(anchor) -> str:
    title = anchor.get("title") or ""
    text = anchor.get_text(" ", strip=True)
    for candidate in (title, text):
        cleaned = candidate.strip()
        if cleaned:
            return _normalize_provider(cleaned)
    return "UNKNOWN"


def _looks_like_direct_file_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def _is_getcomics_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("getcomics.org")


def classify_link(link: GetComicsDownloadLink, resolved_url: str | None = None) -> bool:
    """Return True when the link can be downloaded directly over HTTP."""
    provider = link.provider.lower()
    if any(keyword in provider for keyword in DIRECT_PROVIDER_KEYWORDS):
        return True
    if any(keyword in provider for keyword in MANUAL_PROVIDER_KEYWORDS):
        return False
    target = resolved_url or link.url
    if _looks_like_direct_file_url(target):
        return True
    if _is_getcomics_host(target) and "/dls/" not in target:
        return True
    return False


def _image_url_from_tag(img) -> str:
    if img is None:
        return ""
    for attr in ("data-lazy-src", "data-src", "data-original", "src"):
        value = (img.get(attr) or "").strip()
        if value and not value.startswith("data:"):
            return value
    srcset = (img.get("srcset") or "").strip()
    if srcset:
        first = srcset.split(",")[0].strip().split()
        if first and not first[0].startswith("data:"):
            return first[0]
    return ""


def _find_issue_thumbnail(soup: BeautifulSoup) -> str:
    og = soup.select_one('meta[property="og:image"]')
    if og is not None:
        content = (og.get("content") or "").strip()
        if content and not content.startswith("data:"):
            return urljoin(BASE_URL, content)
    for selector in (
        ".post-thumb img",
        ".entry-content img.wp-post-image",
        ".entry-content img",
        "article img",
    ):
        url = _image_url_from_tag(soup.select_one(selector))
        if url:
            return urljoin(BASE_URL, url)
    return ""


def _parse_title_metadata(title: str) -> ParsedTitleMetadata:
    cleaned = re.sub(r"\s+", " ", (title or "").strip())
    if not cleaned:
        return ParsedTitleMetadata()

    year = ""
    year_match = re.search(r"\((19\d{2}|20\d{2})\)", cleaned)
    if year_match:
        year = year_match.group(1)
        cleaned = (cleaned[: year_match.start()] + cleaned[year_match.end() :]).strip()

    issue_number = ""
    issue_match = re.search(r"#\s*(\d+(?:\.\d+)?)", cleaned)
    if issue_match:
        issue_number = issue_match.group(1).lstrip("0") or "0"
        if "." not in issue_number and issue_number.isdigit():
            issue_number = str(int(issue_number))
        cleaned = (cleaned[: issue_match.start()] + cleaned[issue_match.end() :]).strip()

    series_name = cleaned.strip(" -")
    return ParsedTitleMetadata(series_name=series_name, issue_number=issue_number, year=year)


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _normalize_issue_number(value: str) -> str:
    cleaned = (value or "").strip().lstrip("#")
    if not cleaned:
        return ""
    try:
        number = float(cleaned)
        return str(int(number)) if number.is_integer() else str(number)
    except ValueError:
        return cleaned.casefold()


def build_search_query(book: CBLBook) -> str:
    """Build a GetComics name search query from a CBL reference."""
    from comicdesk.services.cbl_display import cbl_book_issue_label, cbl_book_series_label

    series = cbl_book_series_label(book).strip()
    if series == "—":
        series = ""
    issue = cbl_book_issue_label(book).strip().lstrip("#")
    if issue == "—":
        issue = ""
    if series and issue:
        return f"{series} #{issue}"
    if series:
        return series
    if issue:
        return f"#{issue}"
    return ""


def rank_search_result(book: CBLBook, result: GetComicsSearchResult) -> int:
    """Score how well a search result matches a CBL reference."""
    parsed = _parse_title_metadata(result.title)
    score = 0

    book_series = _normalize_match_text(book.series_name)
    if not book_series and book.cv_metadata:
        book_series = _normalize_match_text(book.cv_metadata.series_name)
    result_series = _normalize_match_text(parsed.series_name)
    if book_series and result_series:
        if book_series == result_series:
            score += 40
        elif book_series in result_series or result_series in book_series:
            score += 20

    book_issue = _normalize_issue_number(book.issue_number)
    if not book_issue and book.cv_metadata:
        book_issue = _normalize_issue_number(book.cv_metadata.issue_number)
    result_issue = _normalize_issue_number(parsed.issue_number)
    if book_issue and result_issue:
        if book_issue == result_issue:
            score += 40
        elif book_issue in result_issue or result_issue in book_issue:
            score += 15

    book_year = (book.volume or "").strip()
    if book_year.isdigit() and len(book_year) == 4 and parsed.year == book_year:
        score += 10

    if book.cv_issue_id and book.cv_issue_id in (result.title or ""):
        score += 5

    return score


def pick_best_search_result(
    book: CBLBook,
    results: list[GetComicsSearchResult],
    *,
    minimum_score: int = 40,
) -> GetComicsSearchResult | None:
    """Return the best search result for a CBL reference, if confident enough."""
    if not results:
        return None
    ranked = sorted(
        ((rank_search_result(book, result), result) for result in results),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score, best_result = ranked[0]
    if best_score < minimum_score:
        return None
    if len(ranked) > 1 and ranked[1][0] == best_score:
        return None
    return best_result


def _extract_meta_refresh_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)})
    if not meta:
        return None
    content = meta.get("content") or ""
    match = re.search(r"url=(.+)$", content, flags=re.I)
    if not match:
        return None
    return match.group(1).strip().strip("'\"")


def _parse_search_results(html: str) -> list[GetComicsSearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article")
    if not articles:
        articles = soup.select(".post, .type-post")

    results: list[GetComicsSearchResult] = []
    for article in articles:
        title_link = (
            article.select_one("h1.post-title a")
            or article.select_one("h2.entry-title a")
            or article.select_one("h2 a")
            or article.select_one("a[rel='bookmark']")
        )
        if title_link is None:
            continue
        title = title_link.get_text(strip=True)
        url = urljoin(BASE_URL, title_link.get("href", ""))
        if not title or not url:
            continue

        thumb = article.select_one("img")
        thumbnail_url = urljoin(BASE_URL, _image_url_from_tag(thumb)) if thumb else ""

        date_el = article.select_one("time, .post-date, .entry-date")
        date = date_el.get_text(strip=True) if date_el else ""

        excerpt_el = article.select_one(".entry-summary, .excerpt, p")
        excerpt = ""
        if excerpt_el is not None:
            excerpt = excerpt_el.get_text(" ", strip=True)

        results.append(
            GetComicsSearchResult(
                title=title,
                url=url,
                thumbnail_url=thumbnail_url,
                date=date,
                excerpt=excerpt,
            )
        )
    return results


def _extract_download_links(soup: BeautifulSoup) -> list[GetComicsDownloadLink]:
    links: list[GetComicsDownloadLink] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href*="/dls/"]'):
        href = urljoin(BASE_URL, anchor.get("href", ""))
        if not href or href in seen:
            continue
        seen.add(href)
        provider = _provider_from_link(anchor)
        label = anchor.get_text(" ", strip=True) or provider
        link = GetComicsDownloadLink(
            label=label,
            provider=provider,
            url=href,
            is_auto_downloadable=classify_link(
                GetComicsDownloadLink(label=label, provider=provider, url=href)
            ),
        )
        links.append(link)
    return links


def _parse_issue_page(html: str, url: str = "") -> GetComicsIssue:
    soup = BeautifulSoup(html, "html.parser")
    title_el = (
        soup.select_one("h1.post-title")
        or soup.select_one("h1.entry-title")
        or soup.select_one("article h1")
    )
    if title_el is None:
        raise GetComicsParseError("Issue page is missing a title")

    title = title_el.get_text(strip=True)
    date_el = soup.select_one("time, .post-date, .entry-date")
    date = date_el.get_text(strip=True) if date_el else ""

    excerpt_el = soup.select_one(".entry-summary, .excerpt, .entry-content p, .post-content p")
    excerpt = excerpt_el.get_text(" ", strip=True) if excerpt_el else ""

    thumbnail_url = _find_issue_thumbnail(soup)

    parsed = _parse_title_metadata(title)
    download_links = _extract_download_links(soup)
    if not download_links:
        raise GetComicsParseError("No download links found on issue page")

    return GetComicsIssue(
        title=title,
        url=url or "",
        date=date,
        excerpt=excerpt,
        thumbnail_url=thumbnail_url,
        download_links=download_links,
        series_name=parsed.series_name,
        issue_number=parsed.issue_number,
        year=parsed.year,
    )


def _search_url(criterion: str, query: str, page: int = 1) -> str:
    slug = query.strip().strip("/")
    if criterion == "name":
        base = str(httpx.URL(f"{BASE_URL}/", params={"s": slug}))
    elif criterion == "category":
        base = f"{BASE_URL}/cat/{slug}/"
    elif criterion == "tag":
        base = f"{BASE_URL}/tag/{slug}/"
    else:
        raise ValueError(f"Unknown search criterion: {criterion}")
    if page > 1:
        if "?" in base:
            path, qs = base.split("?", 1)
            return f"{path}page/{page}/?{qs}"
        return f"{base}page/{page}/"
    return base


def _dedupe_filename(dest_dir: Path, filename: str) -> Path:
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 1
    while True:
        alt = dest_dir / f"{stem}_{index}{suffix}"
        if not alt.exists():
            return alt
        index += 1


class GetComicsClient:
    """HTTP client for getcomics.org pages and direct file downloads."""

    def __init__(self, timeout: float = 30.0, download_timeout: float = 600.0):
        self.timeout = timeout
        self.download_timeout = download_timeout
        self._scraper = cloudscraper.create_scraper(
            browser={"browser": "firefox", "platform": "linux", "mobile": False}
        )
        self._scraper.headers.update({"User-Agent": USER_AGENT})

    def close(self) -> None:
        self._scraper.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def fetch_image_bytes(self, url: str) -> bytes:
        if not url:
            raise GetComicsNetworkError("Image URL is empty")
        started = time.monotonic()
        logger.info("getcomics_image_fetch_started url=%s", url)
        try:
            response = self._scraper.get(url, timeout=self.timeout)
        except Exception as exc:
            raise GetComicsNetworkError(f"Image request failed for {url}: {exc}") from exc
        if response.status_code >= 400:
            raise GetComicsNetworkError(f"HTTP {response.status_code} for image {url}")
        logger.info(
            "getcomics_image_fetch_finished url=%s bytes=%d duration_ms=%d",
            url,
            len(response.content),
            _elapsed_ms(started),
        )
        return response.content

    def _fetch_html(self, url: str) -> str:
        started = time.monotonic()
        logger.info("getcomics_request_started url=%s", url)
        try:
            response = self._scraper.get(url, timeout=self.timeout)
        except Exception as exc:
            logger.warning(
                "getcomics_request_failed url=%s duration_ms=%d error=%s",
                url,
                _elapsed_ms(started),
                exc,
            )
            raise GetComicsNetworkError(f"Request failed for {url}: {exc}") from exc
        if response.status_code == 403 and "cloudflare" in response.text.lower():
            logger.warning(
                "getcomics_request_cloudflare url=%s duration_ms=%d",
                url,
                _elapsed_ms(started),
            )
            raise CloudflareChallengeError("Cloudflare challenge blocked the request")
        if response.status_code >= 400:
            logger.warning(
                "getcomics_request_http_error url=%s status_code=%d duration_ms=%d",
                url,
                response.status_code,
                _elapsed_ms(started),
            )
            raise GetComicsNetworkError(
                f"HTTP {response.status_code} for {url}"
            )
        logger.info(
            "getcomics_request_finished url=%s status_code=%d bytes=%d duration_ms=%d",
            url,
            response.status_code,
            len(response.text),
            _elapsed_ms(started),
        )
        return response.text

    def search_by_name(self, query: str, page: int = 1) -> list[GetComicsSearchResult]:
        url = _search_url("name", query, page)
        return self._search(url, criterion="name", query=query, page=page)

    def search_by_category(self, slug: str, page: int = 1) -> list[GetComicsSearchResult]:
        url = _search_url("category", slug, page)
        return self._search(url, criterion="category", query=slug, page=page)

    def search_by_tag(self, slug: str, page: int = 1) -> list[GetComicsSearchResult]:
        url = _search_url("tag", slug, page)
        return self._search(url, criterion="tag", query=slug, page=page)

    def _search(
        self, url: str, *, criterion: str, query: str, page: int
    ) -> list[GetComicsSearchResult]:
        started = time.monotonic()
        logger.info(
            "getcomics_search_started criterion=%s query=%s page=%d url=%s",
            criterion,
            query,
            page,
            url,
        )
        results = _parse_search_results(self._fetch_html(url))
        logger.info(
            "getcomics_search_finished criterion=%s query=%s page=%d result_count=%d duration_ms=%d",
            criterion,
            query,
            page,
            len(results),
            _elapsed_ms(started),
        )
        return results

    def get_issue(self, url: str) -> GetComicsIssue:
        started = time.monotonic()
        logger.info("getcomics_issue_fetch_started url=%s", url)
        html = self._fetch_html(url)
        issue = _parse_issue_page(html, url=url)
        logger.info(
            "getcomics_issue_fetch_finished url=%s title=%s link_count=%d duration_ms=%d",
            url,
            issue.title,
            len(issue.download_links),
            _elapsed_ms(started),
        )
        return issue

    def resolve_redirect(self, url: str, max_hops: int = 10) -> str:
        started = time.monotonic()
        current = url
        logger.info("getcomics_resolve_started url=%s", url)
        for hop in range(1, max_hops + 1):
            if _looks_like_direct_file_url(current):
                logger.info(
                    "getcomics_resolve_finished source=%s resolved=%s hops=%d duration_ms=%d",
                    url,
                    current,
                    hop - 1,
                    _elapsed_ms(started),
                )
                return current
            try:
                response = self._scraper.get(
                    current, timeout=self.timeout, allow_redirects=False
                )
            except Exception as exc:
                raise GetComicsNetworkError(
                    f"Redirect resolution failed for {current}: {exc}"
                ) from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    break
                next_url = urljoin(current, location)
                logger.info(
                    "getcomics_resolve_hop hop=%d from=%s to=%s status=%d",
                    hop,
                    current,
                    next_url,
                    response.status_code,
                )
                current = next_url
                continue

            if response.status_code == 200:
                refresh = _extract_meta_refresh_url(response.text)
                if refresh:
                    next_url = urljoin(current, refresh)
                    logger.info(
                        "getcomics_resolve_meta_refresh hop=%d from=%s to=%s",
                        hop,
                        current,
                        next_url,
                    )
                    current = next_url
                    continue
                if _looks_like_direct_file_url(current):
                    logger.info(
                        "getcomics_resolve_finished source=%s resolved=%s hops=%d duration_ms=%d",
                        url,
                        current,
                        hop,
                        _elapsed_ms(started),
                    )
                    return current
                break

            if response.status_code >= 400:
                raise GetComicsNetworkError(
                    f"HTTP {response.status_code} while resolving {current}"
                )
            break
        logger.info(
            "getcomics_resolve_finished source=%s resolved=%s hops=%d duration_ms=%d",
            url,
            current,
            max_hops,
            _elapsed_ms(started),
        )
        return current

    def pick_auto_download_link(
        self,
        links: list[GetComicsDownloadLink],
        *,
        exclude_urls: set[str] | None = None,
    ) -> GetComicsDownloadLink | None:
        skipped = exclude_urls or set()
        auto_links = [
            link for link in links if classify_link(link) and link.url not in skipped
        ]
        logger.info(
            "getcomics_pick_link_started total_links=%d auto_candidates=%d",
            len(links),
            len(auto_links),
        )
        if not auto_links:
            logger.info("getcomics_pick_link_finished selected=none")
            return None
        for link in auto_links:
            started = time.monotonic()
            logger.info(
                "getcomics_pick_link_try provider=%s url=%s",
                link.provider,
                link.url,
            )
            try:
                resolved = self.resolve_redirect(link.url)
            except GetComicsError as exc:
                logger.warning(
                    "getcomics_pick_link_failed provider=%s duration_ms=%d error=%s",
                    link.provider,
                    _elapsed_ms(started),
                    exc,
                )
                continue
            if classify_link(link, resolved):
                logger.info(
                    "getcomics_pick_link_finished provider=%s resolved=%s duration_ms=%d",
                    link.provider,
                    resolved,
                    _elapsed_ms(started),
                )
                return GetComicsDownloadLink(
                    label=link.label,
                    provider=link.provider,
                    url=link.url,
                    is_auto_downloadable=True,
                    resolved_url=resolved,
                )
            logger.info(
                "getcomics_pick_link_rejected provider=%s resolved=%s duration_ms=%d",
                link.provider,
                resolved,
                _elapsed_ms(started),
            )
        logger.info("getcomics_pick_link_finished selected=none")
        return None

    def download_file(
        self,
        url: str,
        dest_dir: Path,
        *,
        resolved_url: str | None = None,
        filename: str | None = None,
        overwrite: bool = False,
        progress_callback: Callable[[int, int | None], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        referer: str | None = None,
    ) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        if resolved_url:
            resolved = resolved_url
            logger.info("getcomics_download_using_cached_resolve source=%s resolved=%s", url, resolved)
        else:
            resolved = self.resolve_redirect(url)
        logger.info(
            "getcomics_download_started source=%s resolved=%s dest_dir=%s",
            url,
            resolved,
            dest_dir,
        )
        errors: list[Exception] = []
        backends = (
            ("httpx", self._download_with_httpx),
            ("cloudscraper", self._download_with_scraper),
        )
        for backend_name, downloader in backends:
            try:
                target = downloader(
                    resolved,
                    dest_dir,
                    filename=filename,
                    overwrite=overwrite,
                    progress_callback=progress_callback,
                    cancelled=cancelled,
                    backend=backend_name,
                    referer=referer,
                )
                logger.info(
                    "getcomics_download_finished backend=%s source=%s resolved=%s path=%s duration_ms=%d",
                    backend_name,
                    url,
                    resolved,
                    target,
                    _elapsed_ms(started),
                )
                return target
            except GetComicsDownloadError as exc:
                if cancelled and cancelled():
                    logger.info(
                        "getcomics_download_cancelled source=%s resolved=%s duration_ms=%d",
                        url,
                        resolved,
                        _elapsed_ms(started),
                    )
                    raise
                logger.warning(
                    "getcomics_download_backend_failed backend=%s source=%s resolved=%s duration_ms=%d error=%s",
                    backend_name,
                    url,
                    resolved,
                    _elapsed_ms(started),
                    exc,
                )
                errors.append(exc)
                if backend_name == "cloudscraper":
                    raise
                continue
            except Exception as exc:
                raise GetComicsDownloadError(f"Download failed for {resolved}: {exc}") from exc
        if errors:
            raise errors[-1]
        raise GetComicsDownloadError(f"Download failed for {resolved}")

    def _prepare_download_target(
        self,
        headers,
        resolved: str,
        dest_dir: Path,
        filename: str | None,
        overwrite: bool,
    ) -> tuple[Path, Path, str, int | None]:
        if filename is None:
            filename = self._filename_from_headers(headers, resolved)
        if not filename:
            raise GetComicsDownloadError(f"Could not determine filename for {resolved}")
        target = dest_dir / filename
        if target.exists() and not overwrite:
            target = _dedupe_filename(dest_dir, filename)
        fd, tmp_name = tempfile.mkstemp(dir=dest_dir, suffix=".part")
        os.close(fd)
        return target, Path(tmp_name), filename, self._content_length(headers)

    def _write_chunks(
        self,
        chunks,
        tmp_path: Path,
        target: Path,
        total: int | None,
        *,
        backend: str,
        resolved: str,
        progress_callback: Callable[[int, int | None], None] | None,
        cancelled: Callable[[], bool] | None,
    ) -> None:
        downloaded = 0
        started = time.monotonic()
        last_log = started
        logger.info(
            "getcomics_stream_started backend=%s resolved=%s target=%s total=%s",
            backend,
            resolved,
            target.name,
            _format_bytes(total),
        )
        try:
            with open(tmp_path, "wb") as handle:
                for chunk in chunks:
                    if cancelled and cancelled():
                        raise GetComicsDownloadError("Download cancelled")
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)
                    now = time.monotonic()
                    if now - last_log >= 5.0:
                        elapsed = now - started
                        speed = downloaded / elapsed if elapsed > 0 else 0.0
                        logger.info(
                            "getcomics_stream_progress backend=%s downloaded=%s total=%s speed=%s elapsed_s=%.1f",
                            backend,
                            _format_bytes(downloaded),
                            _format_bytes(total),
                            _format_speed(speed),
                            elapsed,
                        )
                        last_log = now
            os.replace(tmp_path, target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        elapsed = time.monotonic() - started
        speed = downloaded / elapsed if elapsed > 0 else 0.0
        logger.info(
            "getcomics_stream_finished backend=%s downloaded=%s total=%s speed=%s duration_ms=%d path=%s",
            backend,
            _format_bytes(downloaded),
            _format_bytes(total),
            _format_speed(speed),
            int(elapsed * 1000),
            target,
        )

    def _download_with_httpx(
        self,
        resolved: str,
        dest_dir: Path,
        *,
        filename: str | None,
        overwrite: bool,
        progress_callback: Callable[[int, int | None], None] | None,
        cancelled: Callable[[], bool] | None,
        backend: str,
        referer: str | None = None,
    ) -> Path:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": referer or f"{BASE_URL}/",
        }
        timeout = httpx.Timeout(self.timeout, read=self.download_timeout)
        started = time.monotonic()
        logger.info(
            "getcomics_download_backend_started backend=%s resolved=%s referer=%s",
            backend,
            resolved,
            headers["Referer"],
        )
        try:
            with httpx.stream(
                "GET",
                resolved,
                follow_redirects=True,
                timeout=timeout,
                headers=headers,
            ) as response:
                if response.status_code in (401, 403, 503):
                    raise GetComicsDownloadError(
                        f"HTTP {response.status_code} while downloading {resolved}"
                    )
                if response.status_code >= 400:
                    raise GetComicsDownloadError(
                        f"HTTP {response.status_code} while downloading {resolved}"
                    )
                target, tmp_path, chosen_name, total = self._prepare_download_target(
                    response.headers,
                    resolved,
                    dest_dir,
                    filename,
                    overwrite,
                )
                logger.info(
                    "getcomics_download_response backend=%s status=%d filename=%s total=%s connect_ms=%d",
                    backend,
                    response.status_code,
                    chosen_name,
                    _format_bytes(total),
                    _elapsed_ms(started),
                )
                self._write_chunks(
                    response.iter_bytes(DOWNLOAD_CHUNK_SIZE),
                    tmp_path,
                    target,
                    total,
                    backend=backend,
                    resolved=resolved,
                    progress_callback=progress_callback,
                    cancelled=cancelled,
                )
                return target
        except GetComicsDownloadError:
            raise
        except httpx.HTTPError as exc:
            raise GetComicsDownloadError(f"Download failed for {resolved}: {exc}") from exc

    def _download_with_scraper(
        self,
        resolved: str,
        dest_dir: Path,
        *,
        filename: str | None,
        overwrite: bool,
        progress_callback: Callable[[int, int | None], None] | None,
        cancelled: Callable[[], bool] | None,
        backend: str,
        referer: str | None = None,
    ) -> Path:
        response = None
        started = time.monotonic()
        logger.info(
            "getcomics_download_backend_started backend=%s resolved=%s referer=%s",
            backend,
            resolved,
            referer or f"{BASE_URL}/",
        )
        try:
            response = self._scraper.get(
                resolved,
                stream=True,
                timeout=(self.timeout, self.download_timeout),
                headers={"Referer": referer or f"{BASE_URL}/"},
            )
            if response.status_code >= 400:
                raise GetComicsDownloadError(
                    f"HTTP {response.status_code} while downloading {resolved}"
                )
            target, tmp_path, chosen_name, total = self._prepare_download_target(
                response.headers,
                resolved,
                dest_dir,
                filename,
                overwrite,
            )
            logger.info(
                "getcomics_download_response backend=%s status=%d filename=%s total=%s connect_ms=%d",
                backend,
                response.status_code,
                chosen_name,
                _format_bytes(total),
                _elapsed_ms(started),
            )
            self._write_chunks(
                response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE),
                tmp_path,
                target,
                total,
                backend=backend,
                resolved=resolved,
                progress_callback=progress_callback,
                cancelled=cancelled,
            )
            return target
        finally:
            if response is not None:
                response.close()

    @staticmethod
    def _content_length(headers) -> int | None:
        raw = headers.get("content-length") or headers.get("Content-Length")
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _filename_from_headers(headers, url: str) -> str:
        disposition = headers.get("content-disposition") or headers.get("Content-Disposition") or ""
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition, re.I)
        if match:
            return Path(unquote(match.group(1))).name
        path_name = unquote(Path(urlparse(url).path).name)
        if path_name:
            return path_name
        return "download.cbz"
