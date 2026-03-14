"""Validation command -- Phase 4 workflow."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..client import ShatteredClient

console = Console()

# Comparison pairs: (description, vault glob pattern, API fetch method name, API kwargs builder)
COMPARISON_PAIRS = [
    {
        "name": "Disclosure Schedule",
        "vault_pattern": "disclosure*",
        "description": "Disclosure schedule vs vault disclosure documents",
    },
    {
        "name": "Bundle Index",
        "vault_pattern": "bundle*",
        "description": "Bundle index vs vault bundle documents",
    },
    {
        "name": "Costs Application",
        "vault_pattern": "cost*",
        "description": "Costs application vs vault costs documents",
    },
    {
        "name": "Cross-Examination Notes",
        "vault_pattern": "cross*exam*",
        "description": "Cross-exam notes vs vault cross-exam documents",
    },
    {
        "name": "Skeleton Arguments",
        "vault_pattern": "skeleton*",
        "description": "Skeleton arguments vs vault skeleton documents",
    },
    {
        "name": "Respondent Intel",
        "vault_pattern": "cast*",
        "description": "Respondent intel vs vault cast of characters",
    },
    {
        "name": "Timeline",
        "vault_pattern": "chronolog*",
        "description": "Timeline vs vault chronology",
    },
]


def _find_vault_docs(vault_path: Path, pattern: str) -> list[Path]:
    """Find markdown files matching a glob pattern in the vault."""
    results: list[Path] = []
    for p in vault_path.rglob(f"*{pattern}*"):
        if p.is_file() and p.suffix.lower() in (".md", ".markdown"):
            results.append(p)
    return sorted(results)


@click.command()
@click.option("--case-id", required=True, help="Case UUID for validation")
@click.option(
    "--vault-path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to Obsidian vault with manual documents",
)
@click.pass_context
def validate(ctx: click.Context, case_id: str, vault_path: Path) -> None:
    """Validate shard outputs against manual vault documents (Phase 4)."""
    _client: ShatteredClient = ctx.obj["client"]  # used when validation logic is implemented

    console.print(f"[bold]Validation: case [cyan]{case_id}[/] vs vault [cyan]{vault_path}[/][/]\n")

    table = Table(title="Validation Comparison Pairs", border_style="blue")
    table.add_column("Category", style="bold")
    table.add_column("Vault Docs", justify="right")
    table.add_column("Status")
    table.add_column("Description")

    total_vault_docs = 0

    for pair in COMPARISON_PAIRS:
        vault_docs = _find_vault_docs(vault_path, pair["vault_pattern"])
        doc_count = len(vault_docs)
        total_vault_docs += doc_count

        if doc_count > 0:
            status = "[yellow]READY[/]"
        else:
            status = "[dim]NO DOCS[/]"

        table.add_row(
            pair["name"],
            str(doc_count),
            status,
            pair["description"],
        )

    console.print(table)
    console.print(f"\n[bold]{total_vault_docs}[/] vault document(s) found across all categories")
    console.print()
    console.print("[yellow]Note:[/] Full validation logic (fetching shard outputs and generating")
    console.print("comparison reports) will be implemented in a future iteration.")
    console.print("This skeleton identifies the comparison pairs and available vault documents.")
