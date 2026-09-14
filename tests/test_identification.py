"""Offline tests for Comic Vine identification and merge policy."""

from pathlib import Path
from types import SimpleNamespace

from comicdesk.models import Comic, ComicVineIssue
from comicdesk.services.identification import (
    STATUS_CANDIDATES,
    STATUS_EMPTY,
    STATUS_EXACT,
    IdentificationResult,
    apply_issue_to_comic,
    identify_comic,
)


def issue(issue_id, series_id="20", series_name="Saga", volume="1", number="3",
          name="", store_date=""):
    return ComicVineIssue(
        id=str(issue_id), series_id=str(series_id), series_name=series_name,
        volume=volume, issue_number=number, cover_date="2020-03-04",
        web_url=f"https://comicvine.test/4000-{issue_id}/", name=name,
        store_date=store_date,
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
    assert client.calls[0] == ("list_issues", "55", "3")


def test_ambiguous_scoped_results_are_candidates_not_first_result():
    first = issue("11", series_id="55")
    second = issue("12", series_id="55")
    comic = Comic(Path("local.cbz"), cv_series_id="55", issue_number="3")

    result = identify_comic(comic, Client(listed=[first, second]))

    assert result.status == STATUS_CANDIDATES
    assert result.issue is None
    assert result.issues == [first, second]
    assert result.candidates == [first, second]


def test_series_and_number_uses_volume_lookup_before_broad_search():
    volume = SimpleNamespace(id="100", name="The Amazing Spider-Man")
    asm61 = issue(
        "61",
        series_id="100",
        series_name="The Amazing Spider-Man",
        number="61",
        name="The Darkness Calls",
        store_date="2004-08-01",
    )
    noise = issue("99", series_name="The Amazing Spider-Man", number="12", name="Other")
    comic = Comic(Path(), series_name="The Amazing Spider-Man", issue_number="61")

    class VolumeClient(Client):
        def get_issue(self, issue_id):
            self.calls.append(("get_issue", issue_id))
            if issue_id == "61":
                return asm61
            return issue(issue_id, number="0")

    client = VolumeClient(volumes=[volume], listed=[asm61], searched=[noise])
    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is not None
    assert result.issue.name == "The Darkness Calls"
    assert result.issue.issue_number == "61"
    assert ("search_volume", "The Amazing Spider-Man") in client.calls
    assert ("list_issues", "100", "61") in client.calls
    assert not any(call[0] == "search_issue" for call in client.calls)


def test_issue_search_does_not_return_other_numbers_when_filter_misses():
    noise = [
        issue("1", series_name="The Amazing Spider-Man", number="12"),
        issue("2", series_name="The Amazing Spider-Man", number="88"),
    ]
    comic = Comic(Path(), series_name="The Amazing Spider-Man", issue_number="61")
    client = Client(searched=noise)

    result = identify_comic(comic, client)

    assert result.status == STATUS_EMPTY
    assert result.issues == []


def test_series_volume_and_number_disambiguate_search_results():
    found = issue("21", series_name="Saga", volume="2", number="3")
    comic = Comic(Path("local.cbz"), series_name=" saga ", volume="2",
                  issue_number="03")
    client = Client(searched=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is found
    assert ("search_issue", "saga #03") in client.calls


def test_search_can_use_series_and_title_when_number_is_missing():
    found = issue("31", series_name="Batman", number="", name="Year One")
    comic = Comic(Path("local.cbz"), series_name="Batman", title="Year One")
    client = Client(searched=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert client.calls[0] == ("search_issue", "Batman Year One")


def test_filename_is_used_when_local_metadata_is_empty():
    found = issue("42", series_name="Saga", volume="2", number="3")
    comic = Comic(Path("Saga Vol. 02 #003 (2020).cbz"))
    client = Client(searched=[found])

    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is found
    assert client.calls[0] == ("search_issue", "Saga #3")
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


def test_search_exact_match_is_hydrated_by_id():
    partial = issue("42", series_name="Saga", number="3")
    hydrated = issue("42", series_name="Saga", number="3", name="Full Title")
    hydrated.description = "Complete description"

    class HydratingClient(Client):
        def get_issue(self, issue_id):
            self.calls.append(("get_issue", issue_id))
            return hydrated

    comic = Comic(Path("local.cbz"), series_name="Saga", issue_number="3")
    client = HydratingClient(searched=[partial])
    result = identify_comic(comic, client)

    assert result.status == STATUS_EXACT
    assert result.issue is hydrated
    assert result.issue.name == "Full Title"
    assert result.issue.description == "Complete description"
    assert ("get_issue", "42") in client.calls


def test_search_exact_match_falls_back_when_hydration_fails():
    partial = issue("42", series_name="Saga", number="3")

    class FailingHydrateClient(Client):
        def get_issue(self, issue_id):
            self.calls.append(("get_issue", issue_id))
            raise RuntimeError("network down")

    comic = Comic(Path("local.cbz"), series_name="Saga", issue_number="3")
    result = identify_comic(comic, FailingHydrateClient(searched=[partial]))

    assert result.status == STATUS_EXACT
    assert result.issue is partial


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


def test_apply_strips_html_from_description():
    comic = Comic(Path("local.cbz"))
    remote = issue("70", series_id="71", series_name="Remote")
    remote.description = "<p>A <b>bold</b> description with &amp; entities.</p>"

    apply_issue_to_comic(comic, remote, overwrite=True)

    assert comic.summary == "A bold description with & entities."
    assert "<p>" not in comic.summary
    assert "<b>" not in comic.summary


def test_apply_uses_store_date_over_cover_date():
    comic = Comic(Path("local.cbz"))
    remote = issue("80", series_id="81", series_name="Remote", number="1",
                   store_date="2025-11-12")

    apply_issue_to_comic(comic, remote, overwrite=True)

    assert comic.year == "2025"
    assert comic.month == "11"
    assert comic.day == "12"


def test_apply_falls_back_to_cover_date_when_store_date_empty():
    comic = Comic(Path("local.cbz"))
    remote = issue("80", series_id="81", series_name="Remote", number="1")

    apply_issue_to_comic(comic, remote, overwrite=True)

    assert comic.year == "2020"
    assert comic.month == "03"
    assert comic.day == "04"


def test_apply_falls_back_to_cover_date_when_store_date_none():
    comic = Comic(Path("local.cbz"))
    remote = ComicVineIssue(
        id="80", series_id="81", series_name="Remote",
        volume="1", issue_number="1", cover_date="2020-03-04",
        web_url="https://comicvine.test/4000-80/", store_date="",
    )

    apply_issue_to_comic(comic, remote, overwrite=True)

    assert comic.year == "2020"
    assert comic.month == "03"
    assert comic.day == "04"
