"""
Export Shard - Format Generators

Pure functions that convert lists of dicts into export-ready bytes.
No external dependencies beyond Python stdlib (csv, json, io).
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional, Sequence


def generate_csv(
    records: List[Dict[str, Any]],
    columns: Optional[Sequence[str]] = None,
) -> bytes:
    """
    Generate CSV bytes from a list of record dicts.

    Args:
        records: List of dicts to export.
        columns: Optional ordered list of column names to include.
                 If None, all unique keys across records are used (sorted).

    Returns:
        UTF-8 encoded CSV bytes with proper escaping.
    """
    if not records:
        return b""

    if columns is None:
        all_keys: set[str] = set()
        for record in records:
            all_keys.update(record.keys())
        columns = sorted(all_keys)

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(columns),
        extrasaction="ignore",
        restval="",
    )
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue().encode("utf-8")


def generate_json(
    records: List[Dict[str, Any]],
) -> bytes:
    """
    Generate formatted JSON bytes from a list of record dicts.

    Args:
        records: List of dicts to export.

    Returns:
        UTF-8 encoded, indented JSON bytes.
    """
    output = json.dumps(
        records,
        indent=2,
        default=str,
        ensure_ascii=False,
    )
    return output.encode("utf-8")


def generate_markdown(
    records: List[Dict[str, Any]],
    title: Optional[str] = None,
) -> bytes:
    """
    Generate a Markdown table from a list of record dicts.

    Args:
        records: List of dicts to export.
        title: Optional heading above the table. Defaults to "Export".

    Returns:
        UTF-8 encoded Markdown bytes with heading and table.
    """
    heading = title or "Export"
    lines: list[str] = [f"# {heading}", ""]

    if not records:
        lines.append("No data to export.")
        return "\n".join(lines).encode("utf-8")

    # Collect all unique keys, preserving insertion order from first record
    seen: dict[str, None] = {}
    for record in records:
        for key in record:
            if key not in seen:
                seen[key] = None
    columns = list(seen.keys())

    # Header row
    header_cells = [_escape_md(col) for col in columns]
    lines.append("| " + " | ".join(header_cells) + " |")

    # Separator row
    lines.append("| " + " | ".join("---" for _ in columns) + " |")

    # Data rows
    for record in records:
        cells = [_escape_md(str(record.get(col, ""))) for col in columns]
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")  # trailing newline
    return "\n".join(lines).encode("utf-8")


def _escape_md(value: str) -> str:
    """Escape pipe characters in markdown table cell values."""
    return value.replace("|", "\\|")
