# AGENTS.md

## Project

ComicDesk is a PySide6 desktop workstation for managing local CBZ comic libraries. It covers metadata editing (ComicInfo.xml), Comic Vine enrichment, ComicRack CBL reading lists, GetComics acquisition, wishlist tracking, and a sequential download queue.

## Run

```bash
source venv/bin/activate
python3 main.py            # start the app
python -m pytest            # run all tests
python -m pytest tests/test_models.py   # single file
python -m pytest -k "test_name"         # single test
```

No linter, formatter, or type checker is configured.

## Stack & Dependencies

- Python 3.14
- PySide6 — Qt GUI framework
- httpx — HTTP client (Comic Vine API, GetComics downloads)
- beautifulsoup4 — HTML parsing for GetComics
- cloudscraper — Cloudflare-compatible scraping for GetComics pages
- `h2` is in `requirements.txt` but unused at runtime (`http2=False` in `comicvine_api.py`)

## Packaging

PyInstaller builds single-file executables for Linux and Windows.

```bash
# Local build (Linux)
./packaging/build_linux.sh           # output: dist/comicdesk
bash packaging/verify_build.sh       # verify binary integrity

# Local build (Windows)
packaging\build_windows.bat          # output: dist\comicdesk.exe
```

- **Spec file**: `packaging/comicdesk.spec` — shared across platforms
- **CI**: `.github/workflows/release.yml` — triggers on `v*` tags or manual dispatch
- **Release flow**: push tag `v1.x.x` → tests run → Linux + Windows binaries built → GitHub Release created with changelog and artifacts
- **Version source**: `comicdesk/__init__.py` (`__version__`)
- **No external assets bundled** — theme is CSS-based, UI is code-only

## Architecture

- **Entry**: `main.py` → `comicdesk.app.run()` → Qt event loop
- **Config**: `~/.config/comicdesk/config.json` — migrated automatically from `~/.config/cbl-maker/` on first launch
- **API cache**: `~/.config/comicdesk/cache/api_cache.json`
- **Wishlist**: `~/.config/comicdesk/wishlist.json`

### Config keys

| Key | Type | Default |
|-----|------|---------|
| `api_key` | str | `""` |
| `default_folder` | str | `""` |
| `cache_enabled` | bool | `True` |
| `last_cbl_directory` | str | `""` |
| `getcomics_download_folder` | str | `""` |
| `auto_enrich_after_download` | bool | `True` |
| `theme` | str | `"dark"` |

### UI tabs

| Tab | Key modules |
|-----|-------------|
| Workspace | `folder_panel`, `comic_list`, `reading_list_panel`, `cbl_preview` |
| Metadata | `cbz_metadata_panel`, `cbz_metadata_workers` |
| GetComics | `getcomics_panel`, `getcomics_workers` |
| Downloads | `download_queue_panel` |

Background workers live in `comic_list_workers.py`, `cbz_metadata_workers.py`, and `getcomics_workers.py`.

### Services

| Module | Responsibility |
|--------|----------------|
| `cbz_reader.py` / `cbz_writer.py` | Read/write ComicInfo.xml inside CBZ archives |
| `cbl_reader.py` / `cbl_writer.py` | Parse/generate ComicRack CBL XML, reconciliation |
| `comicinfo.py` | `FIELD_TAGS` — single source of truth for ComicInfo XML mapping |
| `comicvine_api.py` | Comic Vine REST client with rate limiting and disk caching |
| `comicvine_mapping.py` | Comic Vine DTO → `Comic` field mapping |
| `identification.py` | Multi-strategy match of local comics to CV issues/volumes |
| `metadata_session.py` | Transactional draft/commit/discard for metadata editing |
| `getcomics.py` | GetComics HTML scraping, download, CBL-aware search ranking |
| `download_queue.py` | Sequential download queue with Qt signals |
| `wishlist.py` | Persistent missing-issue tracking and library reconciliation |

### Models

- `Comic` — local file metadata with full ComicInfo + CV identifiers
- `CBLBook` — frozen, path-less CBL reference (no `path` field by design)
- `ReadingList` — named list of `Comic` with sort criteria
- `ComicVineIssue` / `ComicVineVolume` — Comic Vine API DTOs
- `ComicVineMetadata = ComicVineIssue` — alias in `models.py` for backward compatibility

## Code Conventions

- Dataclasses for models, config, and service DTOs
- Atomic writes everywhere: temp file + `os.replace` (config, CBZ, wishlist, cache)
- Background work via Qt threads/signals in `*_workers.py` modules
- `FIELD_TAGS` in `comicinfo.py` is the single source of truth for ComicInfo fields
- `CBLBook` is a frozen dataclass intentionally without a `path` field
- Tests use `tmp_path` for filesystem isolation and `monkeypatch` for config path substitution
- Structured logging in GetComics and download services

## Gotchas

- **Comic Vine search results are partial.** Always hydrate via `get_issue(id)` before reading credits, descriptions, or volume metadata.
- **Volume field = start_year, never the database ID.** A past bug stored the CV volume ID in `Comic.volume`; code explicitly replaces that value.
- **`http2=False` is hardcoded** in `comicvine_api.py`. The `h2` package in `requirements.txt` is unused at runtime.
- **Atomic writes everywhere.** Both config and CBZ writes use temp file + `os.replace`. Don't introduce non-atomic save paths.
- **CBL namespace dual-read.** Exports use `https://comicdesk.dev/xml/metadata`; imports also accept the legacy `https://cbl-maker.dev/xml/metadata` namespace. Must preserve both on read.
- **XML limits enforced**: ComicInfo max 2MB/50K nodes/128 depth; CBL max 10MB/50K nodes/128 depth. Tests exercise these bounds.
- **`CBLBook` is intentionally path-less.** CBL files contain references, not file paths. Don't add a `path` field to it.
- **`ComicVineMetadata = ComicVineIssue`** — alias in `models.py` for backward compatibility. Both names refer to the same dataclass.
- **Config migration is non-destructive.** `_migrate_legacy_config()` copies `~/.config/cbl-maker/` to `~/.config/comicdesk/` but does not delete the legacy directory.
- **GetComics uses `cloudscraper`**, not a REST API. Cloudflare 403 → `CloudflareChallengeError`.
- **Download queue is sequential** — one active download at a time. `needs_attention` pauses the queue for manual provider selection.
- **Wishlist auto-reconciles** on library scan and download completion — don't duplicate that logic in UI code.
- **`auto_enrich_after_download` applies only to `.cbz`** files after GetComics download.
- **GetComics search ranking** requires score ≥ 40 and rejects ties.
- **`Comic.status`** returns emoji (✅/⚠️/❌) based on CV ID completeness.

## Testing

- pytest with default config (no `conftest.py`, no `pytest.ini`, no `pyproject.toml`)
- 27 test files, ~170+ test functions
- `test_cbz_reader.py` creates zip fixtures inline; no shared fixture files
- API tests in `test_comicvine_api.py` hit the real API (no mocks) — may fail without network or with rate limits
- GetComics HTML fixtures in `tests/fixtures/getcomics/`
- Python 3.14 in the venv
