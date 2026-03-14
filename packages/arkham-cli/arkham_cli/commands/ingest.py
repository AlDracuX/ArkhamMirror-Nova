"""File ingestion command."""

from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..client import APIError

console = Console()

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".eml",
    ".msg",
    ".docx",
    ".xlsx",
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".jpg",
    ".jpeg",
    ".png",
}


def discover_files(path: Path) -> list[Path]:
    """Recursively discover supported files under path."""
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [path]
        return []

    files: list[Path] = []
    for item in sorted(path.rglob("*")):
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(item)
    return files


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, help="List files without uploading")
@click.option("--delay", default=0.5, type=float, show_default=True, help="Seconds between uploads")
@click.pass_context
def ingest(ctx: click.Context, path: Path, dry_run: bool, delay: float) -> None:
    """Ingest documents from PATH into SHATTERED.

    PATH can be a single file or a directory (recursively scanned).
    """
    client = ctx.obj["client"]

    files = discover_files(path)
    if not files:
        console.print(f"[yellow]No supported files found in {path}[/]")
        console.print(f"[dim]Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}[/]")
        return

    console.print(f"[bold]Found {len(files)} file(s)[/]")

    if dry_run:
        for f in files:
            size_kb = f.stat().st_size / 1024
            console.print(f"  [cyan]{f.name}[/] [dim]({size_kb:.1f} KB) {f.suffix}[/]")
        console.print(f"\n[dim]Dry run: {len(files)} file(s) would be uploaded[/]")
        return

    success = 0
    failed = 0
    errors: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Uploading", total=len(files))

        for f in files:
            progress.update(task, description=f"Uploading {f.name}")
            try:
                result = client.upload(f)
                success += 1
                doc_id = result.get("id", result.get("document_id", ""))
                if doc_id:
                    console.print(f"  [green]OK[/] {f.name} -> {str(doc_id)[:12]}")
                else:
                    console.print(f"  [green]OK[/] {f.name}")
            except APIError as exc:
                failed += 1
                errors.append((f.name, str(exc)))
                console.print(f"  [red]FAIL[/] {f.name}: HTTP {exc.status_code}")
            except Exception as exc:
                failed += 1
                errors.append((f.name, str(exc)))
                console.print(f"  [red]FAIL[/] {f.name}: {exc}")

            progress.advance(task)
            if delay > 0 and f != files[-1]:
                time.sleep(delay)

    console.print()
    console.print(f"[bold green]{success} uploaded[/]  [bold red]{failed} failed[/]  of {len(files)} total")

    if errors:
        console.print("\n[bold red]Errors:[/]")
        for name, err in errors:
            console.print(f"  {name}: {err}")
