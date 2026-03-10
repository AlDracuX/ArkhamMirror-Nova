"""Sentiment Shard - Tone and language pattern analyzer."""

import logging
from typing import Any, Dict

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class SentimentShard(ArkhamShard):
    """
    Sentiment shard for ArkhamFrame.

    Tone and language pattern analyzer
    """

    name = "sentiment"
    version = "0.1.0"
    description = "Tone and language pattern analyzer"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Sentiment shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Sentiment Shard...")

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
            await self._event_bus.subscribe("comms.thread.reconstructed", self.handle_thread_reconstructed)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.sentiment_shard = self
            logger.debug("Sentiment Shard registered on app.state")

        logger.info("Sentiment Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Sentiment Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("documents.processed", self.handle_document_processed)
            await self._event_bus.unsubscribe("comms.thread.reconstructed", self.handle_thread_reconstructed)
        logger.info("Sentiment Shard shutdown complete")

    async def handle_document_processed(self, event_data: Dict[str, Any]) -> None:
        """Handle document processed event."""
        payload = event_data.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id:
            logger.info(f"Sentiment Shard: Notified of document {doc_id}")

    async def handle_thread_reconstructed(self, event_data: Dict[str, Any]) -> None:
        """Handle thread reconstructed event."""
        payload = event_data.get("payload", {})
        thread_id = payload.get("thread_id")
        if thread_id:
            logger.info(f"Sentiment Shard: Notified of thread {thread_id}")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Sentiment tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_sentiment")

            # Core table: sentiment_results
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_sentiment.sentiment_results (
                    id UUID PRIMARY KEY,
                    document_id UUID NOT NULL,
                    case_id UUID,
                    overall_score FLOAT NOT NULL DEFAULT 0.0,
                    label TEXT NOT NULL DEFAULT 'neutral',
                    confidence FLOAT NOT NULL DEFAULT 0.0,
                    passages JSONB DEFAULT '[]',
                    entity_sentiments JSONB DEFAULT '{}',
                    analyzed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Legacy tables (kept for existing data)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_sentiment.analyses (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    document_id TEXT,
                    thread_id TEXT,
                    project_id TEXT NOT NULL,
                    summary TEXT,
                    overall_sentiment FLOAT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_sentiment.tone_scores (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT REFERENCES arkham_sentiment.analyses(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    score FLOAT NOT NULL,
                    reasoning TEXT,
                    evidence_segments JSONB DEFAULT '[]'
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_sentiment.patterns (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    significance_score FLOAT,
                    analysis_ids JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_sentiment.comparator_diffs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    claimant_analysis_id TEXT REFERENCES arkham_sentiment.analyses(id) ON DELETE CASCADE,
                    comparator_analysis_id TEXT REFERENCES arkham_sentiment.analyses(id) ON DELETE CASCADE,
                    divergence_score FLOAT,
                    description TEXT,
                    findings JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_results_doc ON arkham_sentiment.sentiment_results(document_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_results_case ON arkham_sentiment.sentiment_results(case_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_results_label ON arkham_sentiment.sentiment_results(label)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_analyses_project ON arkham_sentiment.analyses(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_analyses_doc ON arkham_sentiment.analyses(document_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_sentiment_patterns_project ON arkham_sentiment.patterns(project_id)"
            )

            logger.info("Sentiment database schema created")

        except Exception as e:
            logger.error(f"Failed to create Sentiment schema: {e}")
