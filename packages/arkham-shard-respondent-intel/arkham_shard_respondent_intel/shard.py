"""RespondentIntel Shard - Corporate structure and respondent background intelligence."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class RespondentIntelShard(ArkhamShard):
    """
    RespondentIntel shard for ArkhamFrame.

    Corporate structure and respondent background intelligence
    """

    name = "respondent-intel"
    version = "0.1.0"
    description = "Corporate structure and respondent background intelligence"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the RespondentIntel shard with Frame services."""
        self._frame = frame

        logger.info("Initializing RespondentIntel Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("entities.extracted", self.handle_entities_extracted)
            await self._event_bus.subscribe("ingest.document.processed", self.handle_document_processed)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.respondent_intel_shard = self
            logger.debug("RespondentIntel Shard registered on app.state")

        logger.info("RespondentIntel Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down RespondentIntel Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("entities.extracted", self.handle_entities_extracted)
            await self._event_bus.unsubscribe("ingest.document.processed", self.handle_document_processed)
        logger.info("RespondentIntel Shard shutdown complete")

    async def handle_entities_extracted(self, event_data: Dict[str, Any]) -> None:
        """Handle entities extracted event."""
        logger.info("RespondentIntel Shard: Entities extracted, updating respondent profiles")

    async def handle_document_processed(self, event_data: Dict[str, Any]) -> None:
        """Handle document processed event."""
        logger.info("RespondentIntel Shard: Document processed, checking for public records")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for RespondentIntel tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_respondent_intel")

            # Create tables
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.profiles (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    corporate_structure JSONB DEFAULT '{}',
                    key_personnel JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.connections (
                    id TEXT PRIMARY KEY,
                    source_respondent_id TEXT NOT NULL,
                    target_respondent_id TEXT NOT NULL,
                    relationship_type TEXT,
                    description TEXT,
                    strength FLOAT
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.public_records (
                    id TEXT PRIMARY KEY,
                    respondent_id TEXT REFERENCES arkham_respondent_intel.profiles(id) ON DELETE CASCADE,
                    record_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    summary TEXT,
                    record_date TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.vulnerabilities (
                    id TEXT PRIMARY KEY,
                    respondent_id TEXT REFERENCES arkham_respondent_intel.profiles(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    description TEXT,
                    severity TEXT,
                    evidence_ids JSONB DEFAULT '[]'
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_respondent_profiles_name ON arkham_respondent_intel.profiles(name)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_respondent_records_respondent ON arkham_respondent_intel.public_records(respondent_id)"
            )

            logger.info("RespondentIntel database schema created")

        except Exception as e:
            logger.error(f"Failed to create RespondentIntel schema: {e}")
