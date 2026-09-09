"""Unit tests for the GetComics service layer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from cbl_maker.services.getcomics import (
    GetComicsClient,
    GetComicsDownloadLink,
    _extract_meta_refresh_url,
    _parse_issue_page,
    _parse_search_results,
    _parse_title_metadata,
    classify_link,
)

FIXTURES = Path(__file__).parent / "fixtures" / "getcomics"


def test_parse_search_results():
    html = (FIXTURES / "search_results.html").read_text(encoding="utf-8")
    results = _parse_search_results(html)
    assert len(results) == 2
    assert results[0].title == "The Amazing Spider-Man #001 (2024)"
    assert results[0].url.endswith("/spider-man-001-2024/")
    assert results[0].date == "March 1, 2024"


def test_parse_issue_page():
    html = (FIXTURES / "issue_detail.html").read_text(encoding="utf-8")
    issue = _parse_issue_page(html, url="https://getcomics.org/comics/spider-man-001-2024/")
    assert issue.title == "The Amazing Spider-Man #001 (2024)"
    assert issue.series_name == "The Amazing Spider-Man"
    assert issue.issue_number == "1"
    assert issue.year == "2024"
    assert issue.thumbnail_url.endswith("spider-cover-og.jpg")
    assert len(issue.download_links) == 4
    providers = {link.provider for link in issue.download_links}
    assert providers == {"MAIN SERVER", "MEGA", "PIXELDRAIN", "DOWNLOAD NOW"}
    download_now = next(link for link in issue.download_links if link.provider == "DOWNLOAD NOW")
    assert download_now.is_auto_downloadable is True


def test_parse_title_metadata():
    parsed = _parse_title_metadata("Batman #007 (2018)")
    assert parsed.series_name == "Batman"
    assert parsed.issue_number == "7"
    assert parsed.year == "2018"


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

    with patch("cbl_maker.services.getcomics.httpx.stream", return_value=FakeStream()):
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
