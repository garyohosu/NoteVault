"""
End-to-end tests for the full export pipeline.

These tests exercise the complete vertical slice:
  conftest fixture DB  →  extract_notes()  →  export_notes()  →  filesystem

They intentionally use the same fixtures as the unit tests so that any
regression in the parser or writer shows up here too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from notevault.exporter import export_notes
from notevault.notes_parser import SchemaVariant, extract_notes


# ---------------------------------------------------------------------------
# Variant A — full pipeline
# ---------------------------------------------------------------------------
class TestE2EVariantA:
    def test_notes_dir_created(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path)
        assert (tmp_path / "notes").is_dir()

    def test_reports_dir_created(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path)
        assert (tmp_path / "reports").is_dir()

    def test_note_files_written(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        report = export_notes(records, schema, tmp_path)
        note_files = list((tmp_path / "notes").iterdir())
        assert len(note_files) == report.exported_notes
        assert report.exported_notes > 0

    def test_all_notes_exported(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        report = export_notes(records, schema, tmp_path)
        assert report.total_notes == 6
        assert report.failed_notes == 0
        assert report.exported_notes == 6

    def test_markdown_files_have_md_extension(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path, output_format="md")
        for f in (tmp_path / "notes").iterdir():
            assert f.suffix == ".md"

    def test_txt_files_have_txt_extension(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path, output_format="txt")
        for f in (tmp_path / "notes").iterdir():
            assert f.suffix == ".txt"

    def test_markdown_content_has_heading(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path, output_format="md")
        for f in (tmp_path / "notes").iterdir():
            content = f.read_text(encoding="utf-8")
            assert content.startswith("#"), f"{f.name} does not start with a heading"

    def test_markdown_has_note_id_in_footer(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path, output_format="md")
        for f in (tmp_path / "notes").iterdir():
            content = f.read_text(encoding="utf-8")
            assert "note_id:" in content, f"{f.name} missing note_id footer"

    def test_folder_name_in_footer(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path, output_format="md")
        # At least two notes have folders ("Work", "Personal")
        contents = [f.read_text(encoding="utf-8") for f in (tmp_path / "notes").iterdir()]
        folder_lines = [line for c in contents for line in c.splitlines() if "folder:" in line]
        folder_names = {line.split("folder:")[-1].strip() for line in folder_lines}
        assert "Work" in folder_names
        assert "Personal" in folder_names

    def test_japanese_note_utf8(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path, output_format="md")
        # At least one file must contain the Japanese body text
        contents = [f.read_text(encoding="utf-8") for f in (tmp_path / "notes").iterdir()]
        assert any("りんご" in c for c in contents)

    def test_no_filename_collisions(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path)
        names = [f.name for f in (tmp_path / "notes").iterdir()]
        assert len(names) == len(set(names)), "Duplicate filenames detected"

    def test_export_log_json_valid(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path)
        log = json.loads((tmp_path / "reports" / "export_log.json").read_text(encoding="utf-8"))
        assert log["total_notes"] == 6
        assert log["schema_variant"] == SchemaVariant.VARIANT_A.value
        assert "export_started_at" in log
        assert "export_finished_at" in log

    def test_summary_txt_valid(self, variant_a_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        export_notes(records, schema, tmp_path)
        summary = (tmp_path / "reports" / "summary.txt").read_text(encoding="utf-8")
        assert "NoteVault Export Summary" in summary
        assert "Exported" in summary


# ---------------------------------------------------------------------------
# Variant B — full pipeline
# ---------------------------------------------------------------------------
class TestE2EVariantB:
    def test_all_notes_exported(self, variant_b_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_b_db)
        report = export_notes(records, schema, tmp_path)
        assert report.total_notes == 4
        assert report.failed_notes == 0
        assert report.exported_notes == 4

    def test_gzip_body_in_output(self, variant_b_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_b_db)
        export_notes(records, schema, tmp_path)
        contents = [f.read_text(encoding="utf-8") for f in (tmp_path / "notes").iterdir()]
        assert any("Apples" in c for c in contents)

    def test_note_without_body_still_written(self, variant_b_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_b_db)
        report = export_notes(records, schema, tmp_path)
        # UUID-B04 has no ZICNOTEDATA row — should be exported with placeholder
        assert report.exported_notes == 4

    def test_schema_variant_in_log(self, variant_b_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_b_db)
        export_notes(records, schema, tmp_path)
        log = json.loads((tmp_path / "reports" / "export_log.json").read_text(encoding="utf-8"))
        assert log["schema_variant"] == SchemaVariant.VARIANT_B.value

    def test_no_filename_collisions(self, variant_b_db: Path, tmp_path: Path) -> None:
        schema, records = extract_notes(variant_b_db)
        export_notes(records, schema, tmp_path)
        names = [f.name for f in (tmp_path / "notes").iterdir()]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Both formats work on the same DB
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["md", "txt"])
def test_format_produces_files(fmt: str, variant_a_db: Path, tmp_path: Path) -> None:
    schema, records = extract_notes(variant_a_db)
    report = export_notes(records, schema, tmp_path / fmt, output_format=fmt)
    assert report.exported_notes > 0
    for f in (tmp_path / fmt / "notes").iterdir():
        assert f.suffix == f".{fmt}"
        assert f.stat().st_size > 0
