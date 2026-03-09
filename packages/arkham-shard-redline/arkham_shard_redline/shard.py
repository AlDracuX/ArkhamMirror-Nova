"""Redline Shard - Document version comparison and semantic diff."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class RedlineShard(ArkhamShard):
    """
    Redline shard for ArkhamFrame.

    Document version comparison and semantic diff
    """

    name = "redline"
    version = "0.1.0"
    description = "Document version comparison and semantic diff"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Redline shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Redline Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("documents.processed", self.handle_document_processed)
            await self._event_bus.subscribe("parse.completed", self.handle_parse_completed)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.redline_shard = self
            logger.debug("Redline Shard registered on app.state")

        logger.info("Redline Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Redline Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("documents.processed", self.handle_document_processed)
            await self._event_bus.unsubscribe("parse.completed", self.handle_parse_completed)
        logger.info("Redline Shard shutdown complete")

    async def handle_document_processed(self, event_data: Dict[str, Any]) -> None:
        """Handle document processed event."""
        payload = event_data.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id:
            logger.info(f"Redline Shard: Notified of document {doc_id}")

    async def handle_parse_completed(self, event_data: Dict[str, Any]) -> None:
        """Handle parse completed event."""
        payload = event_data.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id:
            logger.info(f"Redline Shard: Notified of parse complete for {doc_id}")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Redline tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_redline")

            # Create tables
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_redline.comparisons (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    project_id TEXT NOT NULL,
                    base_document_id TEXT NOT NULL,
                    target_document_id TEXT NOT NULL,
                    diff_summary TEXT,
                    change_count INTEGER DEFAULT 0,
                    silent_edits BOOLEAN DEFAULT FALSE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_redline.version_chains (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    document_ids JSONB DEFAULT '[]',
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_redline.changes (
                    id TEXT PRIMARY KEY,
                    comparison_id TEXT REFERENCES arkham_redline.comparisons(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    location TEXT,
                    before_text TEXT,
                    after_text TEXT,
                    significance FLOAT,
                    is_silent BOOLEAN DEFAULT FALSE
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_redline_comparisons_project ON arkham_redline.comparisons(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_redline_chains_project ON arkham_redline.version_chains(project_id)"
            )

            logger.info("Redline database schema created")

        except Exception as e:
            logger.error(f"Failed to create Redline schema: {e}")
