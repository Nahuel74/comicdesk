from comicdesk.services.comicinfo import format_comma_separated, metadata_field_display_label
from comicdesk.services.comicvine_api import _merge_volume_into_issue
from comicdesk.models import ComicVineIssue, ComicVineVolume
from pathlib import Path
from comicdesk.models import Comic
from comicdesk.services.identification import apply_issue_to_comic


def test_metadata_field_display_labels_are_spaced():
    assert metadata_field_display_label("cover_artist") == "Cover Artist"
    assert metadata_field_display_label("story_arc") == "Story Arc"
    assert metadata_field_display_label("age_rating") == "Age Rating"
    assert metadata_field_display_label("cv_series_id") == "Series ID"


def test_format_comma_separated_normalizes_spacing():
    assert format_comma_separated("A,B; C") == "A, B, C"


def test_merge_volume_does_not_map_concepts_to_genre():
    issue = ComicVineIssue("1", "2", "Series", "1", "1", "2020-01-01", "url")
    volume = ComicVineVolume("2", "Series", concepts=["Homage Covers"], imprint="Marvel Comics Group")
    _merge_volume_into_issue(issue, volume)
    assert issue.genres == []
    assert issue.imprint == "Marvel Comics Group"


def test_apply_formats_editor_list():
    comic = Comic(Path("book.cbz"))
    issue = ComicVineIssue(
        "1", "2", "Series", "1", "1", "2020-01-01", "url",
        person_credits=[
            {"name": "One", "role": "editor"},
            {"name": "Two", "role": "editor"},
        ],
    )
    apply_issue_to_comic(comic, issue, overwrite=True)
    assert comic.editor == "One, Two"
