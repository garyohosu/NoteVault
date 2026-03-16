# SPEC.md
Version: 1.0
Status: Draft
Project: NoteVault

## 1. Overview

NoteVault is a local-first utility for bulk exporting Apple Notes from an iPhone to a PC or external USB storage without using iCloud.
The primary goal is to help users preserve privacy while creating offline backups of large note collections, including text content and, where feasible, attachments such as images.

This project is intended as a practical rescue and backup tool for users who already have a large number of Apple Notes and need an offline migration/export workflow.

---

## 2. Problem Statement

Apple Notes on iPhone are convenient for daily note taking, but bulk export and offline migration are weak in the standard user flow.
Users with thousands of notes may face the following issues:

- Notes are difficult to export in bulk
- Manual one-by-one export takes too much time
- Users may not want to use iCloud for privacy reasons
- Users want local backup to PC or external USB storage
- Long-term preservation and readability are important
- Attachments should be preserved when possible

The system should provide an offline, privacy-preserving, batch-oriented export workflow.

---

## 3. Goals

### 3.1 Primary Goals

- Export 10,000+ Apple Notes in bulk
- Work without requiring iCloud
- Work offline after local data preparation is complete
- Save output to PC local storage or external USB
- Preserve note text reliably
- Avoid modifying the original iPhone data

### 3.2 Secondary Goals

- Preserve folder structure where possible
- Preserve metadata such as title, created time, updated time
- Export attachments such as images where possible
- Support resumable export for large datasets
- Generate logs and reports for failed items

---

## 4. Non-Goals

The following are explicitly out of scope for the first release:

- Real-time two-way sync with Apple Notes
- Editing notes and writing them back into Apple Notes
- Full-fidelity rendering identical to Apple Notes UI
- Shared-note collaboration workflows
- Cloud sync services
- Online account integration beyond what is required for local backup preparation

---

## 5. Target Users

### 5.1 Primary Users

- Individuals with large Apple Notes collections on iPhone
- Privacy-conscious users who do not want to rely on iCloud
- Users who want a readable local archive
- Users who want a backup before device replacement or cleanup

### 5.2 Secondary Users

- Power users managing long-term personal archives
- Users who need export for migration or disaster recovery
- Users who want structured Markdown or text output for later processing

---

## 6. Product Scope

The recommended first implementation is a desktop tool that operates on locally available iPhone backup data.
The system should focus on extraction, transformation, and offline export rather than direct in-device note manipulation.

Recommended scope:

- Detect local iPhone backup on PC
- Parse note data from local backup
- Extract note content and metadata
- Export notes in text-based formats
- Save output to local folder or USB storage
- Optionally extract attachments when technically feasible

---

## 7. Recommended Architecture

### 7.1 High-Level Approach

Preferred implementation approach:

1. User connects iPhone to PC
2. User creates local backup on PC without using iCloud
3. NoteVault detects and reads the local backup
4. NoteVault parses Apple Notes data structures
5. NoteVault exports notes into readable files
6. NoteVault generates result logs and reports

### 7.2 Major Components

- Backup Discovery Module
- Backup Access Layer
- Notes Parser
- Metadata Extractor
- Attachment Extractor
- Export Engine
- Logging and Report Module
- UI Layer (CLI or GUI)

---

## 8. Functional Requirements

## F-001 Backup Detection
The system shall detect one or more local iPhone backup datasets on the host computer.

### Acceptance Criteria
- The tool can list available local backups
- If multiple backups exist, the user can choose one
- The selected backup is validated before processing

## F-002 Note Inventory
The system shall read and enumerate notes from the selected backup.

### Acceptance Criteria
- The tool shows total note count
- The tool can identify title or fallback label for untitled notes
- The tool can read created and updated timestamps when available
- The tool can identify folder or collection membership when available

## F-003 Scope Selection
The system shall allow the user to choose export scope.

### Acceptance Criteria
- Export all notes
- Export by folder
- Export by date range
- Export by keyword match when technically feasible

## F-004 Bulk Export
The system shall export notes in batch mode.

### Acceptance Criteria
- The tool can process 10,000+ notes in one execution flow
- The tool supports chunked or iterative processing
- The tool does not require per-note manual confirmation

