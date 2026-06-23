# Changelog — DRIVE v1.2.0

## v1.2.0 — AI SSD Guardian (2026-06-23)

### Fixed
- `sample_framework_writes` blocking the scanner when no usage data exists
- Wrong import in `PathScanner` (was referencing unavailable module)
- Missing API endpoints in the Flask server that caused empty responses

### Improved
- **Scan time 10.4s → 877ms** via depth-limited `folder_size_bytes` calculation (6-framework test set)
- All GB/day numbers now display source badges: `Live`, `Estimated`, `Community`, or `Unverified`
- `sample_framework_writes` now gracefully skips when no usage data is found (no crash)

### Changed
- GB/day figures in the UI and CLI now carry source credibility badges so users know how reliable each estimate is
- Improved error handling in path scanner when AI framework paths are inaccessible

### Added
- **Bundled smartmontools binary** (`smartmontools/smartctl.exe`) — full SMART health data without requiring a system install
- **Gumroad license system** — activation key entry, license validation, grace period for offline use
- **Share panel** — export scan results as shareable text/HTML for forum posts and issue reports

### Known Limitations
- **ImDisk required for RAM Shield** — if ImDisk is not installed, the shield feature will prompt for installation
- **smartmontools is optional for full health data** — DRIVE works without it using estimated/calculated metrics; bundled binary provides full SMART when available

---

## v1.1.0 — Initial PyInstaller Build Support

- First standalone .exe build via `pyinstaller drive.spec`
- Added `drive.spec` with icon, onefile, and console=False