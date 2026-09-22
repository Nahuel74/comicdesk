"""Tests for template-based CBZ rename planning."""

from pathlib import Path

import pytest

from comicdesk.models import Comic
from comicdesk.utils.rename_template import (
    RenameRowStatus,
    count_derived_issue_pad_width,
    format_issue_number,
    normalize_rendered_stem,
    plan_apply_allowed,
    plan_folder_apply_allowed,
    plan_folder_renames,
    plan_renames,
    render_template,
    rendered_stem_to_filename,
    series_folder_for_comic,
)


def test_render_series_number_year_template():
    comic = Comic(
        path=Path("/tmp/Avengers 001.cbz"),
        series_name="Avengers",
        issue_number="1",
        year="2020",
    )
    assert render_template("{Series} - {Number} ({Year})", comic) == "Avengers - 1 (2020)"


def test_render_aliases():
    comic = Comic(
        path=Path("/books/book.cbz"),
        series_name="X-Men",
        issue_number="2",
    )
    assert render_template("{series_name} #{Number}", comic) == "X-Men #2"


def test_issue_pad_width_from_dialog_default():
    comic = Comic(path=Path("/a.cbz"), series_name="S", issue_number="7", year="2020")
    assert render_template("{Series} {Number}", comic, issue_pad_width=0) == "S 7"
    assert render_template("{Series} {Number}", comic, issue_pad_width=3) == "S 007"


def test_issue_pad_from_count_when_present():
    comic = Comic(path=Path("/a.cbz"), series_name="S", issue_number="7", count="9")
    assert render_template("{Number}", comic, issue_pad_width=0) == "07"
    comic.count = "99"
    assert render_template("{Number}", comic, issue_pad_width=0) == "007"
    comic.count = "150"
    assert render_template("{Number}", comic, issue_pad_width=0) == "0007"


def test_issue_pad_manual_when_count_missing():
    comic = Comic(path=Path("/a.cbz"), issue_number="7", count="")
    assert render_template("{Number}", comic, issue_pad_width=4) == "0007"


def test_count_derived_pad_width_examples():
    assert count_derived_issue_pad_width(Comic(path=Path("a.cbz"), count="9")) == 2
    assert count_derived_issue_pad_width(Comic(path=Path("a.cbz"), count="10")) == 3
    assert count_derived_issue_pad_width(Comic(path=Path("a.cbz"), count="999")) == 4
    assert count_derived_issue_pad_width(Comic(path=Path("a.cbz"), count="")) is None


def test_issue_pad_inline_override():
    comic = Comic(path=Path("/a.cbz"), series_name="S", issue_number="7", count="9")
    assert render_template("{Number:2}", comic, issue_pad_width=5) == "07"
    assert render_template("{Number}", comic, issue_pad_width=5) == "07"


def test_issue_pad_preserves_decimal_suffix():
    comic = Comic(path=Path("/a.cbz"), issue_number="1.5")
    assert format_issue_number("1.5", 3) == "001.5"


def test_normalize_empty_year_parentheses():
    comic = Comic(
        path=Path("/tmp/a.cbz"),
        series_name="Alpha",
        issue_number="3",
        year="",
    )
    assert render_template("{Series} - {Number} ({Year})", comic) == "Alpha - 3"


def test_normalize_trailing_dash_when_series_missing():
    assert normalize_rendered_stem(" - 5 (2021)") == "5 (2021)"


def test_rendered_stem_to_filename_reserved_name():
    assert rendered_stem_to_filename("con") == "_con"


def test_rendered_stem_to_filename_preserves_spaces():
    assert rendered_stem_to_filename("Alpha - 1 (2020)") == "Alpha - 1 (2020)"


def test_rendered_stem_preserves_series_colon_as_hyphen():
    comic = Comic(
        path=Path("/tmp/book.cbz"),
        series_name="Fantastic Four: House of M",
        issue_number="1",
    )
    stem = rendered_stem_to_filename(render_template("{Series}", comic))
    assert stem == "Fantastic Four - House of M"


def test_plan_marks_unchanged_and_ok(tmp_path):
    unchanged = tmp_path / "Alpha - 1 (2020).cbz"
    unchanged.touch()
    rename_me = tmp_path / "old.cbz"
    rename_me.touch()
    comics = [
        Comic(
            path=unchanged,
            series_name="Alpha",
            issue_number="1",
            year="2020",
        ),
        Comic(
            path=rename_me,
            series_name="Beta",
            issue_number="2",
            year="2021",
        ),
    ]
    rows = plan_renames(comics, "{Series} - {Number} ({Year})")
    by_name = {row.old_path.name: row for row in rows}
    assert by_name[unchanged.name].status == RenameRowStatus.UNCHANGED
    assert by_name[rename_me.name].status == RenameRowStatus.OK
    assert by_name[rename_me.name].proposed_path.name == "Beta - 2 (2021).cbz"


