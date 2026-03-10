"""RespondentIntel Shard - Corporate structure and respondent background intelligence."""

import logging
from typing import Any, Dict

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .engine import RespondentIntelEngine

logger = logging.getLogger(__name__)


class RespondentIntelShard(ArkhamShard):
    """
    RespondentIntel shard for ArkhamFrame.

    Corporate structure and respondent background intelligence.
    """

    name = "respondent-intel"
    version = "0.1.0"
    description = "Corporate structure and respondent background intelligence"

    def __init__(self):
        super().__init__()
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None
        self.engine: RespondentIntelEngine | None = None

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

        # Instantiate engine
        self.engine = RespondentIntelEngine(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
        )

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("entities.extracted", self._on_entities_extracted)
            await self._event_bus.subscribe("ingest.document.processed", self._on_document_processed)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            engine=self.engine,
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
            await self._event_bus.unsubscribe("entities.extracted", self._on_entities_extracted)
            await self._event_bus.unsubscribe("ingest.document.processed", self._on_document_processed)
        self.engine = None
        logger.info("RespondentIntel Shard shutdown complete")

    async def _on_entities_extracted(self, event_data: Dict[str, Any]) -> None:
        """Handle entities.extracted event - delegate to engine."""
        logger.info("RespondentIntel Shard: Entities extracted, updating respondent profiles")
        if self.engine:
            await self.engine.handle_entities_extracted(event_data)

    async def _on_document_processed(self, event_data: Dict[str, Any]) -> None:
        """Handle documents.processed event - delegate to engine."""
        logger.info("RespondentIntel Shard: Document processed, checking for respondent mentions")
        if self.engine:
            await self.engine.handle_document_processed(event_data)

    # Keep legacy handlers as public API (backwards compat for existing tests)
    async def handle_entities_extracted(self, event_data: Dict[str, Any]) -> None:
        """Handle entities extracted event (legacy, delegates to engine)."""
        await self._on_entities_extracted(event_data)

    async def handle_document_processed(self, event_data: Dict[str, Any]) -> None:
        """Handle document processed event (legacy, delegates to engine)."""
        await self._on_document_processed(event_data)

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

            # Create respondent_profiles table
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.respondent_profiles (
                    id UUID PRIMARY KEY,
                    case_id UUID,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    organization TEXT NOT NULL,
                    title TEXT,
                    background TEXT,
                    strengths JSONB DEFAULT '[]',
                    weaknesses JSONB DEFAULT '[]',
                    known_positions JSONB DEFAULT '[]',
                    credibility_notes TEXT,
                    document_ids UUID[] DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create entity_mentions table (populated by entities.extracted events)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.entity_mentions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    case_id UUID NOT NULL,
                    document_id UUID NOT NULL,
                    entity_text TEXT NOT NULL,
                    context TEXT,
                    document_date TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create respondent_positions table (tracks positions across documents)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_respondent_intel.respondent_positions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    profile_id UUID NOT NULL REFERENCES arkham_respondent_intel.respondent_profiles(id)
                        ON DELETE CASCADE,
                    document_id UUID NOT NULL,
                    position TEXT NOT NULL,
                    date TIMESTAMPTZ,
                    context TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_respondent_profiles_case_id "
                "ON arkham_respondent_intel.respondent_profiles(case_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_respondent_profiles_organization "
                "ON arkham_respondent_intel.respondent_profiles(organization)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_respondent_profiles_name "
                "ON arkham_respondent_intel.respondent_profiles(name)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_mentions_case_id "
                "ON arkham_respondent_intel.entity_mentions(case_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity_text "
                "ON arkham_respondent_intel.entity_mentions(entity_text)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_respondent_positions_profile_id "
                "ON arkham_respondent_intel.respondent_positions(profile_id)"
            )

            logger.info("RespondentIntel database schema created")

        except Exception as e:
            logger.error(f"Failed to create RespondentIntel schema: {e}")