## F-005 Output Formats
The system shall export notes in readable local formats.

### Minimum Required Formats
- TXT
- Markdown

### Optional Formats
- HTML
- JSON metadata files

### Acceptance Criteria
- At least one text-readable file is created per note
- Output filenames are deterministic and safe for filesystem use
- Duplicate note titles do not overwrite each other

## F-006 Attachment Extraction
The system shall attempt to export attachments when technically feasible.

### Acceptance Criteria
- Image attachments are stored as separate files when extractable
- Notes can reference extracted attachments by relative path
- If attachment extraction fails, note text export still succeeds
- Export report records attachment extraction failures

## F-007 Folder Preservation
The system shall preserve note grouping where possible.

### Acceptance Criteria
- Folder names are reflected in export directory structure when available
- If folder metadata is missing, notes fall back to a default grouping
- Export should remain valid even if folder reconstruction is incomplete

## F-008 Destination Selection
The system shall allow export to a chosen local destination.

### Acceptance Criteria
- User can choose a local folder
- User can choose external USB storage if mounted
- Destination write permissions are validated before export starts

## F-009 Resume and Incremental Export
The system should support resumable export.

### Acceptance Criteria
- Interrupted export can be resumed without restarting from zero
- Already exported notes can be skipped on re-run
- Updated notes can be re-exported when change detection is available

## F-010 Logging and Reporting
The system shall generate execution logs and result reports.

### Acceptance Criteria
- Total processed count is recorded
- Success count is recorded
- Failure count is recorded
- Skipped count is recorded
- Failed note identifiers are recorded for troubleshooting

## F-011 Read-Only Safety
The system shall not modify original source data.

### Acceptance Criteria
- Backup source is treated as read-only
- No write operations target the original iPhone note store
- Temporary files are created only in application-controlled locations

---

## 9. Non-Functional Requirements

## N-001 Offline Operation
The system must function offline once the necessary local source data is available.

### Acceptance Criteria
- Main export flow runs without network access
- The tool does not require iCloud
- The tool does not upload note contents externally

## N-002 Privacy
The system must protect user privacy.

### Acceptance Criteria
- Note contents are not sent to external APIs by default
- Logs must avoid storing full sensitive text unless debug mode is explicitly enabled
- All processing happens locally

## N-003 Performance
The system should handle large note collections robustly.

### Acceptance Criteria
- 10,000+ notes can be processed without requiring manual per-item interaction
- Memory usage should remain bounded by streaming or chunking where practical
- Progress indication is available for long-running exports

## N-004 Reliability
The system should tolerate partial failures.

### Acceptance Criteria
- A single malformed note should not abort the entire run
- Failures are isolated and recorded
- Partial successful export remains usable

## N-005 Portability
The system should be designed with desktop portability in mind.

### Acceptance Criteria
- Windows is the primary target
- macOS support is desirable
- The core export engine should be separable from the UI layer

---

## 10. Data Model

## 10.1 Exported Note Metadata

Recommended logical fields:

- note_id
- source_backup_id
- title
- created_at
- updated_at
- folder_name
- filename
- attachment_count
- export_status
- export_error

## 10.2 Example Metadata JSON

```json
{
  "note_id": "local-000001",
  "source_backup_id": "backup-2026-03-16",
  "title": "Shopping Memo",
  "created_at": "2024-01-10T12:34:56",
  "updated_at": "2026-03-01T18:20:00",
  "folder_name": "Personal",
  "filename": "000001_shopping-memo.md",
  "attachment_count": 2,
  "export_status": "success",
  "export_error": null
}
```

---

## 11. Output Structure

Recommended output layout:

```text
export_root/
  notes/
    Personal/
      000001_shopping-memo.md
      000002_meeting-notes.md
    Work/
      000003_project-ideas.md
  attachments/
    000001/
      image_01.jpg
      image_02.png
    000003/
      scan_01.pdf
  reports/
    export_log.json
    summary.txt
```

Requirements:

- Notes shall be readable without proprietary software
- Attachments shall be stored outside the note body as ordinary files
- Paths should remain relative and portable where possible

---

## 12. UX Requirements

## 12.1 Minimum UI

The MVP shall provide at least:

