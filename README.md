# ComicDesk

**Your comic library workstation.**

ComicDesk is a PySide6 desktop application for managing local CBZ comic libraries, enriching metadata via Comic Vine, building ComicRack CBL reading lists, and acquiring missing issues through GetComics. It combines library browsing, metadata editing, list management, and download workflows in a single four-tab workspace.

## Features

### Library Management

- Three-panel workspace: folder browser, comic table, and reading list side by side
- Recursive CBZ scanning with background workers and progress feedback
- Search across file name, series, title, issue, volume, and year
- Filter by Comic Vine status: Enriched, Partial, or Pending
- Comic Vine status icons (✅ / ⚠️ / ❌) and reading-list membership indicator
- Collapsible folder sidebar (`Ctrl+Shift+B`)
- Bulk metadata enrichment for an entire folder

### Metadata Editing

- Dedicated Metadata tab with transactional editing (draft, apply, discard, save)
- Full ComicInfo.xml field set (40+ fields) with changed-field highlighting
- Comic Vine search, hydrate-on-select, and apply-to-draft workflow
- Instances sidebar to switch between CBZs without leaving the tab
- Double-click a comic row or use the context menu to jump to the editor

### Reading Lists

- Import and export ComicRack CBL files (`Ctrl+I` / `Ctrl+E`)
- Reconcile imported lists against the local library (CV ID first, then series/volume/issue)
- Sort by release date, series+issue, volume, title, or manual reorder
- Live CBL XML preview with syntax highlighting, copy, and select-all
- Unsaved-changes indicator in the window title (`[*]`)

### Comic Vine Integration

- REST client with 1 req/s rate limiting and local disk cache
- Multi-strategy identification: existing CV ID → volume+issue list → filename parse → search
- API key validation from Settings
- Rich metadata mapping: credits, genres, characters, locations, teams, story arcs, age rating

### GetComics Integration

- Search getcomics.org by name, category, or tag with pagination
- Issue detail view with cover thumbnail and download link list
- Automatic download for direct HTTP mirrors; manual fallback for MEGA, Mediafire, etc.
- CBL-aware search ranking for wishlist resolution
- Optional post-download Comic Vine enrichment

### Wishlist

- Persistent wishlist for CBL references missing from the local library
- Auto-populated on CBL import when issues are not found locally
- Individual and batch download with resolve progress
- Auto-removal when comics appear after scan or download

### Download Queue

- Dedicated Downloads tab with sequential processing
- Statuses: pending, running, completed, error, cancelled, needs attention
- Context menu: cancel, retry, remove, copy URLs and saved file paths
- Provider picker dialog when auto-download is unavailable

### Appearance

- Dark and Light themes with persistent config and live switching

## Requirements

- Python 3.14+
- PySide6
- httpx
- beautifulsoup4
- cloudscraper

## Installation

### Pre-built Binaries

