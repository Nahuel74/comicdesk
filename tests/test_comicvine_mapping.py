from pathlib import Path

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.services.comicvine_mapping import apply_issue_metadata, apply_volume_metadata


def test_issue_mapping_separates_roles_and_entities():
    issue = ComicVineIssue(
        "1", "2", "Series", "1", "3", "2020-02-03", "url", "Issue",
        description="Summary", publisher="Publisher", genres=["Action"],
        character_credits=["Hero", "Hero"], location_credits=["City"],
        team_credits=["Team"], story_arc_credits=["Arc"],
        person_credits=[{"name": "Writer", "role": "writer"},
                        {"name": "Artist", "role": "penciller"}],
        age_rating="Teen",
    )
    comic = Comic(Path("book.cbz"))

    apply_issue_metadata(comic, issue)

    assert comic.writer == "Writer"
    assert comic.penciller == "Artist"
    assert comic.characters == "Hero, Hero"
    assert comic.summary == "Summary"
    assert comic.age_rating == "Teen"


def test_composite_credit_roles_map_penciler_and_cover():
    issue = ComicVineIssue(
        "101456", "11502", "Black Panther", "1", "1", "2005-02-01", "url", "Issue",
        person_credits=[
            {"name": "John Romita Jr.", "role": "penciler, cover"},
            {"name": "Reginald Hudlin", "role": "writer"},
        ],
    )
    comic = Comic(Path("book.cbz"))

    apply_issue_metadata(comic, issue)

    assert comic.penciller == "John Romita Jr."
    assert comic.cover_artist == "John Romita Jr."
    assert comic.writer == "Reginald Hudlin"


def test_cover_role_alone_maps_to_cover_artist():
    issue = ComicVineIssue(
        "1", "2", "Series", "1", "1", "2020-01-01", "url", "Issue",
        person_credits=[{"name": "Cover Only", "role": "cover"}],
    )
    comic = Comic(Path("book.cbz"))

    apply_issue_metadata(comic, issue)

    assert comic.cover_artist == "Cover Only"
    assert comic.penciller == ""


def test_volume_mapping_uses_start_year_as_comicinfo_volume():
    comic = Comic(Path("book.cbz"), issue_number="2", year="2020")
    volume = ComicVineVolume("9", "Saga", "2012", "url", count_of_issues="66")

    apply_volume_metadata(comic, volume)

    assert comic.cv_series_id == "9"
    assert comic.series_name == "Saga"
    assert comic.volume == "2012"
    assert comic.count == "66"
    assert comic.year == "2020"
