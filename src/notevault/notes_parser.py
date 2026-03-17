"""
Apple Notes database parser for NoteStore.sqlite.

Design philosophy (MVP-1):
- Detection before extraction: understand the schema variant before reading any note data
- Resilient: unknown schema variants are reported, not crashed on
- Protobuf is optional: attempt plain-text / gzip paths first
- note_id: ZIDENTIFIER (UUID) > stable-hash fallback; Z_PK is internal-only

Known schema families (from public Apple Notes forensics research):
  VARIANT_A  — Older format (pre-iOS 9 era).
               Tables: ZNOTE, ZNOTEBODY, ZFOLDER, ZATTACHMENT
               Body in ZNOTEBODY.ZCONTENT (plain text or HTML fragment)

  VARIANT_B  — Cloud-sync era (iOS 9–13).
               Tables: ZICCLOUDSYNCINGOBJECT, ZICNOTEDATA, ZFOLDER (may coexist)
               Body in ZICNOTEDATA.ZDATA (gzip-compressed blob)

  VARIANT_C  — Modern (iOS 14+).
               Same tables as B, but ZDATA may contain a protobuf envelope
               wrapping the gzip stream.

  UNKNOWN    — Tables do not match any recognised pattern.
               Inspection output is still emitted for manual review.
"""

from __future__ import annotations

import gzip
import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Apple Core Data epoch: 2001-01-01 00:00:00 UTC
# ---------------------------------------------------------------------------
_APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


def _apple_ts(seconds: float | None) -> datetime | None:
    """Convert a Core Data timestamp (float seconds since 2001-01-01) to UTC datetime."""
    if seconds is None:
        return None
    return _APPLE_EPOCH + __import__("datetime").timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Known table names per schema family
# ---------------------------------------------------------------------------
_VARIANT_A_TABLES = {"ZNOTE", "ZNOTEBODY"}
_VARIANT_B_TABLES = {"ZICCLOUDSYNCINGOBJECT", "ZICNOTEDATA"}

# Columns we look for in each candidate table
_CANDIDATE_ID_COLS = {"ZIDENTIFIER", "ZIDENTIFIER1", "ZUUID", "ZGUID"}
_CANDIDATE_TITLE_COLS = {"ZTITLE", "ZTITLE1", "ZNAME"}
_CANDIDATE_DATE_COLS = {
    "ZCREATIONDATE",
    "ZCREATIONDATE1",
    "ZMODIFICATIONDATE",
    "ZMODIFICATIONDATE1",
    "ZSERVERMODIFICATIONDATE",
}
_CANDIDATE_BODY_COLS = {"ZCONTENT", "ZBODY", "ZSNIPPET", "ZTEXT"}
_CANDIDATE_BLOB_COLS = {"ZDATA"}
_CANDIDATE_FOLDER_NAME_COLS = {"ZNAME", "ZTITLE", "ZTITLE1"}
# FK column names on the note table that point to a folder
_CANDIDATE_FOLDER_FK_COLS = {"ZFOLDER", "ZPARENTFOLDER", "ZPARENT"}

# Inspection SQL queries (also useful when run manually against a real DB)
INSPECTION_QUERIES: dict[str, str] = {
    "list_tables": "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;",
    "pragma_znote": "PRAGMA table_info(ZNOTE);",
    "pragma_znotebody": "PRAGMA table_info(ZNOTEBODY);",
    "pragma_zicnotedata": "PRAGMA table_info(ZICNOTEDATA);",
    "pragma_ziccloudsyncingobject": "PRAGMA table_info(ZICCLOUDSYNCINGOBJECT);",
    "pragma_zfolder": "PRAGMA table_info(ZFOLDER);",
    "pragma_zattachment": "PRAGMA table_info(ZATTACHMENT);",
    "sample_znote": "SELECT * FROM ZNOTE LIMIT 5;",
    "sample_znotebody": "SELECT * FROM ZNOTEBODY LIMIT 5;",
    "sample_zicnotedata": "SELECT Z_PK, length(ZDATA) AS data_len FROM ZICNOTEDATA LIMIT 5;",
    "sample_ziccloudsyncingobject": "SELECT * FROM ZICCLOUDSYNCINGOBJECT LIMIT 5;",
}


