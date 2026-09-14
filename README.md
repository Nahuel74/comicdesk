# ComicDesk

**Your comic library workstation.**

ComicDesk is a PySide6 desktop app for local CBZ libraries: browse and enrich metadata, edit ComicInfo, manage ComicRack CBL reading lists, and download missing issues via GetComics.

## Features

- **Library** — folder browser, CBZ scan, search, metadata-status filter, bulk enrichment, add comics to a reading list
- **Metadata** — transactional ComicInfo editing, online metadata search, per-folder instance list
- **Lists** — import/export CBL, sort and reorder, live XML preview, manual **Add issue** (with metadata lookup), entries with or without a local file
- **Acquire** — GetComics search, wishlist, sequential download queue

Themes (dark/light), Comic Vine API client with cache, and atomic config/CBZ/wishlist writes.

## Requirements

- Python 3.14+
- PySide6, httpx, beautifulsoup4, cloudscraper

## Installation

### Pre-built binaries

Download from [Releases](https://github.com/Nahuel74/comicdesk/releases) (Linux tarball or Windows executable).

### From source

```bash
git clone https://github.com/Nahuel74/comicdesk.git
cd comicdesk
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

## First run

Open **Settings** (`Ctrl+,`):

1. **Comic Vine API key** — https://comicvine.gamespot.com/api/
2. **Default folder** (optional)
3. **GetComics download folder** and **auto-enrich after download** (optional)

## Usage

**Library:** pick a folder → scan → filter/search → **Enrich all metadata** (needs API key).

**Metadata:** open a comic from Library (double-click or context menu) → search → apply proposal → save to CBZ.

**Lists:** build a list from Library (**Add to list**) and/or **Add issue** on the Lists tab → export CBL (`Ctrl+E`).  
**Import CBL** (`Ctrl+I`): review linked vs missing counts → confirm replacing the list → optionally add missing issues to the wishlist. The list keeps all CBL entries (local files and not-in-library rows).

**Acquire:** search GetComics or use the wishlist → download → watch the queue on the same tab.

### Shortcuts

| Action | Shortcut |
|--------|----------|
| Import CBL | `Ctrl+I` |
| Export CBL | `Ctrl+E` |
| Save CBL | `Ctrl+S` |
| Settings | `Ctrl+,` |
| Toggle folder sidebar | `Ctrl+Shift+B` |

## Config and data

`~/.config/comicdesk/config.json`.

| Key | Description |
|-----|-------------|
| `api_key` | Comic Vine API key |
| `default_folder` | Starting library folder |
| `cache_enabled` | API response disk cache |
| `last_cbl_directory` | Last path used for CBL dialogs |
| `getcomics_download_folder` | Download destination |
| `auto_enrich_after_download` | Enrich `.cbz` after GetComics download |
| `theme` | `dark` or `light` |

Also: `cache/api_cache.json`, `wishlist.json`.

## Development

```bash
source venv/bin/activate
python -m pytest
./packaging/build_linux.sh   # optional: dist/comicdesk
```

Tag `v*.*.*` and push to trigger CI release builds (see `.github/workflows/release.yml`).

## License

MIT
