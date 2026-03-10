"""Digest Shard - ADHD-optimized daily briefings and case summaries."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .engine import DigestEngine

logger = logging.getLogger(__name__)


class DigestShard(ArkhamShard):
    """
    Digest shard for ArkhamFrame.

    ADHD-optimized daily briefings and case summaries
    """

    name = "digest"
    version = "0.1.0"
    description = "ADHD-optimized daily briefings and case summaries"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None
        self.engine: Optional[DigestEngine] = None

    async def initialize(self, frame) -> None:
        """Initialize the Digest shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Digest Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Initialize engine with services
        self.engine = DigestEngine(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
        )

        # Subscribe to key event patterns for change logging
        if self._event_bus:
            for pattern in [
                "disclosure.*",
                "rules.*",
                "burden.*",
                "costs.*",
                "deadlines.*",
                "contradictions.*",
                "evidence.*",
                "timeline.*",
            ]:
                await self._event_bus.subscribe(pattern, self._handle_event)

        # Initialize API with engine and services
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            engine=self.engine,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.digest_shard = self
            logger.debug("Digest Shard registered on app.state")

        logger.info("Digest Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Digest Shard...")
        if self._event_bus:
            for pattern in [
                "disclosure.*",
                "rules.*",
                "burden.*",
                "costs.*",
                "deadlines.*",
                "contradictions.*",
                "evidence.*",
                "timeline.*",
            ]:
                await self._event_bus.unsubscribe(pattern, self._handle_event)
        self.engine = None
        logger.info("Digest Shard shutdown complete")

    async def _handle_event(self, event_data: Dict[str, Any]) -> None:
        """Handle subscribed events by logging them via the engine."""
        event_type = event_data.get("event_type", "unknown")
        source = event_data.get("source", "unknown")

        # Filter out self-events
        if source == "digest-shard":
            return

        if self.engine:
            payload = event_data.get("payload", event_data)
            await self.engine.log_change(event_type, payload)
            logger.debug(f"Digest Shard: Logged change event {event_type}")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Digest tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_digest")

            # Create tables
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_digest.briefings (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT,
                    priority_items JSONB DEFAULT '[]',
                    action_items JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_digest.change_log (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    shard TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    description TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_digest.subscriptions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    frequency TEXT DEFAULT 'daily',
                    format TEXT DEFAULT 'markdown',
                    last_sent TIMESTAMP
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_digest_briefings_project ON arkham_digest.briefings(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_digest_changelog_project ON arkham_digest.change_log(project_id)"
            )

            logger.info("Digest database schema created")

        except Exception as e:
            logger.error(f"Failed to create Digest schema: {e}")
