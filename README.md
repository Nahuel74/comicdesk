# ComicDesk

**Your comic library workstation.**

ComicDesk is a PySide6 desktop app for local comic libraries (`.cbz`, `.cbr`): browse and enrich metadata, edit ComicInfo, manage ComicRack CBL reading lists, and download missing issues via GetComics.

## Features

- **Collection** — Browse (folder scan, search, **Organize** menu for rename/metadata/CBR→CBZ), **Series** gaps, **Insights**
- **Issue** — Metadata editor and **Pages** tools for the selected archive (shared folder sidebar)
- **Lists** — CBL editor plus **From arc** (Comic Vine story arcs)
- **Acquire** — GetComics **Search**, **Wishlist**, and download **Queue**

Themes (dark/light), Comic Vine API client with cache, and atomic config/archive/wishlist writes.

## Requirements

- Python 3.14+
- PySide6, httpx, beautifulsoup4, cloudscraper, rarfile
- Optional for `.cbr`: `unrar` or `unar` on your `PATH` (or set `UNRAR_TOOL` to the unrar binary)

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
3. **GetComics download folder** (optional)

## Usage

**Library:** pick a folder → scan → filter/search → edit metadata per comic or use **Rename files…**.

**Metadata:** open a comic from Library (double-click or context menu) → search Comic Vine → apply a proposal → save. Saving writes ComicInfo into the archive; **`.cbr` files are converted to `.cbz` on save** (the original `.cbr` is replaced by the new `.cbz`).

**Recommended Comic Vine workflow (faster searches):**

1. Pick one issue of a series, search Comic Vine, and apply metadata to that file.
2. Copy the **series ID** (and related series fields) and apply them to the rest of the series—multi-select in Metadata supports batch shared-series fields.
3. Search and apply issue metadata for the remaining issues. With the series ID pinned on those rows, lookups stay scoped to that volume and Comic Vine responds much faster than broad title searches.

**Lists:** build a list from Library (**Add to list**) and/or **Add issue** on the Lists tab → export CBL (`Ctrl+E`).  
**Import CBL** (`Ctrl+I`): review linked vs missing counts → confirm replacing the list → optionally add missing issues to the wishlist. The list keeps all CBL entries (local files and not-in-library rows).

**Acquire:** search GetComics or use the wishlist → download → watch the queue on the same tab. Use **Open on GetComics** for the post page; select a provider row and use **Open provider in browser** for a `/dls/` link.

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
