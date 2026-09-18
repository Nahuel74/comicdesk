"""Display helpers for CBL references without duplicating Comic Vine lookups."""

from dataclasses import replace

from comicdesk.models import CBLBook, Comic


def merge_cbl_book(stored: CBLBook, incoming: CBLBook) -> CBLBook:
    """Fill empty fields on *stored* from *incoming* without overwriting local data."""
    incoming = enrich_cbl_book(incoming)
    updates: dict = {}
    for field in ("series_name", "issue_number", "volume", "year"):
        if not (getattr(stored, field) or "").strip():
            value = (getattr(incoming, field) or "").strip()
            if value:
                updates[field] = value
    if stored.cv_series_id is None and incoming.cv_series_id:
        updates["cv_series_id"] = incoming.cv_series_id
    if stored.cv_issue_id is None and incoming.cv_issue_id:
        updates["cv_issue_id"] = incoming.cv_issue_id
    if stored.cv_metadata is None and incoming.cv_metadata is not None:
        updates["cv_metadata"] = incoming.cv_metadata
    return replace(stored, **updates) if updates else stored


def enrich_cbl_book(book: CBLBook) -> CBLBook:
    """Copy empty series/issue/volume/year from embedded Comic Vine metadata."""
    meta = book.cv_metadata
    if meta is None:
        return book
    updates: dict = {}
    if not (book.series_name or "").strip() and (meta.series_name or "").strip():
        updates["series_name"] = meta.series_name.strip()
    if not (book.issue_number or "").strip() and (meta.issue_number or "").strip():
        updates["issue_number"] = meta.issue_number.strip()
    if not (book.volume or "").strip() and (meta.volume or "").strip():
        updates["volume"] = meta.volume.strip()
    if not (book.year or "").strip() and (meta.cover_date or "").strip():
        year = meta.cover_date.strip()[:4]
        if year.isdigit():
            updates["year"] = year
    return replace(book, **updates) if updates else book


def cbl_book_series_label(book: CBLBook) -> str:
    if (book.series_name or "").strip():
        return book.series_name.strip()
    if book.cv_metadata and (book.cv_metadata.series_name or "").strip():
        return book.cv_metadata.series_name.strip()
    return "—"


def cbl_book_issue_label(book: CBLBook) -> str:
    issue = (book.issue_number or "").strip()
    if issue:
        return issue
    if book.cv_metadata and (book.cv_metadata.issue_number or "").strip():
        return book.cv_metadata.issue_number.strip()
    return "—"


def cbl_book_volume_label(book: CBLBook) -> str:
    if (book.volume or "").strip():
        return book.volume.strip()
    if book.cv_metadata and (book.cv_metadata.volume or "").strip():
        return book.cv_metadata.volume.strip()
    return "—"


def comic_release_display(comic: Comic) -> str:
    """Label for release: full ComicInfo date, CBL/comic year, or CV cover date."""
    if comic.release_date is not None:
        return comic.release_date.strftime("%Y-%m-%d")
    if comic.year:
        return comic.year
    if comic.cv_metadata and comic.cv_metadata.cover_date:
        return comic.cv_metadata.cover_date
    return "—"
