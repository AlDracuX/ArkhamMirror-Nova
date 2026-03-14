"""Analysis pipeline command."""

from __future__ import annotations

from typing import Any

import click
from rich.console import Console
from rich.table import Table

from ..client import APIError

console = Console()

PIPELINE_STEPS = [
    "rules-seed",
    "burden-s13",
    "burden-s26",
    "burden-s27",
    "disclosure-gaps",
    "costs-conduct",
    "respondent-profiles",
    "comms-gaps",
    "comparator-s13",
    "comparator-s26",
    "timeline",
]


def _run_step(client: Any, case_id: str, step: str) -> tuple[bool, str]:
    """Run a single analysis step. Returns (success, summary)."""
    try:
        if step == "rules-seed":
            result = client.rules_seed()
            count = result.get("count", result.get("rules_count", "?"))
            return True, f"{count} rules seeded"

        elif step == "burden-s13":
            result = client.burden_populate(case_id, "s13")
            count = result.get("count", result.get("elements", "?"))
            return True, f"s.13 burden: {count} elements"

        elif step == "burden-s26":
            result = client.burden_populate(case_id, "s26")
            count = result.get("count", result.get("elements", "?"))
            return True, f"s.26 burden: {count} elements"

        elif step == "burden-s27":
            result = client.burden_populate(case_id, "s27")
            count = result.get("count", result.get("elements", "?"))
            return True, f"s.27 burden: {count} elements"

        elif step == "disclosure-gaps":
            result = client.disclosure_gaps(case_id)
            gaps = result.get("gaps", result.get("count", "?"))
            if isinstance(gaps, list):
                gaps = len(gaps)
            return True, f"{gaps} disclosure gap(s) detected"

        elif step == "costs-conduct":
            result = client.costs_conduct_score(case_id)
            score = result.get("score", result.get("conduct_score", "?"))
            return True, f"Conduct score: {score}"

        elif step == "respondent-profiles":
            result = client.respondent_profiles(case_id)
            count = result.get("count", "?")
            if isinstance(result.get("profiles"), list):
                count = len(result["profiles"])
            return True, f"{count} profile(s) built"

        elif step == "comms-gaps":
            result = client.comms_gaps(case_id)
            gaps = result.get("gaps", result.get("count", "?"))
            if isinstance(gaps, list):
                gaps = len(gaps)
            return True, f"{gaps} communication gap(s)"

        elif step == "comparator-s13":
            result = client.comparator_s13(case_id)
            count = result.get("count", "?")
            if isinstance(result.get("elements"), list):
                count = len(result["elements"])
            return True, f"s.13 comparator: {count} elements"

        elif step == "comparator-s26":
            result = client.comparator_s26(case_id)
            count = result.get("count", "?")
            if isinstance(result.get("elements"), list):
                count = len(result["elements"])
            return True, f"s.26 comparator: {count} elements"

        elif step == "timeline":
            result = client.timeline_events(case_id)
            events = result.get("events", result.get("items", []))
            count = len(events) if isinstance(events, list) else result.get("count", "?")
            return True, f"{count} timeline event(s)"

        else:
            return False, f"Unknown step: {step}"

    except APIError as exc:
        return False, f"HTTP {exc.status_code}: {exc.body[:80]}"
    except Exception as exc:
        return False, str(exc)[:100]


@click.command()
@click.option("--case-id", required=True, help="Case UUID for analysis")
@click.option("--skip", multiple=True, type=click.Choice(PIPELINE_STEPS), help="Steps to skip")
@click.pass_context
def analyze(ctx: click.Context, case_id: str, skip: tuple[str, ...]) -> None:
    """Run the full SHATTERED analysis pipeline for a case."""
    client = ctx.obj["client"]
    skip_set = set(skip)

    results: list[tuple[str, bool, str]] = []

    console.print(f"[bold]Running analysis pipeline for case [cyan]{case_id}[/][/]\n")

    for step in PIPELINE_STEPS:
        if step in skip_set:
            console.print(f"  [dim]SKIP[/]  {step}")
            results.append((step, True, "skipped"))
            continue

        console.print(f"  [yellow]RUN[/]   {step}...", end="")
        ok, summary = _run_step(client, case_id, step)

        if ok:
            console.print(f"\r  [green]PASS[/]  {step}: {summary}")
        else:
            console.print(f"\r  [red]FAIL[/]  {step}: {summary}")

        results.append((step, ok, summary))

    # Summary table
    console.print()
    table = Table(title="Analysis Pipeline Results", border_style="blue")
    table.add_column("Step", style="bold")
    table.add_column("Result")
    table.add_column("Summary")

    passed = 0
    failed = 0
    for step, ok, summary in results:
        if summary == "skipped":
            table.add_row(step, "[dim]SKIP[/]", summary)
        elif ok:
            table.add_row(step, "[green]PASS[/]", summary)
            passed += 1
        else:
            table.add_row(step, "[red]FAIL[/]", summary)
            failed += 1

    console.print(table)
    console.print(f"\n[bold]{passed} passed[/], [bold red]{failed} failed[/], {len(skip_set)} skipped")
