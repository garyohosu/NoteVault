"""
Unit tests for notes_parser.py.

Covers:
- Schema variant detection (A and B)
- Folder hint annotation
- Note extraction with folder JOIN
- Duplicate titles, Japanese titles, missing body, no ZIDENTIFIER
- Orphaned folder FK (best-effort: folder_name=None, no crash)
- Gzip body decoding (Variant B)
- Missing ZICNOTEDATA row (body_text=None, no extraction_warning)
"""

from __future__ import annotations

from pathlib import Path

from notevault.notes_parser import (
    SchemaVariant,
    extract_notes,
    inspect_db,
)


# ---------------------------------------------------------------------------
# inspect_db — Variant A
# ---------------------------------------------------------------------------
class TestInspectVariantA:
    def test_variant_detected(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert schema.variant == SchemaVariant.VARIANT_A

    def test_note_table(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert schema.candidate_note_table == "ZNOTE"

    def test_id_columns(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert "ZIDENTIFIER" in schema.candidate_id_columns

    def test_title_columns(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert "ZTITLE" in schema.candidate_title_columns

    def test_date_columns(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert "ZCREATIONDATE" in schema.candidate_date_columns
        assert "ZMODIFICATIONDATE" in schema.candidate_date_columns

    def test_no_gzip(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert schema.requires_gzip_decode is False
        assert schema.may_require_protobuf is False

    def test_notes_count(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert schema.notes_count == 6

    def test_folder_table_detected(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert "ZFOLDER" in schema.candidate_folder_tables

    def test_folder_join_hint_present(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert len(schema.note_folder_join_hints) == 1
        hint = schema.note_folder_join_hints[0]
        assert hint["note_table"] == "ZNOTE"
        assert hint["folder_table"] == "ZFOLDER"
        assert hint["folder_name_col"] == "ZNAME"

    def test_no_warnings(self, variant_a_db: Path) -> None:
        schema = inspect_db(variant_a_db)
        assert schema.warnings == []


# ---------------------------------------------------------------------------
# inspect_db — Variant B
# ---------------------------------------------------------------------------
class TestInspectVariantB:
    def test_variant_detected(self, variant_b_db: Path) -> None:
        schema = inspect_db(variant_b_db)
        assert schema.variant == SchemaVariant.VARIANT_B

    def test_note_table(self, variant_b_db: Path) -> None:
        schema = inspect_db(variant_b_db)
        assert schema.candidate_note_table == "ZICCLOUDSYNCINGOBJECT"

    def test_gzip_required(self, variant_b_db: Path) -> None:
        schema = inspect_db(variant_b_db)
        assert schema.requires_gzip_decode is True

    def test_protobuf_not_needed(self, variant_b_db: Path) -> None:
        # Our mock ZDATA is plain gzip(UTF-8 text), so protobuf should be False
        schema = inspect_db(variant_b_db)
        assert schema.may_require_protobuf is False

    def test_folder_table_detected(self, variant_b_db: Path) -> None:
        schema = inspect_db(variant_b_db)
        assert "ZFOLDER" in schema.candidate_folder_tables

    def test_folder_join_hint(self, variant_b_db: Path) -> None:
        schema = inspect_db(variant_b_db)
        assert len(schema.note_folder_join_hints) >= 1
        hint = schema.note_folder_join_hints[0]
        assert hint["folder_table"] == "ZFOLDER"


# ---------------------------------------------------------------------------
# extract_notes — Variant A
# ---------------------------------------------------------------------------
class TestExtractVariantA:
    def _records_by_id(self, variant_a_db: Path) -> dict:
        _, records = extract_notes(variant_a_db)
        return {r.note_id: r for r in records}

    def test_count(self, variant_a_db: Path) -> None:
        _, records = extract_notes(variant_a_db)
        assert len(records) == 6

    def test_note_id_uses_zidentifier(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert "UUID-001" in by_id

    def test_note_id_hash_fallback(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        hash_notes = [r for nid, r in by_id.items() if nid.startswith("hash-")]
        assert len(hash_notes) == 1
        assert hash_notes[0].title == "Untitled"

    def test_folder_name_populated(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-001"].folder_name == "Work"
        assert by_id["UUID-002"].folder_name == "Personal"

    def test_no_folder_is_none(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-003"].folder_name is None

    def test_orphan_folder_fk_is_none(self, variant_a_db: Path) -> None:
        # Z_PK 99 doesn't exist in ZFOLDER — should be None, not a crash
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-006"].folder_name is None

    def test_duplicate_titles_different_folders(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-001"].folder_name == "Work"
        assert by_id["UUID-002"].folder_name == "Personal"
        assert by_id["UUID-001"].title == by_id["UUID-002"].title == "Task List"

    def test_japanese_title(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-003"].title == "日本語タイトル"

    def test_body_text_extracted(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert "Buy milk" in (by_id["UUID-001"].body_text or "")

    def test_missing_body_is_none(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-005"].body_text is None
        assert by_id["UUID-005"].extraction_warning is None

    def test_created_at_parsed(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-001"].created_at is not None
        assert by_id["UUID-001"].created_at.year >= 2020

    def test_z_pk_internal_only(self, variant_a_db: Path) -> None:
        by_id = self._records_by_id(variant_a_db)
        assert by_id["UUID-001"].z_pk == 1
        # z_pk is present but note_id is not z_pk
        assert by_id["UUID-001"].note_id != str(by_id["UUID-001"].z_pk)

    def test_no_crash_on_all_notes(self, variant_a_db: Path) -> None:
        schema, records = extract_notes(variant_a_db)
        assert schema.warnings == []
        assert len(records) == 6


# ---------------------------------------------------------------------------
# extract_notes — Variant B
# ---------------------------------------------------------------------------
class TestExtractVariantB:
    def _records_by_id(self, variant_b_db: Path) -> dict:
        _, records = extract_notes(variant_b_db)
        return {r.note_id: r for r in records}

    def test_count(self, variant_b_db: Path) -> None:
        _, records = extract_notes(variant_b_db)
        assert len(records) == 4

    def test_gzip_body_decoded(self, variant_b_db: Path) -> None:
        by_id = self._records_by_id(variant_b_db)
        assert "Apples" in (by_id["UUID-B01"].body_text or "")

    def test_missing_zicnotedata_body_is_none(self, variant_b_db: Path) -> None:
        by_id = self._records_by_id(variant_b_db)
        assert by_id["UUID-B04"].body_text is None
        # No extraction_warning expected when blob is simply absent
        assert by_id["UUID-B04"].extraction_warning is None

    def test_folder_name_populated(self, variant_b_db: Path) -> None:
        by_id = self._records_by_id(variant_b_db)
        assert by_id["UUID-B01"].folder_name == "iCloud"
        assert by_id["UUID-B02"].folder_name == "Work"

    def test_no_folder_is_none(self, variant_b_db: Path) -> None:
        by_id = self._records_by_id(variant_b_db)
        hash_notes = [r for nid, r in by_id.items() if nid.startswith("hash-")]
        assert hash_notes[0].folder_name is None

    def test_no_crash_on_all_notes(self, variant_b_db: Path) -> None:
        schema, records = extract_notes(variant_b_db)
        assert schema.warnings == []
        assert len(records) == 4
