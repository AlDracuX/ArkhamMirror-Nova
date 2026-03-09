"""Deadlines Shard - Legal deadline tracking with urgency scoring."""

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .models import (
    CaseType,
    Deadline,
    DeadlineFilter,
    DeadlineRule,
    DeadlineStats,
    DeadlineStatus,
    DeadlineType,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)


def _parse_json_field(value: Any, default: Any = None) -> Any:
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return default if default is not None else []


# Pre-defined ET/EAT deadline rules
DEFAULT_RULES = [
    {
        "name": "ET Response to Claim (ET3)",
        "description": "Respondent must file ET3 within 28 days of service of ET1",
        "case_type": "et",
        "deadline_type": "response",
        "days_from_trigger": 28,
        "trigger_event": "ET1 served on respondent",
        "working_days_only": False,
    },
    {
        "name": "ET Disclosure of Documents",
        "description": "Standard disclosure deadline from CMO",
        "case_type": "et",
        "deadline_type": "disclosure",
        "days_from_trigger": 14,
        "trigger_event": "Case management order issued",
        "working_days_only": True,
    },
    {
        "name": "ET Witness Statements Exchange",
        "description": "Exchange witness statements per CMO date",
        "case_type": "et",
        "deadline_type": "witness_statement",
        "days_from_trigger": 28,
        "trigger_event": "Case management order issued",
        "working_days_only": True,
    },
    {
        "name": "EAT Notice of Appeal",
        "description": "Appeal must be lodged within 42 days of judgment sent to parties",
        "case_type": "eat",
        "deadline_type": "appeal",
        "days_from_trigger": 42,
        "trigger_event": "ET judgment sent to parties",
        "working_days_only": False,
    },
    {
        "name": "EAT Skeleton Argument",
        "description": "Skeleton argument due 21 days before EAT hearing",
        "case_type": "eat",
        "deadline_type": "filing",
        "days_from_trigger": -21,
        "trigger_event": "EAT hearing date",
        "working_days_only": True,
    },
    {
        "name": "ET Costs Application",
        "description": "Costs application typically within 28 days of judgment",
        "case_type": "et",
        "deadline_type": "costs",
        "days_from_trigger": 28,
        "trigger_event": "ET judgment issued",
        "working_days_only": False,
    },
    {
        "name": "ET Reconsideration Application",
        "description": "Application for reconsideration within 14 days of judgment sent",
        "case_type": "et",
        "deadline_type": "filing",
        "days_from_trigger": 14,
        "trigger_event": "ET judgment sent to parties",
        "working_days_only": False,
    },
    {
        "name": "ET Strike-Out Response",
        "description": "Response to strike-out application typically 14 days",
        "case_type": "et",
        "deadline_type": "response",
        "days_from_trigger": 14,
        "trigger_event": "Strike-out application received",
        "working_days_only": True,
    },
]


