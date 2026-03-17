"""
Render NoteRecord objects to Markdown or plain-text files.

Responsibilities (single module):
- Title → safe filesystem slug
- NoteRecord → Markdown / TXT string
- Output filename construction
- Path deduplication (rare, but safe)

NOT responsible for: directory creation, error handling, or reporting.
Those live in exporter.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from slugify import slugify

from notevault.notes_parser import NoteRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_FORMATS = ("md", "txt")

# Windows forbids these chars in filenames (Path will accept them on Linux
# but we target Windows-safe output everywhere).
_WIN_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Maximum slug length (chars).  Combined with note_id prefix, total filename
# stays well under Windows' 255-char limit.
_MAX_SLUG_LEN = 100

# Placeholder body when extraction produced nothing
_NO_BODY_PLACEHOLDER = "_No body extracted._"


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------
def slugify_title(title: str) -> str:
    """
    Convert a note title to a lowercase, filesystem-safe ASCII slug.

    Uses python-slugify for Unicode normalisation, then truncates.
    Empty / whitespace-only input becomes "untitled".
    """
    if not title or not title.strip():
        return "untitled"
    slug = slugify(title, separator="-", max_length=_MAX_SLUG_LEN, word_boundary=True)
    # slugify returns "" for titles that contain only non-ASCII and no
    # transliteration is available (rare).  Fall back gracefully.
    return slug or "untitled"


def build_output_filename(note: NoteRecord, output_format: str) -> str:
    """
    Return a Windows-safe filename for *note*.

    Format: ``{note_id}_{slug}.{ext}``

    The note_id prefix guarantees uniqueness even when two notes share the
    same title (QandA #6).  The slug is truncated so the total length stays
    under 200 characters.
    """
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{output_format}'. Use: {SUPPORTED_FORMATS}")

    # Sanitise note_id for use in a filename (UUIDs contain hyphens — fine;
    # hash- prefix is also safe).
    safe_id = _WIN_FORBIDDEN.sub("_", note.note_id)
    slug = slugify_title(note.title)
    ext = output_format
    return f"{safe_id}_{slug}.{ext}"


def resolve_unique_path(target: Path) -> Path:
    """
    If *target* already exists, append ``_2``, ``_3`` … until the path is free.

    Collisions should be extremely rare (would require two notes with the same
    ZIDENTIFIER), but we guard against it rather than silently overwriting.
    """
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def render_markdown(note: NoteRecord, source_variant: str = "") -> str:
    """
    Render *note* as a Markdown string.

    Structure:
      # Title
      <blank line>
      body text  (or placeholder)
      <blank line>
      ---
      metadata footer
    """
    lines: list[str] = []

    # Title heading
    lines.append(f"# {note.title or 'Untitled'}")
    lines.append("")

    # Body
    body = (note.body_text or "").strip()
    if body:
        lines.append(body)
    else:
        lines.append(_NO_BODY_PLACEHOLDER)

    # Extraction warning (if any) — shown as a blockquote so it's visually
    # distinct but doesn't break the document structure.
    if note.extraction_warning:
        lines.append("")
        lines.append(f"> ⚠ {note.extraction_warning}")

    # Metadata footer
    lines.append("")
    lines.append("---")
    lines.append(f"note_id: {note.note_id}")
    if note.created_at:
        lines.append(f"created_at: {note.created_at.isoformat()}")
    if note.updated_at:
        lines.append(f"updated_at: {note.updated_at.isoformat()}")
    if note.folder_name:
        lines.append(f"folder: {note.folder_name}")
    if source_variant:
        lines.append(f"source_variant: {source_variant}")

    lines.append("")  # trailing newline
    return "\n".join(lines)


def render_txt(note: NoteRecord) -> str:
    """
    Render *note* as plain UTF-8 text.

    Minimal structure — title on the first line, body follows.
    """
    lines: list[str] = []

    title = note.title or "Untitled"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")

    body = (note.body_text or "").strip()
    if body:
        lines.append(body)
    else:
        lines.append("[No body extracted]")

    if note.extraction_warning:
        lines.append("")
        lines.append(f"[WARNING: {note.extraction_warning}]")

    lines.append("")  # trailing newline
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------
def write_note(
    note: NoteRecord,
    output_dir: Path,
    output_format: str,
    source_variant: str = "",
) -> Path:
    """
    Render *note* and write it to *output_dir*.

    Returns the resolved output path.
    Raises on I/O failure — the caller (exporter.py) decides whether to
    skip-and-continue or abort.
    """
    filename = build_output_filename(note, output_format)
    target = resolve_unique_path(output_dir / filename)

    if output_format == "md":
        content = render_markdown(note, source_variant=source_variant)
    else:
        content = render_txt(note)

    target.write_text(content, encoding="utf-8")
    return target
