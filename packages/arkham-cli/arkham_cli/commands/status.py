"""Status and shard listing commands."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ..client import APIError

console = Console()


@click.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show SHATTERED server status and service health."""
    client = ctx.obj["client"]
    url = ctx.obj["url"]

    # Fetch health
    try:
        health = client.health()
    except APIError:
        health = {}

    # Fetch status
    try:
        status_data = client.status()
    except APIError:
        status_data = {}

    # Fetch document stats
    try:
        doc_stats = client.document_stats()
    except APIError:
        doc_stats = {}

    # Determine overall health
    is_healthy = health.get("status") == "healthy" or health.get("status") == "ok"
    health_display = "[bold green]healthy[/]" if is_healthy else "[bold red]unhealthy[/]"

    # Services check
    services = status_data.get("services", {})
    shard_list = status_data.get("shards", [])
    shard_count = len(shard_list) if isinstance(shard_list, list) else status_data.get("shard_count", "?")

    table = Table(title="SHATTERED Server Status", show_header=False, border_style="blue")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Server URL", url)
    table.add_row("Status", health_display)

    # Service checks
    service_names = ["database", "db", "vectors", "llm", "workers"]
    for svc in service_names:
        if svc in services:
            val = services[svc]
            if isinstance(val, dict):
                ok = val.get("healthy", val.get("status") == "ok")
            elif isinstance(val, bool):
                ok = val
            else:
                ok = str(val).lower() in ("ok", "healthy", "true")
            icon = "[green]OK[/]" if ok else "[red]DOWN[/]"
            label = svc.capitalize()
            table.add_row(f"  {label}", icon)

    table.add_row("Shards loaded", str(shard_count))

    # Document stats
    total_docs = doc_stats.get("total", doc_stats.get("count", ""))
    if total_docs != "":
        table.add_row("Documents", str(total_docs))

    console.print(table)


@click.command()
@click.pass_context
def shards(ctx: click.Context) -> None:
    """List all loaded shards."""
    client = ctx.obj["client"]

    status_data = client.status()
    shard_list = status_data.get("shards", [])

    if not shard_list:
        console.print("[yellow]No shards reported by the server.[/]")
        return

    table = Table(title="Loaded Shards", border_style="blue")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Shard Name", style="bold cyan")
    table.add_column("Category", style="dim")

    for i, shard in enumerate(shard_list, 1):
        if isinstance(shard, dict):
            name = shard.get("name", str(shard))
            category = shard.get("category", "")
        else:
            name = str(shard)
            category = ""
        table.add_row(str(i), name, category)

    console.print(table)
    console.print(f"\n[dim]{len(shard_list)} shard(s) loaded[/]")
