"""Unit tests for the GetComics service layer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from comicdesk.services.getcomics import (
    GetComicsClient,
    GetComicsDownloadLink,
    GetComicsSearchResult,
    _extract_meta_refresh_url,
    _parse_issue_page,
    _parse_search_results,
    _parse_title_metadata,
    _search_url,
    build_search_query,
    classify_link,
    pick_best_search_result,
    rank_search_result,
)
from comicdesk.models import CBLBook

FIXTURES = Path(__file__).parent / "fixtures" / "getcomics"


def test_parse_search_results():
    html = (FIXTURES / "search_results.html").read_text(encoding="utf-8")
    results = _parse_search_results(html)
    assert len(results) == 2
    assert results[0].title == "The Amazing Spider-Man #001 (2024)"
    assert results[0].url.endswith("/spider-man-001-2024/")
    assert results[0].date == "March 1, 2024"
    assert results[0].excerpt == "Peter Parker returns in a new adventure."


def test_parse_issue_page_entry_summary_excerpt():
    html = """
    <html><body><article>
      <h1 class="post-title">Batman #001 (2020)</h1>
      <div class="entry-summary">Only in entry-summary, no content paragraph.</div>
      <a href="https://getcomics.org/dls/main/">MAIN SERVER</a>
    </article></body></html>
    """
    issue = _parse_issue_page(html)
    assert issue.excerpt == "Only in entry-summary, no content paragraph."


def test_parse_issue_page():
    html = (FIXTURES / "issue_detail.html").read_text(encoding="utf-8")
    issue = _parse_issue_page(html, url="https://getcomics.org/comics/spider-man-001-2024/")
    assert issue.title == "The Amazing Spider-Man #001 (2024)"
    assert issue.series_name == "The Amazing Spider-Man"
    assert issue.issue_number == "1"
    assert issue.year == "2024"
    assert issue.excerpt == "Peter Parker returns in a brand new series from Marvel Comics."
    assert issue.thumbnail_url.endswith("spider-cover-og.jpg")
    assert len(issue.download_links) == 4
    providers = {link.provider for link in issue.download_links}
    assert providers == {"MAIN SERVER", "MEGA", "PIXELDRAIN", "DOWNLOAD NOW"}
    download_now = next(link for link in issue.download_links if link.provider == "DOWNLOAD NOW")
    assert download_now.is_auto_downloadable is True


def test_parse_issue_page_aio_button_direct_hosts():
    html = """
    <html><body><article>
      <h1 class="post-title">Excalibur Vol. 3 #1 – 14 (2004-2005)</h1>
      <div class="entry-content">
        <h2>Free Comics Download</h2>
        <div class="aio-button-center">
          <div class="aio-pulse">
            <a href="https://1024terabox.com/s/example" title="TERABOX">TERABOX</a>
          </div>
        </div>
        <div class="aio-button-center">
          <div class="aio-pulse">
            <a href="https://getcomics.org/dls/mega123/" title="MEGA">MEGA</a>
          </div>
        </div>
      </div>
    </article></body></html>
    """
    issue = _parse_issue_page(html)
    providers = {link.provider for link in issue.download_links}
    assert providers == {"TERABOX", "MEGA"}
    assert len(issue.download_links) == 2
    terabox = next(link for link in issue.download_links if link.provider == "TERABOX")
    assert terabox.url == "https://1024terabox.com/s/example"
    assert terabox.is_auto_downloadable is False


def test_parse_title_metadata():
    parsed = _parse_title_metadata("Batman #007 (2018)")
    assert parsed.series_name == "Batman"
    assert parsed.issue_number == "7"
    assert parsed.year == "2018"


def test_build_search_query():
    book = CBLBook(series_name="Batman", issue_number="7", volume="2018")
    assert build_search_query(book) == "Batman #7"


def test_build_search_query_ignores_volume():
    book = CBLBook(series_name="Avengers", issue_number="19", volume="2018")
    assert build_search_query(book) == "Avengers #19"


def test_search_url_encodes_hash_and_spaces():
    url = _search_url("name", "Avengers #19")
    assert url == "https://getcomics.org/?s=Avengers+%2319"


def test_search_url_encodes_hash_on_later_pages():
    url = _search_url("name", "Avengers #19", page=2)
    assert url == "https://getcomics.org/page/2/?s=Avengers+%2319"


def test_rank_search_result_prefers_matching_issue():
    book = CBLBook(series_name="Batman", issue_number="7", volume="2018")
    good = GetComicsSearchResult(title="Batman #007 (2018)", url="https://example.com/a")
    weak = GetComicsSearchResult(title="Batman #001 (2018)", url="https://example.com/b")
    assert rank_search_result(book, good) > rank_search_result(book, weak)


def test_pick_best_search_result():
    book = CBLBook(series_name="Spider-Man", issue_number="1", volume="2024")
    results = [
        GetComicsSearchResult(title="Batman #001 (2024)", url="https://example.com/b"),
        GetComicsSearchResult(title="The Amazing Spider-Man #001 (2024)", url="https://example.com/a"),
    ]
    match = pick_best_search_result(book, results)
    assert match is not None
    assert match.url.endswith("/a")


def test_classify_link_auto_and_manual():
    main = GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/a/")
    download_now = GetComicsDownloadLink(
        "DOWNLOAD NOW", "DOWNLOAD NOW", "https://getcomics.org/dls/now/"
    )
    mega = GetComicsDownloadLink("MEGA", "MEGA", "https://getcomics.org/dls/b/")
    assert classify_link(main) is True
    assert classify_link(download_now) is True
    assert classify_link(mega) is False
    assert classify_link(
        GetComicsDownloadLink("UNKNOWN", "UNKNOWN", "https://example.com/file.cbz"),
        "https://example.com/file.cbz",
    )


def test_extract_meta_refresh_url():
    html = (FIXTURES / "dls_meta_refresh.html").read_text(encoding="utf-8")
    url = _extract_meta_refresh_url(html)
    assert url == "https://getcomics.org/files/Spider-Man-001.cbz"


def test_resolve_redirect_follows_meta_refresh():
    client = GetComicsClient()
    first = MagicMock()
    first.status_code = 200
    first.text = (FIXTURES / "dls_meta_refresh.html").read_text(encoding="utf-8")
    first.headers = {}
    client._scraper.get = MagicMock(return_value=first)
    resolved = client.resolve_redirect("https://getcomics.org/dls/abc123/")
    assert resolved.endswith("Spider-Man-001.cbz")


def test_download_file_writes_atomically(tmp_path):
    client = GetComicsClient()

    def fake_resolve(url, max_hops=10):
        return "https://getcomics.org/files/test.cbz"

    client.resolve_redirect = fake_resolve

    class FakeStream:
        status_code = 200
        headers = {
            "content-disposition": 'attachment; filename="Spider.cbz"',
            "content-length": "9",
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, chunk_size=262144):
            yield b"PK\x03\x04test"

    with patch("comicdesk.services.getcomics.httpx.stream", return_value=FakeStream()):
        path = client.download_file("https://getcomics.org/dls/test/", tmp_path)

    assert path.exists()
    assert path.name == "Spider.cbz"
    assert path.read_bytes() == b"PK\x03\x04test"


def test_pick_auto_download_link_prefers_resolvable_main_server():
    client = GetComicsClient()
    links = [
        GetComicsDownloadLink("MEGA", "MEGA", "https://getcomics.org/dls/mega/"),
        GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/"),
    ]
    client.resolve_redirect = MagicMock(
        side_effect=lambda url, max_hops=10: (
            "https://getcomics.org/files/book.cbz"
            if "main" in url
            else "https://mega.nz/file/abc"
        )
    )
    picked = client.pick_auto_download_link(links)
    assert picked is not None
    assert picked.provider == "MAIN SERVER"


def test_pick_auto_download_link_skips_excluded_urls():
    client = GetComicsClient()
    main = GetComicsDownloadLink("MAIN SERVER", "MAIN SERVER", "https://getcomics.org/dls/main/")
    mirror = GetComicsDownloadLink("MIRROR", "MIRROR", "https://getcomics.org/dls/mirror/")
    client.resolve_redirect = MagicMock(
        return_value="https://getcomics.org/files/book.cbz"
    )
    picked = client.pick_auto_download_link(
        [main, mirror],
        exclude_urls={main.url},
    )
    assert picked is not None
    assert picked.provider == "MIRROR"
