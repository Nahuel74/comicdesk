# AGENTS.md

## Project

ComicDesk is a PySide6 desktop workstation for local CBZ libraries: metadata (ComicInfo.xml), Comic Vine enrichment, ComicRack CBL reading lists, GetComics acquisition, wishlist, and a sequential download queue.

## Run

```bash
source venv/bin/activate
python3 main.py
python -m pytest
python -m pytest tests/test_models.py
python -m pytest -k "test_name"
```

No linter, formatter, or type checker is configured.

## Stack

- Python 3.14, PySide6, httpx, beautifulsoup4, cloudscraper
- `h2` in `requirements.txt` is unused at runtime (`http2=False` in `comicvine_api.py`)

## Packaging

```bash
./packaging/build_linux.sh      # dist/comicdesk
packaging\build_windows.bat     # dist\comicdesk.exe
bash packaging/verify_build.sh
```

- Spec: `packaging/comicdesk.spec`
- CI: `.github/workflows/release.yml` on `v*` tags
- Version: `comicdesk/__init__.py` (`__version__`)
- **Changelog**: edit `CHANGELOG.md` under `## [Unreleased]`; on release, rename that block to `## [x.y.z] - date`, bump `__version__`, tag `vx.y.z`. CI publishes only that version’s section to GitHub Releases.

## Architecture

- **Entry**: `main.py` → `comicdesk.app.run()`
- **Config**: `~/.config/comicdesk/config.json` (non-destructive migration from `~/.config/cbl-maker/`)
- **Cache / wishlist**: `~/.config/comicdesk/cache/api_cache.json`, `wishlist.json`

### Config keys

| Key | Type | Default |
|-----|------|---------|
| `api_key` | str | `""` |
| `default_folder` | str | `""` |
| `cache_enabled` | bool | `True` |
| `last_cbl_directory` | str | `""` |
| `getcomics_download_folder` | str | `""` |
| `auto_enrich_after_download` | bool | `True` |
| `theme` | str | `"dark"` (`dark`, `light`, or `system`) |
| `last_rename_template` | str | `""` |
| `rename_issue_pad_width` | int | `0` — fallback leading zeros for `{Number}` when ComicInfo Count is empty |

### UI (primary nav)

| Tab | Modules |
|-----|---------|
| Library | `folder_panel` (sidebar), `comic_list`, `comic_list_workers` |
| Metadata | `cbz_metadata_panel`, `cbz_metadata_workers`, `metadata_instance_model` |
| Lists | `reading_list_panel`, `reading_list_header`, `add_reading_list_issue_dialog`, `cbl_preview` |
| Acquire | `getcomics_panel`, `download_queue_panel`, `acquire_page` |

Shell: `ui/shell/app_shell.py`, `primary_nav.py`. Background workers in `*_workers.py`.

### Services (selected)

| Module | Role |
|--------|------|
| `cbz_reader.py` / `cbz_writer.py` | ComicInfo in CBZ |
| `cbl_reader.py` / `cbl_writer.py` | CBL parse/write, `reconcile_cbl`, `ordered_comics_for_import` |
| `comicinfo.py` | `FIELD_TAGS` — ComicInfo field mapping |
| `comicvine_api.py` | Comic Vine client, cache, rate limit |
| `identification.py` | Match comics to issues/volumes (volume+issue lookup before broad search) |
| `metadata_session.py` | Draft/commit metadata edits |
| `getcomics.py` | Scrape, download, wishlist ranking |
| `download_queue.py` | Sequential downloads |
| `wishlist.py` | Persistent CBL references |

### Models

- `Comic` — file metadata + CV IDs; `has_local_file`, `status` (emoji for metadata completeness)
- `CBLBook` — frozen CBL reference, no `path`
- `ReadingList` — `Comic` entries (local or virtual); identity dedupe via `comic_dedupe_key`
- `ComicVineIssue` / `ComicVineVolume` — API DTOs; `ComicVineMetadata = ComicVineIssue`

## Conventions

- Dataclasses; atomic writes (temp + `os.replace`)
- Qt threads/signals in `*_workers.py`
- `CBLBook` stays path-less; don't add `path` to it
- Tests: `tmp_path`, `monkeypatch` for config paths

## Gotchas

- Hydrate search hits with `get_issue(id)` before credits/descriptions.
- `Comic.volume` is publication/start year, not the CV volume database ID.
- CBL export namespace `https://comicdesk.dev/xml/metadata`; import also accepts legacy `cbl-maker.dev`.
- XML size/depth limits on ComicInfo and CBL (see tests).
- **Reading lists** may include comics without a local CBZ (`has_local_file` false); CBL import uses `ordered_comics_for_import` to preserve full CBL order. Wishlist updates on import only after explicit user confirmation.
- **Library table** has no status column; **Metadata** instance list shows **Metadata status**. Toolbar filter on Library still filters by enrichment state.
- GetComics: `cloudscraper`; sequential download queue; `needs_attention` for manual provider pick.
- Wishlist reconciles on library scan and download completion — don't duplicate in UI.

## Testing

- pytest, no `conftest.py` / `pyproject.toml`
- ~27 test files, ~230+ tests
- `test_comicvine_api.py` may hit the real API (network/rate limits)
- GetComics fixtures: `tests/fixtures/getcomics/`
