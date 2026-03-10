"""CostsEngine - Domain logic for costs aggregation, scoring, and application building.

Handles:
- Time entry aggregation with hourly rate calculation
- Expense rollup by category
- Conduct scoring for Rule 76 costs basis strength
- Costs application assembly from linked records
- Schedule of Costs document generation
- Automatic conduct logging from upstream events
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Severity weights for Rule 76 conduct scoring
SEVERITY_WEIGHTS: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 5,
}

# Costs basis strength thresholds (based on total weighted score)
STRENGTH_THRESHOLDS: list[tuple[int, str]] = [
    (20, "strong"),
    (10, "high"),
    (5, "medium"),
    (0, "low"),
]


def _costs_basis_strength(total_score: int) -> str:
    """Map a total conduct score to a costs basis strength label."""
    for threshold, label in STRENGTH_THRESHOLDS:
        if total_score >= threshold:
            return label
    return "low"


class CostsEngine:
    """Domain engine for costs calculations and application building."""

    def __init__(self, db, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Time aggregation
    # ------------------------------------------------------------------

    async def aggregate_time(self, project_id: str, hourly_rate: float = 0.0) -> dict[str, Any]:
        """Sum time_entries for a project.

        Returns:
            dict with total_minutes, total_hours, total_cost, entries_count.
        """
        rows = await self._db.fetch_all(
            "SELECT duration_minutes FROM arkham_costs.time_entries WHERE project_id = :project_id",
            {"project_id": project_id},
        )

        total_minutes = sum(row["duration_minutes"] for row in rows)
        total_hours = total_minutes / 60.0
        total_cost = total_hours * hourly_rate

        return {
            "project_id": project_id,
            "total_minutes": total_minutes,
            "total_hours": round(total_hours, 2),
            "total_cost": round(total_cost, 2),
            "hourly_rate": hourly_rate,
            "entries_count": len(rows),
        }

    # ------------------------------------------------------------------
    # Expense rollup
    # ------------------------------------------------------------------

    async def rollup_expenses(self, project_id: str) -> dict[str, Any]:
        """Sum expenses for a project, grouped by category (description field used as category proxy).

        Returns:
            dict with total_amount, currency, items_count, by_category.
        """
        rows = await self._db.fetch_all(
            "SELECT description, amount, currency FROM arkham_costs.expenses WHERE project_id = :project_id",
            {"project_id": project_id},
        )

        total_amount = 0.0
        by_category: dict[str, float] = {}
        currency = "GBP"

        for row in rows:
            amount = float(row["amount"])
            total_amount += amount
            cat = row.get("description", "other")
            by_category[cat] = by_category.get(cat, 0.0) + amount
            if row.get("currency"):
                currency = row["currency"]

        return {
            "project_id": project_id,
            "total_amount": round(total_amount, 2),
            "currency": currency,
            "items_count": len(rows),
            "by_category": {k: round(v, 2) for k, v in by_category.items()},
        }

    # ------------------------------------------------------------------
    # Conduct scoring (Rule 76)
    # ------------------------------------------------------------------

    async def score_conduct(self, project_id: str) -> dict[str, Any]:
        """Score conduct log entries for Rule 76 costs basis strength.

        severity_weights: low=1, medium=2, high=3, critical=5
        Frequency multiplier: count of entries per conduct_type.

        Returns:
            dict with total_score, conduct_count, by_type, costs_basis_strength.
        """
        rows = await self._db.fetch_all(
            "SELECT conduct_type, significance FROM arkham_costs.conduct_log WHERE project_id = :project_id",
            {"project_id": project_id},
        )

        by_type: dict[str, dict[str, Any]] = {}
        total_score = 0

        for row in rows:
            ctype = row["conduct_type"]
            severity = row.get("significance", "medium")
            weight = SEVERITY_WEIGHTS.get(severity, 2)

            if ctype not in by_type:
                by_type[ctype] = {"count": 0, "total_weight": 0}
            by_type[ctype]["count"] += 1
            by_type[ctype]["total_weight"] += weight

        # Apply frequency multiplier: score = sum(weight) * count per type
        for ctype, info in by_type.items():
            type_score = info["total_weight"] * info["count"]
            info["score"] = type_score
            total_score += type_score

        return {
            "project_id": project_id,
            "total_score": total_score,
            "conduct_count": len(rows),
            "by_type": by_type,
            "costs_basis_strength": _costs_basis_strength(total_score),
        }

    # ------------------------------------------------------------------
    # Application building
    # ------------------------------------------------------------------

    async def build_application(self, application_id: str) -> dict[str, Any]:
        """Assemble a costs application from linked conduct_ids, time_entry_ids, expense_ids.

        Calculates total_amount_claimed and generates a structured summary.

        Returns:
            Updated application dict.
        """
        app_row = await self._db.fetch_one(
            "SELECT * FROM arkham_costs.applications WHERE id = :id",
            {"id": application_id},
        )
        if not app_row:
            return {"error": "Application not found", "application_id": application_id}

        app = dict(app_row)
        project_id = app.get("project_id", "")

        # Parse JSONB arrays
        time_entry_ids = (
            json.loads(app["time_entry_ids"])
            if isinstance(app["time_entry_ids"], str)
            else (app["time_entry_ids"] or [])
        )
        expense_ids = (
            json.loads(app["expense_ids"]) if isinstance(app["expense_ids"], str) else (app["expense_ids"] or [])
        )
        conduct_ids = (
            json.loads(app["conduct_ids"]) if isinstance(app["conduct_ids"], str) else (app["conduct_ids"] or [])
        )

        # Sum time costs
        time_cost = 0.0
        if time_entry_ids:
            for tid in time_entry_ids:
                row = await self._db.fetch_one(
                    "SELECT duration_minutes, hourly_rate FROM arkham_costs.time_entries WHERE id = :id",
                    {"id": tid},
                )
                if row:
                    rate = float(row.get("hourly_rate") or 0.0)
                    minutes = int(row.get("duration_minutes") or 0)
                    time_cost += (minutes / 60.0) * rate

        # Sum expenses
        expense_total = 0.0
        if expense_ids:
            for eid in expense_ids:
                row = await self._db.fetch_one(
                    "SELECT amount FROM arkham_costs.expenses WHERE id = :id",
                    {"id": eid},
                )
                if row:
                    expense_total += float(row["amount"])

        total_claimed = round(time_cost + expense_total, 2)

        # Update the application record
        await self._db.execute(
            "UPDATE arkham_costs.applications SET total_amount_claimed = :total, updated_at = :now WHERE id = :id",
            {"total": total_claimed, "now": datetime.utcnow(), "id": application_id},
        )

        app["total_amount_claimed"] = total_claimed
        app["time_cost"] = round(time_cost, 2)
        app["expense_total"] = round(expense_total, 2)
        app["conduct_count"] = len(conduct_ids)

        return app

    # ------------------------------------------------------------------
    # Schedule generation
    # ------------------------------------------------------------------

    async def generate_schedule(self, application_id: str) -> str:
        """Render a Schedule of Costs document (plain text) with line items, subtotals, and grand total."""
        app_row = await self._db.fetch_one(
            "SELECT * FROM arkham_costs.applications WHERE id = :id",
            {"id": application_id},
        )
        if not app_row:
            return f"ERROR: Application {application_id} not found."

        app = dict(app_row)
        title = app.get("title", "Costs Application")

        time_entry_ids = (
            json.loads(app["time_entry_ids"])
            if isinstance(app["time_entry_ids"], str)
            else (app["time_entry_ids"] or [])
        )
        expense_ids = (
            json.loads(app["expense_ids"]) if isinstance(app["expense_ids"], str) else (app["expense_ids"] or [])
        )

        lines: list[str] = []
        lines.append("=" * 60)
        lines.append(f"SCHEDULE OF COSTS - {title.upper()}")
        lines.append("=" * 60)
        lines.append("")

        # Time entries section
        time_subtotal = 0.0
        if time_entry_ids:
            lines.append("SECTION A: TIME COSTS")
            lines.append("-" * 40)
            for i, tid in enumerate(time_entry_ids, 1):
                row = await self._db.fetch_one(
                    "SELECT activity, duration_minutes, hourly_rate FROM arkham_costs.time_entries WHERE id = :id",
                    {"id": tid},
                )
                if row:
                    rate = float(row.get("hourly_rate") or 0.0)
                    minutes = int(row.get("duration_minutes") or 0)
                    cost = round((minutes / 60.0) * rate, 2)
                    time_subtotal += cost
                    lines.append(f"  {i}. {row['activity']} ({minutes} min @ {rate}/hr) ... {cost:.2f}")
            lines.append(f"  SUBTOTAL TIME COSTS: {time_subtotal:.2f}")
            lines.append("")

        # Expenses section
        expense_subtotal = 0.0
        if expense_ids:
            lines.append("SECTION B: EXPENSES")
            lines.append("-" * 40)
            for i, eid in enumerate(expense_ids, 1):
                row = await self._db.fetch_one(
                    "SELECT description, amount FROM arkham_costs.expenses WHERE id = :id",
                    {"id": eid},
                )
                if row:
                    amount = float(row["amount"])
                    expense_subtotal += amount
                    lines.append(f"  {i}. {row['description']} ... {amount:.2f}")
            lines.append(f"  SUBTOTAL EXPENSES: {expense_subtotal:.2f}")
            lines.append("")

        # Grand total
        grand_total = round(time_subtotal + expense_subtotal, 2)
        lines.append("=" * 60)
        lines.append(f"GRAND TOTAL: {grand_total:.2f}")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Auto-log conduct from upstream events
    # ------------------------------------------------------------------

    async def auto_log_conduct_from_event(self, event_type: str, event_data: dict[str, Any]) -> str | None:
        """Automatically create a conduct_log entry from upstream events.

        Handles event types:
        - disclosure.evasion.scored
        - rules.breach.detected
        - deadlines.breach.detected

        Returns:
            conduct_log id or None if event is not actionable.
        """
        mapping: dict[str, dict[str, str]] = {
            "disclosure.evasion.scored": {
                "conduct_type": "evasion",
                "significance": "high",
                "description": "Evasion of disclosure obligations detected",
                "legal_reference": "Rule 76(1)(a)",
            },
            "rules.breach.detected": {
                "conduct_type": "breach_of_order",
                "significance": "high",
                "description": "Breach of tribunal rules detected",
                "legal_reference": "Rule 76(1)(b)",
            },
            "deadlines.breach.detected": {
                "conduct_type": "delay",
                "significance": "medium",
                "description": "Failure to comply with deadline",
                "legal_reference": "Rule 76(1)(a)",
            },
        }

        config = mapping.get(event_type)
        if not config:
            return None

        log_id = str(uuid.uuid4())
        party_name = event_data.get("party_name", event_data.get("respondent", "Respondent"))
        project_id = event_data.get("project_id", event_data.get("case_id", ""))
        occurred_at = event_data.get("occurred_at", datetime.utcnow().isoformat())

        # Override significance if event provides a score
        significance = config["significance"]
        if event_data.get("severity"):
            significance = event_data["severity"]
        if event_data.get("score", 0) >= 8:
            significance = "critical"

        description = config["description"]
        if event_data.get("description"):
            description = f"{config['description']}: {event_data['description']}"

        await self._db.execute(
            """
            INSERT INTO arkham_costs.conduct_log
            (id, party_name, conduct_type, description, occurred_at, significance, legal_reference, project_id, created_by)
            VALUES (:id, :party_name, :conduct_type, :description, :occurred_at, :significance, :legal_reference, :project_id, :created_by)
            """,
            {
                "id": log_id,
                "party_name": party_name,
                "conduct_type": config["conduct_type"],
                "description": description,
                "occurred_at": occurred_at,
                "significance": significance,
                "legal_reference": config["legal_reference"],
                "project_id": project_id,
                "created_by": "system:event:" + event_type,
            },
        )

        # Emit downstream event
        if self._event_bus:
            await self._event_bus.emit(
                "costs.conduct.logged",
                {"log_id": log_id, "source_event": event_type, "party": party_name},
                source="costs-shard",
            )

        logger.info(f"Auto-logged conduct {log_id} from {event_type}")
        return log_id
