"""ComicInfo XML schema and conversion helpers.

ComicInfo is deliberately handled in one place so the CBZ reader and writer
agree on field names, namespaces, casing and text conversion.  Unknown XML
elements are retained by the model and copied back by the writer.
"""

from __future__ import annotations

from copy import deepcopy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.utils.url_parser import extract_all_cv_ids


MAX_COMICINFO_BYTES = 2 * 1024 * 1024
MAX_COMICINFO_NODES = 50_000
MAX_COMICINFO_DEPTH = 128


class ComicInfoError(ValueError):
    """Raised when a ComicInfo document is malformed or unsafe to parse."""


# XML tag -> Comic attribute.  Ordering follows the commonly used ComicInfo
# schema and makes generated files stable for users and version control.
FIELD_TAGS: tuple[tuple[str, str], ...] = (
    ("Title", "title"), ("Series", "series_name"), ("Number", "issue_number"),
    ("Volume", "volume"), ("AlternateSeries", "alternate_series"),
    ("AlternateNumber", "alternate_number"), ("AlternateCount", "alternate_count"),
    ("Count", "count"),
    ("StoryArc", "story_arc"),
    ("StoryArcNumber", "story_arc_number"), ("Summary", "summary"),
    ("Notes", "notes"), ("Year", "year"), ("Month", "month"),
    ("Day", "day"), ("Writer", "writer"), ("Penciller", "penciller"),
    ("Inker", "inker"), ("Colorist", "colorist"), ("Letterer", "letterer"),
    ("CoverArtist", "cover_artist"), ("Editor", "editor"),
    ("Translator", "translator"), ("Publisher", "publisher"),
    ("Imprint", "imprint"), ("Genre", "genre"), ("Tags", "tags"),
    ("PageCount", "page_count"), ("LanguageISO", "language_iso"),
    ("Format", "format"), ("BlackAndWhite", "black_and_white"),
    ("Manga", "manga"), ("Characters", "characters"), ("Teams", "teams"),
    ("Locations", "locations"), ("ScanInformation", "scan_information"),
    ("AgeRating", "age_rating"), ("CommunityRating", "community_rating"),
    ("MainCharacterOrTeam", "main_character_or_team"), ("Review", "review"),
    ("SeriesGroup", "series_group"), ("GTIN", "gtin"), ("Web", "web_links"),
)
KNOWN_TAGS = {tag.casefold() for tag, _ in FIELD_TAGS}


def parse_comicinfo(data: bytes | str, path: Path) -> Comic:
    """Parse a ComicInfo document into a Comic.

    Passing bytes to ElementTree lets its XML declaration select UTF-8,
    UTF-16, Latin-1, or another declared encoding correctly.  Parse errors
    are intentionally allowed to reach the caller.
    """
    if isinstance(data, bytes) and len(data) > MAX_COMICINFO_BYTES:
        raise ComicInfoError("ComicInfo.xml exceeds the supported size limit")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ComicInfoError("ComicInfo.xml is corrupt") from exc
    _validate_root(root)
    _validate_tree_limits(root)
    return comic_from_element(root, path)


def comic_from_element(root: ET.Element, path: Path) -> Comic:
    """Convert an already parsed ComicInfo root to a Comic instance."""
    _validate_root(root)
    _validate_tree_limits(root)
    comic = Comic(path=path)
    for child in list(root):
        tag = local_name(child.tag)
        field_name = _field_for_tag(tag)
        if field_name is None:
            comic.comicinfo_unknown.append(deepcopy(child))
            continue
        value = child.text if child.text is not None else ""
        if field_name != "notes":
            value = value.strip()
        if field_name == "web_links":
            comic.web_links.extend(split_web_links(value))
        elif field_name == "notes" and comic.notes and value:
            comic.notes = f"{comic.notes}\n{value}"
        else:
            setattr(comic, field_name, value)

    combined = " ".join(comic.web_links + ([comic.notes] if comic.notes else []))
    ids = extract_all_cv_ids(combined)
    for item in ids:
        if not comic.cv_series_id and item.get("series_id"):
            comic.cv_series_id = item["series_id"]
        if not comic.cv_issue_id and item.get("issue_id"):
            comic.cv_issue_id = item["issue_id"]
    return comic