# ---------------------------------------------------------------------------
# Schema inspection result
# ---------------------------------------------------------------------------
class SchemaVariant(Enum):
    VARIANT_A = "VARIANT_A"  # ZNOTE + ZNOTEBODY (plain text / HTML)
    VARIANT_B = "VARIANT_B"  # ZICCLOUDSYNCINGOBJECT + ZICNOTEDATA (gzip blob)
    VARIANT_C = "VARIANT_C"  # As B, but ZDATA may wrap a protobuf envelope
    UNKNOWN = "UNKNOWN"


@dataclass
class ColumnInfo:
    name: str
    type: str
    notnull: bool
    pk: bool


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)

    @property
    def column_names(self) -> set[str]:
        return {c.name for c in self.columns}


@dataclass
class NoteStoreSchema:
    """Result of inspecting a NoteStore.sqlite file."""

    sqlite_path: Path
    all_tables: list[str] = field(default_factory=list)
    table_schemas: dict[str, TableSchema] = field(default_factory=dict)

    variant: SchemaVariant = SchemaVariant.UNKNOWN
    candidate_note_table: str | None = None
    candidate_id_columns: list[str] = field(default_factory=list)
    candidate_title_columns: list[str] = field(default_factory=list)
    candidate_date_columns: list[str] = field(default_factory=list)
    candidate_text_columns: list[str] = field(default_factory=list)
    candidate_blob_columns: list[str] = field(default_factory=list)

    requires_gzip_decode: bool = False
    may_require_protobuf: bool = False

    # Folder-related hints (populated by _annotate_folder_hints)
    candidate_folder_tables: list[str] = field(default_factory=list)
    candidate_folder_columns: dict[str, list[str]] = field(default_factory=dict)
    note_folder_join_hints: list[dict[str, str]] = field(default_factory=list)

    notes_count: int | None = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core inspection
# ---------------------------------------------------------------------------
def inspect_db(sqlite_path: Path) -> NoteStoreSchema:
    """
    Open *sqlite_path* read-only and return a NoteStoreSchema describing
    the schema variant, candidate columns, and decoding requirements.

    Never raises on schema surprises — unexpected findings go into
    schema.warnings so the caller can decide what to do.
    """
    schema = NoteStoreSchema(sqlite_path=sqlite_path)

    uri = sqlite_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row

        # 1. List all tables
        rows = conn.execute(INSPECTION_QUERIES["list_tables"]).fetchall()
        schema.all_tables = [r["name"] for r in rows]
        table_set = set(schema.all_tables)

        # 2. Collect PRAGMA table_info for known candidate tables
        candidates = [
            "ZNOTE",
            "ZNOTEBODY",
            "ZICNOTEDATA",
            "ZICCLOUDSYNCINGOBJECT",
            "ZFOLDER",
            "ZATTACHMENT",
        ]
        for tname in candidates:
            if tname in table_set:
                schema.table_schemas[tname] = _load_table_schema(conn, tname)

        # 3. Determine schema variant
        schema.variant = _detect_variant(table_set, schema.table_schemas)

        # 4. Identify candidate columns
        _annotate_candidates(schema)

        # 4b. Folder hints
        _annotate_folder_hints(schema)

        # 5. Count notes (best-effort)
        schema.notes_count = _count_notes(conn, schema)

        # 6. Check if ZDATA exists and probe gzip/protobuf
        if "ZICNOTEDATA" in schema.table_schemas:
            schema.requires_gzip_decode = True
            schema.may_require_protobuf = _probe_protobuf(conn, schema)

    return schema


def _load_table_schema(conn: sqlite3.Connection, table: str) -> TableSchema:
    ts = TableSchema(name=table)
    for row in conn.execute(f"PRAGMA table_info({table});"):
        ts.columns.append(
            ColumnInfo(
                name=row["name"],
                type=row["type"],
                notnull=bool(row["notnull"]),
                pk=bool(row["pk"]),
            )
        )
    return ts


