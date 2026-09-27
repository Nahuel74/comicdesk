"""Story arc import and Comic Vine arc helpers."""

from pathlib import Path

from comicdesk.models import Comic, ComicVineIssue
from comicdesk.services.arc_list_import import (
    arc_items_from_cv_issues,
    arc_items_from_story_arc_stubs,
    match_arc_items_to_library,
    normalize_cv_issue_id,
)
from comicdesk.services.comicvine_api import normalize_cv_story_arc_id


def test_normalize_cv_story_arc_id():
    assert normalize_cv_story_arc_id("4045-22963") == "22963"
    assert normalize_cv_story_arc_id("22963") == "22963"


def test_match_arc_items_links_local_comic_by_cv_issue_id():
    issues = [
        ComicVineIssue(
            id="4000-1",
            series_id="4050-10",
            series_name="Test",
            volume="1",
            issue_number="2",
            cover_date="2020-01-01",
            web_url="",
        )
    ]
    items = arc_items_from_cv_issues(issues)
    comics = [
        Comic(
            Path("b.cbz"),
            series_name="Test",
            issue_number="2",
            cv_issue_id="4000-1",
        )
    ]
    ordered, linked, missing = match_arc_items_to_library(items, comics)
    assert linked == 1
    assert missing == 0
    assert ordered[0] is comics[0]


def test_arc_items_from_cv_issues_preserves_order():
    issues = [
        ComicVineIssue("4000-1", "4050-1", "A", "1", "1", "2020-01-01", ""),
        ComicVineIssue("4000-2", "4050-1", "A", "1", "2", "2020-02-01", ""),
    ]
    items = arc_items_from_cv_issues(issues)
    assert [item.issue_number for item in items] == ["1", "2"]
    assert items[0].position == 1


def test_arc_items_from_story_arc_stubs_parses_site_url():
    stubs = [
        {
            "id": 37038,
            "site_detail_url": (
                "https://comicvine.gamespot.com/batman-491-the-freedom-of-madness/4000-37038/"
            ),
        }
    ]
    items = arc_items_from_story_arc_stubs(stubs, arc_title='"Batman" Knightfall')
    assert len(items) == 1
    assert items[0].issue_number == "491"
    assert items[0].series_name == "Batman"
    assert items[0].cv_issue_id == "4000-37038"


def test_normalize_cv_issue_id_matches_prefixed_ids():
    assert normalize_cv_issue_id("4000-99") == normalize_cv_issue_id("99")