def comic_to_element(comic: Comic, root: ET.Element | None = None) -> ET.Element:
    """Apply Comic fields to a ComicInfo root, retaining unknown elements."""
    if root is None:
        root = ET.Element("ComicInfo")
        for extra in comic.comicinfo_unknown:
            root.append(deepcopy(extra))
    _validate_root(root)
    namespace = namespace_uri(root.tag)
    for tag, field_name in FIELD_TAGS:
        value = getattr(comic, field_name, "")
        if field_name == "web_links":
            value = join_web_links_for_comic(comic)
        elif isinstance(value, (list, tuple, set)):
            value = ", ".join(str(item) for item in value)
        _set_child_text(root, tag, str(value or ""), namespace)
    return root


def local_name(tag: str) -> str:
    """Return an XML name without its namespace, safely for regular tags."""
    return tag.rsplit("}", 1)[-1]


def namespace_uri(tag: str) -> str:
    """Return the namespace URI embedded in an ElementTree qualified name."""
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def split_web_links(value: str) -> list[str]:
    """Split Web content while retaining all links and non-empty content."""
    text = value or ""
    links = re.findall(r"(?:https?|ftp)://[^\s,;]+", text, flags=re.IGNORECASE)
    if links:
        return [link.strip() for link in links if link.strip()]
    return [part for part in re.split(r"[\s,]+", text.strip()) if part]


def join_web_links(value: object) -> str:
    """Convert the public list of Web links into ComicInfo text."""
    if isinstance(value, str):
        return value.strip()
    if not value:
        return ""
    return " ".join(str(item).strip() for item in value if str(item).strip())


def join_web_links_for_comic(comic: Comic) -> str:
    """Serialize explicit links and derive stable Comic Vine links from IDs."""
    links = join_web_links(comic.web_links).split()
    derived = []
    if comic.cv_issue_id:
        derived.append(f"https://comicvine.gamespot.com/issue/4000-{comic.cv_issue_id}/")
    if comic.cv_series_id:
        derived.append(f"https://comicvine.gamespot.com/volume/4050-{comic.cv_series_id}/")
    for link in derived:
        if link not in links:
            links.append(link)
    return " ".join(links)


def _field_for_tag(tag: str) -> str | None:
    folded = tag.casefold()
    for xml_tag, field_name in FIELD_TAGS:
        if xml_tag.casefold() == folded:
            return field_name
    return None


def _validate_root(root: ET.Element) -> None:
    if local_name(root.tag).casefold() != "comicinfo":
        raise ComicInfoError("ComicInfo.xml has an invalid root element")


def _validate_tree_limits(root: ET.Element) -> None:
    count = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > MAX_COMICINFO_NODES:
            raise ComicInfoError("ComicInfo.xml contains too many XML nodes")
        if depth > MAX_COMICINFO_DEPTH:
            raise ComicInfoError("ComicInfo.xml is too deeply nested")
        stack.extend((child, depth + 1) for child in list(element))


def _set_child_text(root: ET.Element, tag: str, value: str, namespace: str) -> None:
    children = [child for child in list(root)
                if local_name(child.tag).casefold() == tag.casefold()]
    if not children:
        if value:
            qualified = f"{{{namespace}}}{tag}" if namespace else tag
            ET.SubElement(root, qualified).text = value
        return
    children[0].text = value or None
    for duplicate in children[1:]:
        root.remove(duplicate)


def _find_child(root: ET.Element, tag: str) -> ET.Element | None:
    wanted = tag.casefold()
    for child in list(root):
        if local_name(child.tag).casefold() == wanted:
            return child
    return None
