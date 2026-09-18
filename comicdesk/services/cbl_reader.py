"""Reader and local-file reconciliation for ComicRack CBL files."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Union
import re
import xml.etree.ElementTree as ET

from comicdesk.models import CBLBook, Comic, ComicVineMetadata, ReadingList
from comicdesk.services.cbl_display import enrich_cbl_book


LEGACY_NAMESPACE = "https://cbl-maker.dev/xml/metadata"
COMICDESK_NAMESPACE = "https://comicdesk.dev/xml/metadata"
KNOWN_NAMESPACES = (LEGACY_NAMESPACE, COMICDESK_NAMESPACE)
MAX_CBL_BYTES = 10 * 1024 * 1024
MAX_CBL_NODES = 50_000
MAX_CBL_DEPTH = 128
_CV_METADATA_FIELDS = {
    "id": "id",
    "seriesid": "series_id",
    "seriesname": "series_name",
    "volume": "volume",
    "issuenumber": "issue_number",
    "coverdate": "cover_date",
    "weburl": "web_url",
}
_SUPPORTED_ORDERING = {"manual", "release_date", "series_issue", "volume", "title"}


class CBLParseError(ValueError):
    """Raised when a CBL cannot be safely interpreted."""


class _CBLLimitError(ValueError):
    pass

class _LimitedTreeBuilder(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._nodes = 0

    def start(self, tag, attrs):
        self._nodes += 1
        self._depth += 1
        if self._nodes > MAX_CBL_NODES:
            raise _CBLLimitError("CBL contains too many XML nodes")
        if self._depth > MAX_CBL_DEPTH:
            raise _CBLLimitError("CBL XML nesting is too deep")
        return super().start(tag, attrs)

    def end(self, tag):
        element = super().end(tag)
        self._depth -= 1
        return element


@dataclass
class CBLDocument:
    """Parsed CBL data, retaining the order supplied by the document."""
    name: str
    books: list[CBLBook]
    ordered_by: str = "manual"
    order_direction: str = "asc"

    def to_reading_list(self) -> ReadingList:
        """Return references as Comics (their paths are intentionally empty)."""
        return ReadingList(self.name, [book.to_comic() for book in self.books],
                           self.ordered_by, self.order_direction)


@dataclass
class ReconciliationResult:
    """Result of matching CBL references to already scanned comics."""
    matches: list[Comic]
    new_issues: list[Comic]
    missing_files: list[CBLBook]

    @property
    def unmatched(self) -> list[CBLBook]:
        return self.missing_files

    @property
    def matched(self) -> list[Comic]:
        return self.matches


def read_cbl(source: Union[str, bytes, Path]) -> CBLDocument:
    """Read a CBL from XML text, bytes, or a filesystem path."""
    try:
        parser = ET.XMLParser(target=_LimitedTreeBuilder())
        if isinstance(source, Path):
            _check_file_size(source)
            root = ET.parse(source, parser=parser).getroot()
        elif isinstance(source, bytes):
            _check_input_size(len(source))
            root = ET.fromstring(source, parser=parser)
        elif isinstance(source, str) and source.lstrip().startswith("<"):
            _check_input_size(len(source.encode("utf-8")))
            root = ET.fromstring(source, parser=parser)
        else:
            path = Path(str(source))
            _check_file_size(path)
            root = ET.parse(path, parser=parser).getroot()
    except _CBLLimitError as exc:
        raise CBLParseError(str(exc)) from exc
    except CBLParseError:
        raise
    except (OSError, ET.ParseError, UnicodeError, ValueError) as exc:
        raise CBLParseError("Invalid CBL XML") from exc
    if _local(root.tag).lower() != "readinglist":
        raise CBLParseError("CBL root must be ReadingList")

    name = _child_text(root, "name") or "Imported reading list"
    root_attrs = {_local(k).lower(): _clean(v) for k, v in root.attrib.items()}
    ordered_by = (root_attrs.get("orderedby") or root_attrs.get("orderby") or
                  _child_text(root, "orderedby") or "manual").casefold()
    if ordered_by not in _SUPPORTED_ORDERING:
        ordered_by = "manual"
    direction = (root_attrs.get("orderdirection") or
                 _child_text(root, "orderdirection") or "asc").casefold()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    books: list[CBLBook] = []
    for index, element in enumerate(root.iter()):
        if _local(element.tag).lower() != "book":
            continue
        attrs = {_local(k).lower(): _clean(v) for k, v in element.attrib.items()}
        database = next((child for child in element if _local(child.tag).lower() == "database"), None)
        db_attrs = ({_local(k).lower(): _clean(v) for k, v in database.attrib.items()}
                    if database is not None else {})
        # ComicRack commonly uses attributes; accepting child fields makes the
        # importer useful with CBL producers that emit element-based XML.
        series = _first_book_field(attrs, element, "seriesname", "series")
        volume = _first_book_field(attrs, element, "volume")
        issue = _first_book_field(attrs, element, "issue", "number")
        year = _first_book_field(attrs, element, "year")
        cv_issue = db_attrs.get("issue") or attrs.get("cvissueid")
        cv_series = db_attrs.get("series") or attrs.get("cvseriesid")
        if db_attrs.get("name", "").lower() not in {"", "cv", "comicvine"}:
            cv_issue = cv_series = None
        metadata = _read_cv_metadata(element)
        books.append(
            enrich_cbl_book(
                CBLBook(
                    series,
                    volume,
                    issue,
                    year,
                    cv_series or None,
                    cv_issue or None,
                    index,
                    metadata,
                )
            )
        )
    return CBLDocument(name=name, books=_deduplicate(books),
                       ordered_by=ordered_by, order_direction=direction)


def _check_input_size(size: int) -> None:
    if size > MAX_CBL_BYTES:
        raise CBLParseError("CBL input exceeds the maximum size")


def _check_file_size(path: Path) -> None:
    _check_input_size(path.stat().st_size)

def parse_cbl(source: Union[str, bytes, Path]) -> CBLDocument:
    """Compatibility alias for :func:`read_cbl`."""
    return read_cbl(source)


def read_cbl_file(source: Union[str, Path]) -> CBLDocument:
    """Explicitly named compatibility entry point for file imports."""
    return read_cbl(Path(source))

def reconcile_cbl(cbl: Union[CBLDocument, Iterable[CBLBook]],
                  scanned: Iterable[Comic]) -> ReconciliationResult:
    """Match references by CV issue ID, then series/volume/issue.

    Matching consumes each scanned comic once. Existing Comic objects are
    enriched from the CBL only where local values are absent.
    """
    books = cbl.books if isinstance(cbl, CBLDocument) else list(cbl)
    comics = list(scanned)
    used: set[int] = set()
    matches: list[Comic] = []
    missing: list[CBLBook] = []
    matched_ids: set[int] = set()
    for book in _deduplicate(books):
        candidate = _find_by_cv(book, comics, used)
        if candidate is None:
            candidate = _find_by_key(book, comics, used)
        if candidate is None:
            missing.append(book)
            continue
        used.add(id(candidate))
        matched_ids.add(id(candidate))
        _enrich_from_cbl(candidate, book)
        matches.append(candidate)
    new_issues = [comic for comic in comics if id(comic) not in matched_ids]
    return ReconciliationResult(matches, new_issues, missing)

def reconcile(cbl: Union[CBLDocument, Iterable[CBLBook]],
              scanned: Iterable[Comic]) -> ReconciliationResult:
    return reconcile_cbl(cbl, scanned)


def _find_by_cv(book: CBLBook, comics: list[Comic], used: set[int]):
    if not book.cv_issue_id:
        return None
    for comic in comics:
        if (id(comic) in used or
                _normal(comic.cv_issue_id or "") != _normal(book.cv_issue_id)):
            continue
        if (book.cv_series_id and comic.cv_series_id and
                _normal(book.cv_series_id) != _normal(comic.cv_series_id)):
            continue
        return comic
    return None

def _find_by_key(book: CBLBook, comics: list[Comic], used: set[int]):
    key = _identity(book.series_name, book.volume, book.issue_number)
    if not all(key):
        return None
    for comic in comics:
        if id(comic) in used:
            continue
        if _identity(comic.series_name, comic.volume, comic.issue_number) == key:
            return comic
    return None

def _identity(series: str, volume: str, issue: str):
    return (_normal(series), _normal(volume), _issue(issue))


def comic_dedupe_key(comic: Comic) -> tuple:
    """Return a stable deduplication key for a local or virtual list entry."""
    return book_dedupe_key(
        CBLBook(
            series_name=comic.series_name,
            volume=comic.volume,
            issue_number=comic.issue_number,
            cv_series_id=comic.cv_series_id,
            cv_issue_id=comic.cv_issue_id,
        )
    )


def ordered_comics_for_import(document: CBLDocument, staged: Iterable[Comic]) -> list[Comic]:
    """Return one Comic per CBL book in document order (library match or virtual)."""
    comics = list(staged)
    used: set[int] = set()
    ordered: list[Comic] = []
    for book in _deduplicate(document.books):
        candidate = _find_by_cv(book, comics, used)
        if candidate is None:
            candidate = _find_by_key(book, comics, used)
        if candidate is None:
            ordered.append(book.to_comic())
            continue
        used.add(id(candidate))
        _enrich_from_cbl(candidate, book)
        ordered.append(candidate)
    return ordered


def book_dedupe_key(book: CBLBook) -> tuple:
    """Return a stable deduplication key for a CBL reference."""
    if book.cv_issue_id:
        key: tuple = ("cv", _normal(book.cv_issue_id), _normal(book.cv_series_id or ""))
    else:
        key = ("key",) + _identity(book.series_name, book.volume, book.issue_number)
    if key == ("key", "", "", ""):
        key = ("position", book.position)
    return key


def _deduplicate(books: Iterable[CBLBook]) -> list[CBLBook]:
    seen: set[tuple] = set()
    result = []
    for book in books:
        key = book_dedupe_key(book)
        if key not in seen:
            seen.add(key)
            result.append(book)
    return result

def _enrich_from_cbl(comic: Comic, book: CBLBook) -> None:
    """Copy non-empty CBL identifiers and metadata without replacing local data."""
    if not comic.cv_series_id and book.cv_series_id:
        comic.cv_series_id = book.cv_series_id
    if not comic.cv_issue_id and book.cv_issue_id:
        comic.cv_issue_id = book.cv_issue_id
    if comic.cv_metadata is None and book.cv_metadata is not None:
        comic.cv_metadata = book.cv_metadata

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local(child.tag).lower() == name.lower() and child.text:
            return _clean(child.text)
    return ""


def _first_book_field(attrs: dict, element: ET.Element, *names: str) -> str:
    """Return the first non-empty Book field from attributes or child elements."""
    for name in names:
        value = attrs.get(name.casefold(), "")
        if not value:
            value = _child_text(element, name)
        if value:
            return value
    return ""

def _read_cv_metadata(book: ET.Element) -> ComicVineMetadata | None:
    """Read the v1 ComicDesk extension, ignoring unknown versions/fields."""
    extension = next((child for child in book
                      if _local(child.tag).lower() == "comicvinemetadata"), None)
    if extension is None or not _is_comicdesk_extension(extension):
        return None
    version = next((value for key, value in extension.attrib.items()
                    if _local(key).lower() == "version"), "1")
    if _clean(version) != "1":
        return None
    values = {}
    for child in extension:
        field = _CV_METADATA_FIELDS.get(_local(child.tag).lower())
        if field is not None and child.text is not None:
            values[field] = child.text.strip()
    if not values:
        return None
    return ComicVineMetadata(
        values.get("id", ""), values.get("series_id", ""),
        values.get("series_name", ""), values.get("volume", ""),
        values.get("issue_number", ""), values.get("cover_date", ""),
        values.get("web_url", ""),
    )

def _is_comicdesk_extension(element: ET.Element) -> bool:
    """Accept ComicVineMetadata from current or legacy ComicDesk namespaces."""
    return any(
        element.tag == f"{{{namespace}}}ComicVineMetadata"
        for namespace in KNOWN_NAMESPACES
    )

def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()

def _normal(value: str) -> str:
    return _clean(value).casefold()

def _issue(value: str) -> str:
    value = _normal(value)
    try:
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    except ValueError:
        return value