def test_plan_excludes_non_local():
    rows = plan_renames([Comic(path=Path("."))], "{Series}")
    assert len(rows) == 1
    assert rows[0].status == RenameRowStatus.EXCLUDED


def test_plan_excludes_cbr_until_converted(tmp_path):
    cbr = tmp_path / "series.cbr"
    cbr.write_bytes(b"x")
    rows = plan_renames(
        [Comic(path=cbr, series_name="Series", issue_number="1")],
        "{Series} - {Number}",
    )
    assert len(rows) == 1
    assert rows[0].status == RenameRowStatus.EXCLUDED
    assert "convert the archive" in rows[0].message


def test_plan_detects_duplicate_targets(tmp_path):
    a = tmp_path / "a.cbz"
    b = tmp_path / "b.cbz"
    a.touch()
    b.touch()
    comics = [
        Comic(path=a, series_name="Same", issue_number="1", year="2020"),
        Comic(path=b, series_name="Same", issue_number="1", year="2020"),
    ]
    rows = plan_renames(comics, "{Series} - {Number} ({Year})")
    assert all(row.status == RenameRowStatus.COLLISION for row in rows)
    assert rows[0].proposed_path.name == "Same - 1 (2020).cbz"


def test_plan_detects_foreign_file_collision(tmp_path):
    existing = tmp_path / "Taken - 9 (1999).cbz"
    existing.touch()
    source = tmp_path / "source.cbz"
    source.touch()
    comic = Comic(
        path=source,
        series_name="Taken",
        issue_number="9",
        year="1999",
    )
    rows = plan_renames([comic], "{Series} - {Number} ({Year})")
    assert rows[0].status == RenameRowStatus.COLLISION


def test_plan_allows_batch_swap_targets(tmp_path):
    foo = tmp_path / "foo.cbz"
    bar = tmp_path / "bar.cbz"
    foo.touch()
    bar.touch()
    comics = [
        Comic(path=foo, series_name="Bar", issue_number="1", year="2020"),
        Comic(path=bar, series_name="Foo", issue_number="1", year="2020"),
    ]
    rows = plan_renames(comics, "{Series} - {Number} ({Year})")
    assert {row.status for row in rows} == {RenameRowStatus.OK}


def test_plan_apply_allowed():
    ok_row = plan_renames(
        [Comic(path=Path("/x/a.cbz"), series_name="A", issue_number="1")],
        "{Series}",
    )[0]
    ok_row = ok_row.__class__(
        comic=ok_row.comic,
        old_path=ok_row.old_path,
        proposed_path=ok_row.proposed_path,
        status=RenameRowStatus.OK,
    )
    assert plan_apply_allowed([ok_row])
    assert not plan_apply_allowed(
        [
            ok_row.__class__(
                comic=ok_row.comic,
                old_path=ok_row.old_path,
                proposed_path=ok_row.proposed_path,
                status=RenameRowStatus.COLLISION,
            )
        ]
    )