class DeadlinesShard(ArkhamShard):
    """Legal deadline tracking with urgency scoring and countdown."""

    name = "deadlines"
    version = "0.1.0"
    description = "Legal deadline tracking with urgency scoring and countdown"

    def __init__(self):
        super().__init__()
        self._frame = None
        self._db = None
        self._event_bus = None

    async def initialize(self, frame) -> None:
        self._frame = frame
        self.frame = frame
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        await self._create_schema()
        await self._seed_default_rules()
        init_api(shard=self, event_bus=self._event_bus)
        if hasattr(frame, "app") and frame.app:
            frame.app.state.deadlines_shard = self
        logger.info("Deadlines shard initialized")

    async def shutdown(self) -> None:
        logger.info("Deadlines shard shutting down")
        self._db = None
        self._event_bus = None

    def get_routes(self):
        return router

    # === Schema ===

    async def _create_schema(self) -> None:
        await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_deadlines")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_deadlines.deadlines (
                id UUID PRIMARY KEY,
                tenant_id UUID,
                title VARCHAR(500) NOT NULL,
                description TEXT DEFAULT '',
                deadline_date DATE NOT NULL,
                deadline_time TIME,
                deadline_type VARCHAR(50) NOT NULL DEFAULT 'custom',
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                urgency VARCHAR(50) DEFAULT 'future',
                case_type VARCHAR(50) DEFAULT 'et',
                case_reference VARCHAR(500) DEFAULT '',
                source_document VARCHAR(500) DEFAULT '',
                source_order_date DATE,
                rule_reference VARCHAR(500) DEFAULT '',
                auto_calculated BOOLEAN DEFAULT false,
                calculation_base_date DATE,
                calculation_days INT,
                notes TEXT DEFAULT '',
                completed_at TIMESTAMP,
                completed_by VARCHAR(500) DEFAULT '',
                linked_document_ids JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_deadlines.deadline_rules (
                id UUID PRIMARY KEY,
                tenant_id UUID,
                name VARCHAR(500) NOT NULL,
                description TEXT DEFAULT '',
                case_type VARCHAR(50) DEFAULT 'et',
                deadline_type VARCHAR(50) DEFAULT 'custom',
                days_from_trigger INT NOT NULL DEFAULT 14,
                trigger_event VARCHAR(500) DEFAULT '',
                working_days_only BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadlines_tenant_date
            ON arkham_deadlines.deadlines(tenant_id, deadline_date, status)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_deadlines_urgency
            ON arkham_deadlines.deadlines(tenant_id, urgency)
        """)

    async def _seed_default_rules(self) -> None:
        """Seed default rules if none exist for system tenant."""
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")

        row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_deadlines.deadline_rules
            WHERE tenant_id = :tid
        """, {"tid": tenant_id})

        if row and row["cnt"] > 0:
            return

        for rule in DEFAULT_RULES:
            await self._db.execute("""
                INSERT INTO arkham_deadlines.deadline_rules
                (id, tenant_id, name, description, case_type, deadline_type,
                 days_from_trigger, trigger_event, working_days_only)
                VALUES (:id, :tid, :name, :desc, :ct, :dt,
                        :days, :trigger, :wd)
            """, {
                "id": str(uuid.uuid4()),
                "tid": tenant_id,
                "name": rule["name"],
                "desc": rule["description"],
                "ct": rule["case_type"],
                "dt": rule["deadline_type"],
                "days": rule["days_from_trigger"],
                "trigger": rule["trigger_event"],
                "wd": rule["working_days_only"],
            })
        logger.info(f"Seeded {len(DEFAULT_RULES)} default deadline rules")

    # === Urgency Calculation ===

    @staticmethod
    def calculate_urgency(deadline_date: date) -> UrgencyLevel:
        today = date.today()
        days_remaining = (deadline_date - today).days

        if days_remaining < 0:
            return UrgencyLevel.OVERDUE
        elif days_remaining <= 2:
            return UrgencyLevel.CRITICAL
        elif days_remaining <= 7:
            return UrgencyLevel.HIGH
        elif days_remaining <= 14:
            return UrgencyLevel.MEDIUM
        elif days_remaining <= 30:
            return UrgencyLevel.LOW
        else:
            return UrgencyLevel.FUTURE

    @staticmethod
    def add_working_days(start_date: date, days: int) -> date:
        """Add working days (Mon-Fri) to a date."""
        if days == 0:
            return start_date
        direction = 1 if days > 0 else -1
        remaining = abs(days)
        current = start_date
        while remaining > 0:
            current += timedelta(days=direction)
            if current.weekday() < 5:  # Mon=0, Fri=4
                remaining -= 1
        return current

    def calculate_deadline_from_rule(self, rule: DeadlineRule, base_date: date) -> date:
        """Calculate deadline date from a rule and base date."""
        if rule.working_days_only:
            return self.add_working_days(base_date, rule.days_from_trigger)
        return base_date + timedelta(days=rule.days_from_trigger)

    # === Deadline CRUD ===

    async def create_deadline(self, data: Dict[str, Any]) -> Deadline:
        dl_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        dl_date = data.get("deadline_date")
        if isinstance(dl_date, str):
            dl_date = date.fromisoformat(dl_date)

        urgency = self.calculate_urgency(dl_date)

        await self._db.execute("""
            INSERT INTO arkham_deadlines.deadlines
            (id, tenant_id, title, description, deadline_date, deadline_time,
             deadline_type, status, urgency, case_type, case_reference,
             source_document, source_order_date, rule_reference,
             auto_calculated, calculation_base_date, calculation_days,
             notes, linked_document_ids, metadata)
            VALUES (:id, :tid, :title, :desc, :date, :time,
                    :type, :status, :urgency, :ct, :ref,
                    :src_doc, :src_date, :rule_ref,
                    :auto, :calc_base, :calc_days,
                    :notes, :doc_ids, :meta)
        """, {
            "id": dl_id,
            "tid": tenant_id,
            "title": data.get("title", ""),
            "desc": data.get("description", ""),
            "date": dl_date,
            "time": data.get("deadline_time"),
            "type": data.get("deadline_type", "custom"),
            "status": data.get("status", "pending"),
            "urgency": urgency.value,
            "ct": data.get("case_type", "et"),
            "ref": data.get("case_reference", ""),
            "src_doc": data.get("source_document", ""),
            "src_date": data.get("source_order_date"),
            "rule_ref": data.get("rule_reference", ""),
            "auto": data.get("auto_calculated", False),
            "calc_base": data.get("calculation_base_date"),
            "calc_days": data.get("calculation_days"),
            "notes": data.get("notes", ""),
            "doc_ids": json.dumps(data.get("linked_document_ids", [])),
            "meta": json.dumps(data.get("metadata", {})),
        })

        if self._event_bus:
            await self._event_bus.emit("deadlines.deadline.created", {
                "deadline_id": dl_id,
                "title": data.get("title"),
                "deadline_date": str(dl_date),
                "urgency": urgency.value,
            }, source="deadlines-shard")

        return await self.get_deadline(dl_id)

    async def get_deadline(self, dl_id: str) -> Optional[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        row = await self._db.fetch_one("""
            SELECT * FROM arkham_deadlines.deadlines
            WHERE id = :id AND tenant_id = :tid
        """, {"id": dl_id, "tid": tenant_id})
        if not row:
            return None
        return self._row_to_deadline(row)

    async def list_deadlines(self, filters: Optional[DeadlineFilter] = None,
                              limit: int = 100, offset: int = 0) -> List[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        conditions = ["tenant_id = :tid"]
        params: Dict[str, Any] = {"tid": tenant_id}

        if filters:
            if filters.status:
                conditions.append("status = :status")
                params["status"] = filters.status.value
            if filters.deadline_type:
                conditions.append("deadline_type = :dtype")
                params["dtype"] = filters.deadline_type.value
            if filters.case_type:
                conditions.append("case_type = :ctype")
                params["ctype"] = filters.case_type.value
            if filters.urgency:
                conditions.append("urgency = :urgency")
                params["urgency"] = filters.urgency.value
            if filters.from_date:
                conditions.append("deadline_date >= :from_date")
                params["from_date"] = filters.from_date
            if filters.to_date:
                conditions.append("deadline_date <= :to_date")
                params["to_date"] = filters.to_date
            if filters.search_text:
                conditions.append("(title ILIKE :search OR description ILIKE :search OR notes ILIKE :search)")
                params["search"] = f"%{filters.search_text}%"
            if not filters.show_completed:
                conditions.append("status NOT IN ('completed', 'waived')")

        where = " AND ".join(conditions)
        params["limit"] = limit
        params["offset"] = offset

        rows = await self._db.fetch_all(f"""
            SELECT * FROM arkham_deadlines.deadlines
            WHERE {where}
            ORDER BY deadline_date ASC
            LIMIT :limit OFFSET :offset
        """, params)

        return [self._row_to_deadline(r) for r in rows]

    async def get_upcoming(self, days: int = 30) -> List[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        cutoff = date.today() + timedelta(days=days)
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_deadlines.deadlines
            WHERE tenant_id = :tid
              AND deadline_date <= :cutoff
              AND status NOT IN ('completed', 'waived')
            ORDER BY deadline_date ASC
        """, {"tid": tenant_id, "cutoff": cutoff})
        return [self._row_to_deadline(r) for r in rows]

    async def count_upcoming(self) -> int:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        cutoff = date.today() + timedelta(days=30)
        row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_deadlines.deadlines
            WHERE tenant_id = :tid
              AND deadline_date <= :cutoff
              AND status NOT IN ('completed', 'waived')
        """, {"tid": tenant_id, "cutoff": cutoff})
        return row["cnt"] if row else 0

    async def update_deadline(self, dl_id: str, data: Dict[str, Any]) -> Optional[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        sets = ["updated_at = NOW()"]
        params: Dict[str, Any] = {"id": dl_id, "tid": tenant_id}

        simple_fields = [
            "title", "description", "deadline_type", "status", "case_type",
            "case_reference", "source_document", "rule_reference", "notes",
            "completed_by",
        ]
        for f in simple_fields:
            if f in data:
                sets.append(f"{f} = :{f}")
                params[f] = data[f]

        if "deadline_date" in data:
            dl_date = data["deadline_date"]
            if isinstance(dl_date, str):
                dl_date = date.fromisoformat(dl_date)
            sets.append("deadline_date = :dl_date")
            params["dl_date"] = dl_date
            urgency = self.calculate_urgency(dl_date)
            sets.append("urgency = :urgency")
            params["urgency"] = urgency.value

        if "linked_document_ids" in data:
            sets.append("linked_document_ids = :doc_ids")
            params["doc_ids"] = json.dumps(data["linked_document_ids"])

        if "metadata" in data:
            sets.append("metadata = :meta")
            params["meta"] = json.dumps(data["metadata"])

        set_clause = ", ".join(sets)
        await self._db.execute(f"""
            UPDATE arkham_deadlines.deadlines
            SET {set_clause}
            WHERE id = :id AND tenant_id = :tid
        """, params)

        if self._event_bus:
            await self._event_bus.emit("deadlines.deadline.updated", {
                "deadline_id": dl_id,
            }, source="deadlines-shard")

        return await self.get_deadline(dl_id)

    async def complete_deadline(self, dl_id: str, completed_by: str = "") -> Optional[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        await self._db.execute("""
            UPDATE arkham_deadlines.deadlines
            SET status = 'completed', completed_at = NOW(), completed_by = :by, updated_at = NOW()
            WHERE id = :id AND tenant_id = :tid
        """, {"id": dl_id, "tid": tenant_id, "by": completed_by})

        if self._event_bus:
            await self._event_bus.emit("deadlines.deadline.completed", {
                "deadline_id": dl_id,
            }, source="deadlines-shard")

        return await self.get_deadline(dl_id)

    async def extend_deadline(self, dl_id: str, new_date: date, reason: str = "") -> Optional[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        urgency = self.calculate_urgency(new_date)
        await self._db.execute("""
            UPDATE arkham_deadlines.deadlines
            SET deadline_date = :new_date, urgency = :urgency,
                status = 'extended', notes = notes || E'\n[Extended] ' || :reason,
                updated_at = NOW()
            WHERE id = :id AND tenant_id = :tid
        """, {"id": dl_id, "tid": tenant_id, "new_date": new_date,
              "urgency": urgency.value, "reason": reason})
        return await self.get_deadline(dl_id)

    async def delete_deadline(self, dl_id: str) -> bool:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        await self._db.execute("""
            DELETE FROM arkham_deadlines.deadlines
            WHERE id = :id AND tenant_id = :tid
        """, {"id": dl_id, "tid": tenant_id})
        return True

    # === Breach Detection ===

    async def check_breaches(self) -> List[Deadline]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        today = date.today()

        # Find overdue, non-completed deadlines
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_deadlines.deadlines
            WHERE tenant_id = :tid
              AND deadline_date < :today
              AND status IN ('pending', 'in_progress')
        """, {"tid": tenant_id, "today": today})

        breached = []
        for row in rows:
            dl_id = str(row["id"])
            await self._db.execute("""
                UPDATE arkham_deadlines.deadlines
                SET status = 'breached', urgency = 'overdue', updated_at = NOW()
                WHERE id = :id AND tenant_id = :tid
            """, {"id": dl_id, "tid": tenant_id})

            if self._event_bus:
                await self._event_bus.emit("deadlines.deadline.breached", {
                    "deadline_id": dl_id,
                    "title": row["title"],
                    "deadline_date": str(row["deadline_date"]),
                }, source="deadlines-shard")

            breached.append(self._row_to_deadline(row))

        return breached

    # === Urgency Refresh ===

    async def refresh_urgencies(self) -> int:
        """Recalculate urgency for all active deadlines."""
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        rows = await self._db.fetch_all("""
            SELECT id, deadline_date FROM arkham_deadlines.deadlines
            WHERE tenant_id = :tid AND status IN ('pending', 'in_progress')
        """, {"tid": tenant_id})

        count = 0
        for row in rows:
            urgency = self.calculate_urgency(row["deadline_date"])
            await self._db.execute("""
                UPDATE arkham_deadlines.deadlines
                SET urgency = :urgency, updated_at = NOW()
                WHERE id = :id
            """, {"id": str(row["id"]), "urgency": urgency.value})
            count += 1
        return count

    # === Rules ===

    async def list_rules(self) -> List[DeadlineRule]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_deadlines.deadline_rules
            WHERE tenant_id = :tid ORDER BY case_type, name
        """, {"tid": tenant_id})
        return [self._row_to_rule(r) for r in rows]

    async def create_rule(self, data: Dict[str, Any]) -> DeadlineRule:
        rule_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        await self._db.execute("""
            INSERT INTO arkham_deadlines.deadline_rules
            (id, tenant_id, name, description, case_type, deadline_type,
             days_from_trigger, trigger_event, working_days_only)
            VALUES (:id, :tid, :name, :desc, :ct, :dt,
                    :days, :trigger, :wd)
        """, {
            "id": rule_id, "tid": tenant_id,
            "name": data.get("name", ""),
            "desc": data.get("description", ""),
            "ct": data.get("case_type", "et"),
            "dt": data.get("deadline_type", "custom"),
            "days": data.get("days_from_trigger", 14),
            "trigger": data.get("trigger_event", ""),
            "wd": data.get("working_days_only", True),
        })
        return DeadlineRule(id=rule_id, name=data.get("name", ""))

    async def calculate_from_rule(self, rule_id: str, base_date: date) -> Dict[str, Any]:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        row = await self._db.fetch_one("""
            SELECT * FROM arkham_deadlines.deadline_rules
            WHERE id = :id AND tenant_id = :tid
        """, {"id": rule_id, "tid": tenant_id})
        if not row:
            return {"error": "Rule not found"}

        rule = self._row_to_rule(row)
        calculated_date = self.calculate_deadline_from_rule(rule, base_date)
        urgency = self.calculate_urgency(calculated_date)

        return {
            "rule_name": rule.name,
            "base_date": str(base_date),
            "calculated_date": str(calculated_date),
            "days": rule.days_from_trigger,
            "working_days_only": rule.working_days_only,
            "urgency": urgency.value,
        }

    # === ICS Export ===

    async def export_ics(self, deadline_ids: Optional[List[str]] = None) -> str:
        if deadline_ids:
            deadlines = []
            for did in deadline_ids:
                dl = await self.get_deadline(did)
                if dl:
                    deadlines.append(dl)
        else:
            deadlines = await self.get_upcoming(days=90)

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ArkhamMirror-Nova//Deadlines//EN",
            "CALSCALE:GREGORIAN",
        ]

        for dl in deadlines:
            dl_date_str = dl.deadline_date.strftime("%Y%m%d")
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{dl.id}@arkham-nova",
                f"DTSTART;VALUE=DATE:{dl_date_str}",
                f"SUMMARY:{dl.title}",
                f"DESCRIPTION:{dl.description or dl.notes}",
                f"CATEGORIES:{dl.case_type},{dl.deadline_type}",
                "BEGIN:VALARM",
                "TRIGGER:-P1D",
                "ACTION:DISPLAY",
                f"DESCRIPTION:Deadline tomorrow: {dl.title}",
                "END:VALARM",
                "END:VEVENT",
            ])

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    # === Stats ===

    async def get_stats(self) -> DeadlineStats:
        tenant_id = str(self.get_tenant_id_or_none() or "00000000-0000-0000-0000-000000000000")
        rows = await self._db.fetch_all("""
            SELECT status, urgency, case_type, COUNT(*) as cnt
            FROM arkham_deadlines.deadlines
            WHERE tenant_id = :tid
            GROUP BY status, urgency, case_type
        """, {"tid": tenant_id})

        stats = DeadlineStats()
        for r in rows:
            stats.total += r["cnt"]
            if r["status"] == "pending":
                stats.pending += r["cnt"]
            elif r["status"] == "breached":
                stats.breached += r["cnt"]
            elif r["status"] == "completed":
                stats.completed += r["cnt"]
            stats.by_urgency[r["urgency"]] = stats.by_urgency.get(r["urgency"], 0) + r["cnt"]
            stats.by_case_type[r["case_type"]] = stats.by_case_type.get(r["case_type"], 0) + r["cnt"]

        # Next deadline
        next_row = await self._db.fetch_one("""
            SELECT * FROM arkham_deadlines.deadlines
            WHERE tenant_id = :tid AND status IN ('pending', 'in_progress')
            ORDER BY deadline_date ASC LIMIT 1
        """, {"tid": tenant_id})
        if next_row:
            stats.next_deadline = {
                "id": str(next_row["id"]),
                "title": next_row["title"],
                "deadline_date": str(next_row["deadline_date"]),
                "urgency": next_row["urgency"],
            }

        return stats

    # === Row Mapping ===

    def _row_to_deadline(self, row: Dict[str, Any]) -> Deadline:
        dl_date = row["deadline_date"]
        return Deadline(
            id=str(row["id"]),
            title=row["title"],
            deadline_date=dl_date,
            deadline_type=row.get("deadline_type", "custom"),
            status=row.get("status", "pending"),
            urgency=self.calculate_urgency(dl_date) if dl_date else UrgencyLevel.FUTURE,
            description=row.get("description", ""),
            deadline_time=row.get("deadline_time"),
            case_type=row.get("case_type", "et"),
            case_reference=row.get("case_reference", ""),
            source_document=row.get("source_document", ""),
            source_order_date=row.get("source_order_date"),
            rule_reference=row.get("rule_reference", ""),
            auto_calculated=row.get("auto_calculated", False),
            calculation_base_date=row.get("calculation_base_date"),
            calculation_days=row.get("calculation_days"),
            notes=row.get("notes", ""),
            completed_at=row.get("completed_at"),
            completed_by=row.get("completed_by", ""),
            linked_document_ids=_parse_json_field(row.get("linked_document_ids"), []),
            created_at=row.get("created_at", datetime.utcnow()),
            updated_at=row.get("updated_at", datetime.utcnow()),
            metadata=_parse_json_field(row.get("metadata"), {}),
        )

    def _row_to_rule(self, row: Dict[str, Any]) -> DeadlineRule:
        return DeadlineRule(
            id=str(row["id"]),
            name=row["name"],
            description=row.get("description", ""),
            case_type=row.get("case_type", "et"),
            deadline_type=row.get("deadline_type", "custom"),
            days_from_trigger=row.get("days_from_trigger", 14),
            trigger_event=row.get("trigger_event", ""),
            working_days_only=row.get("working_days_only", True),
            created_at=row.get("created_at", datetime.utcnow()),
        )
