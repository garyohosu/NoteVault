# Changelog

All notable changes to NoteVault will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

*(next milestone: MVP-2 — folder hierarchy output + incremental export)*

---

## [0.1.0] — 2026-03-17

### MVP-1: Text Rescue

First working vertical slice.  Core goal: rescue readable text from a local
iPhone backup without iCloud, without data loss, without crashing on partial
failures.

### Added

**Backup discovery**
- Auto-detect iTunes / Finder backup paths on Windows
  (`%APPDATA%\Apple Computer\MobileSync\Backup\` and `%USERPROFILE%\Apple\…`)
- Manual path override via `--path`
- `list-backups` command with human-readable and `--json` output
- Backup validation: detects encrypted backups, missing files, plist parse errors

**Schema inspection (`inspect-db` command)**
- Detects three known NoteStore.sqlite schema variants:
  - `VARIANT_A` — ZNOTE + ZNOTEBODY (pre-iOS 9 era, plain-text body)
  - `VARIANT_B` — ZICCLOUDSYNCINGOBJECT + ZICNOTEDATA (gzip body)
  - `VARIANT_C` — as B with suspected protobuf envelope
- Reports candidate note/ID/title/date/blob/folder columns per variant
- Probes gzip decompressibility and protobuf likelihood
- `--json` flag for machine-readable schema dump

**Note extraction**
- `ZIDENTIFIER` (UUID) used as stable `note_id`; `Z_PK` kept internal-only
- Stable-hash fallback when `ZIDENTIFIER` is absent
- Apple Core Data timestamp conversion (seconds since 2001-01-01 UTC)
- Folder name resolved via ZFOLDER JOIN (best-effort; None if missing)
- Orphaned FK / missing body handled gracefully — no crash, no silent skip

**Writer**
- Markdown output: `# Title` heading + body + metadata footer
  (note_id, created_at, updated_at, folder, source_variant)
- TXT output: title + underline + body
- Extraction warnings surfaced as blockquotes (Markdown) or `[WARNING: …]` (TXT)
- `_No body extracted._` placeholder for notes with no accessible body
- Windows-safe filenames: `{note_id}_{slugified_title}.{ext}`
- Automatic deduplication: `_2`, `_3` … suffix on filename collision

**Export orchestration**
- `NoteStore.sqlite` located via `Manifest.db` SHA1-hash lookup
- `notes/` + `reports/` directory structure created automatically
- Per-note failure handling: skip-and-continue by default; `--fail-fast` option
- `export_log.json`: full machine-readable report (counts, warnings, failures)
- `summary.txt`: human-readable one-page summary

**Developer tooling**
- `pytest` test suite: 132 tests, 0 failures
  - Unit tests: `test_notes_parser`, `test_writer`, `test_exporter`
  - End-to-end tests: `test_e2e` (Variant A + B full pipeline)
  - Fixtures: Variant A and B minimal SQLite databases
- `ruff` lint + format (line-length 100, `E, F, I, UP` rules)
- `mypy` type checking
- GitHub Actions CI: Python 3.11 + 3.12 matrix on push / PR

### Known Limitations

- Encrypted backups: not supported (detected and reported as `[ENCRYPTED]`)
- Protobuf body decoding (iOS 14+ notes): not implemented; affected notes
  recorded in `export_log.json` with reason
- Output folder structure: flat (folder name preserved in metadata only)
- Attachments (images, PDFs): not extracted
- Primary platform: Windows; macOS / Linux is best-effort
