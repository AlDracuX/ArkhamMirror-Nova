"""Playbook Shard - Litigation strategy and scenario planner."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class PlaybookShard(ArkhamShard):
    """
    Playbook shard for ArkhamFrame.

    Litigation strategy and scenario planner
    """

    name = "playbook"
    version = "0.1.0"
    description = "Litigation strategy and scenario planner"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Playbook shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Playbook Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("casemap.theory.updated", self.handle_theory_updated)
            await self._event_bus.subscribe("burden.gap.critical", self.handle_burden_gap)
            await self._event_bus.subscribe("deadlines.approaching", self.handle_deadlines)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.playbook_shard = self
            logger.debug("Playbook Shard registered on app.state")

        logger.info("Playbook Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Playbook Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("casemap.theory.updated", self.handle_theory_updated)
            await self._event_bus.unsubscribe("burden.gap.critical", self.handle_burden_gap)
            await self._event_bus.unsubscribe("deadlines.approaching", self.handle_deadlines)
        logger.info("Playbook Shard shutdown complete")

    async def handle_theory_updated(self, event_data: Dict[str, Any]) -> None:
        """Handle case theory updated event."""
        logger.info("Playbook Shard: Case theory updated, updating strategy tree")

    async def handle_burden_gap(self, event_data: Dict[str, Any]) -> None:
        """Handle critical burden gap event."""
        logger.info("Playbook Shard: Critical burden gap detected, adjusting settlement leverage")

    async def handle_deadlines(self, event_data: Dict[str, Any]) -> None:
        """Handle approaching deadlines event."""
        logger.info("Playbook Shard: Deadlines approaching, prioritizing strategy objectives")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Playbook tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_playbook")

            # Create tables
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_playbook.strategies (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'draft',
                    main_claims JSONB DEFAULT '[]',
                    fallback_positions JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_playbook.scenarios (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT REFERENCES arkham_playbook.strategies(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT,
                    probability FLOAT,
                    impact TEXT,
                    consequences JSONB DEFAULT '[]'
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_playbook.evidence_objectives (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    objective_id TEXT NOT NULL,
                    relevance_score FLOAT,
                    notes TEXT
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_playbook_strategies_project ON arkham_playbook.strategies(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_playbook_objectives_project ON arkham_playbook.evidence_objectives(project_id)"
            )

            logger.info("Playbook database schema created")

        except Exception as e:
            logger.error(f"Failed to create Playbook schema: {e}")
