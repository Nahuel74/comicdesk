"""Tests for transactional single-comic metadata editing."""

from pathlib import Path

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.services.metadata_session import MetadataSession


def _issue():
    return ComicVineIssue(
        "20", "10", "Saga", "1", "2", "2020-01-02",
        "https://comicvine.test/4000-20/", name="The Issue",
    )


def test_session_uses_an_isolated_draft_and_commit_is_explicit():
    comic = Comic(Path("book.cbz"), title="Original", notes="Keep")
    session = MetadataSession(comic)

    session.set_field("title", "Draft")
    assert comic.title == "Original"
    assert session.draft.title == "Draft"
    assert session.is_dirty

    session.discard()
    assert session.draft.title == "Original"
    assert not session.is_dirty

    session.set_field("title", "Saved")
    session.commit()
    assert comic.title == "Saved"
    assert not session.is_dirty


def test_proposal_changes_draft_only_and_web_links_are_normalized():
    comic = Comic(Path("book.cbz"), series_name="Saga", issue_number="2")
    session = MetadataSession(comic)

    session.apply_proposal(_issue())
    assert comic.cv_issue_id is None
    assert session.draft.cv_issue_id == "20"
    session.set_field("web_links", "https://one.test, https://two.test")
    assert session.draft.web_links == ["https://one.test", "https://two.test"]


def test_volume_proposal_sets_series_without_inventing_issue_id():
    comic = Comic(Path("book.cbz"), issue_number="4")
    session = MetadataSession(comic)

    session.apply_proposal(ComicVineVolume("10", "Saga", "2012", "volume-url"))

    assert session.draft.cv_series_id == "10"
    assert session.draft.series_name == "Saga"
    assert session.draft.issue_number == "4"
    assert session.draft.volume == "2012"
    assert session.draft.year == ""
    assert session.draft.cv_issue_id is None
