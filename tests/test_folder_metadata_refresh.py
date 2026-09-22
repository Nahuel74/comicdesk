"""Offline tests for library batch Comic Vine metadata refresh."""

from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.cbz_writer import CbzWriteError
from comicdesk.ui.comic_list_workers import (
    FolderMetadataRefreshWorker,
    format_metadata_refresh_details,
    metadata_refresh_status_line,
    refresh_comic_metadata_from_comicvine,
)
from tests.test_identification import Client, issue


def test_refresh_success_via_cv_issue_id(monkeypatch):
    comic = Comic(Path("local.cbz"), cv_issue_id="77", series_name="Local")
    found = issue("77", series_name="Remote", name="Remote title")
    found.person_credits = [{"name": "Writer", "role": "writer"}]
    client = Client(by_id=found)

    def fake_write(draft):
        assert draft.series_name == "Remote"
        return draft.path

    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.write_comic_metadata", fake_write
    )

    result = refresh_comic_metadata_from_comicvine(comic, client)

    assert result.outcome == "success"
    assert comic.series_name == "Remote"
    assert comic.title == "Remote title"
    assert client.calls[0] == ("get_issue", "77")


def test_refresh_skips_candidates(monkeypatch):
    first = issue("11", series_id="55")
    second = issue("12", series_id="55")
    comic = Comic(Path("local.cbz"), cv_series_id="55", issue_number="3")
    client = Client(listed=[first, second])
    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.write_comic_metadata",
        lambda draft: draft.path,
    )

    result = refresh_comic_metadata_from_comicvine(comic, client)

    assert result.outcome == "skipped"
    assert "more than one" in result.message


def test_refresh_skips_empty_match(monkeypatch):
    comic = Comic(Path("local.cbz"), cv_series_id="55", issue_number="3")
    client = Client(listed=[])
    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.write_comic_metadata",
        lambda draft: draft.path,
    )

    result = refresh_comic_metadata_from_comicvine(comic, client)

    assert result.outcome == "skipped"
    assert "did not find" in result.message


def test_refresh_hydrates_list_hit_without_credits(monkeypatch):
    partial = issue("11", series_id="55", number="3")
    partial.person_credits = []
    hydrated = issue("11", series_id="55", number="3", name="Full")
    hydrated.person_credits = [{"name": "Claremont", "role": "writer"}]
    comic = Comic(Path("local.cbz"), cv_series_id="55", issue_number="3")

    class HydrateClient(Client):
        def get_issue(self, issue_id):
            self.calls.append(("get_issue", issue_id))
            return hydrated

    client = HydrateClient(listed=[partial])

    def fake_write(draft):
        assert draft.title == "Full"
        return draft.path

    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.write_comic_metadata", fake_write
    )

    result = refresh_comic_metadata_from_comicvine(comic, client)

    assert result.outcome == "success"
    assert ("get_issue", "11") in client.calls


def test_refresh_write_failure(monkeypatch):
    comic = Comic(Path("local.cbz"), cv_issue_id="77")
    found = issue("77")
    found.person_credits = [{"name": "Writer", "role": "writer"}]
    client = Client(by_id=found)

    def fail_write(_draft):
        raise CbzWriteError("missing unrar")

    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.write_comic_metadata", fail_write
    )

    result = refresh_comic_metadata_from_comicvine(comic, client)

    assert result.outcome == "failed"
    assert "Unable to save" in result.message


def test_folder_worker_run_processes_all(monkeypatch):
    comics = [
        Comic(Path("a.cbz"), cv_issue_id="1"),
        Comic(Path("b.cbz"), cv_issue_id="2"),
    ]

    calls = []

    def stub_refresh(comic, _client):
        from comicdesk.ui.comic_list_workers import MetadataRefreshItemResult

        calls.append(comic.path.name)
        return MetadataRefreshItemResult(comic, "success")

    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.refresh_comic_metadata_from_comicvine",
        stub_refresh,
    )
    monkeypatch.setattr(
        "comicdesk.ui.comic_list_workers.ComicVineClient",
        lambda *args, **kwargs: object(),
    )

    worker = FolderMetadataRefreshWorker(comics, "test-key", cache_enabled=False)
    finished = []
    worker.finished.connect(finished.append)
    worker.run()

    assert len(finished) == 1
    assert len(finished[0]) == 2
    assert calls == ["a.cbz", "b.cbz"]


def test_format_metadata_refresh_details_lists_files():
    comics = [
        Comic(Path("ambiguous.cbz"), cv_series_id="1", issue_number="1"),
        Comic(Path("missing.cbz"), cv_series_id="2", issue_number="2"),
    ]
    from comicdesk.ui.comic_list_workers import MetadataRefreshItemResult

    results = [
        MetadataRefreshItemResult(
            comics[0],
            "skipped",
            "Comic Vine returned more than one possible issue.",
        ),
        MetadataRefreshItemResult(
            comics[1],
            "failed",
            "Comic Vine rate limit exceeded; try again later",
        ),
    ]
    text = format_metadata_refresh_details(results)
    assert "ambiguous.cbz" in text
    assert "missing.cbz" in text
    assert "Not updated" in text
    assert "Could not save" in text
    assert metadata_refresh_status_line(results) == "Updated 0 archive(s); 1 skipped; 1 failed"
