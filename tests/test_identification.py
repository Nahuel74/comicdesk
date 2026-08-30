"""Offline tests for Comic Vine identification and merge policy."""

from pathlib import Path
from types import SimpleNamespace

from cbl_maker.models import Comic, ComicVineIssue
from cbl_maker.services.identification import (
    STATUS_CANDIDATES,
    STATUS_EMPTY,
    STATUS_EXACT,
    IdentificationResult,
    apply_issue_to_comic,
    identify_comic,
)


def issue(issue_id, series_id="20", series_name="Saga", volume="1", number="3",
          name=""):
    return ComicVineIssue(
        id=str(issue_id), series_id=str(series_id), series_name=series_name,
        volume=volume, issue_number=number, cover_date="2020-03-04",
        web_url=f"https://comicvine.test/4000-{issue_id}/", name=name,
    )


class Client:
    def __init__(self, *, by_id=None, listed=None, searched=None, volumes=None):
        self.by_id = by_id
        self.listed = listed
        self.searched = searched or []
        self.volumes = volumes or []
        self.calls = []

    def get_issue(self, issue_id):
        self.calls.append(("get_issue", issue_id))
        return self.by_id

    def list_issues(self, series_id, issue_number):
        self.calls.append(("list_issues", series_id, issue_number))
        return self.listed

    def search_issue(self, query):
        self.calls.append(("search_issue", query))
        return self.searched

    def search_volume(self, query):
        self.calls.append(("search_volume", query))
        return self.volumes


def test_issue_id_is_an_exact_match_and_identification_is_read_only():
    comic = Comic(Path("local.cbz"), series_name="Local", issue_number="9",
                  cv_issue_id="77")
    found = issue("77", series_name="Remote")
    result = identify_comic(comic, Client(by_id=found))

    assert result.status == STATUS_EXACT
    assert result.issue is found
    assert comic.series_name == "Local"
    assert comic.issue_number == "9"


def test_series_id_and_number_use_scoped_issue_lookup():
    found = issue("11", series_id="55", number="03")
    comic = Comic(Path("local.cbz"), cv_series_id="55", issue_number="3")
    client = Client(listed=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is found
    assert client.calls == [("list_issues", "55", "3")]


def test_ambiguous_scoped_results_are_candidates_not_first_result():
    first = issue("11", series_id="55")
    second = issue("12", series_id="55")
    comic = Comic(Path("local.cbz"), cv_series_id="55", issue_number="3")

    result = identify_comic(comic, Client(listed=[first, second]))

    assert result.status == STATUS_CANDIDATES
    assert result.issue is None
    assert result.issues == [first, second]
    assert result.candidates == [first, second]


def test_series_volume_and_number_disambiguate_search_results():
    found = issue("21", series_name="Saga", volume="2", number="3")
    comic = Comic(Path("local.cbz"), series_name=" saga ", volume="2",
                  issue_number="03")
    client = Client(searched=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is found
    assert client.calls == [("search_issue", "saga #03")]


def test_search_can_use_series_and_title_when_number_is_missing():
    found = issue("31", series_name="Batman", number="", name="Year One")
    comic = Comic(Path("local.cbz"), series_name="Batman", title="Year One")
    client = Client(searched=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert client.calls == [("search_issue", "Batman Year One")]


def test_filename_is_used_when_local_metadata_is_empty():
    found = issue("42", series_name="Saga", volume="2", number="3")
    comic = Comic(Path("Saga Vol. 02 #003 (2020).cbz"))
    client = Client(searched=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is found
    assert client.calls == [("search_issue", "Saga #3")]
    assert comic.series_name == ""


def test_empty_issue_search_falls_back_to_volume_candidates():
    volume = SimpleNamespace(id="9", name="Unknown Series")
    comic = Comic(Path("Unknown.cbz"), series_name="Unknown")
    client = Client(volumes=[volume])

    result = identify_comic(comic, client)

    assert result.status == STATUS_CANDIDATES
    assert result.issues == []
    assert result.volumes == [volume]


def test_empty_result_does_not_select_unrelated_search_result():
    comic = Comic(Path("Nothing.cbz"), series_name="Nothing", issue_number="4")
    client = Client(searched=[])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EMPTY
    assert result.issue is None


def test_api_failure_still_allows_filename_fallback():
    found = issue("50", series_name="Fallback", number="1")

    class FailingClient(Client):
        def search_issue(self, query):
            self.calls.append(("search_issue", query))
            if query == "Local #9":
                raise RuntimeError("offline")
            return [found]

    comic = Comic(Path("Fallback #001.cbz"), series_name="Local", issue_number="9")
    result = identify_comic(comic, FailingClient())

    assert result.status == STATUS_EXACT
    assert result.issue is found


def test_apply_preserves_manual_values_and_keeps_remote_proposal():
    comic = Comic(
        Path("local.cbz"), title="Manual title", series_name="Manual series",
        volume="9", issue_number="99", year="1999", month="01", day="02",
        cv_issue_id="manual-issue", cv_series_id="manual-series",
        web_links=["https://manual.test"],
    )
    remote = issue("60", series_id="61", series_name="Remote", volume="2",
                   number="4", name="Remote title")

    apply_issue_to_comic(comic, remote)

    assert comic.cv_metadata is remote
    assert comic.cv_issue_id == "manual-issue"
    assert comic.cv_series_id == "manual-series"
    assert (comic.title, comic.series_name, comic.volume, comic.issue_number) == (
        "Manual title", "Manual series", "9", "99"
    )
    assert (comic.year, comic.month, comic.day) == ("1999", "01", "02")
    assert comic.web_links == ["https://manual.test", remote.web_url]


def test_apply_fills_missing_fields_and_overwrite_is_explicit():
    comic = Comic(Path("local.cbz"), series_name="Manual", issue_number="1")
    remote = issue("70", series_id="71", series_name="Remote", volume="3",
                   number="2", name="Remote title")

    apply_issue_to_comic(comic, remote)
    assert (comic.cv_issue_id, comic.cv_series_id) == ("70", "71")
    assert (comic.series_name, comic.volume, comic.issue_number) == (
        "Manual", "3", "1"
    )
    assert comic.title == "Remote title"

    apply_issue_to_comic(comic, remote, overwrite=True)
    assert (comic.series_name, comic.volume, comic.issue_number) == (
        "Remote", "3", "2"
    )
