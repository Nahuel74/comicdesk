# Changelog

## [1.0.0] - 2026-09-03

First stable release of CBL Maker.

### Added

- Three-panel workspace: folder browser, comic list, and reading list side by side
- CBZ metadata editing via embedded ComicInfo.xml
- Comic Vine API integration with rate limiting and local disk caching
- Automatic metadata enrichment from Comic Vine (series, issue, volume, credits)
- CBL reading list import and export (ComicRack format)
- Dedicated metadata editor tab with transactional editing (snapshot/commit/discard)
- Sort controls for reading lists (by name, issue number, or manual order)
- Persistent configuration at `~/.config/cbl-maker/config.json`
- PyInstaller packaging for Linux and Windows single-file executables
- GitHub Actions CI/CD pipeline for automated testing and releases

### Fixed

- Alphabetical sort and series handling in CBL import
- EnrichWorker now uses ComicVineClient API to fetch series_id correctly
- Metadata search reliability
- Date parsing and display