def test_series_folder_for_comic_at_library_root(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    cbz = root / "book.cbz"
    cbz.touch()
    comic = Comic(path=cbz)
    assert series_folder_for_comic(comic, root) == root.resolve()


def test_series_folder_for_comic_one_level_under_root(tmp_path):
    root = tmp_path / "lib"
    series = root / "Old Series"
    series.mkdir(parents=True)
    cbz = series / "01.cbz"
    cbz.touch()
    comic = Comic(path=cbz)
    assert series_folder_for_comic(comic, root) == series.resolve()


def test_series_folder_for_comic_skips_issue_subdirectory(tmp_path):
    root = tmp_path / "lib"
    series = root / "Old Series"
    issue_dir = series / "issue sub"
    issue_dir.mkdir(parents=True)
    cbz = issue_dir / "01.cbz"
    cbz.touch()
    comic = Comic(path=cbz)
    assert series_folder_for_comic(comic, root) == series.resolve()


def test_series_folder_annual_subdirectory_is_separate(tmp_path):
    root = tmp_path / "Marvel"
    series = root / "Black Panther (2005)"
    annual = series / "Annual"
    annual.mkdir(parents=True)
    regular = series / "01.cbz"
    regular.touch()
    annual_cbz = annual / "annual.cbz"
    annual_cbz.touch()
    regular_comic = Comic(path=regular, series_name="Black Panther", volume="2005")
    annual_comic = Comic(
        path=annual_cbz,
        series_name="Black Panther Annual",
        volume="2005",
    )
    assert series_folder_for_comic(regular_comic, root) == series.resolve()
    assert series_folder_for_comic(annual_comic, root) == annual.resolve()


def test_plan_folder_does_not_mix_annual_with_series(tmp_path):
    root = tmp_path / "Marvel"
    series = root / "Black Panther (2005)"
    annual_dir = series / "Annual"
    annual_dir.mkdir(parents=True)
    (series / "01.cbz").touch()
    (annual_dir / "annual.cbz").touch()
    comics = [
        Comic(path=series / "01.cbz", series_name="Black Panther", volume="2005"),
        Comic(
            path=annual_dir / "annual.cbz",
            series_name="Black Panther Annual",
            volume="2005",
        ),
    ]
    rows = plan_folder_renames(comics, "{Series} ({Volume})", root)
    assert len(rows) == 2
    assert {row.folder_old.resolve() for row in rows} == {series.resolve(), annual_dir.resolve()}
    assert all(
        row.status in (RenameRowStatus.OK, RenameRowStatus.UNCHANGED) for row in rows
    )


def test_plan_folder_renames_ok(tmp_path):
    root = tmp_path / "lib"
    series = root / "Old Name"
    series.mkdir(parents=True)
    cbz = series / "a.cbz"
    cbz.touch()
    comic = Comic(path=cbz, series_name="Alpha", volume="2020")
    rows = plan_folder_renames([comic], "{Series} ({Volume})", root)
    assert len(rows) == 1
    assert rows[0].status == RenameRowStatus.OK
    assert rows[0].folder_new is not None
    assert rows[0].folder_new.name == "Alpha (2020)"


def test_plan_folder_rejects_issue_placeholder_conflict(tmp_path):
    root = tmp_path / "lib"
    series = root / "Series"
    series.mkdir(parents=True)
    first = series / "a.cbz"
    second = series / "b.cbz"
    first.touch()
    second.touch()
    comics = [
        Comic(path=first, series_name="S", issue_number="1", volume="2020"),
        Comic(path=second, series_name="S", issue_number="2", volume="2020"),
    ]
    rows = plan_folder_renames(comics, "{Series} - {Number}", root)
    assert len(rows) == 1
    assert rows[0].status == RenameRowStatus.INVALID
    assert rows[0].message.startswith("Names do not match")


def test_plan_folder_mismatch_lists_examples(tmp_path):
    root = tmp_path / "lib"
    series = root / "Old"
    series.mkdir(parents=True)
    first = series / "a.cbz"
    second = series / "b.cbz"
    first.touch()
    second.touch()
    comics = [
        Comic(path=first, series_name="Doom's Division", volume="2025"),
        Comic(path=second, series_name="Doom's Division", volume=""),
    ]
    rows = plan_folder_renames(comics, "{Series} ({Volume})", root)
    assert rows[0].status == RenameRowStatus.INVALID
    assert "Doom's Division" in rows[0].message


def test_plan_folder_unchanged(tmp_path):
    root = tmp_path / "lib"
    series = root / "Alpha (2020)"
    series.mkdir(parents=True)
    cbz = series / "a.cbz"
    cbz.touch()
    comic = Comic(path=cbz, series_name="Alpha", volume="2020")
    rows = plan_folder_renames([comic], "{Series} ({Volume})", root)
    assert rows[0].status == RenameRowStatus.UNCHANGED


def test_plan_folder_foreign_collision(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    taken = root / "Taken (2020)"
    taken.mkdir()
    source = root / "Source"
    source.mkdir()
    cbz = source / "a.cbz"
    cbz.touch()
    comic = Comic(path=cbz, series_name="Taken", volume="2020")
    rows = plan_folder_renames([comic], "{Series} ({Volume})", root)
    assert rows[0].status == RenameRowStatus.COLLISION


def test_plan_folder_apply_allowed(tmp_path):
    root = tmp_path / "lib"
    series = root / "Old"
    series.mkdir(parents=True)
    cbz = series / "a.cbz"
    cbz.touch()
    row = plan_folder_renames(
        [Comic(path=cbz, series_name="Alpha", volume="2020")],
        "{Series} ({Volume})",
        root,
    )[0]
    assert row.status == RenameRowStatus.OK
    assert plan_folder_apply_allowed([row])
    assert not plan_folder_apply_allowed(
        [
            row.__class__(
                folder_old=row.folder_old,
                folder_new=row.folder_new,
                comics=row.comics,
                status=RenameRowStatus.COLLISION,
            )
        ]
    )
