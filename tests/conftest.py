"""
Pytest fixtures: in-memory-equivalent SQLite databases for Variant A and B.

Files are written to a tmp_path so each test run gets a clean slate.
The Apple Core Data epoch offset (seconds since 2001-01-01) is used for
all date values to match what a real NoteStore.sqlite would contain.
"""

from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest

# A few fixed Core Data timestamps (seconds since 2001-01-01 UTC)
_TS_BASE = 700_000_000.0  # ~2023-03-02
_TS_LATER = 700_086_400.0  # +1 day


# ---------------------------------------------------------------------------
# Variant A  — ZNOTE + ZNOTEBODY + ZFOLDER
# ---------------------------------------------------------------------------
def _build_variant_a(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ZFOLDER (
            Z_PK   INTEGER PRIMARY KEY,
            ZNAME  TEXT,
            ZPARENT INTEGER
        );
        CREATE TABLE ZNOTE (
            Z_PK              INTEGER PRIMARY KEY,
            ZIDENTIFIER       TEXT,
            ZTITLE            TEXT,
            ZCREATIONDATE     REAL,
            ZMODIFICATIONDATE REAL,
            ZFOLDER           INTEGER
        );
        CREATE TABLE ZNOTEBODY (
            Z_PK    INTEGER PRIMARY KEY,
            ZNOTE   INTEGER,
            ZCONTENT TEXT
        );

        -- Folders
        INSERT INTO ZFOLDER VALUES (1, 'Work',     NULL);
        INSERT INTO ZFOLDER VALUES (2, 'Personal', NULL);

        -- Notes
        -- 1: normal note in Work folder
        INSERT INTO ZNOTE VALUES (1,'UUID-001','Task List',      700000000,700086400,1);
        -- 2: duplicate title in Personal folder
        INSERT INTO ZNOTE VALUES (2,'UUID-002','Task List',      700000001,700086401,2);
        -- 3: Japanese title, no folder
        INSERT INTO ZNOTE VALUES (3,'UUID-003','日本語タイトル', 700000002,700086402,NULL);
        -- 4: no ZIDENTIFIER (triggers stable-hash fallback)
        INSERT INTO ZNOTE VALUES (4,NULL,      'Untitled',       700000003,700086403,1);
        -- 5: no body (ZNOTEBODY row missing)
        INSERT INTO ZNOTE VALUES (5,'UUID-005','No Body Note',   700000004,700086404,2);
        -- 6: broken ZFOLDER FK (folder Z_PK 99 does not exist)
        INSERT INTO ZNOTE VALUES (6,'UUID-006','Orphan Note',    700000005,700086405,99);

        -- Bodies (note 5 intentionally omitted)
        INSERT INTO ZNOTEBODY VALUES (1,1,'Buy milk\nBuy eggs');
        INSERT INTO ZNOTEBODY VALUES (2,2,'Meeting agenda');
        INSERT INTO ZNOTEBODY VALUES (3,3,'りんご\nバナナ');
        INSERT INTO ZNOTEBODY VALUES (4,4,'Some content');
        INSERT INTO ZNOTEBODY VALUES (6,6,'Orphan body');
    """)
    conn.close()


@pytest.fixture()
def variant_a_db(tmp_path: Path) -> Path:
    """Path to a minimal Variant A NoteStore.sqlite."""
    p = tmp_path / "variant_a.sqlite"
    _build_variant_a(p)
    return p


# ---------------------------------------------------------------------------
# Variant B  — ZICCLOUDSYNCINGOBJECT + ZICNOTEDATA + ZFOLDER
# ---------------------------------------------------------------------------
def _gzip_text(text: str) -> bytes:
    return gzip.compress(text.encode("utf-8"))


def _build_variant_b(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ZFOLDER (
            Z_PK   INTEGER PRIMARY KEY,
            ZNAME  TEXT,
            ZPARENT INTEGER
        );
        CREATE TABLE ZICCLOUDSYNCINGOBJECT (
            Z_PK              INTEGER PRIMARY KEY,
            ZIDENTIFIER       TEXT,
            ZTITLE1           TEXT,
            ZCREATIONDATE1    REAL,
            ZMODIFICATIONDATE1 REAL,
            ZFOLDER           INTEGER
        );
        CREATE TABLE ZICNOTEDATA (
            Z_PK   INTEGER PRIMARY KEY,
            ZNOTE  INTEGER,
            ZDATA  BLOB
        );

        -- Folders
        INSERT INTO ZFOLDER VALUES (10, 'iCloud', NULL);
        INSERT INTO ZFOLDER VALUES (11, 'Work',   10);

        -- Notes (ZICCLOUDSYNCINGOBJECT)
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES
            (1,'UUID-B01','Shopping List',700000000,700086400,10);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES
            (2,'UUID-B02','Meeting Notes',700000001,700086401,11);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES
            (3,NULL,      'Untitled',     700000002,700086402,NULL);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES
            (4,'UUID-B04','Empty Note',   700000003,700086403,10);
    """)
    # Insert ZDATA as gzip-compressed blobs (must use parameterised query for BLOB)
    note_bodies = {
        1: _gzip_text("Apples\nBananas\nOranges"),
        2: _gzip_text("Agenda item 1\nAgenda item 2"),
        3: _gzip_text("Hello world"),
        # note 4 intentionally has no ZICNOTEDATA row
    }
    for note_pk, blob in note_bodies.items():
        conn.execute(
            "INSERT INTO ZICNOTEDATA (ZNOTE, ZDATA) VALUES (?, ?);",
            (note_pk, blob),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def variant_b_db(tmp_path: Path) -> Path:
    """Path to a minimal Variant B NoteStore.sqlite with gzip-compressed bodies."""
    p = tmp_path / "variant_b.sqlite"
    _build_variant_b(p)
    return p