Download the latest release from [Releases](https://github.com/Nahuel74/comicdesk/releases):

- **Linux**: `comicdesk-linux.tar.gz` — extract and run `./comicdesk`
- **Windows**: `comicdesk-windows.exe` — run directly

### From Source

```bash
git clone https://github.com/Nahuel74/comicdesk.git
cd comicdesk
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python3 main.py
```

On first launch, open **Settings** (`Ctrl+,`) to configure:

1. **Comic Vine API Key** — get one at https://comicvine.gamespot.com/api/
2. **Default Folder** — optional starting directory for the folder browser
3. **API Cache** — enable/disable local caching of API responses
4. **Theme** — Dark or Light
5. **GetComics Download Folder** — destination for downloaded comics
6. **Auto-enrich after download** — identify and write ComicInfo.xml after GetComics downloads

### Workflows

**Browse and enrich:** select a folder → Scan for CBZ → filter/search → Update all metadata from Comic Vine.

**Edit metadata:** double-click a comic → search Comic Vine → select proposal → Apply → Save.

**Build a reading list:** add comics from the table → sort or reorder → preview CBL XML → Export CBL.

**Import a CBL:** Import CBL → review reconciliation summary → missing issues go to the wishlist → switch to GetComics to download.

**Acquire missing issues:** open GetComics tab → search or use wishlist → Download → monitor the Downloads tab.

### Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Import CBL | `Ctrl+I` |
| Export CBL | `Ctrl+E` |
| Settings | `Ctrl+,` |
| Toggle folder sidebar | `Ctrl+Shift+B` |
| Exit | `Ctrl+Q` |

## Configuration

Configuration is stored at `~/.config/comicdesk/config.json`. On first launch, ComicDesk automatically copies settings from the legacy `~/.config/cbl-maker/` directory if present.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `api_key` | string | `""` | Comic Vine API key |
| `default_folder` | string | `""` | Starting folder for the browser |
| `cache_enabled` | bool | `true` | Enable Comic Vine API disk cache |
| `last_cbl_directory` | string | `""` | Last directory used for CBL file dialogs |
| `getcomics_download_folder` | string | `""` | Default GetComics download destination |
| `auto_enrich_after_download` | bool | `true` | Enrich CBZ files after GetComics download |
| `theme` | string | `"dark"` | UI theme (`dark` or `light`) |

Additional persistent files:

- `~/.config/comicdesk/cache/api_cache.json` — Comic Vine response cache
- `~/.config/comicdesk/wishlist.json` — wishlist of missing CBL references

## Project Structure

```
comicdesk/
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── packaging/
│   ├── comicdesk.spec       # PyInstaller spec (shared)
│   ├── build_linux.sh       # Linux build script
│   ├── build_windows.bat    # Windows build script
│   └── verify_build.sh      # Binary verification
├── comicdesk/
│   ├── __init__.py          # Version
│   ├── app.py               # Application setup
│   ├── config.py            # Configuration management
│   ├── models.py            # Data models (Comic, CBLBook, ReadingList)
│   ├── services/
│   │   ├── cbz_reader.py    # Read CBZ archives
│   │   ├── cbz_writer.py    # Write CBZ archives
│   │   ├── cbl_reader.py    # Parse CBL files
│   │   ├── cbl_writer.py    # Generate CBL files
│   │   ├── comicinfo.py     # ComicInfo.xml field mapping
│   │   ├── comicvine_api.py # Comic Vine REST client
│   │   ├── comicvine_mapping.py # CV → Comic field mapping
│   │   ├── identification.py# Match comics to Comic Vine
│   │   ├── metadata_session.py # Transactional metadata editing
│   │   ├── getcomics.py     # GetComics search and download
│   │   ├── download_queue.py# Sequential download queue
│   │   └── wishlist.py      # Persistent wishlist
│   ├── ui/                  # PySide6 interface (4 tabs)
│   └── utils/               # Filename parsing, URL parsing
├── tests/                   # Test suite (27 files)
└── .github/workflows/
    └── release.yml          # CI: test → build → release
```

## Testing

```bash
python -m pytest                  # Run all tests
python -m pytest tests/test_models.py   # Single file
python -m pytest -k "test_name"         # Single test
```

## Building Executables

Requires [PyInstaller](https://pyinstaller.org/):

```bash
pip install pyinstaller

# Linux
./packaging/build_linux.sh            # → dist/comicdesk

# Windows
packaging\build_windows.bat           # → dist\comicdesk.exe
```

### Releasing

```bash
git tag v1.x.x
git push origin --tags
```

This triggers the GitHub Actions workflow: tests run, binaries are built for Linux and Windows, and a GitHub Release is created with the changelog and executables attached.

## Architecture Notes

- Config, API cache, and wishlist live in `~/.config/comicdesk/`, outside the repository
- Legacy config at `~/.config/cbl-maker/` is migrated automatically on first launch
- All file writes (config, CBZ, wishlist, cache) are atomic via temp file + `os.replace`
- Comic Vine search results are partial — always hydrate via `get_issue()` before using credits or descriptions
- The `Comic.volume` field stores the publication start year, never the Comic Vine database ID
- CBL exports use the `https://comicdesk.dev/xml/metadata` namespace; legacy `cbl-maker.dev` namespaces are still read on import

## License

MIT