def _detect_variant(table_set: set[str], schemas: dict[str, TableSchema]) -> SchemaVariant:
    has_b = _VARIANT_B_TABLES.issubset(table_set)
    has_a = _VARIANT_A_TABLES.issubset(table_set)

    if has_b:
        # Distinguish B vs C: iOS 14+ often has a Z_ENT type-discriminator
        # and ZICNOTEDATA.ZDATA tends to start with a protobuf magic byte
        # (we mark as C but confirm during _probe_protobuf)
        if "ZICCLOUDSYNCINGOBJECT" in schemas:
            cols = schemas["ZICCLOUDSYNCINGOBJECT"].column_names
            if "ZMERGEABLEDATA1" in cols or "ZMERGEABLEDATA" in cols:
                return SchemaVariant.VARIANT_C
        return SchemaVariant.VARIANT_B
    if has_a:
        return SchemaVariant.VARIANT_A
    return SchemaVariant.UNKNOWN


def _annotate_candidates(schema: NoteStoreSchema) -> None:
    """Fill candidate_* lists based on detected variant and available columns."""
    variant = schema.variant

    if variant in (SchemaVariant.VARIANT_B, SchemaVariant.VARIANT_C):
        note_table = "ZICCLOUDSYNCINGOBJECT"
    elif variant == SchemaVariant.VARIANT_A:
        note_table = "ZNOTE"
    else:
        # UNKNOWN: try any table that has PK-like columns
        note_table = schema.all_tables[0] if schema.all_tables else None

    schema.candidate_note_table = note_table

    if note_table and note_table in schema.table_schemas:
        cols = schema.table_schemas[note_table].column_names
        schema.candidate_id_columns = sorted(cols & _CANDIDATE_ID_COLS)
        schema.candidate_title_columns = sorted(cols & _CANDIDATE_TITLE_COLS)
        schema.candidate_date_columns = sorted(cols & _CANDIDATE_DATE_COLS)
        schema.candidate_text_columns = sorted(cols & _CANDIDATE_BODY_COLS)
        schema.candidate_blob_columns = sorted(cols & _CANDIDATE_BLOB_COLS)

    # ZDATA lives in ZICNOTEDATA, not the note table — add separately
    if "ZICNOTEDATA" in schema.table_schemas:
        data_cols = schema.table_schemas["ZICNOTEDATA"].column_names & _CANDIDATE_BLOB_COLS
        for c in sorted(data_cols):
            if c not in schema.candidate_blob_columns:
                schema.candidate_blob_columns.append(c)


def _annotate_folder_hints(schema: NoteStoreSchema) -> None:
    """
    Detect how notes relate to folder names and populate folder hint fields.

    Three scenarios handled:
      1. Standalone ZFOLDER table — most common in both Variant A and B
      2. Variant B/C self-join — folders are rows in ZICCLOUDSYNCINGOBJECT
         distinguished by having no matching ZICNOTEDATA row
      3. No folder info found — hints are left empty (best-effort, not fatal)
    """
    # --- Scenario 1: explicit ZFOLDER table ---
    if "ZFOLDER" in schema.table_schemas:
        ts = schema.table_schemas["ZFOLDER"]
        name_cols = sorted(ts.column_names & _CANDIDATE_FOLDER_NAME_COLS)
        schema.candidate_folder_tables.append("ZFOLDER")
        schema.candidate_folder_columns["ZFOLDER"] = name_cols

        # Find which FK column the note table uses to point at ZFOLDER
        note_table = schema.candidate_note_table
        if note_table and note_table in schema.table_schemas:
            note_cols = schema.table_schemas[note_table].column_names
            fk_cols = sorted(note_cols & _CANDIDATE_FOLDER_FK_COLS)
            name_col = name_cols[0] if name_cols else None
            if fk_cols and name_col:
                schema.note_folder_join_hints.append(
                    {
                        "note_table": note_table,
                        "note_fk_col": fk_cols[0],
                        "folder_table": "ZFOLDER",
                        "folder_pk_col": "Z_PK",
                        "folder_name_col": name_col,
                    }
                )
        return

    # --- Scenario 2: Variant B/C folders embedded in ZICCLOUDSYNCINGOBJECT ---
    if "ZICCLOUDSYNCINGOBJECT" in schema.table_schemas:
        ts = schema.table_schemas["ZICCLOUDSYNCINGOBJECT"]
        note_cols = ts.column_names
        fk_cols = sorted(note_cols & _CANDIDATE_FOLDER_FK_COLS)
        name_cols = sorted(note_cols & _CANDIDATE_FOLDER_NAME_COLS)
        if fk_cols and name_cols:
            schema.candidate_folder_tables.append("ZICCLOUDSYNCINGOBJECT")
            schema.candidate_folder_columns["ZICCLOUDSYNCINGOBJECT"] = name_cols
            schema.note_folder_join_hints.append(
                {
                    "note_table": "ZICCLOUDSYNCINGOBJECT",
                    "note_fk_col": fk_cols[0],
                    "folder_table": "ZICCLOUDSYNCINGOBJECT",
                    "folder_pk_col": "Z_PK",
                    "folder_name_col": name_cols[0],
                    "hint": "self-join: folder rows share the same table as notes",
                }
            )


