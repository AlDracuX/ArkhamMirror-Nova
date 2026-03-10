"""Chain Shard - Cryptographic evidence chain of custody."""

import logging
from typing import Any, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .engine import ChainEngine

logger = logging.getLogger(__name__)


class ChainShard(ArkhamShard):
    """
    Chain shard for ArkhamFrame.

    Cryptographic evidence chain of custody: logs SHA-256 hashes at every
    custody transition, detects tampering, and generates court-admissible
    provenance reports.
    """

    name = "chain"
    version = "0.1.0"
    description = "Cryptographic evidence chain of custody"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._storage_service = None
        self.engine: Optional[ChainEngine] = None

    async def initialize(self, frame) -> None:
        """Initialize the Chain shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Chain Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._storage_service = frame.get_service("storage")

        # Create database schema
        await self._create_schema()

        # Initialize engine
        self.engine = ChainEngine(db=self._db, event_bus=self._event_bus)

        # Subscribe to frame events
        if self._event_bus:
            await self._event_bus.subscribe("ingest.document.processed", self._on_document_ingested)
            await self._event_bus.subscribe("documents.accessed", self._on_document_accessed)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            storage_service=self._storage_service,
            shard=self,
            engine=self.engine,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.chain_shard = self
            logger.debug("Chain Shard registered on app.state")

        logger.info("Chain Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Chain Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("ingest.document.processed", self._on_document_ingested)
            await self._event_bus.unsubscribe("documents.accessed", self._on_document_accessed)
        self.engine = None
        logger.info("Chain Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_document_ingested(self, event_data: dict) -> None:
        """Auto-log a custody event when a document is ingested."""
        try:
            payload = event_data.get("payload", {})
            document_id = payload.get("document_id")
            if not document_id:
                return

            # Import here to avoid circular at module level
            from .api import _log_hash_and_event

            await _log_hash_and_event(
                db=self._db,
                storage_service=self._storage_service,
                event_bus=self._event_bus,
                document_id=document_id,
                action="received",
                actor=payload.get("source", "ingest-pipeline"),
                location="ingest",
                previous_event_id=None,
                tenant_id=None,
                notes="Auto-logged on document ingestion",
            )
        except Exception as exc:
            logger.warning("Chain: failed to auto-log ingestion event: %s", exc)

    async def _on_document_accessed(self, event_data: dict) -> None:
        """Auto-log a custody event when a document is accessed."""
        try:
            payload = event_data.get("payload", {})
            document_id = payload.get("document_id")
            if not document_id:
                return

            from .api import _log_hash_and_event

            await _log_hash_and_event(
                db=self._db,
                storage_service=self._storage_service,
                event_bus=self._event_bus,
                document_id=document_id,
                action="accessed",
                actor=payload.get("actor", "system"),
                location=payload.get("location", "documents"),
                previous_event_id=None,
                tenant_id=None,
                notes="Auto-logged on document access",
            )
        except Exception as exc:
            logger.warning("Chain: failed to auto-log access event: %s", exc)

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Chain tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_chain")

            # ----------------------------------------------------------------
            # hashes — SHA-256 snapshot per document per custody transition
            # ----------------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_chain.hashes (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    document_id TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ----------------------------------------------------------------
            # custody_events — full audit trail for every document
            # ----------------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_chain.custody_events (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    document_id TEXT NOT NULL,
                    action TEXT NOT NULL
                        CHECK (action IN ('received','stored','accessed','transformed','exported','verified')),
                    actor TEXT NOT NULL,
                    location TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    previous_event_id TEXT REFERENCES arkham_chain.custody_events(id),
                    hash_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ----------------------------------------------------------------
            # provenance_reports — generated JSON provenance reports
            # ----------------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_chain.provenance_reports (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    document_id TEXT NOT NULL,
                    report_json JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ----------------------------------------------------------------
            # Indexes
            # ----------------------------------------------------------------
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_chain_hashes_document ON arkham_chain.hashes(document_id)",
                "CREATE INDEX IF NOT EXISTS idx_chain_hashes_tenant ON arkham_chain.hashes(tenant_id)",
                "CREATE INDEX IF NOT EXISTS idx_chain_events_document ON arkham_chain.custody_events(document_id)",
                "CREATE INDEX IF NOT EXISTS idx_chain_events_tenant ON arkham_chain.custody_events(tenant_id)",
                "CREATE INDEX IF NOT EXISTS idx_chain_events_timestamp ON arkham_chain.custody_events(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_chain_reports_document ON arkham_chain.provenance_reports(document_id)",
                "CREATE INDEX IF NOT EXISTS idx_chain_reports_tenant ON arkham_chain.provenance_reports(tenant_id)",
            ]:
                await self._db.execute(idx_sql)

            logger.info("Chain database schema created")

        except Exception as exc:
            logger.error("Failed to create Chain schema: %s", exc)
