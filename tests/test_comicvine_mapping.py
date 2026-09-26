from pathlib import Path

from comicdesk.models import Comic, ComicVineIssue, ComicVineVolume
from comicdesk.services.comicvine_api import VOLUME_FIELDS
from comicdesk.services.comicvine_mapping import apply_issue_metadata, apply_volume_metadata
from comicdesk.services.identification import apply_issue_to_comic, apply_volume_to_comic


def _issue(**kwargs):
    defaults = {
        "id": "1", "series_id": "2", "series_name": "Series", "volume": "1",
        "issue_number": "1", "cover_date": "2020-01-01", "web_url": "url", "name": "Issue",
    }
    defaults.update(kwargs)
    return ComicVineIssue(**defaults)


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


def test_artist_role_fills_penciller_and_inker_when_both_empty():
    issue = _issue(person_credits=[{"name": "Alex", "role": "artist"}])
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.penciller == "Alex"
    assert comic.inker == "Alex"
    assert comic.cover_artist == ""


def test_several_artist_credits_share_same_penciller_and_inker_list():
    issue = _issue(person_credits=[
        {"name": "One", "role": "artist"},
        {"name": "Two", "role": "artists"},
    ])
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.penciller == "One, Two"
    assert comic.inker == "One, Two"


def test_artist_and_cover_composite_sets_all_three_roles():
    issue = _issue(person_credits=[{"name": "Combo", "role": "artist, cover"}])
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.penciller == "Combo"
    assert comic.inker == "Combo"
    assert comic.cover_artist == "Combo"


def test_existing_penciller_blocks_artist_fallback():
    issue = _issue(person_credits=[
        {"name": "Pen", "role": "penciler"},
        {"name": "Art", "role": "artist"},
    ])
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.penciller == "Pen"
    assert comic.inker == ""


def test_existing_inker_blocks_artist_fallback():
    issue = _issue(person_credits=[
        {"name": "Ink", "role": "inker"},
        {"name": "Art", "role": "artist"},
    ])
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.penciller == ""
    assert comic.inker == "Ink"


def test_artist_fallback_respects_overwrite_false():
    issue = _issue(person_credits=[{"name": "Alex", "role": "artist"}])
    comic = Comic(Path("book.cbz"), penciller="Manual", inker="Manual")

    apply_issue_to_comic(comic, issue, overwrite=False)

    assert comic.penciller == "Manual"
    assert comic.inker == "Manual"


def test_issue_concept_tags_exclude_variant_names():
    concepts = ["Homage Covers", "Variant Cover", "Variant Artists", "Magic"]
    issue = _issue(concept_credits=concepts)
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.tags == "Homage Covers, Magic"


def test_issue_concept_tags_exclude_colon_variant_lines():
    concepts = [
        "All-New, All-Different Marvel",
        "Variant Artist: Skottie Young",
        "Variant Cover: Blank Sketch",
        "Variant Theme: Marvel Hip-Hop",
    ]
    issue = _issue(concept_credits=concepts)
    comic = Comic(Path("book.cbz"))

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.tags == "All-New, All-Different Marvel"


def test_only_excluded_concepts_do_not_change_tags():
    issue = _issue(concept_credits=["Variant Cover", "variant artists"])
    comic = Comic(Path("book.cbz"), tags="Keep Me")

    apply_issue_to_comic(comic, issue, overwrite=True)

    assert comic.tags == "Keep Me"


def test_apply_issue_metadata_filters_tags_on_overwrite():
    issue = _issue(concept_credits=["Variant Cover", "Magic"])
    comic = Comic(Path("book.cbz"), tags="Old")

    apply_issue_metadata(comic, issue, overwrite=True)

    assert comic.tags == "Magic"


def test_volume_tags_use_concepts_when_present():
    volume = ComicVineVolume(
        "9", "Saga", concepts=["Homage Covers", "Variant Cover", "Magic"],
        concept_credits=["Should Not Use"],
    )
    comic = Comic(Path("book.cbz"))

    apply_volume_to_comic(comic, volume, overwrite=True)

    assert comic.tags == "Homage Covers, Magic"


def test_volume_tags_fall_back_to_concept_credits():
    volume = ComicVineVolume(
        "9", "Saga", concept_credits=["Alpha", "Variant Artists"],
    )
    comic = Comic(Path("book.cbz"))

    apply_volume_to_comic(comic, volume, overwrite=True)

    assert comic.tags == "Alpha"


def test_volume_concepts_only_excluded_do_not_clear_tags():
    volume = ComicVineVolume("9", "Saga", concepts=["Variant Cover"])
    comic = Comic(Path("book.cbz"), tags="Existing")

    apply_volume_to_comic(comic, volume, overwrite=True)

    assert comic.tags == "Existing"


def test_volume_fields_requests_concepts():
    assert "concepts" in VOLUME_FIELDS
