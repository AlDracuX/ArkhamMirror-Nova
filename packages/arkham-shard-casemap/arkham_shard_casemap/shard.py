"""Casemap Shard - Legal case theory mapping with evidence linkage."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .models import (
    CLAIM_ELEMENT_TEMPLATES,
    BurdenOfProof,
    ClaimType,
    ElementStatus,
    EvidenceLink,
    EvidenceStrength,
    LegalElement,
    LegalTheory,
    StrengthAssessment,
    TheoryFilter,
    TheoryStatus,
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


class CasemapShard(ArkhamShard):
    """Legal case theory mapping with evidence linkage and burden tracking."""

    name = "casemap"
    version = "0.1.0"
    description = "Legal case theory mapping with evidence linkage and burden tracking"

    async def initialize(self, frame) -> None:
        self.frame = frame
        self._db = frame.database
        await self._create_schema()
        self._subscribe_events()
        init_api(shard=self, event_bus=frame.events)
        logger.info("Casemap shard initialized")

    async def shutdown(self) -> None:
        logger.info("Casemap shard shutting down")

    def get_routes(self):
        return router

    # === Schema ===

    async def _create_schema(self) -> None:
        await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_casemap")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_casemap.legal_theories (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                title VARCHAR(500) NOT NULL,
                claim_type VARCHAR(100) NOT NULL,
                description TEXT DEFAULT '',
                statutory_basis VARCHAR(500) DEFAULT '',
                respondent_ids JSONB DEFAULT '[]',
                status VARCHAR(50) DEFAULT 'active',
                overall_strength INT DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_casemap.legal_elements (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                theory_id UUID NOT NULL REFERENCES arkham_casemap.legal_theories(id) ON DELETE CASCADE,
                title VARCHAR(500) NOT NULL,
                description TEXT DEFAULT '',
                burden VARCHAR(50) NOT NULL DEFAULT 'claimant',
                status VARCHAR(50) DEFAULT 'unproven',
                required BOOLEAN DEFAULT true,
                statutory_reference VARCHAR(500) DEFAULT '',
                notes TEXT DEFAULT '',
                display_order INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS arkham_casemap.evidence_links (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                element_id UUID NOT NULL REFERENCES arkham_casemap.legal_elements(id) ON DELETE CASCADE,
                document_id UUID,
                witness_id UUID,
                description TEXT DEFAULT '',
                strength VARCHAR(50) DEFAULT 'neutral',
                source_reference VARCHAR(500) DEFAULT '',
                supports_element BOOLEAN DEFAULT true,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_theories_tenant
            ON arkham_casemap.legal_theories(tenant_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_elements_theory
            ON arkham_casemap.legal_elements(tenant_id, theory_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_evidence_element
            ON arkham_casemap.evidence_links(tenant_id, element_id)
        """)

    # === Events ===

    def _subscribe_events(self) -> None:
        try:
            self.frame.events.subscribe("claims.created", self._handle_claim_created)
            self.frame.events.subscribe("contradictions.found", self._handle_contradiction)
            self.frame.events.subscribe("document.processed", self._handle_document)
        except Exception as e:
            logger.debug(f"Event subscription skipped: {e}")

    async def _handle_claim_created(self, event: Dict[str, Any]) -> None:
        logger.debug(f"Claim created event: {event}")

    async def _handle_contradiction(self, event: Dict[str, Any]) -> None:
        logger.debug(f"Contradiction found event: {event}")

    async def _handle_document(self, event: Dict[str, Any]) -> None:
        logger.debug(f"Document processed event: {event}")

    # === Theory CRUD ===

    async def create_theory(self, data: Dict[str, Any]) -> LegalTheory:
        theory_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id())

        await self._db.execute("""
            INSERT INTO arkham_casemap.legal_theories
            (id, tenant_id, title, claim_type, description, statutory_basis,
             respondent_ids, status, notes, metadata)
            VALUES (%(id)s, %(tid)s, %(title)s, %(ct)s, %(desc)s, %(stat)s,
                    %(resp)s, %(status)s, %(notes)s, %(meta)s)
        """, {
            "id": theory_id, "tid": tenant_id,
            "title": data.get("title", ""),
            "ct": data.get("claim_type", "custom"),
            "desc": data.get("description", ""),
            "stat": data.get("statutory_basis", ""),
            "resp": json.dumps(data.get("respondent_ids", [])),
            "status": data.get("status", "active"),
            "notes": data.get("notes", ""),
            "meta": json.dumps(data.get("metadata", {})),
        })

        await self.frame.events.emit("casemap.theory.created", {
            "theory_id": theory_id,
            "title": data.get("title"),
            "claim_type": data.get("claim_type"),
        }, source="casemap-shard")

        return await self.get_theory(theory_id)

    async def get_theory(self, theory_id: str) -> Optional[LegalTheory]:
        tenant_id = str(self.get_tenant_id())
        row = await self._db.fetch_one("""
            SELECT * FROM arkham_casemap.legal_theories
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, {"id": theory_id, "tid": tenant_id})
        if not row:
            return None
        return self._row_to_theory(row)

    async def list_theories(self, filters: Optional[TheoryFilter] = None,
                             limit: int = 100, offset: int = 0) -> List[LegalTheory]:
        tenant_id = str(self.get_tenant_id())
        conditions = ["tenant_id = %(tid)s"]
        params: Dict[str, Any] = {"tid": tenant_id}

        if filters:
            if filters.claim_type:
                conditions.append("claim_type = %(ct)s")
                params["ct"] = filters.claim_type.value
            if filters.status:
                conditions.append("status = %(status)s")
                params["status"] = filters.status.value
            if filters.search_text:
                conditions.append("(title ILIKE %(search)s OR description ILIKE %(search)s)")
                params["search"] = f"%{filters.search_text}%"
            if filters.min_strength is not None:
                conditions.append("overall_strength >= %(min_str)s")
                params["min_str"] = filters.min_strength

        where = " AND ".join(conditions)
        params["limit"] = limit
        params["offset"] = offset

        rows = await self._db.fetch_all(f"""
            SELECT * FROM arkham_casemap.legal_theories
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """, params)
        return [self._row_to_theory(r) for r in rows]

    async def count_theories(self) -> int:
        tenant_id = str(self.get_tenant_id())
        row = await self._db.fetch_one("""
            SELECT COUNT(*) as cnt FROM arkham_casemap.legal_theories
            WHERE tenant_id = %(tid)s
        """, {"tid": tenant_id})
        return row["cnt"] if row else 0

    async def update_theory(self, theory_id: str, data: Dict[str, Any]) -> Optional[LegalTheory]:
        tenant_id = str(self.get_tenant_id())
        sets = ["updated_at = NOW()"]
        params: Dict[str, Any] = {"id": theory_id, "tid": tenant_id}

        for f in ["title", "claim_type", "description", "statutory_basis", "status", "notes"]:
            if f in data:
                sets.append(f"{f} = %({f})s")
                params[f] = data[f]
        if "respondent_ids" in data:
            sets.append("respondent_ids = %(resp)s")
            params["resp"] = json.dumps(data["respondent_ids"])
        if "metadata" in data:
            sets.append("metadata = %(meta)s")
            params["meta"] = json.dumps(data["metadata"])

        set_clause = ", ".join(sets)
        await self._db.execute(f"""
            UPDATE arkham_casemap.legal_theories
            SET {set_clause}
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, params)

        await self.frame.events.emit("casemap.theory.updated", {
            "theory_id": theory_id,
        }, source="casemap-shard")

        return await self.get_theory(theory_id)

    async def delete_theory(self, theory_id: str) -> bool:
        tenant_id = str(self.get_tenant_id())
        await self._db.execute("""
            DELETE FROM arkham_casemap.legal_theories
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, {"id": theory_id, "tid": tenant_id})

        await self.frame.events.emit("casemap.theory.deleted", {
            "theory_id": theory_id,
        }, source="casemap-shard")
        return True

    # === Elements ===

    async def create_element(self, theory_id: str, data: Dict[str, Any]) -> LegalElement:
        elem_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id())

        # Auto-increment display_order
        row = await self._db.fetch_one("""
            SELECT COALESCE(MAX(display_order), 0) + 1 as next_ord
            FROM arkham_casemap.legal_elements
            WHERE theory_id = %(tid_theory)s AND tenant_id = %(tid)s
        """, {"tid_theory": theory_id, "tid": tenant_id})
        order = row["next_ord"] if row else 1

        await self._db.execute("""
            INSERT INTO arkham_casemap.legal_elements
            (id, tenant_id, theory_id, title, description, burden, status,
             required, statutory_reference, notes, display_order)
            VALUES (%(id)s, %(tid)s, %(theory_id)s, %(title)s, %(desc)s, %(burden)s,
                    %(status)s, %(req)s, %(stat_ref)s, %(notes)s, %(order)s)
        """, {
            "id": elem_id, "tid": tenant_id,
            "theory_id": theory_id,
            "title": data.get("title", ""),
            "desc": data.get("description", ""),
            "burden": data.get("burden", "claimant"),
            "status": data.get("status", "unproven"),
            "req": data.get("required", True),
            "stat_ref": data.get("statutory_reference", ""),
            "notes": data.get("notes", ""),
            "order": data.get("display_order", order),
        })

        await self.frame.events.emit("casemap.element.created", {
            "theory_id": theory_id,
            "element_id": elem_id,
            "title": data.get("title"),
        }, source="casemap-shard")

        return await self.get_element(elem_id)

    async def get_element(self, element_id: str) -> Optional[LegalElement]:
        tenant_id = str(self.get_tenant_id())
        row = await self._db.fetch_one("""
            SELECT * FROM arkham_casemap.legal_elements
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, {"id": element_id, "tid": tenant_id})
        if not row:
            return None
        return self._row_to_element(row)

    async def list_elements(self, theory_id: str) -> List[LegalElement]:
        tenant_id = str(self.get_tenant_id())
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_casemap.legal_elements
            WHERE theory_id = %(theory_id)s AND tenant_id = %(tid)s
            ORDER BY display_order ASC
        """, {"theory_id": theory_id, "tid": tenant_id})
        return [self._row_to_element(r) for r in rows]

    async def update_element(self, element_id: str, data: Dict[str, Any]) -> Optional[LegalElement]:
        tenant_id = str(self.get_tenant_id())
        sets = ["updated_at = NOW()"]
        params: Dict[str, Any] = {"id": element_id, "tid": tenant_id}

        for f in ["title", "description", "burden", "status", "statutory_reference", "notes"]:
            if f in data:
                sets.append(f"{f} = %({f})s")
                params[f] = data[f]
        if "required" in data:
            sets.append("required = %(req)s")
            params["req"] = data["required"]
        if "display_order" in data:
            sets.append("display_order = %(order)s")
            params["order"] = data["display_order"]

        set_clause = ", ".join(sets)
        await self._db.execute(f"""
            UPDATE arkham_casemap.legal_elements
            SET {set_clause}
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, params)

        return await self.get_element(element_id)

    async def delete_element(self, element_id: str) -> bool:
        tenant_id = str(self.get_tenant_id())
        await self._db.execute("""
            DELETE FROM arkham_casemap.legal_elements
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, {"id": element_id, "tid": tenant_id})
        return True

    # === Evidence Links ===

    async def link_evidence(self, element_id: str, data: Dict[str, Any]) -> EvidenceLink:
        link_id = str(uuid.uuid4())
        tenant_id = str(self.get_tenant_id())

        await self._db.execute("""
            INSERT INTO arkham_casemap.evidence_links
            (id, tenant_id, element_id, document_id, witness_id, description,
             strength, source_reference, supports_element, notes)
            VALUES (%(id)s, %(tid)s, %(eid)s, %(doc_id)s, %(wit_id)s, %(desc)s,
                    %(strength)s, %(src_ref)s, %(supports)s, %(notes)s)
        """, {
            "id": link_id, "tid": tenant_id,
            "eid": element_id,
            "doc_id": data.get("document_id"),
            "wit_id": data.get("witness_id"),
            "desc": data.get("description", ""),
            "strength": data.get("strength", "neutral"),
            "src_ref": data.get("source_reference", ""),
            "supports": data.get("supports_element", True),
            "notes": data.get("notes", ""),
        })

        await self.frame.events.emit("casemap.evidence.linked", {
            "element_id": element_id,
            "evidence_link_id": link_id,
        }, source="casemap-shard")

        return EvidenceLink(
            id=link_id, element_id=element_id,
            document_id=data.get("document_id"),
            witness_id=data.get("witness_id"),
            description=data.get("description", ""),
            strength=data.get("strength", "neutral"),
            source_reference=data.get("source_reference", ""),
            supports_element=data.get("supports_element", True),
            notes=data.get("notes", ""),
        )

    async def list_evidence(self, element_id: str) -> List[EvidenceLink]:
        tenant_id = str(self.get_tenant_id())
        rows = await self._db.fetch_all("""
            SELECT * FROM arkham_casemap.evidence_links
            WHERE element_id = %(eid)s AND tenant_id = %(tid)s
            ORDER BY created_at DESC
        """, {"eid": element_id, "tid": tenant_id})
        return [self._row_to_evidence(r) for r in rows]

    async def delete_evidence(self, link_id: str) -> bool:
        tenant_id = str(self.get_tenant_id())
        await self._db.execute("""
            DELETE FROM arkham_casemap.evidence_links
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, {"id": link_id, "tid": tenant_id})
        return True

    # === Strength Assessment ===

    async def assess_strength(self, theory_id: str) -> StrengthAssessment:
        elements = await self.list_elements(theory_id)
        if not elements:
            return StrengthAssessment(theory_id=theory_id)

        assessment = StrengthAssessment(
            theory_id=theory_id,
            total_elements=len(elements),
        )

        element_scores = []
        for elem in elements:
            evidence = await self.list_evidence(elem.id)

            if elem.status in ("proven", "conceded"):
                assessment.proven_count += 1
                element_scores.append(100)
                assessment.strengths.append(elem.id)
            elif elem.status == "likely":
                element_scores.append(75)
                assessment.strengths.append(elem.id)
            elif elem.status == "contested":
                assessment.contested_count += 1
                element_scores.append(50)
            elif elem.status == "weak":
                element_scores.append(25)
                assessment.weaknesses.append(elem.id)
            else:
                assessment.unproven_count += 1
                element_scores.append(0)

            # Check for gaps (required elements with no supporting evidence)
            supporting = [e for e in evidence if e.supports_element]
            adverse = [e for e in evidence if not e.supports_element]

            if not supporting and elem.required:
                assessment.gaps.append(elem.id)

            if adverse and not supporting:
                assessment.weaknesses.append(elem.id)

        # Calculate overall score (weighted by required elements)
        if element_scores:
            assessment.overall_score = int(sum(element_scores) / len(element_scores))

        # Update theory strength
        tenant_id = str(self.get_tenant_id())
        await self._db.execute("""
            UPDATE arkham_casemap.legal_theories
            SET overall_strength = %(strength)s, updated_at = NOW()
            WHERE id = %(id)s AND tenant_id = %(tid)s
        """, {"strength": assessment.overall_score, "id": theory_id, "tid": tenant_id})

        await self.frame.events.emit("casemap.strength.updated", {
            "theory_id": theory_id,
            "overall_score": assessment.overall_score,
        }, source="casemap-shard")

        return assessment

    async def identify_gaps(self, theory_id: str) -> List[Dict[str, Any]]:
        elements = await self.list_elements(theory_id)
        gaps = []
        for elem in elements:
            if not elem.required:
                continue
            evidence = await self.list_evidence(elem.id)
            supporting = [e for e in evidence if e.supports_element]
            if not supporting:
                gaps.append({
                    "element_id": elem.id,
                    "title": elem.title,
                    "burden": elem.burden,
                    "statutory_reference": elem.statutory_reference,
                    "status": elem.status,
                })

        if gaps:
            await self.frame.events.emit("casemap.gap.identified", {
                "theory_id": theory_id,
                "gap_count": len(gaps),
            }, source="casemap-shard")

        return gaps

    async def get_evidence_matrix(self, theory_id: str) -> Dict[str, Any]:
        """Get element x evidence grid (like ACH matrix)."""
        elements = await self.list_elements(theory_id)
        matrix = {"elements": [], "evidence_columns": set()}

        all_evidence = {}
        for elem in elements:
            evidence = await self.list_evidence(elem.id)
            elem_row = {
                "element_id": elem.id,
                "title": elem.title,
                "burden": elem.burden,
                "status": elem.status,
                "required": elem.required,
                "ratings": {},
            }
            for ev in evidence:
                ev_key = ev.document_id or ev.witness_id or ev.id
                matrix["evidence_columns"].add(ev_key)
                all_evidence[ev_key] = ev.description or ev.source_reference
                elem_row["ratings"][ev_key] = {
                    "strength": ev.strength,
                    "supports": ev.supports_element,
                }
            matrix["elements"].append(elem_row)

        matrix["evidence_columns"] = [
            {"id": k, "label": v} for k, v in all_evidence.items()
        ]
        return matrix

    async def get_theory_tree(self, theory_id: str) -> Dict[str, Any]:
        """Get hierarchical: theory -> elements -> evidence."""
        theory = await self.get_theory(theory_id)
        if not theory:
            return {}

        elements = await self.list_elements(theory_id)
        tree = {
            "theory": _theory_dict(theory),
            "elements": [],
        }
        for elem in elements:
            evidence = await self.list_evidence(elem.id)
            tree["elements"].append({
                "element": _element_dict(elem),
                "evidence": [_evidence_dict(e) for e in evidence],
            })
        return tree

    # === Seed Templates ===

    async def seed_elements(self, theory_id: str, claim_type: str) -> List[LegalElement]:
        """Seed standard legal elements from claim type templates."""
        templates = CLAIM_ELEMENT_TEMPLATES.get(claim_type, [])
        elements = []
        for i, tmpl in enumerate(templates):
            elem = await self.create_element(theory_id, {
                "title": tmpl["title"],
                "burden": tmpl["burden"],
                "statutory_reference": tmpl.get("statutory_reference", ""),
                "required": tmpl.get("required", True),
                "display_order": i + 1,
            })
            elements.append(elem)
        return elements

    # === Row Mapping ===

    def _row_to_theory(self, row: Dict[str, Any]) -> LegalTheory:
        return LegalTheory(
            id=str(row["id"]),
            title=row["title"],
            claim_type=row.get("claim_type", "custom"),
            description=row.get("description", ""),
            statutory_basis=row.get("statutory_basis", ""),
            respondent_ids=_parse_json_field(row.get("respondent_ids"), []),
            status=row.get("status", "active"),
            overall_strength=row.get("overall_strength", 0),
            notes=row.get("notes", ""),
            created_at=row.get("created_at", datetime.utcnow()),
            updated_at=row.get("updated_at", datetime.utcnow()),
            metadata=_parse_json_field(row.get("metadata"), {}),
        )

    def _row_to_element(self, row: Dict[str, Any]) -> LegalElement:
        return LegalElement(
            id=str(row["id"]),
            theory_id=str(row["theory_id"]),
            title=row["title"],
            description=row.get("description", ""),
            burden=row.get("burden", "claimant"),
            status=row.get("status", "unproven"),
            required=row.get("required", True),
            statutory_reference=row.get("statutory_reference", ""),
            notes=row.get("notes", ""),
            display_order=row.get("display_order", 0),
            created_at=row.get("created_at", datetime.utcnow()),
            updated_at=row.get("updated_at", datetime.utcnow()),
        )

    def _row_to_evidence(self, row: Dict[str, Any]) -> EvidenceLink:
        return EvidenceLink(
            id=str(row["id"]),
            element_id=str(row["element_id"]),
            document_id=str(row["document_id"]) if row.get("document_id") else None,
            witness_id=str(row["witness_id"]) if row.get("witness_id") else None,
            description=row.get("description", ""),
            strength=row.get("strength", "neutral"),
            source_reference=row.get("source_reference", ""),
            supports_element=row.get("supports_element", True),
            notes=row.get("notes", ""),
            created_at=row.get("created_at", datetime.utcnow()),
        )


# === Helper dicts (module-level for API use) ===

def _theory_dict(t: LegalTheory) -> dict:
    return {
        "id": t.id, "title": t.title, "claim_type": t.claim_type,
        "description": t.description, "statutory_basis": t.statutory_basis,
        "respondent_ids": t.respondent_ids, "status": t.status,
        "overall_strength": t.overall_strength, "notes": t.notes,
        "created_at": str(t.created_at), "updated_at": str(t.updated_at),
        "metadata": t.metadata,
    }

def _element_dict(e: LegalElement) -> dict:
    return {
        "id": e.id, "theory_id": e.theory_id, "title": e.title,
        "description": e.description, "burden": e.burden, "status": e.status,
        "required": e.required, "statutory_reference": e.statutory_reference,
        "notes": e.notes, "display_order": e.display_order,
        "created_at": str(e.created_at), "updated_at": str(e.updated_at),
    }

def _evidence_dict(e: EvidenceLink) -> dict:
    return {
        "id": e.id, "element_id": e.element_id,
        "document_id": e.document_id, "witness_id": e.witness_id,
        "description": e.description, "strength": e.strength,
        "source_reference": e.source_reference,
        "supports_element": e.supports_element, "notes": e.notes,
        "created_at": str(e.created_at),
    }
