"""Library scan timing harness (opt-in via COMICDESK_BENCH=1)."""

import os
import time
import zipfile
from pathlib import Path

import pytest

from comicdesk.services.comic_archive import iter_comic_files, read_comic_metadata, scan_comics
from comicdesk.services.scan_metadata_cache import reset_scan_metadata_cache_for_tests

BENCH_ENABLED = os.environ.get("COMICDESK_BENCH", "").strip() in {"1", "true", "yes"}
DEFAULT_BENCH_COUNT = int(os.environ.get("COMICDESK_BENCH_COUNT", "500"))

SAMPLE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
    <Series>BenchSeries</Series>
    <Number>1</Number>
    <Year>2020</Year>
</ComicInfo>
"""


def make_minimal_cbz(path: Path, *, extra_members: int = 0) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ComicInfo.xml", SAMPLE_XML)
        for index in range(extra_members):
            archive.writestr(f"pages/page-{index:04d}.jpg", b"x")


def populate_bench_folder(folder: Path, count: int, *, extra_members: int = 0) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        make_minimal_cbz(folder / f"issue-{index:04d}.cbz", extra_members=extra_members)


def _bench_scan(folder: Path) -> dict[str, float]:
    reset_scan_metadata_cache_for_tests()
    t0 = time.perf_counter()
    paths = list(iter_comic_files(folder))
    t_enum = time.perf_counter()

    comics = []
    for path in paths:
        comics.append(read_comic_metadata(path))
    t_read = time.perf_counter()

    reset_scan_metadata_cache_for_tests()
    scanned = scan_comics(folder, max_workers=1)
    t_seq_scan = time.perf_counter()

    parallel = scan_comics(folder)
    t_par_scan = time.perf_counter()

    rescan = scan_comics(folder)
    t_rescan = time.perf_counter()

    return {
        "count": float(len(paths)),
        "enumerate_s": t_enum - t0,
        "sequential_read_s": t_read - t_enum,
        "scan_comics_seq_s": t_seq_scan - t_read,
        "scan_comics_parallel_s": t_par_scan - t_seq_scan,
        "scan_comics_rescan_s": t_rescan - t_par_scan,
        "total_sequential_s": t_read - t0,
        "total_parallel_s": t_par_scan - t_seq_scan,
        "comics": float(len(comics)),
        "parallel_comics": float(len(parallel)),
        "rescan_comics": float(len(rescan)),
    }


@pytest.mark.skipif(not BENCH_ENABLED, reason="set COMICDESK_BENCH=1 to run timing harness")
def test_library_scan_benchmark(tmp_path):
    count = DEFAULT_BENCH_COUNT
    populate_bench_folder(tmp_path, count, extra_members=2)
    timings = _bench_scan(tmp_path)
    assert int(timings["count"]) == count
    assert int(timings["comics"]) == count
    assert int(timings["parallel_comics"]) == count
    assert int(timings["rescan_comics"]) == count
    print(
        f"\nCOMICDESK_BENCH n={count}: "
        f"enumerate={timings['enumerate_s']:.3f}s "
        f"read={timings['sequential_read_s']:.3f}s "
        f"scan_seq={timings['scan_comics_seq_s']:.3f}s "
        f"scan_parallel={timings['scan_comics_parallel_s']:.3f}s "
        f"rescan_cached={timings['scan_comics_rescan_s']:.3f}s"
    )