def _build_folder_map(conn: sqlite3.Connection, schema: NoteStoreSchema) -> dict[int, str]:
    """
    Return {Z_PK: folder_name} for all rows in the detected folder table.

    Returns an empty dict if no folder info is available — callers treat
    missing folder as None, not as an error.
    """
    if not schema.note_folder_join_hints:
        return {}

    hint = schema.note_folder_join_hints[0]
    folder_table = hint["folder_table"]
    pk_col = hint["folder_pk_col"]
    name_col = hint["folder_name_col"]
    is_self_join = hint.get("hint", "").startswith("self-join")

    try:
        if is_self_join:
            # Folders in ZICCLOUDSYNCINGOBJECT: rows that have a name but no
            # corresponding ZICNOTEDATA entry are treated as folders.
            sql = f"""
                SELECT o.{pk_col}, o.{name_col}
                FROM {folder_table} o
                LEFT JOIN ZICNOTEDATA d ON d.ZNOTE = o.{pk_col}
                WHERE o.{name_col} IS NOT NULL AND d.Z_PK IS NULL
            """  # noqa: S608
        else:
            sql = f"SELECT {pk_col}, {name_col} FROM {folder_table} WHERE {name_col} IS NOT NULL;"  # noqa: S608
        rows = conn.execute(sql).fetchall()
        return {row[0]: row[1] for row in rows}
    except sqlite3.Error:
        return {}


def _count_notes(conn: sqlite3.Connection, schema: NoteStoreSchema) -> int | None:
    tbl = schema.candidate_note_table
    if not tbl:
        return None
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()  # noqa: S608
        return row[0]
    except sqlite3.Error:
        return None


def _probe_protobuf(conn: sqlite3.Connection, schema: NoteStoreSchema) -> bool:
    """
    Heuristic: read one ZDATA blob, decompress if gzip, check if the result
    starts with a protobuf field tag byte (0x08 or 0x12 are common for Note).

    Returns True if protobuf decoding is likely required, False if plain
    text / HTML appears accessible after gzip.
    """
    try:
        sql = "SELECT ZDATA FROM ZICNOTEDATA WHERE ZDATA IS NOT NULL LIMIT 1;"  # noqa: S608
        row = conn.execute(sql).fetchone()
        if row is None:
            return False
        blob: bytes = row[0]

        # Try gzip decompression
        try:
            decompressed = gzip.decompress(blob)
        except (OSError, EOFError):
            decompressed = blob  # not gzip — treat as raw

        # Protobuf heuristic: starts with a valid field tag byte and
        # does NOT look like readable text or XML
        first_byte = decompressed[0] if decompressed else 0x00
        looks_like_protobuf = first_byte in (0x08, 0x0A, 0x10, 0x12, 0x1A, 0x22)
        looks_like_text = decompressed[:5] in (b"<?xml", b"<html", b"<note") or (
            decompressed[:1].isascii() and not looks_like_protobuf
        )
        return looks_like_protobuf and not looks_like_text

    except sqlite3.Error:
        return False


