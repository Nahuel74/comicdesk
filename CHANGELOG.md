# Changelog

## [1.5.0] - 2026-09-12

### Added

- App shell navigation: Library, Metadata, Lists, and Acquire (GetComics + download queue)
- Lists **Save** (imported CBL path or export dialog) and **Apply** for automatic sort; manual reorder via row controls
- Comic Vine API key prompts when enrichment or search requires a key
- Collapsible library folder sidebar on Library and Metadata screens

### Changed

- Reading list table beside live CBL preview (resizable splitter); columns Series, Volume, Issue, Title, Release Date, and File
- Metadata working-set table and Comic Vine right rail; Acquire screen layout refresh
- Theme split into tokens/stylesheet package; responsive panel chrome and action bars

## [1.4.0] - 2026-09-09

### Changed

- Rebranded from CBL Maker to **ComicDesk** across the entire project
- Python package renamed from `cbl_maker` to `comicdesk`
- Config directory moved to `~/.config/comicdesk/` with automatic migration from `~/.config/cbl-maker/`
- Release binaries renamed to `comicdesk` / `comicdesk.exe`
- CBL exports now use the `https://comicdesk.dev/xml/metadata` namespace (legacy namespace still supported on import)
- README and AGENTS.md synchronized with all current features (GetComics, wishlist, download queue, themes)

## [1.3.0] - 2026-09-09

### Added

- Persistent GetComics wishlist populated automatically from missing CBL import references
- Wishlist panel in GetComics with search, individual/batch download, remove, and clear actions
- Auto-removal of wishlist items when comics become available locally after scan or download

### Fixed

- GetComics name searches now URL-encode `#` correctly (e.g. `Avengers #19`)
- Wishlist and auto-resolve queries use series name and issue number only, without volume/year

## [1.2.0] - 2026-09-09

### Added

- Downloads tab with sequential download queue and right-click actions (cancel, retry, remove, copy links)
- Light/Dark theme selector with persistent config and consistent panel styling
- Automatic fallback to alternate download mirrors when a link fails

### Fixed

- GetComics issue excerpt no longer disappears after issue hydration
- Settings dialog crash on open (`apply_theme` ran before widgets were created)
- Download button passing Qt's `checked` bool as the selected link
- GetComics detail panel theme colors, spacing, and layout

## [1.1.0] - 2026-09-09

### Added

- GetComics tab: search getcomics.org by name, category, or tag
- Issue detail view with cover thumbnail and download link list
- Automatic download for direct HTTP links (e.g. Download Now / main server mirrors)
- Manual download fallback via browser for external hosts (MEGA, Pixeldrain, etc.)
- Configurable GetComics download folder and optional post-download Comic Vine enrichment
- Structured logging across search, resolve, download, and UI actions for easier debugging

### Fixed

- Download button no longer passes Qt's `checked` bool as the selected link
- Thumbnail loading via cloudscraper (Cloudflare-compatible image fetch)
- Duplicate redirect resolution when picking auto-download links
- URL-encoded filenames decoded on save
- Download progress shows speed and ETA; cancel button stops in-flight downloads

## [1.0.0] - 2026-09-03

First stable release of ComicDesk.

### Added

- Three-panel workspace: folder browser, comic list, and reading list side by side
- CBZ metadata editing via embedded ComicInfo.xml
- Comic Vine API integration with rate limiting and local disk caching
- Automatic metadata enrichment from Comic Vine (series, issue, volume, credits)
- CBL reading list import and export (ComicRack format)
- Dedicated metadata editor tab with transactional editing (snapshot/commit/discard)
- Sort controls for reading lists (by name, issue number, or manual order)
- Persistent configuration at `~/.config/comicdesk/config.json`
- PyInstaller packaging for Linux and Windows single-file executables
- GitHub Actions CI/CD pipeline for automated testing and releases

### Fixed

- Alphabetical sort and series handling in CBL import
- EnrichWorker now uses ComicVineClient API to fetch series_id correctly
- Metadata search reliability
- Date parsing and display
