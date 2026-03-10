"""Core domain logic for the Digest shard.

DigestEngine orchestrates change logging, briefing generation,
action item extraction, and subscription management.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from .llm import DigestLLM

logger = logging.getLogger(__name__)

# Event types that indicate actionable items
ACTIONABLE_PATTERNS = {
    "breach": "Disclosure breach detected",
    "gap": "Evidence gap identified",
    "deadline": "Deadline approaching or missed",
    "evasion": "Evasion pattern detected",
    "violation": "Rule violation flagged",
    "risk": "Cost or procedural risk",
}

# Frequency to timedelta mapping
FREQUENCY_DELTAS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "hourly": timedelta(hours=1),
}


class DigestEngine:
    """Core engine for digest generation and change tracking.

    Orchestrates:
    - Change log persistence
    - Briefing generation (LLM-enhanced or rule-based)
    - Action item extraction
    - Subscription management
    """

    def __init__(self, db=None, event_bus=None, llm_service=None):
        self._db = db
        self._event_bus = event_bus
        self._llm = DigestLLM(llm_service=llm_service)

    async def log_change(self, event_type: str, event_data: dict) -> str:
        """Write event to change_log table.

        Args:
            event_type: Dot-separated event type (e.g., "disclosure.breach.detected")
            event_data: Event payload with source, entity details, etc.

        Returns:
            change_log_entry_id
        """
        entry_id = str(uuid.uuid4())

        # Parse event type into components
        parts = event_type.split(".")
        shard = parts[0] if parts else "unknown"
        action = ".".join(parts[1:]) if len(parts) > 1 else event_type

        project_id = event_data.get("project_id", "default")
        entity_type = event_data.get("entity_type", shard)
        entity_id = event_data.get("entity_id", "")
        description = event_data.get("description", f"{event_type} event")

        if self._db:
            await self._db.execute(
                """
                INSERT INTO arkham_digest.change_log
                (id, project_id, shard, entity_type, entity_id, action, description)
                VALUES (:id, :project_id, :shard, :entity_type, :entity_id, :action, :description)
                """,
                {
                    "id": entry_id,
                    "project_id": project_id,
                    "shard": shard,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "action": action,
                    "description": description,
                },
            )

        logger.debug(f"Logged change: {entry_id} [{event_type}]")
        return entry_id

    async def generate_briefing(self, project_id: str, briefing_type: str = "daily") -> dict:
        """Synthesize changes since last briefing into priority-ranked summary.

        ADHD format: short bullets, bold key items, numbered action steps.

        Args:
            project_id: Project to generate briefing for
            briefing_type: One of "daily", "weekly", "sitrep"

        Returns:
            Dict with briefing_id, summary, action_items, change_count, priority_items
        """
        # Fetch recent changes
        changes = []
        if self._db:
            rows = await self._db.fetch_all(
                """
                SELECT id, project_id, shard, entity_type, entity_id, action, description, timestamp
                FROM arkham_digest.change_log
                WHERE project_id = :project_id
                ORDER BY timestamp DESC
                LIMIT :limit
                """,
                {"project_id": project_id, "limit": 100},
            )
            changes = [dict(r) for r in rows] if rows else []

        # Generate briefing content (LLM or fallback)
        result = await self._llm.generate_briefing_content(changes, briefing_type)

        # Extract action items from changes
        action_items = await self.extract_action_items(changes)
        # Merge LLM action items with pattern-matched ones (deduplicate)
        all_actions = list(dict.fromkeys(action_items + result.action_items))

        briefing_id = str(uuid.uuid4())

        # Persist briefing
        if self._db:
            import json

            await self._db.execute(
                """
                INSERT INTO arkham_digest.briefings
                (id, project_id, type, content, priority_items, action_items)
                VALUES (:id, :project_id, :type, :content, :priority_items, :action_items)
                """,
                {
                    "id": briefing_id,
                    "project_id": project_id,
                    "type": briefing_type,
                    "content": result.summary,
                    "priority_items": json.dumps(result.priority_items),
                    "action_items": json.dumps(all_actions),
                },
            )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "digest.briefing.generated",
                {"briefing_id": briefing_id, "project_id": project_id, "change_count": len(changes)},
                source="digest-shard",
            )

        return {
            "briefing_id": briefing_id,
            "summary": result.summary,
            "action_items": all_actions,
            "change_count": len(changes),
            "priority_items": result.priority_items,
        }

    async def extract_action_items(self, changes: list[dict]) -> list[str]:
        """Identify items requiring user action from change log.

        Pattern-match on event types: breach, gap, deadline, evasion -> action needed.

        Args:
            changes: List of change log entry dicts

        Returns:
            List of action item strings
        """
        action_items = []

        for change in changes:
            action = change.get("action", "").lower()
            description = change.get("description", "")
            entity_type = change.get("entity_type", "")

            for pattern, label in ACTIONABLE_PATTERNS.items():
                if pattern in action or pattern in description.lower() or pattern in entity_type.lower():
                    item = description if description else f"{label}: {entity_type} - {action}"
                    if item not in action_items:
                        action_items.append(item)
                    break

        return action_items

    async def manage_subscription(self, user_id: str, project_id: str, frequency: str = "daily") -> dict:
        """Create or update subscription preferences.

        Args:
            user_id: User ID for the subscription
            project_id: Project to subscribe to
            frequency: One of "daily", "weekly", "hourly"

        Returns:
            Dict with subscription_id, user_id, project_id, frequency, next_briefing
        """
        now = datetime.utcnow()
        delta = FREQUENCY_DELTAS.get(frequency, timedelta(days=1))
        next_briefing = now + delta

        # Check for existing subscription
        existing = None
        if self._db:
            existing = await self._db.fetch_one(
                """
                SELECT id FROM arkham_digest.subscriptions
                WHERE user_id = :user_id AND project_id = :project_id
                """,
                {"user_id": user_id, "project_id": project_id},
            )

        if existing:
            sub_id = existing["id"] if isinstance(existing, dict) else existing[0]
            if self._db:
                await self._db.execute(
                    """
                    UPDATE arkham_digest.subscriptions
                    SET frequency = :frequency
                    WHERE id = :id
                    """,
                    {"id": sub_id, "frequency": frequency},
                )
        else:
            sub_id = str(uuid.uuid4())
            if self._db:
                await self._db.execute(
                    """
                    INSERT INTO arkham_digest.subscriptions
                    (id, project_id, user_id, frequency)
                    VALUES (:id, :project_id, :user_id, :frequency)
                    """,
                    {
                        "id": sub_id,
                        "project_id": project_id,
                        "user_id": user_id,
                        "frequency": frequency,
                    },
                )

        return {
            "subscription_id": sub_id,
            "user_id": user_id,
            "project_id": project_id,
            "frequency": frequency,
            "next_briefing": next_briefing.isoformat(),
        }
