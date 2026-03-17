"""
Unit tests for exporter.py.

Covers:
- export_notes: directory creation, file output, report generation
- Per-note failure: skip-and-continue vs --fail-fast
- ExportReport: counts, warnings, failures fields
- JSON log and summary.txt written correctly
- find_notestore_sqlite: Manifest.db lookup
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from notevault.exporter import ExportError, export_notes, find_notestore_sqlite
from notevault.notes_parser import NoteRecord, NoteStoreSchema, SchemaVariant


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def _schema(variant: SchemaVariant = SchemaVariant.VARIANT_A) -> NoteStoreSchema:
    s = NoteStoreSchema(sqlite_path=Path("fake.sqlite"))
    s.variant = variant
    return s


def _note(
    note_id: str = "UUID-001",
    title: str = "Test",
    body: str | None = "Hello",
    folder_name: str | None = None,
    warn: str | None = None,
) -> NoteRecord:
    return NoteRecord(
        note_id=note_id,
        z_pk=1,
        title=title,
        created_at=None,
        updated_at=None,
        folder_name=folder_name,
        body_text=body,
        source_table="ZNOTE",
        extraction_warning=warn,
    )


# ---------------------------------------------------------------------------
# export_notes — directory structure
# ---------------------------------------------------------------------------
class TestExportNotesDirectories:
    def test_notes_dir_created(self, tmp_path: Path) -> None:
        export_notes([_note()], _schema(), tmp_path)
        assert (tmp_path / "notes").is_dir()

    def test_reports_dir_created(self, tmp_path: Path) -> None:
        export_notes([_note()], _schema(), tmp_path)
        assert (tmp_path / "reports").is_dir()

    def test_json_log_created(self, tmp_path: Path) -> None:
        export_notes([_note()], _schema(), tmp_path)
        assert (tmp_path / "reports" / "export_log.json").exists()

    def test_summary_txt_created(self, tmp_path: Path) -> None:
        export_notes([_note()], _schema(), tmp_path)
        assert (tmp_path / "reports" / "summary.txt").exists()


# ---------------------------------------------------------------------------
# export_notes — counts
# ---------------------------------------------------------------------------
class TestExportNotesCounts:
    def test_total_count(self, tmp_path: Path) -> None:
        notes = [_note("UUID-001"), _note("UUID-002"), _note("UUID-003")]
        report = export_notes(notes, _schema(), tmp_path)
        assert report.total_notes == 3

    def test_exported_count(self, tmp_path: Path) -> None:
        notes = [_note("UUID-001"), _note("UUID-002")]
        report = export_notes(notes, _schema(), tmp_path)
        assert report.exported_notes == 2
        assert report.failed_notes == 0

    def test_empty_notes(self, tmp_path: Path) -> None:
        report = export_notes([], _schema(), tmp_path)
        assert report.total_notes == 0
        assert report.exported_notes == 0

    def test_note_files_present(self, tmp_path: Path) -> None:
        notes = [_note("UUID-001", "Alpha"), _note("UUID-002", "Beta")]
        export_notes(notes, _schema(), tmp_path)
        files = list((tmp_path / "notes").iterdir())
        assert len(files) == 2


# ---------------------------------------------------------------------------
# export_notes — failure handling
# ---------------------------------------------------------------------------
class TestExportNotesFailures:
    def test_skip_on_write_error(self, tmp_path: Path) -> None:
        """A note that raises on write is recorded as failed; others continue."""
        good = _note("UUID-001", "Good")
        bad = _note("UUID-002", "Bad")

        # Make write_note raise only for the bad note
        original_write = __import__("notevault.writer", fromlist=["write_note"]).write_note

        def patched_write(note, output_dir, output_format, source_variant=""):
            if note.note_id == "UUID-002":
                raise OSError("disk full")
            return original_write(note, output_dir, output_format, source_variant)

        with patch("notevault.exporter.write_note", side_effect=patched_write):
            report = export_notes([good, bad], _schema(), tmp_path)

        assert report.exported_notes == 1
        assert report.failed_notes == 1
        assert report.failures[0]["note_id"] == "UUID-002"
        assert "disk full" in report.failures[0]["reason"]

    def test_fail_fast_raises(self, tmp_path: Path) -> None:
        def always_fail(note, output_dir, output_format, source_variant=""):
            raise OSError("forced failure")

        with patch("notevault.exporter.write_note", side_effect=always_fail):
            with pytest.raises(ExportError, match="forced failure"):
                export_notes([_note()], _schema(), tmp_path, fail_fast=True)

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            export_notes([_note()], _schema(), tmp_path, output_format="pdf")


# ---------------------------------------------------------------------------
# export_notes — warnings forwarded
# ---------------------------------------------------------------------------
class TestExportNotesWarnings:
    def test_extraction_warning_forwarded(self, tmp_path: Path) -> None:
        note = _note(warn="protobuf required")
        report = export_notes([note], _schema(), tmp_path)
        assert any("protobuf" in w for w in report.warnings)

    def test_schema_warnings_forwarded(self, tmp_path: Path) -> None:
        schema = _schema()
        schema.warnings.append("unknown table XYZ")
        report = export_notes([_note()], schema, tmp_path)
        assert any("XYZ" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# Report content
# ---------------------------------------------------------------------------
class TestReportContent:
    def test_json_log_structure(self, tmp_path: Path) -> None:
        notes = [_note("UUID-001"), _note("UUID-002")]
        export_notes(notes, _schema(), tmp_path)
        data = json.loads((tmp_path / "reports" / "export_log.json").read_text())
        assert data["total_notes"] == 2
        assert data["exported_notes"] == 2
        assert data["failed_notes"] == 0
        assert "export_started_at" in data
        assert "export_finished_at" in data

    def test_json_log_failures_recorded(self, tmp_path: Path) -> None:
        def always_fail(note, output_dir, output_format, source_variant=""):
            raise OSError("test error")

        with patch("notevault.exporter.write_note", side_effect=always_fail):
            export_notes([_note("UUID-BAD", "Bad")], _schema(), tmp_path)

        data = json.loads((tmp_path / "reports" / "export_log.json").read_text())
        assert data["failed_notes"] == 1
        assert data["failures"][0]["note_id"] == "UUID-BAD"

    def test_summary_txt_readable(self, tmp_path: Path) -> None:
        export_notes([_note()], _schema(), tmp_path)
        text = (tmp_path / "reports" / "summary.txt").read_text(encoding="utf-8")
        assert "NoteVault Export Summary" in text
        assert "Exported" in text

    def test_schema_variant_in_report(self, tmp_path: Path) -> None:
        export_notes([_note()], _schema(SchemaVariant.VARIANT_B), tmp_path)
        data = json.loads((tmp_path / "reports" / "export_log.json").read_text())
        assert data["schema_variant"] == "VARIANT_B"


# ---------------------------------------------------------------------------
# find_notestore_sqlite
# ---------------------------------------------------------------------------
class TestFindNotestoreSqlite:
    def _make_backup(self, tmp_path: Path, file_id: str = "ab" * 20) -> Path:
        """Create a minimal fake backup with Manifest.db."""
        from notevault.exporter import _NOTES_DOMAIN, _NOTES_REL_PATH

        backup = tmp_path / "backup"
        backup.mkdir()
        manifest = backup / "Manifest.db"
        conn = sqlite3.connect(manifest)
        conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT)")
        conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?)",
            (file_id, _NOTES_DOMAIN, _NOTES_REL_PATH),
        )
        conn.commit()
        conn.close()

        # Create the hashed file
        hashed_dir = backup / file_id[:2]
        hashed_dir.mkdir()
        (hashed_dir / file_id).write_bytes(b"fake sqlite data")
        return backup

    def test_found(self, tmp_path: Path) -> None:
        file_id = "ab" * 20
        backup = self._make_backup(tmp_path, file_id)
        result = find_notestore_sqlite(backup)
        assert result is not None
        assert result.exists()

    def test_not_found_no_manifest(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        assert find_notestore_sqlite(empty) is None

    def test_not_found_wrong_domain(self, tmp_path: Path) -> None:
        backup = tmp_path / "backup"
        backup.mkdir()
        conn = sqlite3.connect(backup / "Manifest.db")
        conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT)")
        conn.execute("INSERT INTO Files VALUES ('abc', 'WrongDomain', 'NoteStore.sqlite')")
        conn.commit()
        conn.close()
        assert find_notestore_sqlite(backup) is None