# ---------------------------------------------------------------------------
# Note record
# ---------------------------------------------------------------------------
@dataclass
class NoteRecord:
    """Parsed representation of a single Apple Note."""

    note_id: str  # ZIDENTIFIER if available, else stable hash
    z_pk: int | None  # Internal DB key — do NOT use as external ID
    title: str
    created_at: datetime | None
    updated_at: datetime | None
    folder_name: str | None
    body_text: str | None  # Plain text extracted from note (may be None if Protobuf required)
    source_table: str
    extraction_warning: str | None = None


def _stable_hash(title: str, created: datetime | None, updated: datetime | None) -> str:
    raw = f"{title}|{created}|{updated}"
    return "hash-" + hashlib.sha1(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Extraction (MVP-1: detection-first, text-only)
# ---------------------------------------------------------------------------
def extract_notes(sqlite_path: Path) -> tuple[NoteStoreSchema, list[NoteRecord]]:
    """
    Inspect the DB, then attempt to extract notes using the detected schema.

    Returns the schema inspection result alongside extracted NoteRecord list.
    Notes that cannot be decoded are included with body_text=None and a warning.
    """
    schema = inspect_db(sqlite_path)
    records: list[NoteRecord] = []

    uri = sqlite_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row

        folder_map = _build_folder_map(conn, schema)

        if schema.variant == SchemaVariant.VARIANT_A:
            records = _extract_variant_a(conn, schema, folder_map)
        elif schema.variant in (SchemaVariant.VARIANT_B, SchemaVariant.VARIANT_C):
            records = _extract_variant_bc(conn, schema, folder_map)
        else:
            schema.warnings.append(
                f"Unknown schema variant — tables: {schema.all_tables}. "
                "Run 'notevault inspect-db' for manual investigation."
            )

    return schema, records


def _extract_variant_a(
    conn: sqlite3.Connection,
    schema: NoteStoreSchema,
    folder_map: dict[int, str],
) -> list[NoteRecord]:
    """ZNOTE + ZNOTEBODY path (plain text / HTML body)."""
    records: list[NoteRecord] = []

    id_col = _first_match(schema.candidate_id_columns, ("ZIDENTIFIER",))
    title_col = _first_match(schema.candidate_title_columns, ("ZTITLE",))
    created_col = _first_match(schema.candidate_date_columns, ("ZCREATIONDATE",))
    updated_col = _first_match(schema.candidate_date_columns, ("ZMODIFICATIONDATE",))

    # Include the folder FK column if present
    note_cols = schema.table_schemas.get("ZNOTE", TableSchema(name="ZNOTE")).column_names
    folder_fk = _first_match(
        sorted(note_cols & _CANDIDATE_FOLDER_FK_COLS), ("ZFOLDER", "ZPARENTFOLDER")
    )
    folder_expr = f"n.{folder_fk}" if folder_fk else "NULL"

    sql = f"""
        SELECT
            n.Z_PK,
            {f"n.{id_col}" if id_col else "NULL"} AS zidentifier,
            {f"n.{title_col}" if title_col else "NULL"} AS title,
            {f"n.{created_col}" if created_col else "NULL"} AS created,
            {f"n.{updated_col}" if updated_col else "NULL"} AS updated,
            {folder_expr} AS folder_pk,
            b.ZCONTENT AS body
        FROM ZNOTE n
        LEFT JOIN ZNOTEBODY b ON b.ZNOTE = n.Z_PK
    """  # noqa: S608
    for row in conn.execute(sql):
        zid = row["zidentifier"]
        title = row["title"] or ""
        created = _apple_ts(row["created"])
        updated = _apple_ts(row["updated"])
        note_id = zid if zid else _stable_hash(title, created, updated)

        records.append(
            NoteRecord(
                note_id=note_id,
                z_pk=row["Z_PK"],
                title=title,
                created_at=created,
                updated_at=updated,
                folder_name=folder_map.get(row["folder_pk"]) if row["folder_pk"] else None,
                body_text=row["body"],
                source_table="ZNOTE",
            )
        )
    return records


def _extract_variant_bc(
    conn: sqlite3.Connection,
    schema: NoteStoreSchema,
    folder_map: dict[int, str],
) -> list[NoteRecord]:
    """ZICCLOUDSYNCINGOBJECT + ZICNOTEDATA path (gzip blob, possible protobuf)."""
    records: list[NoteRecord] = []

    # Identify title / date columns (may be ZTITLE1, ZCREATIONDATE1, etc.)
    title_col = _first_match(schema.candidate_title_columns, ("ZTITLE1", "ZTITLE"))
    created_col = _first_match(schema.candidate_date_columns, ("ZCREATIONDATE1", "ZCREATIONDATE"))
    updated_col = _first_match(
        schema.candidate_date_columns, ("ZMODIFICATIONDATE1", "ZMODIFICATIONDATE")
    )
    id_col = _first_match(schema.candidate_id_columns, ("ZIDENTIFIER",))

    # Folder FK column on the note row
    note_cols = schema.table_schemas.get(
        "ZICCLOUDSYNCINGOBJECT", TableSchema(name="ZICCLOUDSYNCINGOBJECT")
    ).column_names
    folder_fk = _first_match(
        sorted(note_cols & _CANDIDATE_FOLDER_FK_COLS), ("ZFOLDER", "ZPARENTFOLDER")
    )

    title_expr = f"n.{title_col}" if title_col else "NULL"
    created_expr = f"n.{created_col}" if created_col else "NULL"
    updated_expr = f"n.{updated_col}" if updated_col else "NULL"
    id_expr = f"n.{id_col}" if id_col else "NULL"
    folder_expr = f"n.{folder_fk}" if folder_fk else "NULL"

    sql = f"""
        SELECT
            n.Z_PK,
            {id_expr} AS zidentifier,
            {title_expr} AS title,
            {created_expr} AS created,
            {updated_expr} AS updated,
            {folder_expr} AS folder_pk,
            d.ZDATA AS blob_data
        FROM ZICCLOUDSYNCINGOBJECT n
        LEFT JOIN ZICNOTEDATA d ON d.ZNOTE = n.Z_PK
        WHERE {title_expr} IS NOT NULL
    """  # noqa: S608
    for row in conn.execute(sql):
        zid = row["zidentifier"]
        title = row["title"] or ""
        created = _apple_ts(row["created"])
        updated = _apple_ts(row["updated"])
        note_id = zid if zid else _stable_hash(title, created, updated)

        body_text, warn = _decode_body(row["blob_data"], schema.may_require_protobuf)

        records.append(
            NoteRecord(
                note_id=note_id,
                z_pk=row["Z_PK"],
                title=title,
                created_at=created,
                updated_at=updated,
                folder_name=folder_map.get(row["folder_pk"]) if row["folder_pk"] else None,
                body_text=body_text,
                source_table="ZICCLOUDSYNCINGOBJECT",
                extraction_warning=warn,
            )
        )
    return records


def _decode_body(blob: bytes | None, may_require_protobuf: bool) -> tuple[str | None, str | None]:
    """
    Attempt to decode a ZDATA blob into plain text.

    Returns (text_or_None, warning_or_None).
    Does NOT raise — all failures become warnings so the caller can skip-and-continue.
    """
    if blob is None:
        return None, None

    # Step 1: try gzip decompression
    try:
        data = gzip.decompress(blob)
    except (OSError, EOFError):
        data = blob  # not gzip; treat as raw

    # Step 2: try decoding as UTF-8 text / XML
    try:
        text = data.decode("utf-8")
        return text, None
    except UnicodeDecodeError:
        pass

    # Step 3: if protobuf is suspected, mark as pending — not failing
    if may_require_protobuf:
        return None, "body requires protobuf decoding (not yet implemented)"

    return None, f"body is binary ({len(data)} bytes), encoding unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _first_match(candidates: list[str], preferred_order: tuple[str, ...]) -> str | None:
    """Return the first name from preferred_order that appears in candidates."""
    for name in preferred_order:
        if name in candidates:
            return name
    return candidates[0] if candidates else None
