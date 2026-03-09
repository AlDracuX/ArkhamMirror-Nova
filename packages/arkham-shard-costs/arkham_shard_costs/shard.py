"""Costs Shard - Costs and wasted costs tracker."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class CostsShard(ArkhamShard):
    """
    Costs shard for ArkhamFrame.

    Tracks time, expenses, and respondent conduct for costs applications.
    Logs instances of delay, evasion, or vexatious behavior with evidence.
    """

    name = "costs"
    version = "0.1.0"
    description = "Costs and wasted costs tracker"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Costs shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Costs Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("disclosure.evasion.scored", self._on_disclosure_evasion)
            await self._event_bus.subscribe("rules.breach.detected", self._on_rules_breach)
            await self._event_bus.subscribe("deadlines.breach.detected", self._on_deadline_breach)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.costs_shard = self
            logger.debug("Costs Shard registered on app.state")

        logger.info("Costs Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Costs Shard...")
        logger.info("Costs Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_disclosure_evasion(self, event: Dict[str, Any]) -> None:
        """Handle disclosure.evasion.scored events."""
        logger.debug(f"Costs shard received evasion score: {event.get('respondent_id')}")

    async def _on_rules_breach(self, event: Dict[str, Any]) -> None:
        """Handle rules.breach.detected events."""
        logger.debug(f"Costs shard received breach: {event.get('breach_id')}")

    async def _on_deadline_breach(self, event: Dict[str, Any]) -> None:
        """Handle deadlines.breach.detected events."""
        logger.debug(f"Costs shard received deadline breach: {event.get('deadline_id')}")

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Costs tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_costs")

            # -------------------------------------------------------
            # Time Entries table
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_costs.time_entries (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    activity TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    activity_date DATE NOT NULL,
                    project_id TEXT,
                    hourly_rate REAL,
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Expenses table
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_costs.expenses (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'GBP',
                    expense_date DATE NOT NULL,
                    receipt_document_id TEXT,
                    project_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------------
            # Conduct Log table - logs unreasonable respondent behavior
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_costs.conduct_log (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    party_name TEXT NOT NULL,
                    conduct_type TEXT NOT NULL,
                    description TEXT,
                    occurred_at TIMESTAMP NOT NULL,
                    supporting_evidence JSONB DEFAULT '[]',
                    significance TEXT DEFAULT 'medium',
                    legal_reference TEXT DEFAULT 'Rule 76(1)(a)',
                    project_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Applications table - draft/filed costs applications
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_costs.applications (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    title TEXT NOT NULL DEFAULT '',
                    project_id TEXT,
                    total_amount_claimed REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'draft',
                    conduct_ids JSONB DEFAULT '[]',
                    time_entry_ids JSONB DEFAULT '[]',
                    expense_ids JSONB DEFAULT '[]',
                    application_text TEXT,
                    schedule_document_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Tenant_id migration / addition for all tables
            await self._db.execute("""
                DO $$
                DECLARE
                    tables_to_update TEXT[] := ARRAY[
                        'time_entries', 'expenses', 'conduct_log', 'applications'
                    ];
                    tbl TEXT;
                BEGIN
                    FOREACH tbl IN ARRAY tables_to_update LOOP
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'arkham_costs'
                            AND table_name = tbl
                            AND column_name = 'tenant_id'
                        ) THEN
                            EXECUTE format('ALTER TABLE arkham_costs.%I ADD COLUMN tenant_id UUID', tbl);
                        END IF;
                    END LOOP;
                END $$;
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_time_project ON arkham_costs.time_entries(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_time_tenant ON arkham_costs.time_entries(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_expenses_project ON arkham_costs.expenses(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_conduct_party ON arkham_costs.conduct_log(party_name)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_conduct_project ON arkham_costs.conduct_log(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_apps_project ON arkham_costs.applications(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_costs_apps_tenant ON arkham_costs.applications(tenant_id)"
            )

            logger.info("Costs database schema created")

        except Exception as e:
            logger.error(f"Failed to create Costs schema: {e}")
