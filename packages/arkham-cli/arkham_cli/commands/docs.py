"""Document listing commands."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.command()
@click.option("--status", "doc_status", default=None, help="Filter by document status")
@click.option("--type", "doc_type", default=None, help="Filter by document type")
@click.option("--limit", default=50, type=int, show_default=True, help="Max documents to return")
@click.option("--offset", default=0, type=int, help="Offset for pagination")
@click.option("--count", is_flag=True, help="Show only document count")
@click.pass_context
def docs(
    ctx: click.Context, doc_status: str | None, doc_type: str | None, limit: int, offset: int, count: bool
) -> None:
    """List documents in the system."""
    client = ctx.obj["client"]

    result = client.documents(status=doc_status, doc_type=doc_type, limit=limit, offset=offset)

    # Handle various response shapes
    documents = result.get("documents", result.get("items", []))
    total = result.get("total", result.get("count", len(documents)))

    if count:
        console.print(f"[bold]{total}[/] document(s)")
        return

    if not documents:
        console.print("[yellow]No documents found.[/]")
        return

    table = Table(title=f"Documents ({total} total)", border_style="blue")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Title", style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Pages", justify="right")

    for doc in documents:
        doc_id = str(doc.get("id", ""))[:12]
        title = doc.get("title", doc.get("filename", "untitled"))
        dtype = doc.get("type", doc.get("doc_type", ""))
        dstatus = doc.get("status", "")
        pages = str(doc.get("pages", doc.get("page_count", "")))
        table.add_row(doc_id, title, dtype, dstatus, pages)

    console.print(table)
