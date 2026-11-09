# Changelog

All notable changes to Daisy are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.1] - 2026-11-09

### Fixed
- Drops are accepted anywhere on a highlighted format slice, not just near its inner edge.
- Same-format aliases (`.jpeg`, `.tif`, `.apng`) are no longer offered as conversion targets.
- Archiving or duplicating a folder with a trailing slash no longer creates a hidden `.zip` or an empty copy name.
- Duplicating a folder now copies its contents instead of failing.
- Image conversions and tools preserve animation frames instead of keeping only the first.
- Term and Reveal open a dragged folder itself rather than its parent directory.

## [1.0.0] - 2026-11-02

### Added
- Radial file-conversion wheel with convert, tool, and action menus.
- One-shot Linux installer (`install.sh`) with dependency setup and autostart.
- Image conversion (PNG, JPG, WEBP, TIFF, BMP, GIF) and PDF-to-image/text.
- PDF and Office document conversion via LibreOffice.
- Image tools: compress, resize, rotate, strip metadata.
- PDF and Office compression with a quality dial.
- Archive creation (ZIP, TGZ).
- MIT license, CI workflow, issue templates, and contributor guide.

### Changed
- Renamed project from *filewheel* to *Daisy*.
- Restyled the wheel with a "liquid glass" look.

### Fixed
- PDF → DOCX conversion now uses the correct LibreOffice import filter.
- Folder contents are now included when zipping a directory.
- The wheel no longer offers image tools on non-image files.
