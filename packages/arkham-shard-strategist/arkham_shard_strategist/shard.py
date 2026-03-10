"""Strategist Shard - AI-powered adversarial modeling and red-teaming."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class StrategistShard(ArkhamShard):
    """
    Strategist shard for ArkhamFrame.

    AI-powered adversarial modeling and red-teaming
    """

    name = "strategist"
    version = "0.1.0"
    description = "AI-powered adversarial modeling and red-teaming"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Strategist shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Strategist Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("playbook.strategy.updated", self.handle_strategy_updated)
            await self._event_bus.subscribe("respondent.profile.updated", self.handle_profile_updated)
            await self._event_bus.subscribe("witnesses.statement.created", self.handle_statement_created)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.strategist_shard = self
            logger.debug("Strategist Shard registered on app.state")

        logger.info("Strategist Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Strategist Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("playbook.strategy.updated", self.handle_strategy_updated)
            await self._event_bus.unsubscribe("respondent.profile.updated", self.handle_profile_updated)
            await self._event_bus.unsubscribe("witnesses.statement.created", self.handle_statement_created)
        logger.info("Strategist Shard shutdown complete")

    async def handle_strategy_updated(self, event_data: Dict[str, Any]) -> None:
        """Handle strategy updated event."""
        logger.info("Strategist Shard: Strategy updated, recalculating predictions")

    async def handle_profile_updated(self, event_data: Dict[str, Any]) -> None:
        """Handle respondent profile updated event."""
        logger.info("Strategist Shard: Respondent profile updated, updating tactical models")

    async def handle_statement_created(self, event_data: Dict[str, Any]) -> None:
        """Handle witness statement created event."""
        logger.info("Strategist Shard: New witness statement, simulating testimony angles")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Strategist tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_strategist")

            # Create tables
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_strategist.predictions (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    project_id TEXT NOT NULL,
                    claim_id TEXT,
                    respondent_id TEXT,
                    predicted_argument TEXT,
                    confidence FLOAT,
                    reasoning TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_strategist.counterarguments (
                    id TEXT PRIMARY KEY,
                    prediction_id TEXT REFERENCES arkham_strategist.predictions(id) ON DELETE CASCADE,
                    argument TEXT NOT NULL,
                    rebuttal_strategy TEXT,
                    evidence_ids JSONB DEFAULT '[]'
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_strategist.red_team_reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    weaknesses JSONB DEFAULT '[]',
                    recommendations JSONB DEFAULT '[]',
                    overall_risk_score FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_strategist.tactical_models (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    respondent_id TEXT NOT NULL,
                    likely_tactics JSONB DEFAULT '[]',
                    counter_measures JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_strategist.strategies (
                    id UUID PRIMARY KEY,
                    case_id UUID,
                    name TEXT NOT NULL,
                    approach TEXT NOT NULL,
                    summary TEXT,
                    strengths JSONB DEFAULT '[]',
                    weaknesses JSONB DEFAULT '[]',
                    risks JSONB DEFAULT '[]',
                    opportunities JSONB DEFAULT '[]',
                    recommended BOOLEAN DEFAULT false,
                    confidence_score FLOAT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_strategist_predictions_project ON arkham_strategist.predictions(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_strategist_reports_project ON arkham_strategist.red_team_reports(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_strategist_strategies_case ON arkham_strategist.strategies(case_id)"
            )

            logger.info("Strategist database schema created")

        except Exception as e:
            logger.error(f"Failed to create Strategist schema: {e}")
