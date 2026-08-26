"""Reading-list ordering and manual movement tests."""

from pathlib import Path

from cbl_maker.models import Comic, ReadingList


def comic(name, **kwargs):
    return Comic(path=Path(f"{name}.cbz"), title=name, **kwargs)


def test_all_criteria_and_directions_keep_missing_values_stable():
    items = [
        comic("B", year="2024", series_name="Z", issue_number="2", volume="2"),
        comic("", year="", series_name="", issue_number="", volume=""),
        comic("A", year="2023", series_name="A", issue_number="1", volume="1"),
    ]
    reading_list = ReadingList("test", items)

    for criterion in ("release_date", "series_issue", "volume", "title"):
        reading_list.sort_by(criterion, "asc")
        assert reading_list.ordered_by == criterion
        assert reading_list.order_direction == "asc"
        assert reading_list.comics[-1].title == ""
        reading_list.sort_by(criterion, "desc")
        assert reading_list.order_direction == "desc"
        assert reading_list.comics[-1].title == ""


def test_manual_sort_does_not_change_order_and_move_updates_state():
    first, second, third = comic("first"), comic("second"), comic("third")
    reading_list = ReadingList("test", [first, second, third])
    reading_list.sort_by("manual")
    assert reading_list.comics == [first, second, third]
    reading_list.move_comic(second, 1)
    assert reading_list.comics == [first, third, second]
    assert reading_list.ordered_by == "manual"


def test_move_extremes_do_not_duplicate_or_reorder():
    first, second = comic("first"), comic("second")
    reading_list = ReadingList("test", [first, second])
    reading_list.sort_by("manual")
    reading_list.move_comic(first, -1)
    reading_list.move_comic(second, 1)
    assert reading_list.comics == [first, second]
    assert len({item.path for item in reading_list.comics}) == 2
