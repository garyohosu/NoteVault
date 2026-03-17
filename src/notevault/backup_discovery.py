"""
Discover and validate local iPhone backups (iTunes/Finder format).

MVP-1 scope:
- Auto-detect standard Windows backup paths
- Allow manual path override
- Validate backup structure (unencrypted, expected files present)
- Return a list of BackupInfo dataclasses
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Standard Windows iTunes/Finder backup locations
_CANDIDATE_ROOTS: list[str] = [
    os.path.join(os.environ.get("APPDATA", ""), "Apple Computer", "MobileSync", "Backup"),
    os.path.join(os.environ.get("USERPROFILE", ""), "Apple", "MobileSync", "Backup"),
]

# Files that must exist inside a valid backup folder
_REQUIRED_FILES = ["Info.plist", "Manifest.plist", "Manifest.db"]


@dataclass
class BackupInfo:
    """Represents one discovered iPhone backup."""

    backup_id: str  # UUID folder name
    path: Path  # Absolute path to the backup folder
    device_name: str = "Unknown"
    last_backup_date: datetime | None = None
    is_encrypted: bool = False
    is_valid: bool = False
    validation_error: str | None = None
    extra: dict = field(default_factory=dict)  # Reserved for future metadata


def find_backup_roots() -> list[Path]:
    """Return candidate root directories that exist on this machine."""
    roots: list[Path] = []
    for raw in _CANDIDATE_ROOTS:
        p = Path(raw)
        if p.is_dir():
            roots.append(p)
    return roots


def discover_backups(manual_root: Path | None = None) -> list[BackupInfo]:
    """
    Scan for available backups.

    Args:
        manual_root: If provided, scan only this directory instead of
                     auto-detected paths.  Accepts either the UUID backup
                     folder itself or its parent directory.

    Returns:
        List of BackupInfo objects, sorted by last_backup_date descending
        (most recent first).  Empty list if nothing is found.
    """
    roots: list[Path] = []

    if manual_root is not None:
        manual_root = Path(manual_root).resolve()
        # Accept both the UUID folder itself and its parent
        if _looks_like_backup_folder(manual_root):
            roots = [manual_root.parent]
        else:
            roots = [manual_root]
    else:
        roots = find_backup_roots()

    backups: list[BackupInfo] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir():
                info = _inspect_backup_folder(child)
                if info is not None:
                    backups.append(info)

    backups.sort(key=lambda b: b.last_backup_date or datetime.min, reverse=True)
    return backups


def _looks_like_backup_folder(path: Path) -> bool:
    """Heuristic: does this path look like a UUID backup folder?"""
    return len(path.name) == 40 and all(c in "0123456789abcdefABCDEF-" for c in path.name)


def _inspect_backup_folder(path: Path) -> BackupInfo | None:
    """
    Inspect a single directory and return a BackupInfo if it looks like
    an iPhone backup, or None if it should be ignored entirely.
    """
    # Quick structural check — skip clearly unrelated directories
    if not any((path / f).exists() for f in _REQUIRED_FILES):
        return None

    info = BackupInfo(backup_id=path.name, path=path)

    # Validate that all required files are present
    missing = [f for f in _REQUIRED_FILES if not (path / f).exists()]
    if missing:
        info.is_valid = False
        info.validation_error = f"Missing required files: {', '.join(missing)}"
        return info

    # Read Manifest.plist for device metadata and encryption status
    _parse_manifest_plist(path, info)

    info.is_valid = not info.is_encrypted and info.validation_error is None
    return info


def _parse_manifest_plist(path: Path, info: BackupInfo) -> None:
    """
    Extract device_name, last_backup_date, and is_encrypted from
    Manifest.plist.  Silently records any parse errors in info.validation_error
    rather than raising, to keep discover_backups() resilient.

    NOTE: Full plist parsing (binary/XML) requires the `plistlib` stdlib module.
    This skeleton only reads Info.plist JSON fallback if present; full plist
    support will be added when backup_parser.py is implemented.
    """
    # TODO: implement plistlib-based parsing of Manifest.plist
    # Placeholder: attempt to read Info.plist as JSON for dev/testing convenience
    info_plist = path / "Info.plist"
    try:
        import plistlib

        with open(info_plist, "rb") as fh:
            data = plistlib.load(fh)
        info.device_name = data.get("Device Name", "Unknown")
        raw_date = data.get("Last Backup Date")
        if isinstance(raw_date, datetime):
            info.last_backup_date = raw_date

        # Check encryption flag in Manifest.plist
        manifest_plist = path / "Manifest.plist"
        with open(manifest_plist, "rb") as fh:
            manifest = plistlib.load(fh)
        info.is_encrypted = bool(manifest.get("IsEncrypted", False))

    except Exception as exc:  # noqa: BLE001
        info.validation_error = f"plist parse error: {exc}"
