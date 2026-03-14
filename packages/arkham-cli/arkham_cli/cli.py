"""Main CLI entry point for SHATTERED."""

from __future__ import annotations

import sys

import click
from rich.console import Console

from .client import ServerUnreachableError, ShatteredClient

console = Console(stderr=True)


class ShatteredCLI(click.Group):
    """Custom group that catches ServerUnreachableError globally."""

    def invoke(self, ctx: click.Context) -> None:
        try:
            super().invoke(ctx)
        except ServerUnreachableError as exc:
            console.print(f"[bold red]Error:[/] {exc}")
            console.print(f"[dim]Ensure the SHATTERED server is running at {exc.url}[/]")
            console.print("[dim]Set SHATTERED_URL env var or use --url to change the server address.[/]")
            sys.exit(1)


@click.group(cls=ShatteredCLI)
@click.option(
    "--url",
    envvar="SHATTERED_URL",
    default="http://localhost:8100",
    show_default=True,
    help="SHATTERED server URL",
)
@click.option(
    "--timeout",
    envvar="SHATTERED_TIMEOUT",
    default=30,
    type=int,
    show_default=True,
    help="Request timeout in seconds",
)
@click.version_option(package_name="arkham-cli")
@click.pass_context
def main(ctx: click.Context, url: str, timeout: int) -> None:
    """SHATTERED -- Litigation Analysis Platform CLI"""
    ctx.ensure_object(dict)
    ctx.obj["client"] = ShatteredClient(base_url=url, timeout=timeout)
    ctx.obj["url"] = url


# Register subcommands
from .commands.analyze import analyze  # noqa: E402
from .commands.docs import docs  # noqa: E402
from .commands.export import export  # noqa: E402
from .commands.ingest import ingest  # noqa: E402
from .commands.status import shards, status  # noqa: E402
from .commands.validate import validate  # noqa: E402

main.add_command(status)
main.add_command(shards)
main.add_command(docs)
main.add_command(ingest)
main.add_command(analyze)
main.add_command(validate)
main.add_command(export)