- Backup selection
- Destination folder selection
- Export scope selection
- Start export action
- Progress display
- Final result summary

## 12.2 Ideal Additions

- Retry failed exports
- Preview note counts before execution
- Filter for notes with attachments only
- Duplicate title handling preview
- Incremental export toggle

---

## 13. Constraints and Technical Risks

### 13.1 Constraints

- Apple Notes internal structures may change across iOS versions
- Direct filesystem-style access to Apple Notes on iPhone is not assumed
- Local backup parsing may vary depending on backup encryption and format
- Attachment extraction may be incomplete in some cases

### 13.2 Risks

- Encrypted backups may require additional handling
- Note schema differences may break parsers
- Very large note sets may stress filesystem operations
- Attachment references may be incomplete or difficult to reconstruct

### 13.3 Mitigation Strategy

- Prioritize text export over full-fidelity reconstruction
- Separate parser logic from export logic
- Implement strong logging
- Allow partial success
- Version parser behavior where needed

---

## 14. MVP Definition

## MVP-1
Required for first usable release:

- Detect local backup
- Enumerate notes
- Export note text to Markdown or TXT
- Save to user-selected local directory
- Generate execution report
- Operate fully offline

## MVP-2
Useful follow-up release:

- Preserve folder structure
- Resume interrupted exports
- Incremental export
- Metadata JSON output

## MVP-3
Advanced release:

- Attachment extraction
- Relative attachment linking in Markdown
- ZIP packaging of export result
- Optional GUI improvements

---

## 15. Acceptance Test Scenarios

## AT-001 Large Export
Given a local backup containing more than 10,000 notes,
when the user runs a full export,
then the tool shall complete batch processing without requiring per-note interaction,
and generate a result report.

## AT-002 Offline Use
Given a PC with no internet connection,
when the user runs export from a prepared local backup,
then the export shall succeed without network access.

## AT-003 Privacy
Given a normal export run,
when logs are written,
then note bodies shall not be fully written to logs unless explicit debug mode is enabled.

## AT-004 Partial Failure Tolerance
Given that some notes are malformed or unreadable,
when export runs,
then readable notes shall still be exported,
and failed notes shall be listed in the report.

## AT-005 Destination Validation
Given a user-selected destination,
when export starts,
then the system shall verify write access before processing large volumes of notes.

---

## 16. Suggested Tech Stack

This is not mandatory, but a practical recommendation:

### Option A: Python CLI / Desktop
- Python
- SQLite parsing libraries where needed
- pathlib
- json
- zipfile
- typer or argparse for CLI
- optional tkinter or PySide for GUI

### Option B: Cross-Platform Desktop
- Rust or Go for core engine
- Tauri or Electron for GUI wrapper

For fastest prototyping, Python is recommended.

---

## 17. Open Questions

The following items should be resolved before implementation starts:

1. What exact local backup format(s) will be supported first?
2. Will encrypted backups be supported in MVP-1 or deferred?
3. Should the first release target Windows only?
4. What filename strategy should be used for duplicate titles and unsupported characters?
5. How should embedded rich text be normalized into Markdown?
6. What level of attachment support is realistic for MVP-2?
7. Should ZIP packaging be part of export itself or a post-process step?

---

## 18. Success Metrics

The project will be considered successful if:

- Users can export large Apple Notes collections locally
- Users can avoid iCloud for backup/export
- Exported notes remain readable in ordinary text editors
- Failure cases are visible and recoverable
- The tool is useful even when attachment extraction is incomplete

---

## 19. Repository Naming

Recommended repository name:

- NoteVault

Suggested GitHub description:

- A local-first tool to bulk export Apple Notes from iPhone to PC or USB, without using iCloud.

---

## 20. Future Extensions

Possible future enhancements:

- GUI-driven drag-and-drop workflow
- Searchable archive generation
- HTML index page for exported notes
- Full-text local search
- Deduplication support
- Optional encrypted export package
- Optional import into other note systems

---

## 21. Summary

NoteVault is a practical offline-first bulk export utility for Apple Notes on iPhone.
The first implementation should prioritize safe, read-only, text-preserving bulk export from local backups.
Text rescue comes first. Full attachment handling comes next.

That order keeps the project useful early and avoids drowning in Apple-specific edge cases on day one.
