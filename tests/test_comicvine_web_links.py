"""Tests for Comic Vine Web link normalization."""

from comicdesk.models import Comic
from comicdesk.services.comicinfo import join_web_links_for_comic
from comicdesk.utils.comicvine_web_links import (
    link_covers_issue_id,
    normalize_issue_web_links,
)


def test_link_covers_issue_id_accepts_slug_and_generic():
    slug = "https://comicvine.gamespot.com/the-pulse-10-house-of-m/4000-105810/"
    generic = "https://comicvine.gamespot.com/issue/4000-105810/"
    assert link_covers_issue_id(slug, "105810")
    assert link_covers_issue_id(generic, "105810")
    assert not link_covers_issue_id(
        "https://comicvine.gamespot.com/volume/4050-11310/", "105810"
    )


def test_normalize_issue_web_links_keeps_single_slug():
    links = [
        "https://comicvine.gamespot.com/the-pulse-10-house-of-m/4000-105810/",
        "https://comicvine.gamespot.com/issue/4000-105810/",
        "https://comicvine.gamespot.com/volume/4050-11310/",
    ]
    result = normalize_issue_web_links(
        links,
        issue_id="105810",
        preferred_url=links[0],
    )
    assert result == [links[0]]


def test_normalize_issue_web_links_fallback_generic_when_only_generic_present():
    generic = "https://comicvine.gamespot.com/issue/4000-42/"
    result = normalize_issue_web_links([generic], issue_id="42")
    assert result == [generic]


def test_normalize_keeps_non_cv_links():
    result = normalize_issue_web_links(
        ["https://example.test/page", "https://comicvine.gamespot.com/foo/4000-9/"],
        issue_id="9",
    )
    assert result == ["https://example.test/page", "https://comicvine.gamespot.com/foo/4000-9/"]


def test_join_web_links_for_comic_does_not_duplicate_volume_url():
    comic = Comic(
        path="a.cbz",
        cv_issue_id="105810",
        cv_series_id="11310",
        web_links=[
            "https://comicvine.gamespot.com/the-pulse-10-house-of-m/4000-105810/",
        ],
    )
    serialized = join_web_links_for_comic(comic)
    assert "4050-11310" not in serialized
    assert serialized.count("105810") == 1
    assert "/issue/4000-" not in serialized
