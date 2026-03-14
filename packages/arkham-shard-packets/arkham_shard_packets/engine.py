"""
Packets Engine — Pure packet assembly, indexing, and versioning logic.

Standalone functions for combining documents into ordered packets,
generating tables of contents, and tracking versions.
No DB, no frame, no LLM dependencies.
"""

from datetime import UTC, datetime
from typing import Any, Dict, List
from uuid import uuid4


def assemble_packet(
    documents: List[Dict[str, Any]],
    title: str,
    description: str,
) -> Dict[str, Any]:
    """Assemble documents into an ordered packet structure.

    Takes a list of document metadata dicts and combines them into
    a packet with sequential ordering and a unique packet ID.

    Args:
        documents: List of dicts, each with at least "id" and "title".
        title: Packet title.
        description: Packet description.

    Returns:
        Packet dict with id, title, description, version, items, created_at.

    Raises:
        ValueError: If documents list is empty.
    """
    if not documents:
        raise ValueError("Document list must not be empty")

    items = []
    for i, doc in enumerate(documents):
        item = {
            "id": doc.get("id", str(uuid4())),
            "title": doc.get("title", f"Document {i + 1}"),
            "order": i + 1,
        }
        # Preserve any extra metadata from the source document
        for key, value in doc.items():
            if key not in ("id", "title"):
                item[key] = value
        items.append(item)

    return {
        "id": str(uuid4()),
        "title": title,
        "description": description,
        "version": 1,
        "items": items,
        "created_at": datetime.now(UTC).isoformat(),
    }


def generate_index(packet: Dict[str, Any]) -> str:
    """Generate a markdown table of contents for a packet.

    Creates a numbered index listing each item in the packet
    with optional page counts.

    Args:
        packet: Packet dict with "title" and "items" keys.

    Returns:
        Markdown-formatted index string.
    """
    title = packet.get("title", "Packet")
    items = packet.get("items", [])

    lines = [
        f"# {title}",
        "",
        "## Table of Contents",
        "",
    ]

    if not items:
        lines.append("*No items in this packet.*")
        return "\n".join(lines)

    # Column widths for alignment
    max_num_width = len(str(len(items)))

    for item in items:
        order = item.get("order", 0)
        item_title = item.get("title", "Untitled")
        pages = item.get("pages")

        num_str = f"{order}.".ljust(max_num_width + 1)
        line = f"{num_str} {item_title}"

        if pages is not None:
            line += f" ({pages} pages)"

        lines.append(line)

    lines.append("")
    lines.append(f"**Total items:** {len(items)}")

    return "\n".join(lines)


def create_version(
    packet: Dict[str, Any],
    changes_summary: str,
) -> Dict[str, Any]:
    """Create a new version record for a packet.

    Increments the version number and records the changes.

    Args:
        packet: Current packet dict with "id" and "version" keys.
        changes_summary: Description of changes in this version.

    Returns:
        Version record dict with id, packet_id, version_number,
        changes_summary, and created_at.
    """
    current_version = packet.get("version", 0)

    return {
        "id": str(uuid4()),
        "packet_id": packet["id"],
        "version_number": current_version + 1,
        "changes_summary": changes_summary,
        "created_at": datetime.now(UTC).isoformat(),
    }
