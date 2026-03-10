"""Thread reconstruction engine for the Comms shard.

Reconstructs email conversation threads from fragmented sources,
detects communication gaps, BCC patterns, and coordination signals.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Default gap threshold in hours -- messages without a reply within this window are flagged
DEFAULT_GAP_THRESHOLD_HOURS = 48

# Coordination window -- messages from different senders within this window are flagged
COORDINATION_WINDOW_MINUTES = 5


class ThreadReconstructor:
    """
    Reconstructs email conversation threads and detects anomalous patterns.

    Capabilities:
    - Parse email headers from extracted text
    - Build conversation trees from In-Reply-To/References chains
    - Detect reply gaps (missing or delayed responses)
    - Detect BCC patterns (participants appearing without prior visibility)
    - Detect coordination patterns (simultaneous sends, timing anomalies)
    """

    def __init__(self, db=None, event_bus=None):
        """
        Initialize the reconstructor.

        Args:
            db: Database service for querying thread/message data.
            event_bus: EventBus for emitting detection events.
        """
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Header parsing
    # ------------------------------------------------------------------

    def parse_email_headers(self, parsed_text: str) -> dict[str, Any]:
        """
        Extract email headers from parsed/OCR'd text.

        Handles common header formats found in disclosed document bundles.

        Args:
            parsed_text: Raw text containing email headers and body.

        Returns:
            Dict with keys: message_id, in_reply_to, references,
            from_addr, to_addrs, cc_addrs, date.
        """
        result: dict[str, Any] = {
            "message_id": None,
            "in_reply_to": None,
            "references": [],
            "from_addr": None,
            "to_addrs": [],
            "cc_addrs": [],
            "date": None,
        }

        # Extract Message-ID
        match = re.search(r"^Message-ID:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["message_id"] = match.group(1).strip()

        # Extract In-Reply-To
        match = re.search(r"^In-Reply-To:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["in_reply_to"] = match.group(1).strip()

        # Extract References (space-separated list of message IDs)
        match = re.search(r"^References:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            refs_text = match.group(1).strip()
            result["references"] = [r.strip() for r in refs_text.split() if r.strip()]

        # Extract From
        match = re.search(r"^From:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["from_addr"] = self._extract_email(match.group(1).strip())

        # Extract To (comma-separated)
        match = re.search(r"^To:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["to_addrs"] = self._extract_email_list(match.group(1).strip())

        # Extract CC (comma-separated)
        match = re.search(r"^CC:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["cc_addrs"] = self._extract_email_list(match.group(1).strip())

        # Extract Date
        match = re.search(r"^Date:\s*(.+)$", parsed_text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["date"] = self._parse_date(match.group(1).strip())

        return result

    # ------------------------------------------------------------------
    # Thread reconstruction
    # ------------------------------------------------------------------

    async def reconstruct_thread(self, messages: list[dict]) -> dict[str, Any]:
        """
        Build a conversation tree from a list of message dicts.

        Each message dict must have: message_id, in_reply_to, references.

        Args:
            messages: List of message dicts with header info.

        Returns:
            Dict with thread_id, root_message_id, message_count, tree.
            tree is a list of root nodes, each with children lists.
        """
        thread_id = str(uuid.uuid4())

        # Index messages by message_id
        by_id: dict[str, dict] = {}
        for msg in messages:
            mid = msg.get("message_id")
            if mid:
                by_id[mid] = {
                    "message_id": mid,
                    "children": [],
                    "date": msg.get("date"),
                    "from_addr": msg.get("from_addr"),
                }

        # Build parent-child relationships
        child_ids: set[str] = set()
        for msg in messages:
            mid = msg.get("message_id")
            parent_id = msg.get("in_reply_to")

            if parent_id and parent_id in by_id and mid in by_id:
                by_id[parent_id]["children"].append(by_id[mid])
                child_ids.add(mid)

        # Roots are messages that are not children of any other message
        roots = [by_id[mid] for mid in by_id if mid not in child_ids]

        # Sort roots by date
        roots.sort(key=lambda n: n.get("date") or datetime.min)

        # Sort children at each level by date
        self._sort_tree_children(roots)

        # Determine the root message_id
        root_message_id = roots[0]["message_id"] if roots else None

        result = {
            "thread_id": thread_id,
            "root_message_id": root_message_id,
            "message_count": len(messages),
            "tree": self._serialize_tree(roots),
        }

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "comms.thread.reconstructed",
                {"thread_id": thread_id, "message_count": len(messages)},
                source="comms-shard",
            )

        return result

    # ------------------------------------------------------------------
    # Gap detection
    # ------------------------------------------------------------------

    async def detect_gaps(
        self, thread_id: str, threshold_hours: float = DEFAULT_GAP_THRESHOLD_HOURS
    ) -> list[dict[str, Any]]:
        """
        Identify messages missing a reply within the expected timeframe.

        Args:
            thread_id: Thread to analyse.
            threshold_hours: Hours after which a missing reply is flagged.

        Returns:
            List of gap dicts: message_id, expected_reply_by, gap_duration_hours.
        """
        if not self._db:
            logger.warning("Database not available for gap detection")
            return []

        rows = await self._db.fetch_all(
            "SELECT * FROM arkham_comms.messages WHERE thread_id = :thread_id ORDER BY sent_at ASC",
            {"thread_id": thread_id},
        )

        if not rows:
            return []

        messages = [dict(r) for r in rows]

        # Build a set of message_id_headers that have been replied to
        replied_to: set[str] = set()
        for msg in messages:
            irt = msg.get("in_reply_to")
            if irt:
                replied_to.add(irt)

        gaps: list[dict[str, Any]] = []
        now = datetime.utcnow()

        for msg in messages:
            msg_header = msg.get("message_id_header")
            sent_at = msg.get("sent_at")

            if not msg_header or not sent_at:
                continue

            # If this message was replied to, no gap
            if msg_header in replied_to:
                continue

            # Calculate how long since the message was sent
            if isinstance(sent_at, str):
                sent_at = datetime.fromisoformat(sent_at)

            hours_since = (now - sent_at).total_seconds() / 3600

            if hours_since >= threshold_hours:
                expected_reply_by = sent_at + timedelta(hours=threshold_hours)
                gaps.append(
                    {
                        "message_id": msg_header,
                        "expected_reply_by": expected_reply_by.isoformat(),
                        "gap_duration_hours": round(hours_since, 1),
                    }
                )

        # Emit events for detected gaps
        if gaps and self._event_bus:
            await self._event_bus.emit(
                "comms.gap.detected",
                {"thread_id": thread_id, "gap_count": len(gaps)},
                source="comms-shard",
            )

        return gaps

    # ------------------------------------------------------------------
    # BCC pattern detection
    # ------------------------------------------------------------------

    async def detect_bcc_patterns(self, thread_id: str) -> list[dict[str, Any]]:
        """
        Cross-reference CC/To lists to detect potential BCC recipients.

        If a participant sends a message or is CC'd in a later message but
        was not visible (To/CC) in earlier messages, flag as potential BCC.

        Args:
            thread_id: Thread to analyse.

        Returns:
            List of dicts: participant, first_visible_message, suspected_bcc_from.
        """
        if not self._db:
            logger.warning("Database not available for BCC detection")
            return []

        rows = await self._db.fetch_all(
            "SELECT * FROM arkham_comms.messages WHERE thread_id = :thread_id ORDER BY sent_at ASC",
            {"thread_id": thread_id},
        )

        if not rows:
            return []

        messages = [dict(r) for r in rows]
        patterns: list[dict[str, Any]] = []

        # Track when each participant first becomes visible
        first_visible: dict[str, str] = {}  # email -> message_id
        # Track all participants who actively send messages
        active_senders: dict[str, str] = {}  # email -> first message_id they sent

        for msg in messages:
            msg_id = msg.get("message_id_header", msg.get("id", ""))
            from_addr = msg.get("from_address", "")
            to_addrs = self._parse_json_list(msg.get("to_addresses", "[]"))
            cc_addrs = self._parse_json_list(msg.get("cc_addresses", "[]"))

            # All visible participants in this message
            all_visible = set()
            if from_addr:
                all_visible.add(from_addr.lower())
            for addr in to_addrs + cc_addrs:
                all_visible.add(addr.lower())

            # Check if any participant is a sender but was NOT visible before
            if from_addr:
                from_lower = from_addr.lower()
                if from_lower not in first_visible and from_lower not in active_senders:
                    # First time we see this person as a sender, and they weren't
                    # previously visible as a recipient
                    if len(first_visible) > 0:
                        # There were previous messages where they weren't visible
                        active_senders[from_lower] = msg_id
                        # Find which earlier message they might have been BCC'd on
                        earliest_msg = next(iter(first_visible.values()), None)
                        patterns.append(
                            {
                                "participant": from_addr,
                                "first_visible_message": msg_id,
                                "suspected_bcc_from": earliest_msg,
                            }
                        )

            # Record first visibility for all participants
            for addr in all_visible:
                if addr not in first_visible:
                    first_visible[addr] = msg_id

        return patterns

    # ------------------------------------------------------------------
    # Coordination detection
    # ------------------------------------------------------------------

    async def detect_coordination(
        self, thread_id: str, window_minutes: float = COORDINATION_WINDOW_MINUTES
    ) -> list[dict[str, Any]]:
        """
        Detect suspicious timing patterns in a thread.

        Flags simultaneous sends (messages from different senders within
        the coordination window).

        Args:
            thread_id: Thread to analyse.
            window_minutes: Minutes within which sends are considered simultaneous.

        Returns:
            List of dicts: pattern_type, messages_involved, timing_detail.
        """
        if not self._db:
            logger.warning("Database not available for coordination detection")
            return []

        rows = await self._db.fetch_all(
            "SELECT * FROM arkham_comms.messages WHERE thread_id = :thread_id ORDER BY sent_at ASC",
            {"thread_id": thread_id},
        )

        if not rows:
            return []

        messages = [dict(r) for r in rows]
        coordination: list[dict[str, Any]] = []

        # Check for simultaneous sends from different senders
        for i in range(len(messages)):
            for j in range(i + 1, len(messages)):
                msg_a = messages[i]
                msg_b = messages[j]

                sent_a = msg_a.get("sent_at")
                sent_b = msg_b.get("sent_at")
                from_a = msg_a.get("from_address", "")
                from_b = msg_b.get("from_address", "")

                if not sent_a or not sent_b:
                    continue

                # Parse dates if needed
                if isinstance(sent_a, str):
                    sent_a = datetime.fromisoformat(sent_a)
                if isinstance(sent_b, str):
                    sent_b = datetime.fromisoformat(sent_b)

                # Different senders within the window
                if from_a.lower() != from_b.lower():
                    diff_minutes = abs((sent_b - sent_a).total_seconds()) / 60

                    if diff_minutes <= window_minutes:
                        coordination.append(
                            {
                                "pattern_type": "simultaneous_send",
                                "messages_involved": [
                                    msg_a.get("message_id_header", msg_a.get("id", "")),
                                    msg_b.get("message_id_header", msg_b.get("id", "")),
                                ],
                                "timing_detail": f"{diff_minutes:.1f} minutes apart",
                            }
                        )

        # Emit event if patterns found
        if coordination and self._event_bus:
            await self._event_bus.emit(
                "comms.coordination.flagged",
                {"thread_id": thread_id, "pattern_count": len(coordination)},
                source="comms-shard",
            )

        return coordination

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_email(self, text: str) -> str:
        """Extract a single email address from text like 'Name <email>' or bare email."""
        match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
        return match.group(0) if match else text.strip()

    def _extract_email_list(self, text: str) -> list[str]:
        """Extract multiple email addresses from a comma-separated header value."""
        parts = text.split(",")
        emails = []
        for part in parts:
            email = self._extract_email(part.strip())
            if email and "@" in email:
                emails.append(email)
        return emails

    def _parse_date(self, date_str: str) -> str | None:
        """Parse common email date formats. Returns ISO format string or None."""
        # Common email date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
            "%d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.isoformat()
            except ValueError:
                continue
        logger.debug(f"Could not parse date: {date_str}")
        return date_str  # Return raw string as fallback

    def _sort_tree_children(self, nodes: list[dict]) -> None:
        """Recursively sort children in a tree by date."""
        for node in nodes:
            children = node.get("children", [])
            children.sort(key=lambda n: n.get("date") or datetime.min)
            self._sort_tree_children(children)

    def _serialize_tree(self, nodes: list[dict]) -> list[dict[str, Any]]:
        """Convert tree nodes to serializable format (strip internal fields)."""
        result = []
        for node in nodes:
            serialized = {
                "message_id": node["message_id"],
                "children": self._serialize_tree(node.get("children", [])),
            }
            result.append(serialized)
        return result

    def _parse_json_list(self, value: Any) -> list[str]:
        """Parse a JSON list from a string or return as-is if already a list."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []
