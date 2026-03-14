"""
Letters Engine — Pure document generation logic.

Standalone functions for template rendering, ET letter formatting,
and markdown letter generation. No DB, no frame, no LLM dependencies.
"""

import re
from datetime import UTC, datetime
from typing import Any, Dict, Optional


def render_letter(
    template: str,
    variables: Dict[str, str],
    format: str = "text",
) -> str:
    """Render a letter by substituting {{variables}} in a template string.

    Args:
        template: Template string with {{placeholder}} markers.
        variables: Key-value pairs for substitution.
        format: Output format — "text" (default) or "markdown".

    Returns:
        Rendered letter content as a string.
    """
    # Substitute known variables
    result = template
    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        result = result.replace(placeholder, str(value))

    # Replace any remaining unresolved placeholders with [key] defaults
    result = re.sub(r"\{\{(\w+)\}\}", lambda m: f"[{m.group(1)}]", result)

    if format == "markdown":
        return result
    return result


def generate_letter_pdf(
    content: str,
    metadata: Dict[str, Any],
) -> str:
    """Generate a markdown-formatted letter document.

    Returns markdown string (not actual PDF — markdown output is the
    designated format per project constraints).

    Args:
        content: The letter body text.
        metadata: Dict with optional keys: title, date, reference,
                  sender_name, recipient_name.

    Returns:
        Complete markdown-formatted letter.
    """
    title = metadata.get("title", "Letter")
    date = metadata.get("date", datetime.now(UTC).strftime("%d %B %Y"))
    reference = metadata.get("reference", "")
    sender = metadata.get("sender_name", "")
    recipient = metadata.get("recipient_name", "")

    lines = [f"# {title}", ""]

    if date:
        lines.append(f"**Date:** {date}")
    if reference:
        lines.append(f"**Reference:** {reference}")
    if sender:
        lines.append(f"**From:** {sender}")
    if recipient:
        lines.append(f"**To:** {recipient}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(content)
    lines.append("")

    return "\n".join(lines)


def format_et_letter(
    date: str,
    recipient_name: str,
    sender_name: str,
    body: str,
    reference: Optional[str] = None,
    re_line: Optional[str] = None,
    sender_address: Optional[str] = None,
    recipient_address: Optional[str] = None,
) -> str:
    """Format a standard Employment Tribunal letter.

    Produces a formal letter with: sender block, date, recipient block,
    reference line, RE line, salutation, body, sign-off, and signature.

    Args:
        date: Letter date string (e.g. "14 March 2026").
        recipient_name: Name of recipient.
        sender_name: Name of sender.
        body: Letter body text.
        reference: Optional case reference number.
        re_line: Optional RE: line (e.g. "Dalton v Bylor Ltd").
        sender_address: Optional sender address.
        recipient_address: Optional recipient address.

    Returns:
        Formatted letter as plain text string.
    """
    lines: list[str] = []

    # Sender block
    lines.append(sender_name)
    if sender_address:
        lines.append(sender_address)
    lines.append("")

    # Date
    lines.append(date)
    lines.append("")

    # Recipient block
    lines.append(recipient_name)
    if recipient_address:
        lines.append(recipient_address)
    lines.append("")

    # Reference line
    if reference:
        lines.append(f"Reference: {reference}")
        lines.append("")

    # RE line
    if re_line:
        lines.append(f"RE: {re_line}")
        lines.append("")

    # Salutation
    lines.append(f"Dear {recipient_name},")
    lines.append("")

    # Body
    lines.append(body)
    lines.append("")

    # Sign-off
    lines.append("Yours faithfully,")
    lines.append("")
    lines.append(sender_name)

    return "\n".join(lines)
