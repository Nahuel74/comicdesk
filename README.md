# CBL Maker

A PySide6 desktop application for managing comic book metadata (CBZ ComicInfo.xml) and creating ComicRack CBL reading lists. Integrates with the Comic Vine API for automatic metadata enrichment.

## Features

- **CBZ Metadata Editing** — View and edit ComicInfo.xml embedded in CBZ archives
- **Comic Vine Integration** — Search, identify, and enrich comics with data from Comic Vine
- **CBL Reading Lists** — Import and export ComicRack CBL reading lists
- **Three-Panel Workspace** — Folder browser, comic list, and reading list side by side
- **Metadata Editor** — Dedicated tab for editing comic metadata with validation
- **API Caching** — Local disk cache to reduce API calls and improve performance

## Requirements

- Python 3.14+
- PySide6
- httpx

## Installation

### Pre-built Binaries

Download the latest release from [Releases](https://github.com/Nahuel74/cbl-maker/releases):

- **Linux**: `cbl-maker-linux.tar.gz` — extract and run `./cbl-maker`
- **Windows**: `cbl-maker-windows.exe` — run directly

### From Source

```bash
git clone https://github.com/Nahuel74/cbl-maker.git
cd cbl-maker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python3 main.py
```

On first launch, open **Settings** (`Ctrl+,`) to configure:

1. **Comic Vine API Key** — Get one at https://comicvine.gamespot.com/api/
2. **Default Folder** — Optional starting directory for the folder browser
3. **API Cache** — Enable/disable local caching of API responses

Configuration is stored at `~/.config/cbl-maker/config.json`.

## Project Structure

```
cbl-maker/
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── build/
│   ├── cbl-maker.spec       # PyInstaller spec (shared)
│   ├── build_linux.sh       # Linux build script
│   ├── build_windows.bat    # Windows build script
│   └── verify_build.sh      # Binary verification
├── cbl_maker/
│   ├── __init__.py          # Version (1.0.0)
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
│   │   ├── identification.py# Match comics to Comic Vine
│   │   └── metadata_session.py # Transactional metadata editing
│   ├── ui/                  # PySide6 interface
│   └── utils/               # Filename parsing, URL parsing
├── tests/                   # Test suite
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
./build/build_linux.sh            # → dist/cbl-maker

# Windows
build\build_windows.bat           # → dist\cbl-maker.exe
```

### Releasing

```bash
git tag v1.0.0
git push origin v1.0.0
```

This triggers the GitHub Actions workflow: tests run, binaries are built for Linux and Windows, and a GitHub Release is created with the executables attached.

## Architecture Notes

- Config and API cache live in `~/.config/cbl-maker/`, outside the repository
- All file writes (config, CBZ) are atomic via temp file + `os.replace`
- Comic Vine search results are partial — always hydrate via `get_issue()` before using credits or descriptions
- The `Comic.volume` field stores the publication start year, never the Comic Vine database ID

## License

MIT
