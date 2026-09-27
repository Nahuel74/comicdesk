"""Comic Vine story arc search helpers."""

from comicdesk.models import ComicVineStoryArc
from comicdesk.services.comicvine_api import (
    _parse_story_arc_row,
    _story_arc_relevance,
    _story_arc_search_phrases,
)


def test_parse_story_arc_row_accepts_numeric_id():
    arc = _parse_story_arc_row(
        {
            "id": 40761,
            "name": '"Batman" Knightfall',
            "deck": "Bane breaks Batman.",
        }
    )
    assert arc == ComicVineStoryArc(
        id="4045-40761",
        name='"Batman" Knightfall',
        deck="Bane breaks Batman.",
    )


def test_story_arc_search_phrases_includes_subphrases():
    phrases = _story_arc_search_phrases("one word under doom")
    assert "one word under doom" in phrases
    assert "under doom" in phrases


def test_story_arc_relevance_prefers_closer_title():
    arc = ComicVineStoryArc(id="4045-1", name='"Avengers" One World Under Doom')
    high = _story_arc_relevance(arc, "one world under doom")
    low = _story_arc_relevance(arc, "under doom")
    assert high > low
