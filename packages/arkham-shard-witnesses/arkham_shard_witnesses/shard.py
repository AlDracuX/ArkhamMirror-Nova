"""Witnesses Shard - Witness management and credibility tracking."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .models import (
    CredibilityLevel,
    CrossExamNote,
    Party,
    StatementStatus,
    Witness,
    WitnessFilter,
    WitnessRole,
    WitnessStatement,
    WitnessStats,
    WitnessStatus,
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


class WitnessesShard(ArkhamShard):
    """Witness management and credibility tracking shard."""

    name = "witnesses"
    version = "0.1.0"
    description = "Witness management and credibility tracking for litigation"

    async def initialize(self, frame) -> None:
        self.frame = frame
        self._db = frame.database
        await self._create_schema()
        await self._subscribe_events()
        init_api(shard=self, event_bus=frame.events)
        logger.info("Witnesses shard initialized")

    async def shutdown(self) -> None:
        logger.info("Witnesses shard shutting down")

    def get_routes(self):
        return router

    # === Schema ===

    async def _create_schema(self) -> None:
        await self._db.execute("""
            CREATE SCHEMA IF NOT EXISTS arkham_witnesses
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_witnesses.witnesses (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                name VARCHAR(500) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'claimant',
                status VARCHAR(50) NOT NULL DEFAULT 'identified',
                party VARCHAR(50) NOT NULL DEFAULT 'claimant',
                organization VARCHAR(500),
                position VARCHAR(500),
                contact_info JSONB DEFAULT '{}',
                notes TEXT DEFAULT '',
                credibility_level VARCHAR(50) DEFAULT 'unknown',
                credibility_notes TEXT DEFAULT '',
                linked_entity_id UUID,
                linked_document_ids JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_witnesses.witness_statements (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                witness_id UUID NOT NULL REFERENCES arkham_witnesses.witnesses(id) ON DELETE CASCADE,
                version INT NOT NULL DEFAULT 1,
                title VARCHAR(500) DEFAULT '',
                content TEXT DEFAULT '',
                status VARCHAR(50) NOT NULL DEFAULT 'draft',
                key_points JSONB DEFAULT '[]',
                contradictions_found JSONB DEFAULT '[]',
                filed_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_witnesses.cross_exam_notes (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                witness_id UUID NOT NULL REFERENCES arkham_witnesses.witnesses(id) ON DELETE CASCADE,
                statement_id UUID,
                topic VARCHAR(500) DEFAULT '',
                question TEXT DEFAULT '',
                expected_answer TEXT DEFAULT '',
                actual_answer TEXT DEFAULT '',
                effectiveness VARCHAR(50) DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_witnesses_tenant
            ON arkham_witnesses.witnesses(tenant_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_witnesses_tenant_party
            ON arkham_witnesses.witnesses(tenant_id, party)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_statements_witness
            ON arkham_witnesses.witness_statements(witness_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_cross_exam_witness
            ON arkham_witnesses.cross_exam_notes(witness_id)
        """)

    # === Events ===

    async def _subscribe_events(self) -> None:
        try:
            await self.frame.events.subscribe("entity.created", self._handle_entity_created)
            await self.frame.events.subscribe("credibility.scored", self._handle_credibility_scored)
            await self.frame.events.subscribe("contradictions.found", self._handle_contradiction_found)
        except Exception as e:
            logger.debug(f"Event subscription skipped: {e}")

    async def _handle_entity_created(self, event: Dict[str, Any]) -> None:
        logger.debug(f"Entity created event received: {event}")

    async def _handle_credibility_scored(self, event: Dict[str, Any]) -> None:
        logger.debug(f"Credibility scored event received: {event}")

    async def _handle_contradiction_found(self, event: Dict[str, Any]) -> None:
        logger.debug(f"Contradiction found event received: {event}")

    # === Witness CRUD ===

    async def create_witness(self, data: Dict[str, Any]) -> Witness:
        witness_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id())
        now = datetime.utcnow()

        await self._db.execute("""
            INSERT INTO arkham_witnesses.witnesses
            (id, tenant_id, name, role, status, party, organization, position,
             contact_info, notes, credibility_level, credibility_notes,
             linked_entity_id, linked_document_ids, created_at, updated_at, metadata)
            VALUES (:id, :tenant_id, :name, :role, :status, :party,
                    :organization, :position, :contact_info, :notes,
                    :credibility_level, :credibility_notes, :linked_entity_id,
                    :linked_document_ids, :created_at, :updated_at, :metadata)
        """, {
            "id": witness_id,
            "tenant_id": tenant_id,
            "name": data.get("name", ""),
            "role": data.get("role", WitnessRole.CLAIMANT.value),
            "status": data.get("status", WitnessStatus.IDENTIFIED.value),
            "party": data.get("party", Party.CLAIMANT.value),
            "organization": data.get("organization"),
            "position": data.get("position"),
            "contact_info": json.dumps(data.get("contact_info", {})),
            "notes": data.get("notes", ""),
            "credibility_level": data.get("credibility_level", CredibilityLevel.UNKNOWN.value),
            "credibility_notes": data.get("credibility_notes", ""),
            "linked_entity_id": data.get("linked_entity_id"),
            "linked_document_ids": json.dumps(data.get("linked_document_ids", [])),
            "created_at": now,
            "updated_at": now,
            "metadata": json.dumps(data.get("metadata", {})),
        })

        await self.frame.events.emit("witnesses.witness.created", {
            "witness_id": witness_id,
            "name": data.get("name"),
            "role": data.get("role", "claimant"),
        }, source="witnesses-shard")

        return await self.get_witness(witness_id)

    async def get_witness(self, witness_id: str) -> Optional[Witness]:
        tenant_id = str(self.get_tenant_id())
        row = await self._db.fetch_one("""
            SELECT * FROM arkham_witnesses.witnesses
            WHERE id = :id AND tenant_id = :tenant_id
        """, {"id": witness_id, "tenant_id": tenant_id})

        if not row:
            return None
        return self._row_to_witness(row)

    async def list_witnesses(self, filters: Optional[WitnessFilter] = None,
                              limit: int = 100, offset: int = 0) -> List[Witness]:
        tenant_id = str(self.get_tenant_id())
        conditions = ["tenant_id = :tenant_id"]
        params: Dict[str, Any] = {"tenant_id": tenant_id}

        if filters:
            if filters.role:
                conditions.append("role = :role")
                params["role"] = filters.role.value
            if filters.status:
                conditions.append("status = :status")
                params["status"] = filters.status.value
            if filters.party:
                conditions.append("party = :party")
                params["party"] = filters.party.value
            if filters.credibility_level:
                conditions.append("credibility_level = :cred")
                params["cred"] = filters.credibility_level.value
            if filters.search_text:
                conditions.append("(name ILIKE :search OR notes ILIKE :search OR organization ILIKE :search)")
                params["search"] = f"%{filters.search_text}%"

        where = " AND ".join(conditions)
        params["limit"] = limit
        params["offset"] = offset

        rows = await self._db.fetch_all(f"""
            SELECT * FROM arkham_witnesses.witnesses
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """, params)

        return [self._row_to_witness(r) for r in rows]

    async def count_witnesses(self) -> int:
        tenant_id = str(self.get_tenant_id())
        row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_witnesses.witnesses
            WHERE tenant_id = :tenant_id
        """, {"tenant_id": tenant_id})
        return row["cnt"] if row else 0

    async def update_witness(self, witness_id: str, data: Dict[str, Any]) -> Optional[Witness]:
        tenant_id = str(self.get_tenant_id())
        sets = ["updated_at = NOW()"]
        params: Dict[str, Any] = {"id": witness_id, "tenant_id": tenant_id}

        field_map = {
            "name": "name", "role": "role", "status": "status", "party": "party",
            "organization": "organization", "position": "position", "notes": "notes",
            "credibility_level": "credibility_level", "credibility_notes": "credibility_notes",
            "linked_entity_id": "linked_entity_id",
        }
        for key, col in field_map.items():
            if key in data:
                sets.append(f"{col} = :{key}")
                params[key] = data[key]

        if "contact_info" in data:
            sets.append("contact_info = :contact_info")
            params["contact_info"] = json.dumps(data["contact_info"])
        if "linked_document_ids" in data:
            sets.append("linked_document_ids = :linked_document_ids")
            params["linked_document_ids"] = json.dumps(data["linked_document_ids"])
        if "metadata" in data:
            sets.append("metadata = :metadata")
            params["metadata"] = json.dumps(data["metadata"])

        set_clause = ", ".join(sets)
        await self._db.execute(f"""
            UPDATE arkham_witnesses.witnesses
            SET {set_clause}
            WHERE id = :id AND tenant_id = :tenant_id
        """, params)

        await self.frame.events.emit("witnesses.witness.updated", {
            "witness_id": witness_id,
        }, source="witnesses-shard")

        return await self.get_witness(witness_id)

    async def delete_witness(self, witness_id: str) -> bool:
        tenant_id = str(self.get_tenant_id())
        await self._db.execute("""
            DELETE FROM arkham_witnesses.witnesses
            WHERE id = :id AND tenant_id = :tenant_id
        """, {"id": witness_id, "tenant_id": tenant_id})

        await self.frame.events.emit("witnesses.witness.deleted", {
            "witness_id": witness_id,
        }, source="witnesses-shard")
        return True

    # === Statements ===

    async def add_statement(self, witness_id: str, data: Dict[str, Any]) -> WitnessStatement:
        stmt_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id())

        # Auto-increment version
        row = await self._db.fetch_one("""
            SELECT COALESCE(MAX(version), 0) + 1 as next_ver
            FROM arkham_witnesses.witness_statements
            WHERE witness_id = :wid AND tenant_id = :tid
        """, {"wid": witness_id, "tid": tenant_id})
        version = row["next_ver"] if row else 1

        await self._db.execute("""
            INSERT INTO arkham_witnesses.witness_statements
            (id, tenant_id, witness_id, version, title, content, status,
             key_points, contradictions_found, filed_date, created_at, updated_at)
            VALUES (:id, :tid, :wid, :version, :title, :content,
                    :status, :key_points, :contradictions, :filed_date,
                    NOW(), NOW())
        """, {
            "id": stmt_id,
            "tid": tenant_id,
            "wid": witness_id,
            "version": version,
            "title": data.get("title", ""),
            "content": data.get("content", ""),
            "status": data.get("status", StatementStatus.DRAFT.value),
            "key_points": json.dumps(data.get("key_points", [])),
            "contradictions": json.dumps(data.get("contradictions_found", [])),
            "filed_date": data.get("filed_date"),
        })

        # Update witness status
        await self._db.execute("""
            UPDATE arkham_witnesses.witnesses
            SET status = 'statement_taken', updated_at = NOW()
            WHERE id = :wid AND tenant_id = :tid
        """, {"wid": witness_id, "tid": tenant_id})

        await self.frame.events.emit("witnesses.statement.added", {
            "witness_id": witness_id,
            "statement_id": stmt_id,
            "version": version,
        }, source="witnesses-shard")

        return await self.get_statement(stmt_id)

    async def get_statement(self, statement_id: str) -> Optional[WitnessStatement]:
        tenant_id = str(self.get_tenant_id())
        row = await self._db.fetch_one("""
            SELECT * FROM arkham_witnesses.witness_statements
            WHERE id = :id AND tenant_id = :tid
        """, {"id": statement_id, "tid": tenant_id})
        if not row:
            return None
        return self._row_to_statement(row)

    async def list_statements(self, witness_id: str) -> List[WitnessStatement]:
        tenant_id = str(self.get_tenant_id())
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_witnesses.witness_statements
            WHERE witness_id = :wid AND tenant_id = :tid
            ORDER BY version DESC
        """, {"wid": witness_id, "tid": tenant_id})
        return [self._row_to_statement(r) for r in rows]

    async def update_statement(self, statement_id: str, data: Dict[str, Any]) -> Optional[WitnessStatement]:
        tenant_id = str(self.get_tenant_id())
        sets = ["updated_at = NOW()"]
        params: Dict[str, Any] = {"id": statement_id, "tid": tenant_id}

        for key in ["title", "content", "status"]:
            if key in data:
                sets.append(f"{key} = :{key}")
                params[key] = data[key]
        if "key_points" in data:
            sets.append("key_points = :kp")
            params["kp"] = json.dumps(data["key_points"])
        if "contradictions_found" in data:
            sets.append("contradictions_found = :cf")
            params["cf"] = json.dumps(data["contradictions_found"])
        if "filed_date" in data:
            sets.append("filed_date = :fd")
            params["fd"] = data["filed_date"]

        set_clause = ", ".join(sets)
        await self._db.execute(f"""
            UPDATE arkham_witnesses.witness_statements
            SET {set_clause}
            WHERE id = :id AND tenant_id = :tid
        """, params)

        await self.frame.events.emit("witnesses.statement.updated", {
            "statement_id": statement_id,
        }, source="witnesses-shard")

        return await self.get_statement(statement_id)

    # === Cross Examination Notes ===

    async def add_cross_exam_note(self, witness_id: str, data: Dict[str, Any]) -> CrossExamNote:
        note_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id())

        await self._db.execute("""
            INSERT INTO arkham_witnesses.cross_exam_notes
            (id, tenant_id, witness_id, statement_id, topic, question,
             expected_answer, actual_answer, effectiveness, notes, created_at)
            VALUES (:id, :tid, :wid, :sid, :topic, :question,
                    :expected, :actual, :effectiveness, :notes, NOW())
        """, {
            "id": note_id,
            "tid": tenant_id,
            "wid": witness_id,
            "sid": data.get("statement_id"),
            "topic": data.get("topic", ""),
            "question": data.get("question", ""),
            "expected": data.get("expected_answer", ""),
            "actual": data.get("actual_answer", ""),
            "effectiveness": data.get("effectiveness", ""),
            "notes": data.get("notes", ""),
        })
        return CrossExamNote(
            id=note_id, witness_id=witness_id,
            statement_id=data.get("statement_id"),
            topic=data.get("topic", ""),
            question=data.get("question", ""),
            expected_answer=data.get("expected_answer", ""),
            actual_answer=data.get("actual_answer", ""),
            effectiveness=data.get("effectiveness", ""),
            notes=data.get("notes", ""),
        )

    async def list_cross_exam_notes(self, witness_id: str) -> List[CrossExamNote]:
        tenant_id = str(self.get_tenant_id())
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_witnesses.cross_exam_notes
            WHERE witness_id = :wid AND tenant_id = :tid
            ORDER BY created_at DESC
        """, {"wid": witness_id, "tid": tenant_id})
        return [self._row_to_cross_exam(r) for r in rows]

    # === Entity Linking ===

    async def link_entity(self, witness_id: str, entity_id: str) -> Optional[Witness]:
        return await self.update_witness(witness_id, {"linked_entity_id": entity_id})

    # === Summary ===

    async def get_witness_summary(self, witness_id: str) -> Dict[str, Any]:
        tenant_id = str(self.get_tenant_id())
        witness = await self.get_witness(witness_id)
        if not witness:
            return {}

        stmt_row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_witnesses.witness_statements
            WHERE witness_id = :wid AND tenant_id = :tid
        """, {"wid": witness_id, "tid": tenant_id})

        note_row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_witnesses.cross_exam_notes
            WHERE witness_id = :wid AND tenant_id = :tid
        """, {"wid": witness_id, "tid": tenant_id})

        return {
            "witness_id": witness_id,
            "name": witness.name,
            "role": witness.role,
            "party": witness.party,
            "credibility_level": witness.credibility_level,
            "statement_count": stmt_row["cnt"] if stmt_row else 0,
            "cross_exam_note_count": note_row["cnt"] if note_row else 0,
        }

    # === Stats ===

    async def get_stats(self) -> WitnessStats:
        tenant_id = str(self.get_tenant_id())
        rows = await self._db.fetch_all("""
            SELECT role, status, party, COUNT(*) as cnt
            FROM arkham_witnesses.witnesses
            WHERE tenant_id = :tid
            GROUP BY role, status, party
        """, {"tid": tenant_id})

        stats = WitnessStats()
        for r in rows:
            stats.total_witnesses += r["cnt"]
            stats.by_role[r["role"]] = stats.by_role.get(r["role"], 0) + r["cnt"]
            stats.by_status[r["status"]] = stats.by_status.get(r["status"], 0) + r["cnt"]
            stats.by_party[r["party"]] = stats.by_party.get(r["party"], 0) + r["cnt"]

        stmt_row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_witnesses.witness_statements
            WHERE tenant_id = :tid
        """, {"tid": tenant_id})
        stats.total_statements = stmt_row["cnt"] if stmt_row else 0

        note_row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_witnesses.cross_exam_notes
            WHERE tenant_id = :tid
        """, {"tid": tenant_id})
        stats.total_cross_exam_notes = note_row["cnt"] if note_row else 0

        return stats

    # === Row Mapping ===

    def _row_to_witness(self, row: Dict[str, Any]) -> Witness:
        return Witness(
            id=str(row["id"]),
            name=row["name"],
            role=row.get("role", "claimant"),
            status=row.get("status", "identified"),
            party=row.get("party", "claimant"),
            organization=row.get("organization"),
            position=row.get("position"),
            contact_info=_parse_json_field(row.get("contact_info"), {}),
            notes=row.get("notes", ""),
            credibility_level=row.get("credibility_level", "unknown"),
            credibility_notes=row.get("credibility_notes", ""),
            linked_entity_id=str(row["linked_entity_id"]) if row.get("linked_entity_id") else None,
            linked_document_ids=_parse_json_field(row.get("linked_document_ids"), []),
            created_at=row.get("created_at", datetime.utcnow()),
            updated_at=row.get("updated_at", datetime.utcnow()),
            metadata=_parse_json_field(row.get("metadata"), {}),
        )

    def _row_to_statement(self, row: Dict[str, Any]) -> WitnessStatement:
        return WitnessStatement(
            id=str(row["id"]),
            witness_id=str(row["witness_id"]),
            version=row.get("version", 1),
            title=row.get("title", ""),
            content=row.get("content", ""),
            status=row.get("status", "draft"),
            key_points=_parse_json_field(row.get("key_points"), []),
            contradictions_found=_parse_json_field(row.get("contradictions_found"), []),
            filed_date=row.get("filed_date"),
            created_at=row.get("created_at", datetime.utcnow()),
            updated_at=row.get("updated_at", datetime.utcnow()),
        )

    def _row_to_cross_exam(self, row: Dict[str, Any]) -> CrossExamNote:
        return CrossExamNote(
            id=str(row["id"]),
            witness_id=str(row["witness_id"]),
            statement_id=str(row["statement_id"]) if row.get("statement_id") else None,
            topic=row.get("topic", ""),
            question=row.get("question", ""),
            expected_answer=row.get("expected_answer", ""),
            actual_answer=row.get("actual_answer", ""),
            effectiveness=row.get("effectiveness", ""),
            notes=row.get("notes", ""),
            created_at=row.get("created_at", datetime.utcnow()),
        )
