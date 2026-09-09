"""Tests for the persistent CBL wishlist service."""

from comicdesk.models import CBLBook, Comic
from comicdesk.services.cbl_reader import book_dedupe_key
from comicdesk.services.wishlist import WishlistManager


def test_book_dedupe_key_prefers_cv_issue():
    book = CBLBook(series_name="Spider-Man", issue_number="1", cv_issue_id="123")
    assert book_dedupe_key(book) == ("cv", "123", "")


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
