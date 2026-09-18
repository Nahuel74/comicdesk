"""Tests for the persistent CBL wishlist service."""

from comicdesk.models import CBLBook, Comic
from comicdesk.services.cbl_reader import book_dedupe_key
from comicdesk.services.wishlist import WishlistManager


def test_book_dedupe_key_prefers_cv_issue():
    book = CBLBook(series_name="Spider-Man", issue_number="1", cv_issue_id="123")
    assert book_dedupe_key(book) == ("cv", "123", "")


def test_add_books_upgrades_empty_duplicate_from_cbl(tmp_path):
    path = tmp_path / "wishlist.json"
    manager = WishlistManager(path=path)
    stale = CBLBook(series_name="", issue_number="", volume="2004", cv_issue_id="120015")
    manager.add_books([stale])
    fresh = CBLBook(
        series_name="Excalibur",
        issue_number="13",
        volume="2004",
        year="2005",
        cv_issue_id="120015",
    )
    result = manager.add_books([fresh])
    assert result.added == 0
    assert result.updated == 1
    item = manager.items()[0]
    assert item.series_name == "Excalibur"
    assert item.issue_number == "13"


def test_repair_from_books_updates_existing_wishlist(tmp_path):
    path = tmp_path / "wishlist.json"
    manager = WishlistManager(path=path)
    manager.add_books([
        CBLBook(series_name="", issue_number="", cv_issue_id="104861", volume="2005"),
    ])
    repaired = manager.repair_from_books([
        CBLBook(series_name="House of M", issue_number="1", cv_issue_id="104861"),
    ])
    assert repaired == 1
    assert manager.items()[0].series_name == "House of M"


def test_add_books_deduplicates(tmp_path):
    path = tmp_path / "wishlist.json"
    manager = WishlistManager(path=path)
    first = CBLBook(series_name="Batman", issue_number="1", cv_issue_id="10")
    duplicate = CBLBook(series_name="Batman", issue_number="1", cv_issue_id="10")
    other = CBLBook(series_name="Batman", issue_number="2", cv_issue_id="11")

    result = manager.add_books([first, duplicate, other])
    assert result.added == 2
    assert result.skipped_duplicates == 1
    assert len(manager.items()) == 2


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "wishlist.json"
    manager = WishlistManager(path=path)
    manager.add_books([CBLBook(series_name="X-Men", issue_number="5", volume="2020")])

    reloaded = WishlistManager(path=path)
    items = reloaded.items()
    assert len(items) == 1
    assert items[0].series_name == "X-Men"
    assert items[0].issue_number == "5"
    assert items[0].volume == "2020"


def test_reconcile_with_library_removes_acquired_items(tmp_path):
    path = tmp_path / "wishlist.json"
    manager = WishlistManager(path=path)
    manager.add_books([
        CBLBook(series_name="Batman", issue_number="1", cv_issue_id="100"),
        CBLBook(series_name="Batman", issue_number="2", cv_issue_id="101"),
    ])
    local = [Comic(path="batman-1.cbz", series_name="Batman", issue_number="1", cv_issue_id="100")]

    removed = manager.reconcile_with_library(local)
    assert removed == 1
    assert len(manager.items()) == 1
    assert manager.items()[0].issue_number == "2"


def test_remove_and_clear(tmp_path):
    path = tmp_path / "wishlist.json"
    manager = WishlistManager(path=path)
    books = [
        CBLBook(series_name="A", issue_number="1"),
        CBLBook(series_name="B", issue_number="2"),
    ]
    manager.add_books(books)
    assert manager.remove_books([books[0]]) == 1
    assert len(manager.items()) == 1
    manager.clear()
    assert manager.items() == []
