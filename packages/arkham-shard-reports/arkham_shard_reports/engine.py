"""
Reports Engine — Pure report generation logic.

Standalone functions for rendering reports from templates and data,
extracting structured section data, and formatting output.
No DB, no frame, no LLM, no HTTP dependencies.
"""

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Dict


def get_report_data(
    data_source_type: str,
    raw_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract structured report data from raw input for a given section type.

    Supported section types:
        - document_stats: counts and status breakdown of documents
        - entity_summary: entity counts grouped by type
        - timeline_overview: event count and date range
        - claim_status: claim counts by verification status

    Args:
        data_source_type: One of the supported section type strings.
        raw_data: Raw data dict containing the relevant records.

    Returns:
        Structured data dict with totals and breakdowns.
    """
    if data_source_type == "document_stats":
        return _extract_document_stats(raw_data)
    elif data_source_type == "entity_summary":
        return _extract_entity_summary(raw_data)
    elif data_source_type == "timeline_overview":
        return _extract_timeline_overview(raw_data)
    elif data_source_type == "claim_status":
        return _extract_claim_status(raw_data)
    else:
        return {"total": 0, "message": f"Unknown section type: {data_source_type}"}


def generate_report(
    template_id: str,
    data_sources: Dict[str, Dict[str, Any]],
    format: str = "markdown",
) -> str:
    """Render a report from a template identifier and data sources.

    Each key in data_sources corresponds to a section type (e.g.
    "document_stats", "entity_summary") with its raw data as the value.
    The engine processes each section and renders a combined report.

    Args:
        template_id: Report template identifier (e.g. "summary", "custom").
        data_sources: Dict mapping section type names to raw data dicts.
        format: Output format — currently only "markdown" is supported.

    Returns:
        Rendered report as a markdown string.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Report: {template_id.replace('_', ' ').title()}",
        "",
        f"*Generated: {now}*",
        "",
        "---",
        "",
    ]

    if not data_sources:
        lines.append("*No data sources provided.*")
        return "\n".join(lines)

    # Process each section
    for section_type, raw_data in data_sources.items():
        section_data = get_report_data(section_type, raw_data)
        section_md = _render_section(section_type, section_data)
        lines.append(section_md)
        lines.append("")

    return "\n".join(lines)


# === Private helpers ===


def _extract_document_stats(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract document statistics."""
    docs = raw.get("documents", [])
    status_counts = Counter(d.get("status", "unknown") for d in docs)
    return {
        "total": len(docs),
        "by_status": dict(status_counts),
    }


def _extract_entity_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract entity summary grouped by type."""
    entities = raw.get("entities", [])
    type_counts = Counter(e.get("type", "unknown") for e in entities)
    return {
        "total": len(entities),
        "by_type": dict(type_counts),
    }


def _extract_timeline_overview(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract timeline event overview with date range."""
    events = raw.get("events", [])
    if not events:
        return {
            "total_events": 0,
            "date_range": {"earliest": None, "latest": None},
            "events": [],
        }

    dates = sorted(e.get("date", "") for e in events if e.get("date"))
    return {
        "total_events": len(events),
        "date_range": {
            "earliest": dates[0] if dates else None,
            "latest": dates[-1] if dates else None,
        },
        "events": events,
    }


def _extract_claim_status(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract claim verification status counts."""
    claims = raw.get("claims", [])
    status_counts = Counter(c.get("status", "unknown") for c in claims)
    return {
        "total": len(claims),
        "verified": status_counts.get("verified", 0),
        "unverified": status_counts.get("unverified", 0),
        "by_status": dict(status_counts),
    }


def _render_section(section_type: str, data: Dict[str, Any]) -> str:
    """Render a single report section as markdown."""
    heading = section_type.replace("_", " ").title()
    lines = [f"## {heading}", ""]

    if section_type == "document_stats":
        lines.append(f"**Total documents:** {data.get('total', 0)}")
        by_status = data.get("by_status", {})
        if by_status:
            lines.append("")
            lines.append("| Status | Count |")
            lines.append("|--------|-------|")
            for status, count in sorted(by_status.items()):
                lines.append(f"| {status} | {count} |")

    elif section_type == "entity_summary":
        lines.append(f"**Total entities:** {data.get('total', 0)}")
        by_type = data.get("by_type", {})
        if by_type:
            lines.append("")
            lines.append("| Type | Count |")
            lines.append("|------|-------|")
            for etype, count in sorted(by_type.items()):
                lines.append(f"| {etype} | {count} |")

    elif section_type == "timeline_overview":
        total = data.get("total_events", 0)
        lines.append(f"**Total events:** {total}")
        dr = data.get("date_range", {})
        if dr.get("earliest"):
            lines.append(f"**Date range:** {dr['earliest']} to {dr['latest']}")
        events = data.get("events", [])
        if events:
            lines.append("")
            for ev in events[:20]:  # Cap at 20 for readability
                date = ev.get("date", "")
                desc = ev.get("description", "")
                lines.append(f"- **{date}**: {desc}")

    elif section_type == "claim_status":
        lines.append(f"**Total claims:** {data.get('total', 0)}")
        lines.append(f"**Verified:** {data.get('verified', 0)}")
        lines.append(f"**Unverified:** {data.get('unverified', 0)}")

    else:
        lines.append(f"*Section data:* {data}")

    return "\n".join(lines)
