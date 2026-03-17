import json
from pathlib import Path

import typer

from notevault.backup_discovery import discover_backups
from notevault.exporter import ExportError, run_export
from notevault.notes_parser import inspect_db

app = typer.Typer(
    help="NoteVault: Bulk export Apple Notes from iPhone backups locally.",
    add_completion=False,
)


@app.command()
def list_backups(
    search_path: Path | None = typer.Option(None, "--path", "-p", help="Manual backup root path."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """List available local iPhone backups."""
    typer.echo("Searching for local backups...", err=True)
    backups = discover_backups(manual_root=search_path)

    if not backups:
        typer.echo("No backups found.", err=True)
        raise typer.Exit(code=0)

    if as_json:
        output = [
            {
                "backup_id": b.backup_id,
                "path": str(b.path),
                "device_name": b.device_name,
                "last_backup_date": b.last_backup_date.isoformat() if b.last_backup_date else None,
                "is_encrypted": b.is_encrypted,
                "is_valid": b.is_valid,
                "validation_error": b.validation_error,
            }
            for b in backups
        ]
        typer.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for b in backups:
            status = "OK" if b.is_valid else ("ENCRYPTED" if b.is_encrypted else "INVALID")
            date_str = (
                b.last_backup_date.strftime("%Y-%m-%d %H:%M") if b.last_backup_date else "Unknown"
            )
            typer.echo(f"[{status}] {b.device_name}  {date_str}  {b.path}")


@app.command()
def export(
    backup_path: Path = typer.Option(..., "--backup", "-b", help="Path to iPhone backup folder."),
    output_dir: Path = typer.Option(
        Path("./export"), "--output", "-o", help="Directory to save exported notes."
    ),
    output_format: str = typer.Option("md", "--format", "-f", help="Output format: md or txt."),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Abort on first note failure."),
):
    """Export Apple Notes from a backup to Markdown or TXT files."""
    typer.echo(f"Source  : {backup_path}", err=True)
    typer.echo(f"Output  : {output_dir}", err=True)
    typer.echo(f"Format  : {output_format}", err=True)

    try:
        report = run_export(
            source=backup_path,
            output_dir=output_dir,
            output_format=output_format,
            fail_fast=fail_fast,
        )
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except ExportError as exc:
        typer.echo(f"Aborted (--fail-fast): {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Done. Exported {report.exported_notes}/{report.total_notes} notes "
        f"to {output_dir / 'notes'}",
    )
    if report.failed_notes:
        typer.echo(f"  {report.failed_notes} failed — see {output_dir / 'reports'}", err=True)
    if report.warnings:
        typer.echo(f"  {len(report.warnings)} warnings — see export_log.json", err=True)


@app.command(name="inspect-db")
def inspect_db_cmd(
    sqlite_path: Path = typer.Option(..., "--sqlite", "-s", help="Path to NoteStore.sqlite."),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """Inspect a NoteStore.sqlite and report its schema variant and candidate columns."""
    if not sqlite_path.exists():
        typer.echo(f"Error: file not found: {sqlite_path}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Inspecting: {sqlite_path}", err=True)
    schema = inspect_db(sqlite_path)

    if as_json:
        out = {
            "sqlite_path": str(schema.sqlite_path),
            "variant": schema.variant.value,
            "all_tables": schema.all_tables,
            "candidate_note_table": schema.candidate_note_table,
            "candidate_id_columns": schema.candidate_id_columns,
            "candidate_title_columns": schema.candidate_title_columns,
            "candidate_date_columns": schema.candidate_date_columns,
            "candidate_text_columns": schema.candidate_text_columns,
            "candidate_blob_columns": schema.candidate_blob_columns,
            "requires_gzip_decode": schema.requires_gzip_decode,
            "may_require_protobuf": schema.may_require_protobuf,
            "candidate_folder_tables": schema.candidate_folder_tables,
            "candidate_folder_columns": schema.candidate_folder_columns,
            "note_folder_join_hints": schema.note_folder_join_hints,
            "notes_count": schema.notes_count,
            "warnings": schema.warnings,
            "table_schemas": {
                tname: [
                    {"name": c.name, "type": c.type, "notnull": c.notnull, "pk": c.pk}
                    for c in ts.columns
                ]
                for tname, ts in schema.table_schemas.items()
            },
        }
        typer.echo(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"Variant          : {schema.variant.value}")
        typer.echo(f"Tables           : {', '.join(schema.all_tables)}")
        typer.echo(f"Note table       : {schema.candidate_note_table or 'unknown'}")
        typer.echo(f"ID columns       : {schema.candidate_id_columns or '—'}")
        typer.echo(f"Title columns    : {schema.candidate_title_columns or '—'}")
        typer.echo(f"Date columns     : {schema.candidate_date_columns or '—'}")
        typer.echo(f"Text columns     : {schema.candidate_text_columns or '—'}")
        typer.echo(f"Blob columns     : {schema.candidate_blob_columns or '—'}")
        typer.echo(f"Folder tables    : {schema.candidate_folder_tables or '—'}")
        typer.echo(f"Folder join hints: {len(schema.note_folder_join_hints)} found")
        typer.echo(f"Requires gzip    : {schema.requires_gzip_decode}")
        typer.echo(f"May need protobuf: {schema.may_require_protobuf}")
        count = schema.notes_count if schema.notes_count is not None else "—"
        typer.echo(f"Notes count      : {count}")
        if schema.warnings:
            for w in schema.warnings:
                typer.echo(f"[WARN] {w}", err=True)


if __name__ == "__main__":
    app()
