"""BurdenMap Shard — Burden of proof element tracker.

Schema: arkham_burden_map (3 tables)
  - claim_elements      : one row per legal element to be proved
  - evidence_weights    : evidence items linked to each element
  - burden_assignments  : computed traffic-light status per element

Inter-shard integration (EventBus only — no direct imports):
  Subscribes: casemap.theory.updated, claims.status.changed, credibility.score.updated
  Publishes:  burden.element.satisfied, burden.gap.critical
"""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)

# SQL schema name — uses underscore (valid PostgreSQL identifier)
SCHEMA = "arkham_burden_map"


class BurdenMapShard(ArkhamShard):
    """
    BurdenMap shard for ArkhamFrame.

    Burden of proof element tracker with s.136 EA 2010 reverse burden support.
    """

    name = "burden-map"
    version = "0.1.0"
    description = "Burden of proof element tracker"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the BurdenMap shard with Frame services."""
        self._frame = frame

        logger.info("Initializing BurdenMap Shard...")

        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        await self._create_schema()

        # Subscribe to upstream shard events (EventBus — no direct imports)
        if self._event_bus:
            await self._event_bus.subscribe("casemap.theory.updated", self._on_casemap_theory_updated)
            await self._event_bus.subscribe("claims.status.changed", self._on_claims_status_changed)
            await self._event_bus.subscribe("credibility.score.updated", self._on_credibility_score_updated)

        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self on app state for API dependency injection
        if hasattr(frame, "app") and frame.app:
            frame.app.state.burden_map_shard = self
            logger.debug("BurdenMap Shard registered on app.state")

        logger.info("BurdenMap Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down BurdenMap Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("casemap.theory.updated", self._on_casemap_theory_updated)
            await self._event_bus.unsubscribe("claims.status.changed", self._on_claims_status_changed)
            await self._event_bus.unsubscribe("credibility.score.updated", self._on_credibility_score_updated)
        logger.info("BurdenMap Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create arkham_burden_map schema and all domain tables."""
        if not self._db:
            logger.warning("Database service not available — persistence disabled")
            return

        try:
            await self._db.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

            # --- claim_elements -----------------------------------------------
            # One row per legal element that must be established for a claim.
            # burden_holder values: claimant | respondent | shared | reverse
            # 'reverse' = s.136 EA 2010 shift (once prima facie shown, burden
            # moves to respondent to disprove discrimination).
            await self._db.execute(f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA}.claim_elements (
                    id                      TEXT PRIMARY KEY,
                    title                   TEXT NOT NULL,
                    claim_type              TEXT NOT NULL,
                    statutory_reference     TEXT DEFAULT '',
                    description             TEXT DEFAULT '',
                    burden_holder           TEXT NOT NULL DEFAULT 'claimant',
                    required                BOOLEAN NOT NULL DEFAULT TRUE,
                    display_order           INTEGER NOT NULL DEFAULT 0,
                    theory_id               TEXT,
                    casemap_element_id      TEXT,
                    linked_claim_id         TEXT,
                    prima_facie_established BOOLEAN NOT NULL DEFAULT FALSE,
                    burden_shifted          BOOLEAN NOT NULL DEFAULT FALSE,
                    project_id              TEXT,
                    status                  TEXT NOT NULL DEFAULT 'active',
                    notes                   TEXT DEFAULT '',
                    metadata                JSONB DEFAULT '{{}}',
                    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by              TEXT
                )
            """)

            # --- evidence_weights ---------------------------------------------
            # Each row is one piece of evidence assessed against a claim element.
            # weight values: strong | moderate | weak | neutral | adverse
            # supports_burden_holder = FALSE flips the numeric sign (adverse effect).
            await self._db.execute(f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA}.evidence_weights (
                    id                      TEXT PRIMARY KEY,
                    element_id              TEXT NOT NULL
                        REFERENCES {SCHEMA}.claim_elements(id) ON DELETE CASCADE,
                    weight                  TEXT NOT NULL DEFAULT 'neutral',
                    source_type             TEXT NOT NULL DEFAULT 'document',
                    source_id               TEXT,
                    source_title            TEXT,
                    excerpt                 TEXT,
                    supports_burden_holder  BOOLEAN NOT NULL DEFAULT TRUE,
                    analyst_notes           TEXT DEFAULT '',
                    added_by                TEXT NOT NULL DEFAULT 'system',
                    added_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata                JSONB DEFAULT '{{}}'
                )
            """)

            # --- burden_assignments -------------------------------------------
            # One row per claim element; holds the computed traffic-light status.
            # Recalculated on every evidence_weights write and on subscribed events.
            # traffic_light values: green | amber | red
            await self._db.execute(f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA}.burden_assignments (
                    id                      TEXT PRIMARY KEY,
                    element_id              TEXT NOT NULL UNIQUE
                        REFERENCES {SCHEMA}.claim_elements(id) ON DELETE CASCADE,
                    traffic_light           TEXT NOT NULL DEFAULT 'red',
                    net_score               INTEGER NOT NULL DEFAULT 0,
                    supporting_count        INTEGER NOT NULL DEFAULT 0,
                    adverse_count           INTEGER NOT NULL DEFAULT 0,
                    gap_summary             TEXT DEFAULT '',
                    calculated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata                JSONB DEFAULT '{{}}'
                )
            """)

            # --- Indexes -------------------------------------------------------
            for idx_sql in [
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_project ON {SCHEMA}.claim_elements(project_id)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_claim_type ON {SCHEMA}.claim_elements(claim_type)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_theory ON {SCHEMA}.claim_elements(theory_id)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_status ON {SCHEMA}.claim_elements(status)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_weights_element ON {SCHEMA}.evidence_weights(element_id)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_weights_source "
                f"ON {SCHEMA}.evidence_weights(source_type, source_id)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_assignments_light "
                f"ON {SCHEMA}.burden_assignments(traffic_light)",
            ]:
                await self._db.execute(idx_sql)

            logger.info("BurdenMap database schema created (arkham_burden_map)")

        except Exception as e:
            logger.error(f"Failed to create BurdenMap schema: {e}")
            raise

    # --- Event Handlers (inter-shard via EventBus) ---

    async def _on_casemap_theory_updated(self, event: Dict[str, Any]) -> None:
        """
        React to casemap.theory.updated.

        When a casemap theory changes (elements added/removed, burden revised),
        trigger recalculation of all burden_assignments for linked elements.
        """
        theory_id = event.get("theory_id")
        if not theory_id or not self._db:
            return

        try:
            rows = await self._db.fetch_all(
                f"SELECT id FROM {SCHEMA}.claim_elements WHERE theory_id = :theory_id AND status = 'active'",
                {"theory_id": theory_id},
            )
            for row in rows:
                await self._recalculate_assignment(row["id"])
            logger.debug(f"BurdenMap: recalculated {len(rows)} elements for theory {theory_id}")
        except Exception as e:
            logger.error(f"BurdenMap: error handling casemap.theory.updated: {e}")

    async def _on_claims_status_changed(self, event: Dict[str, Any]) -> None:
        """
        React to claims.status.changed.

        When a claim is verified/disputed/retracted, recalculate burden
        assignments for all elements linked to that claim.
        """
        claim_id = event.get("claim_id")
        if not claim_id or not self._db:
            return

        try:
            rows = await self._db.fetch_all(
                f"SELECT id FROM {SCHEMA}.claim_elements WHERE linked_claim_id = :cid AND status = 'active'",
                {"cid": claim_id},
            )
            for row in rows:
                await self._recalculate_assignment(row["id"])
        except Exception as e:
            logger.error(f"BurdenMap: error handling claims.status.changed: {e}")

    async def _on_credibility_score_updated(self, event: Dict[str, Any]) -> None:
        """
        React to credibility.score.updated.

        A source credibility change may affect evidence weight assessments.
        We trigger full recalculation for all elements with evidence from
        that source.
        """
        source_id = event.get("source_id")
        if not source_id or not self._db:
            return

        try:
            rows = await self._db.fetch_all(
                f"""
                SELECT DISTINCT ce.id
                FROM {SCHEMA}.claim_elements ce
                JOIN {SCHEMA}.evidence_weights ew ON ew.element_id = ce.id
                WHERE ew.source_id = :sid AND ce.status = 'active'
                """,
                {"sid": source_id},
            )
            for row in rows:
                await self._recalculate_assignment(row["id"])
        except Exception as e:
            logger.error(f"BurdenMap: error handling credibility.score.updated: {e}")

    # --- Internal recalculation ---

    async def _recalculate_assignment(self, element_id: str) -> None:
        """
        Recompute the BurdenAssignment for a single element and persist it.
        Publishes burden.element.satisfied or burden.gap.critical as appropriate.
        """
        if not self._db:
            return

        import uuid

        from .models import (
            WEIGHT_SCORES,
            EvidenceSource,
            EvidenceWeight,
            EvidenceWeightValue,
            compute_burden_assignment,
        )

        # Fetch all evidence weights for this element
        rows = await self._db.fetch_all(
            f"SELECT * FROM {SCHEMA}.evidence_weights WHERE element_id = :eid",
            {"eid": element_id},
        )

        weight_objs: List[EvidenceWeight] = []
        for r in rows:
            w = EvidenceWeight(
                id=r["id"],
                element_id=r["element_id"],
                weight=EvidenceWeightValue(r["weight"]),
                source_type=EvidenceSource(r["source_type"]),
                source_id=r.get("source_id"),
                source_title=r.get("source_title"),
                excerpt=r.get("excerpt"),
                supports_burden_holder=bool(r["supports_burden_holder"]),
                analyst_notes=r.get("analyst_notes", ""),
            )
            weight_objs.append(w)

        # Fetch existing assignment id (or generate new)
        existing = await self._db.fetch_one(
            f"SELECT id FROM {SCHEMA}.burden_assignments WHERE element_id = :eid",
            {"eid": element_id},
        )
        assignment_id = existing["id"] if existing else str(uuid.uuid4())

        assignment = compute_burden_assignment(element_id, assignment_id, weight_objs)

        await self._db.execute(
            f"""
            INSERT INTO {SCHEMA}.burden_assignments
                (id, element_id, traffic_light, net_score,
                 supporting_count, adverse_count, gap_summary, calculated_at)
            VALUES
                (:id, :element_id, :traffic_light, :net_score,
                 :supporting_count, :adverse_count, :gap_summary, CURRENT_TIMESTAMP)
            ON CONFLICT (element_id) DO UPDATE SET
                traffic_light    = EXCLUDED.traffic_light,
                net_score        = EXCLUDED.net_score,
                supporting_count = EXCLUDED.supporting_count,
                adverse_count    = EXCLUDED.adverse_count,
                gap_summary      = EXCLUDED.gap_summary,
                calculated_at    = CURRENT_TIMESTAMP
            """,
            {
                "id": assignment.id,
                "element_id": element_id,
                "traffic_light": assignment.traffic_light.value,
                "net_score": assignment.net_score,
                "supporting_count": assignment.supporting_count,
                "adverse_count": assignment.adverse_count,
                "gap_summary": assignment.gap_summary,
            },
        )

        # Emit appropriate event
        if self._event_bus:
            # Fetch element metadata for event payload
            el_row = await self._db.fetch_one(
                f"SELECT title, claim_type, required FROM {SCHEMA}.claim_elements WHERE id = :eid",
                {"eid": element_id},
            )
            payload: Dict[str, Any] = {
                "element_id": element_id,
                "traffic_light": assignment.traffic_light.value,
                "net_score": assignment.net_score,
            }
            if el_row:
                payload["element_title"] = el_row["title"]
                payload["claim_type"] = el_row["claim_type"]
                payload["required"] = el_row["required"]

            from .models import TrafficLight

            if assignment.traffic_light == TrafficLight.GREEN:
                await self._event_bus.emit("burden.element.satisfied", payload, source="burden-map-shard")
            elif assignment.traffic_light == TrafficLight.RED and el_row and el_row["required"]:
                await self._event_bus.emit("burden.gap.critical", payload, source="burden-map-shard")
