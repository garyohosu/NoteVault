"""
Export orchestration for NoteVault MVP-1.

Responsibilities:
- Locate NoteStore.sqlite inside an iTunes/Finder backup folder
- Drive notes_parser → writer pipeline
- Create output directory structure  (notes/ + reports/)
- Collect per-note results and write export_log.json + summary.txt
- Skip-and-continue on per-note failure; honour --fail-fast

NOT responsible for: SQLite parsing or text rendering.
Those live in notes_parser.py and writer.py.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from notevault.notes_parser import NoteRecord, NoteStoreSchema, extract_notes
from notevault.writer import SUPPORTED_FORMATS, write_note

# ---------------------------------------------------------------------------
# Manifest.db lookup — find NoteStore.sqlite inside a backup folder
# ---------------------------------------------------------------------------
_NOTES_DOMAIN = "AppDomainGroup-group.com.apple.notes"
_NOTES_REL_PATH = "NoteStore.sqlite"


def find_notestore_sqlite(backup_path: Path) -> Path | None:
    """
    Locate NoteStore.sqlite inside an iTunes/Finder backup folder.

    iTunes backups store files by SHA1 hash.  The mapping is in Manifest.db.
    Returns the resolved path, or None if not found.
    """
    manifest_db = backup_path / "Manifest.db"
    if not manifest_db.exists():
        return None

    try:
        with sqlite3.connect(manifest_db) as conn:
            row = conn.execute(
                "SELECT fileID FROM Files WHERE domain = ? AND relativePath = ?",
                (_NOTES_DOMAIN, _NOTES_REL_PATH),
            ).fetchone()
    except sqlite3.Error:
        return None

    if row is None:
        return None

    file_id: str = row[0]
    hashed_path = backup_path / file_id[:2] / file_id
    return hashed_path if hashed_path.exists() else None


# ---------------------------------------------------------------------------
# Result / Report dataclasses
# ---------------------------------------------------------------------------
@dataclass
class NoteExportResult:
    """Outcome of exporting a single note."""

    note_id: str
    title: str
    success: bool
    output_path: str | None = None  # relative to export root
    warning: str | None = None  # extraction_warning forwarded
    error: str | None = None  # write error message


@dataclass
class ExportReport:
    """Aggregate report for one export run."""

    total_notes: int = 0
    exported_notes: int = 0
    skipped_notes: int = 0
    failed_notes: int = 0
    warnings: list[str] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    output_format: str = "md"
    export_started_at: str = ""
    export_finished_at: str = ""
    output_dir: str = ""
    schema_variant: str = ""
    source_sqlite: str = ""


# ---------------------------------------------------------------------------
# Core export function
# ---------------------------------------------------------------------------
class ExportError(Exception):
    """Raised only when --fail-fast is set and a note write fails."""


def export_notes(
    records: list[NoteRecord],
    schema: NoteStoreSchema,
    output_dir: Path,
    output_format: str = "md",
    fail_fast: bool = False,
) -> ExportReport:
    """
    Write *records* to *output_dir* and return an ExportReport.

    Directory layout::

        output_dir/
          notes/         ← one file per note
          reports/
            export_log.json
            summary.txt

    Per-note failures are recorded and skipped unless *fail_fast* is True,
    in which case ExportError is raised on the first failure.
    """
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{output_format}'. Use: {SUPPORTED_FORMATS}")

    notes_dir = output_dir / "notes"
    reports_dir = output_dir / "reports"
    notes_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    report = ExportReport(
        total_notes=len(records),
        output_format=output_format,
        export_started_at=datetime.now(UTC).isoformat(),
        output_dir=str(output_dir),
        schema_variant=schema.variant.value,
        source_sqlite=str(schema.sqlite_path),
    )

    # Forward schema-level warnings into the report
    report.warnings.extend(schema.warnings)

    source_variant = schema.variant.value

    for note in records:
        result = _export_single(
            note=note,
            notes_dir=notes_dir,
            output_dir=output_dir,
            output_format=output_format,
            source_variant=source_variant,
            fail_fast=fail_fast,
        )
        report.total_notes  # already set
        if result.success:
            report.exported_notes += 1
            if result.warning:
                report.warnings.append(f"[{note.note_id}] {note.title!r}: {result.warning}")
        else:
            report.failed_notes += 1
            report.failures.append(
                {
                    "note_id": result.note_id,
                    "title": result.title,
                    "reason": result.error,
                }
            )

    report.export_finished_at = datetime.now(UTC).isoformat()
    _write_reports(report, reports_dir)
    return report


def _export_single(
    note: NoteRecord,
    notes_dir: Path,
    output_dir: Path,
    output_format: str,
    source_variant: str,
    fail_fast: bool,
) -> NoteExportResult:
    """Write one note; return a NoteExportResult regardless of outcome."""
    try:
        out_path = write_note(
            note=note,
            output_dir=notes_dir,
            output_format=output_format,
            source_variant=source_variant,
        )
        return NoteExportResult(
            note_id=note.note_id,
            title=note.title,
            success=True,
            output_path=str(out_path.relative_to(output_dir)),
            warning=note.extraction_warning,
        )
    except Exception as exc:  # noqa: BLE001
        if fail_fast:
            raise ExportError(
                f"Export failed for note '{note.note_id}' ({note.title!r}): {exc}"
            ) from exc
        return NoteExportResult(
            note_id=note.note_id,
            title=note.title,
            success=False,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------
def _write_reports(report: ExportReport, reports_dir: Path) -> None:
    _write_json_log(report, reports_dir / "export_log.json")
    _write_summary(report, reports_dir / "summary.txt")


def _write_json_log(report: ExportReport, path: Path) -> None:
    data = {
        "total_notes": report.total_notes,
        "exported_notes": report.exported_notes,
        "skipped_notes": report.skipped_notes,
        "failed_notes": report.failed_notes,
        "output_format": report.output_format,
        "schema_variant": report.schema_variant,
        "source_sqlite": report.source_sqlite,
        "output_dir": report.output_dir,
        "export_started_at": report.export_started_at,
        "export_finished_at": report.export_finished_at,
        "warnings": report.warnings,
        "failures": report.failures,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_summary(report: ExportReport, path: Path) -> None:
    lines = [
        "NoteVault Export Summary",
        "=" * 30,
        f"Total notes   : {report.total_notes}",
        f"Exported      : {report.exported_notes}",
        f"Skipped       : {report.skipped_notes}",
        f"Failed        : {report.failed_notes}",
        f"Format        : {report.output_format}",
        f"Schema variant: {report.schema_variant}",
        f"Started       : {report.export_started_at}",
        f"Finished      : {report.export_finished_at}",
    ]
    if report.warnings:
        lines.append("")
        lines.append(f"Warnings ({len(report.warnings)}):")
        for w in report.warnings:
            lines.append(f"  - {w}")
    if report.failures:
        lines.append("")
        lines.append(f"Failures ({len(report.failures)}):")
        for f in report.failures:
            lines.append(f"  - [{f['note_id']}] {f['title']!r}: {f['reason']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Convenience: run a full export from a backup or sqlite path
# ---------------------------------------------------------------------------
def run_export(
    source: Path,
    output_dir: Path,
    output_format: str = "md",
    fail_fast: bool = False,
) -> ExportReport:
    """
    High-level entry point used by the CLI.

    *source* may be:
      - A direct path to NoteStore.sqlite
      - An iTunes/Finder backup UUID folder (Manifest.db must be present)

    Raises FileNotFoundError if NoteStore.sqlite cannot be located.
    """
    sqlite_path = _resolve_sqlite(source)
    schema, records = extract_notes(sqlite_path)
    return export_notes(
        records=records,
        schema=schema,
        output_dir=output_dir,
        output_format=output_format,
        fail_fast=fail_fast,
    )


def _resolve_sqlite(source: Path) -> Path:
    source = source.resolve()
    if source.suffix.lower() == ".sqlite":
        if not source.exists():
            raise FileNotFoundError(f"SQLite file not found: {source}")
        return source

    # Assume backup folder
    found = find_notestore_sqlite(source)
    if found is None:
        raise FileNotFoundError(
            f"Could not locate NoteStore.sqlite in backup: {source}\n"
            "Ensure the backup is unencrypted and Manifest.db is present."
        )
    return found
