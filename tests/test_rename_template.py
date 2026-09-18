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
    plan_renames,
    render_template,
    rendered_stem_to_filename,
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
