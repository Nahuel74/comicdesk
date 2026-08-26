"""Tests for CBL parsing and local reconciliation."""

from pathlib import Path

import pytest

from cbl_maker.models import Comic, ComicVineIssue
from cbl_maker.services.cbl_reader import (
    CBLParseError,
    MAX_CBL_BYTES,
    MAX_CBL_DEPTH,
    MAX_CBL_NODES,
    read_cbl,
    reconcile_cbl,
)


XML = """<ReadingList><Name>Example</Name><Books>
<Book SeriesName="Saga" Volume="1" Issue="2">
  <Database Name="cv" Series="10" Issue="20" />
</Book>
<Book SeriesName="Saga" Volume="2" Issue="2" />
</Books></ReadingList>"""


def test_reads_name_and_book_references():
    document = read_cbl(XML)
    assert document.name == "Example"
    assert [(book.series_name, book.volume, book.issue_number)
            for book in document.books] == [("Saga", "1", "2"), ("Saga", "2", "2")]
    assert document.books[0].cv_issue_id == "20"


def test_invalid_xml_is_a_controlled_error():
    with pytest.raises(CBLParseError):
        read_cbl("<ReadingList>")


def test_rejects_input_larger_than_configured_limit():
    oversized = b"<ReadingList>" + b" " * MAX_CBL_BYTES + b"</ReadingList>"
    with pytest.raises(CBLParseError, match="maximum size"):
        read_cbl(oversized)


def test_rejects_excessive_xml_depth():
    nested = "<ReadingList>" + "<Container>" * MAX_CBL_DEPTH
    nested += "</Container>" * MAX_CBL_DEPTH + "</ReadingList>"
    with pytest.raises(CBLParseError, match="nesting"):
        read_cbl(nested)


def test_rejects_excessive_xml_node_count():
    xml = "<ReadingList>" + "<Container />" * MAX_CBL_NODES + "</ReadingList>"
    with pytest.raises(CBLParseError, match="nodes"):
        read_cbl(xml)


def test_reconciles_by_cv_first_and_preserves_metadata():
    metadata = ComicVineIssue("20", "10", "Saga", "1", "2", "2020-01-01", "url")
    comic = Comic(Path("saga.cbz"), series_name="Different", cv_issue_id="20",
                  cv_series_id="10", cv_metadata=metadata)
    result = reconcile_cbl(read_cbl(XML), [comic])
    assert result.matches == [comic]
    assert result.matches[0].cv_metadata is metadata
    assert len(result.missing_files) == 1


def test_fallback_keeps_same_issue_in_different_volumes_separate():
    document = read_cbl(XML)
    comics = [Comic(Path("one.cbz"), series_name="Saga", volume="1", issue_number="2"),
              Comic(Path("two.cbz"), series_name="Saga", volume="2", issue_number="2")]
    result = reconcile_cbl(document, comics)
    assert result.matches == comics
    assert result.missing_files == []


@pytest.mark.parametrize("criterion", ["manual", "release_date", "series_issue",
                                        "volume", "title"])
def test_accepts_supported_ordering_criteria(criterion):
    document = read_cbl(f'<ReadingList OrderedBy="{criterion}" />')
    assert document.ordered_by == criterion


def test_unknown_ordering_criterion_falls_back_to_manual():
    document = read_cbl('<ReadingList OrderedBy="unsupported" />')
    assert document.ordered_by == "manual"


@pytest.mark.parametrize("xml", [
    '<ReadingList OrderDirection="DESC" />',
    "<ReadingList><OrderDirection>DESC</OrderDirection></ReadingList>",
])
def test_reads_order_direction_from_attribute_or_child(xml):
    document = read_cbl(xml)
    assert document.order_direction == "desc"


def test_cv_issue_match_requires_matching_series_when_both_are_available():
    xml = '<ReadingList><Book><Database Name="cv" Series="10" Issue="20" /></Book></ReadingList>'
    wrong_series = Comic(Path("wrong.cbz"), cv_issue_id="20", cv_series_id="11")
    result = reconcile_cbl(read_cbl(xml), [wrong_series])
    assert result.matches == []
    assert result.missing_files


def test_reconciliation_fills_missing_ids_and_metadata_only():
    metadata = ComicVineIssue("20", "10", "Saga", "1", "2", "2020-01-01", "url")
    xml = """<ReadingList><Book><Database Name="cv" Series="10" Issue="20" />
    <cblmaker:ComicVineMetadata xmlns:cblmaker="https://cbl-maker.dev/xml/metadata" version="1">
      <cblmaker:Id>20</cblmaker:Id><cblmaker:SeriesId>10</cblmaker:SeriesId>
    </cblmaker:ComicVineMetadata></Book></ReadingList>"""
    comic = Comic(Path("issue.cbz"), cv_issue_id="20")
    result = reconcile_cbl(read_cbl(xml), [comic])
    assert result.matches == [comic]
    assert comic.cv_series_id == "10"
    assert comic.cv_issue_id == "20"
    assert comic.cv_metadata is not None
    assert comic.cv_metadata.id == metadata.id


def test_reconciliation_preserves_existing_ids_and_metadata():
    cbl_metadata = """<cblmaker:ComicVineMetadata
      xmlns:cblmaker="https://cbl-maker.dev/xml/metadata" version="1">
      <cblmaker:Id>20</cblmaker:Id><cblmaker:SeriesId>10</cblmaker:SeriesId>
    </cblmaker:ComicVineMetadata>"""
    xml = f"""<ReadingList><Book SeriesName="Saga" Volume="1" Issue="2">
    <Database Name="cv" Series="10" Issue="20" />
    {cbl_metadata}</Book></ReadingList>"""
    local_metadata = ComicVineIssue("local", "local-series", "Local", "", "", "", "")
    comic = Comic(Path("issue.cbz"), cv_issue_id="local-issue",
                  cv_series_id="local-series", cv_metadata=local_metadata,
                  series_name="Saga", volume="1", issue_number="2")
    # CV IDs intentionally do not match, so the textual identity is the fallback.
    result = reconcile_cbl(read_cbl(xml), [comic])
    assert result.matches == [comic]
    assert comic.cv_issue_id == "local-issue"
    assert comic.cv_series_id == "local-series"
    assert comic.cv_metadata is local_metadata
