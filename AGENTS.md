# AGENTS.md

## Project

PySide6 desktop app for managing comic metadata (CBZ ComicInfo.xml) and creating ComicRack CBL reading lists. Integrates with the Comic Vine API for enrichment.

## Run

```bash
source venv/bin/activate
python3 main.py            # start the app
python -m pytest            # run all tests
python -m pytest tests/test_models.py   # single file
python -m pytest -k "test_name"         # single test
```

No linter, formatter, or type checker is configured.

## Packaging

PyInstaller builds single-file executables for Linux and Windows.

```bash
# Local build (Linux)
./packaging/build_linux.sh           # output: dist/cbl-maker
bash packaging/verify_build.sh       # verify binary integrity

# Local build (Windows)
packaging\build_windows.bat          # output: dist\cbl-maker.exe
```

- **Spec file**: `packaging/cbl-maker.spec` — shared across platforms
- **CI**: `.github/workflows/release.yml` — triggers on `v*` tags or manual dispatch
- **Release flow**: push tag `v1.0.0` → tests run → Linux + Windows binaries built → GitHub Release created with artifacts
- **Version source**: `cbl_maker/__init__.py` (`__version__`)
- **No external assets bundled** — theme is CSS-based, UI is code-only

## Architecture

- **Entry**: `main.py` → `cbl_maker.app.run()` → Qt event loop
- **Config**: `~/.config/cbl-maker/config.json` (api_key, default_folder, cache_enabled)
- **API cache**: `~/.config/cbl-maker/cache/api_cache.json`
- **Services**:
  - `cbz_reader.py` / `cbz_writer.py` — read/write ComicInfo.xml inside CBZ archives
  - `cbl_reader.py` / `cbl_writer.py` — parse/generate ComicRack CBL XML
  - `comicvine_api.py` — Comic Vine REST client with rate limiting and disk caching
  - `comicinfo.py` — single source of truth for ComicInfo XML field mapping
  - `identification.py` — match local comics to Comic Vine issues/volumes
- **UI**: three-panel workspace (folder browser | comic list | reading list) + metadata editor tab
- **Models**: `Comic` (local file metadata), `CBLBook` (CBL reference, no path), `ReadingList`, `ComicVineIssue`/`ComicVineVolume`

## Gotchas

- **Comic Vine search results are partial.** Always hydrate via `get_issue(id)` before reading credits, descriptions, or volume metadata.
- **Volume field = start_year, never the database ID.** A past bug stored the CV volume ID in `Comic.volume`; code explicitly replaces that value.
- **`http2=False` is hardcoded** in `comicvine_api.py:176`. The `h2` package in `requirements.txt` is unused at runtime.
- **Atomic writes everywhere.** Both config and CBZ writes use temp file + `os.replace`. Don't introduce non-atomic save paths.
- **CBL custom namespace**: `https://cbl-maker.dev/xml/metadata` — used for `ComicVineMetadata` extension elements. Must be preserved on read/write.
- **XML limits enforced**: ComicInfo max 2MB/50K nodes/128 depth; CBL max 10MB/50K nodes/128 depth. Tests exercise these bounds.
- **`CBLBook` is intentionally path-less.** CBL files contain references, not file paths. Don't add a `path` field to it.
- **`ComicVineMetadata = ComicVineIssue`** — alias in `models.py:233` for backward compatibility. Both names refer to the same dataclass.

## Testing

- pytest with default config (no `conftest.py`, no `pytest.ini`, no `pyproject.toml`)
- Tests use `tmp_path` for filesystem isolation, `monkeypatch` for config path substitution
- `test_cbz_reader.py` creates zip fixtures inline; no shared fixture files
- API tests in `test_comicvine_api.py` hit the real API (no mocks) — may fail without network or with rate limits
- Python 3.14 in the venv (`pip3.14` visible)
