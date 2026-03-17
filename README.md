# NoteVault

A local-first tool to bulk export Apple Notes from iPhone to PC or USB,
**without using iCloud**.  Works directly from a standard iTunes / Finder
backup stored on your Windows PC.

> **Status: MVP-1 (Text Rescue)** — core vertical slice is working.
> Folder hierarchy mirroring and rich-text (Protobuf) support are planned
> for later milestones.

---

## Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Step-by-step Usage](#step-by-step-usage)
- [Sample Output](#sample-output)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | [python.org](https://www.python.org/) |
| iTunes or Finder backup | Must be **unencrypted** and stored locally |
| Windows 10 / 11 | Primary target; macOS/Linux best-effort |

### Creating an unencrypted local backup

1. Open **iTunes** (or **Finder** on a Mac) and connect your iPhone.
2. Under *Backups*, choose **"This computer"**.
3. Make sure **"Encrypt local backup"** is **unchecked**.
4. Click **Back Up Now** and wait for it to finish.

The backup will be stored at one of these paths on Windows:

```
%APPDATA%\Apple Computer\MobileSync\Backup\
%USERPROFILE%\Apple\MobileSync\Backup\
```

---

## Installation

```bash
# Clone and install in editable/development mode
git clone https://github.com/your-org/notevault.git
cd notevault
pip install -e .

# With dev tools (pytest, ruff, mypy)
pip install -e ".[dev]"
```

---

## Quick Start

```bash
# 1. Find your backups
notevault list-backups

# 2. Export notes from one of them
notevault export --backup "C:\Users\you\AppData\Roaming\Apple Computer\MobileSync\Backup\<UUID>" --output "./my-notes"
```

That's it.  Your notes land in `my-notes/notes/` and a report goes to
`my-notes/reports/`.

---

## Step-by-step Usage

### 1 — List available backups

```
notevault list-backups
```

```
[OK] iPhone  2024-11-15 22:31  C:\Users\...\Backup\a1b2c3d4...
[OK] iPhone  2024-09-03 10:12  C:\Users\...\Backup\e5f6g7h8...
```

Use `--json` for machine-readable output:

```bash
notevault list-backups --json
```

Use `--path` to scan a non-standard location:

```bash
notevault list-backups --path "D:\MyBackups"
```

---

### 2 — Inspect a NoteStore.sqlite (optional but recommended)

Before exporting, you can verify the schema variant and confirm that
NoteStore.sqlite is readable:

```bash
notevault inspect-db --sqlite "path\to\NoteStore.sqlite"
```

```
Variant          : VARIANT_B
Tables           : ZICCLOUDSYNCINGOBJECT, ZICNOTEDATA, ZFOLDER, ...
Note table       : ZICCLOUDSYNCINGOBJECT
ID columns       : ['ZIDENTIFIER']
Title columns    : ['ZTITLE1']
Date columns     : ['ZCREATIONDATE1', 'ZMODIFICATIONDATE1']
Blob columns     : ['ZDATA']
Folder tables    : ['ZFOLDER']
Folder join hints: 1 found
Requires gzip    : True
May need protobuf: False
Notes count      : 142
```

Add `--json` for a full machine-readable dump including per-table column
definitions.

---

### 3 — Export notes

```bash
notevault export \
  --backup "C:\...\Backup\<UUID>" \
  --output "./my-notes" \
  --format md
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--backup` / `-b` | *(required)* | Path to the UUID backup folder |
| `--output` / `-o` | `./export` | Destination directory |
| `--format` / `-f` | `md` | Output format: `md` or `txt` |
| `--fail-fast` | off | Abort on first note failure instead of skipping |

```
Source  : C:\...\Backup\a1b2c3d4...
Output  : .\my-notes
Format  : md
Done. Exported 142/142 notes to .\my-notes\notes
```

---

## Sample Output

### Directory layout

```
my-notes/
  notes/
    UUID-001_shopping-list.md
    UUID-002_meeting-notes.md
    hash-3f8a1c2e_untitled.md
  reports/
    export_log.json
    summary.txt
```

### Markdown note (`UUID-001_shopping-list.md`)

```markdown
# Shopping List

Apples
Bananas
Oranges

---
note_id: A4B9C2D1-E3F4-5678-ABCD-123456789ABC
created_at: 2024-10-01T09:00:00+00:00
updated_at: 2024-11-14T18:32:00+00:00
folder: Groceries
source_variant: VARIANT_B
```

### TXT note (`UUID-001_shopping-list.txt`)

```
Shopping List
=============

Apples
Bananas
Oranges
```

### `reports/export_log.json`

```json
{
  "total_notes": 142,
  "exported_notes": 141,
  "skipped_notes": 0,
  "failed_notes": 1,
  "output_format": "md",
  "schema_variant": "VARIANT_B",
  "export_started_at": "2024-11-15T13:00:00+00:00",
  "export_finished_at": "2024-11-15T13:00:04+00:00",
  "warnings": [],
  "failures": [
    {
      "note_id": "UUID-XYZ",
      "title": "Corrupted Note",
      "reason": "body requires protobuf decoding (not yet implemented)"
    }
  ]
}
```

### `reports/summary.txt`

```
NoteVault Export Summary
==============================
Total notes   : 142
Exported      : 141
Skipped       : 0
Failed        : 1
Format        : md
Schema variant: VARIANT_B
Started       : 2024-11-15T13:00:00+00:00
Finished      : 2024-11-15T13:00:04+00:00

Failures (1):
  - [UUID-XYZ] 'Corrupted Note': body requires protobuf decoding (not yet implemented)
```

---

## Troubleshooting

### `No backups found`

- Confirm iTunes / Finder has created a local backup (not iCloud-only).
- Try passing the backup root explicitly: `notevault list-backups --path "D:\Backups"`.

### `[ENCRYPTED]` shown in list-backups

- The backup is encrypted. Decrypt it first:
  iTunes → select device → *Encrypt local backup* → uncheck and enter password.
- Encrypted backups are not supported in MVP-1.

### `Could not locate NoteStore.sqlite`

- The backup folder may be incomplete. Try a fresh backup.
- Confirm `Manifest.db` exists inside the UUID folder.

### Notes export with `body requires protobuf decoding`

- This affects some notes on iOS 14+ where the body is stored in a Protobuf
  envelope.  These notes are recorded in `export_log.json` under `failures`.
- Protobuf support is planned for a future milestone.

### Garbled filenames / encoding issues

- All output is UTF-8.  Ensure your editor / file explorer supports UTF-8.
- Windows: set your terminal to UTF-8 with `chcp 65001` if characters appear
  garbled in the console.

---

## Known Limitations

| Limitation | Status |
|------------|--------|
| Encrypted backups | Not supported (MVP-1) |
| Protobuf body decoding (iOS 14+) | Not implemented (planned) |
| Folder hierarchy in output | Notes are flat; folder stored in metadata only |
| Attachments (images, PDFs) | Not extracted (planned MVP-3) |
| macOS / Linux paths | Best-effort; primary target is Windows |
| iCloud backups | Not supported; local backups only |

---

## Development

```bash
# Run tests
pytest

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy src
```

CI runs automatically on every push and pull request via GitHub Actions
(`.github/workflows/ci.yml`).
