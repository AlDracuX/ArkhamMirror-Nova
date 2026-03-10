"""AuditTrail Engine - Core domain logic for audit search, export, and retention."""

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AuditEngine:
    """
    Core engine for audit trail operations.

    Provides search/filter, session retrieval, export generation,
    and retention management. No LLM needed -- purely data query and export.
    """

    def __init__(self, db=None, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # search_actions
    # ------------------------------------------------------------------

    async def search_actions(
        self,
        shard: str | None = None,
        user_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        entity_id: str | None = None,
    ) -> list[dict]:
        """
        Search/filter audit actions with multiple criteria.

        Returns list of matching action records as dicts.
        """
        if not self._db:
            return []

        query = "SELECT * FROM arkham_audit_trail.actions WHERE 1=1"
        params: dict[str, Any] = {}

        if shard:
            query += " AND shard = :shard"
            params["shard"] = shard

        if user_id:
            query += " AND user_id = :user_id"
            params["user_id"] = user_id

        if date_from:
            query += " AND timestamp >= :date_from"
            params["date_from"] = date_from

        if date_to:
            query += " AND timestamp <= :date_to"
            params["date_to"] = date_to

        if entity_id:
            query += " AND entity_id = :entity_id"
            params["entity_id"] = entity_id

        query += " ORDER BY timestamp DESC"

        rows = await self._db.fetch_all(query, params)
        return [dict(r) if not isinstance(r, dict) else r for r in rows]

    # ------------------------------------------------------------------
    # get_session_actions
    # ------------------------------------------------------------------

    async def get_session_actions(self, session_id: str) -> list[dict]:
        """
        Get all actions within a user session, ordered chronologically.

        Returns list of actions for the session.
        """
        if not self._db:
            return []

        rows = await self._db.fetch_all(
            "SELECT * FROM arkham_audit_trail.actions WHERE session_id = :session_id ORDER BY timestamp ASC",
            {"session_id": session_id},
        )
        return [dict(r) if not isinstance(r, dict) else r for r in rows]

    # ------------------------------------------------------------------
    # export_audit_log
    # ------------------------------------------------------------------

    async def export_audit_log(self, filters: dict, format: str = "json") -> dict:
        """
        Generate audit log export for tribunal submission.

        Formats: json, csv, text.
        Stores export record in DB. Returns {export_id, format, record_count, content}.
        """
        export_id = str(uuid.uuid4())

        # Fetch matching records using search_actions
        records = await self.search_actions(
            shard=filters.get("shard"),
            user_id=filters.get("user_id"),
            date_from=filters.get("date_from"),
            date_to=filters.get("date_to"),
            entity_id=filters.get("entity_id"),
        )

        record_count = len(records)

        # Format content
        if format == "csv":
            content = self._format_csv(records)
        elif format == "text":
            content = self._format_text(records)
        else:
            content = records  # json -- return list of dicts

        # Store export record
        if self._db:
            await self._db.execute(
                """
                INSERT INTO arkham_audit_trail.exports
                (id, tenant_id, user_id, export_format, filters_applied, row_count)
                VALUES (:id, :tenant_id, :user_id, :format, :filters, :rows)
                """,
                {
                    "id": export_id,
                    "tenant_id": None,
                    "user_id": filters.get("user_id"),
                    "format": format,
                    "filters": json.dumps(filters, default=str),
                    "rows": record_count,
                },
            )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "audit.export.created",
                {"export_id": export_id, "format": format, "record_count": record_count},
                source="audit-trail-shard",
            )

        return {
            "export_id": export_id,
            "format": format,
            "record_count": record_count,
            "content": content,
        }

    # ------------------------------------------------------------------
    # manage_retention
    # ------------------------------------------------------------------

    async def manage_retention(self, retention_days: int = 365) -> int:
        """
        Delete audit records older than the retention period.

        Returns count of records deleted.
        """
        if not self._db:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Count first, then delete
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM arkham_audit_trail.actions WHERE timestamp < :cutoff",
            {"cutoff": cutoff},
        )
        count = row["count"] if row else 0

        if count > 0:
            await self._db.execute(
                "DELETE FROM arkham_audit_trail.actions WHERE timestamp < :cutoff",
                {"cutoff": cutoff},
            )
            logger.info(f"Retention: deleted {count} audit records older than {retention_days} days")

        return count

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_csv(self, records: list[dict]) -> str:
        """Format records as CSV string."""
        if not records:
            return ""

        output = io.StringIO()
        fields = ["id", "user_id", "action_type", "shard", "entity_id", "description", "timestamp"]
        writer = csv.writer(output)
        writer.writerow(fields)

        for record in records:
            writer.writerow([self._serialize_value(record.get(f)) for f in fields])

        return output.getvalue()

    def _format_text(self, records: list[dict]) -> str:
        """Format records as human-readable text."""
        if not records:
            return "No audit records found."

        lines = [f"Audit Trail Export - {len(records)} records", "=" * 60]
        for record in records:
            ts = record.get("timestamp", "")
            lines.append(
                f"[{ts}] {record.get('action_type', 'unknown')} | "
                f"shard={record.get('shard', '')} | "
                f"user={record.get('user_id', '')} | "
                f"entity={record.get('entity_id', '')}"
            )
            desc = record.get("description", "")
            if desc:
                lines.append(f"  {desc}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _serialize_value(value: Any) -> str:
        """Serialize a value for CSV/text output."""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
