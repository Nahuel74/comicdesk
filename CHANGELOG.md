# Changelog

All notable changes are documented here. New releases add a section at the top (`## [x.y.z] - date`); older entries stay below. GitHub release notes use only the section for the tagged version.

## [Unreleased]

## [1.11.1] - 2026-09-24

### Fixed

- **Pages** bulk rename could corrupt `.cbz` contents when nested image members flattened to the same path as a rename target
- **Pages** `{Page}` in rename templates no longer inherits issue-number zero padding from ComicInfo Count (only `{Number}` and explicit `{Page:N}` / “Page digits” apply)
- **Pages** `{Page}` uses the page segment from scan-style filenames (e.g. `001-003` → 3) when present, instead of only archive order index
- **Pages** bulk rename resolves duplicate page targets by keeping the root or scan-style member and skipping nested or weaker duplicates so one collision does not block the whole archive
- **Pages** `{Page}` keeps scan page `000` (e.g. `001-000` → 0) instead of treating it as archive index 1

## [1.11.0] - 2026-09-24

### Added

- **Pages** tab: browse image members of the selected issue with page preview; **Delete selected pages…** for manual removal; **Auto-clean folder…** runs filename heuristics across the scanned folder; **Rename pages…** bulk-renames archive members from a template (Library selection or whole folder), including `{PageFolder}` and `{ArchiveStem}` for scan release layouts; renames flatten nested folders to archive root; shared folder sidebar with Library and Metadata

## [1.10.0] - 2026-09-22

### Added

- Library **Update metadata…** batch action: refresh Comic Vine metadata for the current folder or selection when every target has a lookup key (Issue ID, Series ID + number, or series name + number), with sequential identify, apply, and archive write; confirmation before overwrite and a detailed summary when some files are skipped or fail

## [1.9.0] - 2026-09-22

### Added

- Library **Rename folders…** renames series/volume directories under the scanned folder from a metadata template (preview, validation when issues in the same folder would get different names)

### Changed

- Metadata editor: Comic Vine–only fields, spaced Title Case labels, and comma-separated credits normalized with `, ` on apply

### Fixed

- Comic Vine enrichment: composite credit roles (e.g. `penciler, cover`), publisher/imprint from the parent volume when the issue payload is incomplete, and hydration when search/list results lack `person_credits`; genre only when Comic Vine exposes real `genres` (not volume concept tags)
- **Rename folders…** treats nested **Annual** / **Special** (and similar) subfolders as separate rename targets instead of grouping them with the parent series directory

## [1.8.9] - 2026-09-20

### Added

- Library folder scan: parallel metadata reads for large folders, persistent mtime/size metadata cache (`~/.config/comicdesk/cache/scan_metadata.json`), and opt-in benchmark (`COMICDESK_BENCH=1`)
- Library UI: progress bar and **Loading library…** status with file counts while a folder is scanned

### Changed

- Library scan enumerates comic files in a single directory walk, reads CBZ `ComicInfo.xml` with a faster lookup path, and avoids opening misnamed ZIP `.cbr` files twice
- Removed unused duplicate `ScanWorker` from the folder sidebar (scanning uses the library worker only)

### Fixed

- Scan metadata cache no longer crashes when persisting comics whose ComicInfo includes custom XML elements (`comicinfo_unknown`)

## [1.8.8] - 2026-09-20

### Fixed

- Metadata tab and reading-list metadata search no longer crash when switching comics or clearing proposals while Comic Vine cover thumbnails are still loading (`QThread` destroyed while still running)

## [1.8.7] - 2026-09-20

### Fixed

- Metadata save for `.cbr` files that are ZIP archives (misnamed CBZ) now converts to `.cbz` instead of failing as invalid RAR

## [1.8.6] - 2026-09-20

### Added

- Metadata tab: numpad and main-digit **1–4** shortcuts for Comic Vine Search, Apply, Discard draft, and Save; action buttons show matching step numbers (**3.** Discard, **4.** Save)

### Fixed

- ComicInfo save now writes **ComicDeskCvIssueId** and **ComicDeskCvSeriesId** so Comic Vine issue and series IDs survive library rescans, not only Web link parsing
- Comic Vine identification and Metadata apply now resolve series start year and issue count when search or volume-scoped list results already include descriptions or credits
- ComicInfo **Web** keeps a single canonical Comic Vine issue URL (slug preferred); generic `/issue/` and volume links are no longer duplicated on save

## [1.8.5] - 2026-09-20

### Added

- Acquire tab: **Open on GetComics** opens the issue post page in your browser (independent of the download-links table selection)

### Removed

- Automatic Comic Vine metadata enrichment after GetComics downloads; enrich manually from the Metadata tab
- `auto_enrich_after_download` config key (legacy values in `config.json` are ignored)

### Changed

- Acquire: **Open provider in browser** applies only to a selected download-link row; disabled controls use muted button styling
- README: CBR→CBZ on metadata save, recommended Comic Vine series-ID workflow, and Acquire browser controls

### Fixed

- Metadata Comic Vine search with a pinned series ID retries volume-scoped issue listing when Comic Vine’s issue-number filter returns no rows (e.g. Mutopia X with a correct volume id)
- Comic Vine identification ignores ComicInfo issue numbers with an “(of N)” pack suffix when the filename supplies a plain issue number

