"""BurdenMap Shard -- Burden of proof element tracker.

Schema: arkham_burden_map (1 table)
  - burden_elements : one row per legal element to be proved

Inter-shard integration (EventBus only -- no direct imports):
  Subscribes: casemap.theory.updated, claims.status.changed, credibility.score.updated
  Publishes:  burden-map.item.created, burden-map.item.updated, burden-map.item.deleted
"""

import logging
from typing import Any, Dict

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)

# SQL schema name -- uses underscore (valid PostgreSQL identifier)
SCHEMA = "arkham_burden_map"

VALID_STATUSES = {"unmet", "partial", "met", "disputed"}


class BurdenMapShard(ArkhamShard):
    """
    BurdenMap shard for ArkhamFrame.

    Burden of proof element tracker -- maps claims to their constituent
    legal elements and tracks which are met/unmet/disputed.
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

        # Subscribe to upstream shard events (EventBus -- no direct imports)
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
        """Create arkham_burden_map schema and burden_elements table."""
        if not self._db:
            logger.warning("Database service not available -- persistence disabled")
            return

        try:
            await self._db.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

            await self._db.execute(f"""
                CREATE TABLE IF NOT EXISTS {SCHEMA}.burden_elements (
                    id              UUID PRIMARY KEY,
                    case_id         UUID,
                    claim           TEXT NOT NULL,
                    element         TEXT NOT NULL,
                    legal_standard  TEXT NOT NULL DEFAULT '',
                    burden_party    TEXT NOT NULL DEFAULT 'claimant',
                    evidence_ids    UUID[] DEFAULT '{{}}',
                    status          TEXT NOT NULL DEFAULT 'unmet',
                    notes           TEXT,
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # --- Indexes ---
            for idx_sql in [
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_case ON {SCHEMA}.burden_elements(case_id)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_claim ON {SCHEMA}.burden_elements(claim)",
                f"CREATE INDEX IF NOT EXISTS idx_burden_elements_status ON {SCHEMA}.burden_elements(status)",
            ]:
                await self._db.execute(idx_sql)

            logger.info("BurdenMap database schema created (arkham_burden_map)")

        except Exception as e:
            logger.error(f"Failed to create BurdenMap schema: {e}")
            raise

    # --- Event Handlers (inter-shard via EventBus) ---

    async def _on_casemap_theory_updated(self, event: Dict[str, Any]) -> None:
        """React to casemap.theory.updated."""
        logger.debug(f"BurdenMap: received casemap.theory.updated: {event}")

    async def _on_claims_status_changed(self, event: Dict[str, Any]) -> None:
        """React to claims.status.changed."""
        logger.debug(f"BurdenMap: received claims.status.changed: {event}")

    async def _on_credibility_score_updated(self, event: Dict[str, Any]) -> None:
        """React to credibility.score.updated."""
        logger.debug(f"BurdenMap: received credibility.score.updated: {event}")
