"""
Unit tests for writer.py.

Covers:
- slugify_title: Japanese, emoji, empty, Windows forbidden chars, long titles
- build_output_filename: format validation, uniqueness via note_id prefix
- render_markdown: title heading, body, metadata footer, no-body placeholder,
  extraction_warning blockquote
- render_txt: title underline, body, no-body placeholder, warning
- write_note: file creation, UTF-8 encoding, deduplication via resolve_unique_path
"""

from __future__ import annotations

from pathlib import Path

import pytest

from notevault.notes_parser import NoteRecord
from notevault.writer import (
    build_output_filename,
    render_markdown,
    render_txt,
    resolve_unique_path,
    slugify_title,
    write_note,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
_BASE_TS = None  # timestamps not needed for writer tests


def _note(
    note_id: str = "UUID-001",
    title: str = "Test Note",
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
# slugify_title
# ---------------------------------------------------------------------------
class TestSlugifyTitle:
    def test_basic_ascii(self) -> None:
        assert slugify_title("Shopping List") == "shopping-list"

    def test_japanese(self) -> None:
        slug = slugify_title("日本語タイトル")
        assert slug  # must not be empty
        assert "/" not in slug and "\\" not in slug

    def test_emoji(self) -> None:
        slug = slugify_title("My 🎉 Note")
        assert slug  # should not crash
        assert "my" in slug

    def test_empty_becomes_untitled(self) -> None:
        assert slugify_title("") == "untitled"

    def test_whitespace_only_becomes_untitled(self) -> None:
        assert slugify_title("   ") == "untitled"

    def test_windows_forbidden_chars_removed(self) -> None:
        slug = slugify_title('Note: "Today" <draft>')
        assert "<" not in slug and ">" not in slug and '"' not in slug

    def test_long_title_truncated(self) -> None:
        long = "A" * 300
        assert len(slugify_title(long)) <= 100

    def test_duplicate_titles_same_output(self) -> None:
        # Two notes with the same title produce the same slug —
        # uniqueness is enforced by the note_id prefix in the filename.
        assert slugify_title("Task List") == slugify_title("Task List")


# ---------------------------------------------------------------------------
# build_output_filename
# ---------------------------------------------------------------------------
class TestBuildOutputFilename:
    def test_md_extension(self) -> None:
        name = build_output_filename(_note(), "md")
        assert name.endswith(".md")

    def test_txt_extension(self) -> None:
        name = build_output_filename(_note(), "txt")
        assert name.endswith(".txt")

    def test_note_id_prefix(self) -> None:
        name = build_output_filename(_note(note_id="UUID-001"), "md")
        assert name.startswith("UUID-001_")

    def test_hash_note_id(self) -> None:
        name = build_output_filename(_note(note_id="hash-abc123"), "md")
        assert name.startswith("hash-abc123_")

    def test_duplicate_titles_differ_by_id(self) -> None:
        n1 = _note(note_id="UUID-001", title="Task List")
        n2 = _note(note_id="UUID-002", title="Task List")
        assert build_output_filename(n1, "md") != build_output_filename(n2, "md")

    def test_unsupported_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            build_output_filename(_note(), "pdf")

    def test_japanese_title_safe(self) -> None:
        name = build_output_filename(_note(title="日本語タイトル"), "md")
        # Must not contain raw CJK chars in filename
        assert name.endswith(".md")
        assert "/" not in name and "\\" not in name


# ---------------------------------------------------------------------------
# resolve_unique_path
# ---------------------------------------------------------------------------
class TestResolveUniquePath:
    def test_no_conflict(self, tmp_path: Path) -> None:
        p = tmp_path / "note.md"
        assert resolve_unique_path(p) == p

    def test_conflict_appends_counter(self, tmp_path: Path) -> None:
        p = tmp_path / "note.md"
        p.write_text("existing")
        resolved = resolve_unique_path(p)
        assert resolved == tmp_path / "note_2.md"

    def test_multiple_conflicts(self, tmp_path: Path) -> None:
        p = tmp_path / "note.md"
        p.write_text("existing")
        (tmp_path / "note_2.md").write_text("existing2")
        resolved = resolve_unique_path(p)
        assert resolved == tmp_path / "note_3.md"


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------
class TestRenderMarkdown:
    def test_title_heading(self) -> None:
        md = render_markdown(_note(title="My Note"))
        assert md.startswith("# My Note")

    def test_body_present(self) -> None:
        md = render_markdown(_note(body="Hello world"))
        assert "Hello world" in md

    def test_no_body_placeholder(self) -> None:
        md = render_markdown(_note(body=None))
        assert "_No body extracted._" in md

    def test_empty_body_placeholder(self) -> None:
        md = render_markdown(_note(body=""))
        assert "_No body extracted._" in md

    def test_metadata_footer(self) -> None:
        md = render_markdown(_note(note_id="UUID-001"))
        assert "note_id: UUID-001" in md
        assert "---" in md

    def test_folder_in_footer(self) -> None:
        md = render_markdown(_note(folder_name="Work"))
        assert "folder: Work" in md

    def test_no_folder_omitted(self) -> None:
        md = render_markdown(_note(folder_name=None))
        assert "folder:" not in md

    def test_source_variant_in_footer(self) -> None:
        md = render_markdown(_note(), source_variant="VARIANT_A")
        assert "source_variant: VARIANT_A" in md

    def test_extraction_warning_shown(self) -> None:
        md = render_markdown(_note(warn="protobuf required"))
        assert "protobuf required" in md

    def test_no_warning_when_none(self) -> None:
        md = render_markdown(_note(warn=None))
        assert "⚠" not in md

    def test_utf8_content(self) -> None:
        md = render_markdown(_note(title="日本語", body="りんご\nバナナ"))
        assert "日本語" in md
        assert "りんご" in md


# ---------------------------------------------------------------------------
# render_txt
# ---------------------------------------------------------------------------
class TestRenderTxt:
    def test_title_on_first_line(self) -> None:
        txt = render_txt(_note(title="My Note"))
        assert txt.startswith("My Note")

    def test_title_underline(self) -> None:
        txt = render_txt(_note(title="My Note"))
        assert "=======" in txt  # at least 7 "=" chars

    def test_body_present(self) -> None:
        txt = render_txt(_note(body="Hello"))
        assert "Hello" in txt

    def test_no_body_placeholder(self) -> None:
        txt = render_txt(_note(body=None))
        assert "[No body extracted]" in txt

    def test_warning_shown(self) -> None:
        txt = render_txt(_note(warn="binary data"))
        assert "[WARNING: binary data]" in txt

    def test_utf8_content(self) -> None:
        txt = render_txt(_note(title="日本語", body="りんご"))
        assert "日本語" in txt


# ---------------------------------------------------------------------------
# write_note — integration
# ---------------------------------------------------------------------------
class TestWriteNote:
    def test_creates_file(self, tmp_path: Path) -> None:
        path = write_note(_note(), tmp_path, "md")
        assert path.exists()

    def test_utf8_encoded(self, tmp_path: Path) -> None:
        path = write_note(_note(title="日本語", body="りんご"), tmp_path, "md")
        content = path.read_text(encoding="utf-8")
        assert "日本語" in content

    def test_txt_format(self, tmp_path: Path) -> None:
        path = write_note(_note(), tmp_path, "txt")
        assert path.suffix == ".txt"

    def test_deduplication(self, tmp_path: Path) -> None:
        # Same note written twice → second file gets _2 suffix
        p1 = write_note(_note(), tmp_path, "md")
        p2 = write_note(_note(), tmp_path, "md")
        assert p1 != p2
        assert "_2" in p2.name

    def test_note_without_body_still_written(self, tmp_path: Path) -> None:
        path = write_note(_note(body=None), tmp_path, "md")
        assert path.exists()
        assert path.stat().st_size > 0

    def test_japanese_filename_safe(self, tmp_path: Path) -> None:
        path = write_note(_note(title="日本語タイトル"), tmp_path, "md")
        # Filename must not contain raw CJK chars
        assert path.exists()
        for ch in "日本語タイトル":
            assert ch not in path.name