## [1.8.4] - 2026-09-19

### Added

- Metadata working set: taller file list, multi-select, and batch shared-series save for Comic Vine series ID, series name, publication year, and publisher
- Comic Vine search in Metadata is available only when a single working-set row is selected; with a pinned series ID, search uses scoped issue lookup without broad filename fallback

### Changed

- Metadata Comic Vine search with a pinned series ID uses a single scoped `issues/` request (no redundant `get_issue` / volume round trips when list results are already complete); repeat searches hit the API cache for near-instant results
- Metadata batch workflow: multi-select replaces the per-issue editor with a compact shared-series form and hides the Comic Vine panel; **Save to N selected** confirms then writes archives immediately

## [1.8.3] - 2026-09-19

### Fixed

- Metadata Comic Vine search matches series when Comic Vine uses a leading “The” (e.g. Uncanny X-Men #451 from filename metadata)
- Metadata search resolves long-running series (e.g. Uncanny X-Men #457) via volume lookup with cover-date year hints and issue-number search fallbacks
- Settings dialog no longer crashes when resolving the system theme
- Comic Vine client retries on HTTP 420, skips caching empty search results, and uses name-only volume filters with client-side start-year matching

### Changed

- Metadata and Lists “add issue” Comic Vine search show issue proposals only, not volume/series-only rows

## [1.8.2] - 2026-09-19

### Fixed

- Rename files replaces characters that are invalid in filenames with a spaced dash (` - `), with normalized single spaces, so metadata such as series titles with colons is preserved in the new name

## [1.8.1] - 2026-09-19

### Changed

- Metadata Comic Vine search shows an indeterminate progress bar, a result count, and cover thumbnails with structured lines for each candidate

### Fixed

- Comic Vine identification treats punctuation differences in series names as equivalent (e.g. local filenames vs Comic Vine titles with colons)
- Volume lookup no longer runs issue lists on unrelated volumes when the series name does not match
- Publication year hints can be taken from a parent folder name such as `(2005)` when the filename has no year

## [1.8.0] - 2026-09-18

### Added

- Library scan and metadata read support for `.cbr` (RAR) comics alongside `.cbz`
- Saving metadata or GetComics auto-enrich on a `.cbr` converts it to a `.cbz` archive safely (temp file, validation, then remove the original)

### Changed

- **Rename files…** excludes `.cbr` until metadata is saved (conversion to `.cbz`)
- Library and metadata UI copy refers to comic archives instead of CBZ-only wording

### Fixed

- Comic Vine metadata search no longer fails when the API returns brotli or gzip-compressed JSON
- CBR→archive conversion skips empty RAR directory entries (e.g. `Zone/`) that broke saves

### Notes

- Reading and converting `.cbr` requires the `rarfile` package and a system tool such as `unrar` or `unar` on `PATH` (or `UNRAR_TOOL`)

## [1.7.1] - 2026-09-18

### Changed

- Main window opens at 1200×720 by default (was Qt’s implicit smaller size)

### Fixed

- Metadata panel no longer crashes when switching comics or candidates while Comic Vine hydration is still running (`QThread destroyed while thread is still running`)
- Comic Vine metadata search returns more issue and volume candidates (20 results instead of 10)
- Year hints from filenames or ComicInfo now match issues whose cover year is one year after the parent volume’s Comic Vine start year (e.g. *Excalibur* #8 tagged `(2005)` on the 2004 series)

## [1.7.0] - 2026-09-18

### Fixed

- Comic Vine search now parses issue numbers from filenames with trailing `(Digital)` / scan-group tags and uses the publication year to disambiguate duplicate series names (e.g. multiple *Excalibur* #1)
- GetComics issue parsing omitted direct-host download buttons (TERABOX, VIKINGFILE, etc.) when they were not `/dls/` links

### Added

- Library **Rename files…** bulk renames local CBZ files from a metadata template with preview and confirmation
- Settings **System** theme follows the OS light/dark appearance
- Reading list drag-and-drop reorder (custom order); Remove for the selected row

### Changed

- Removed Library **Enrich all metadata** bulk action (enrichment remains in the Metadata tab and optional GetComics auto-enrich)
- CBL import reads ComicRack `Series`, `Number`, and `Year` book attributes (not only `SeriesName`/`Issue`); wishlist labels use embedded Comic Vine metadata when book fields are empty
- Re-importing a CBL repairs existing wishlist rows (same Comic Vine issue) that were saved with empty series/issue before the parser fix
- Table alternating rows use ComicDesk theme tokens instead of the system palette
- Reading list table drops per-row move/remove columns for clearer layout

## [1.6.0] - 2026-09-14

### Added

- Library table **Name** column; Lists **Add issue** with metadata search; reading lists keep non-local CBL entries
- CBL import summary, optional wishlist confirmation, and full-list import order

### Changed

- Library: no status column (filter unchanged); Metadata instance column **Metadata status**
- Bulk enrichment labeled **Enrich all metadata**; README and AGENTS updated
- GitHub Releases use only the changelog section for the tagged version

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
