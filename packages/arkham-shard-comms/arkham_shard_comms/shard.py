"""Comms Shard - Email and message thread reconstruction."""

import json
import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class CommsShard(ArkhamShard):
    """
    Comms shard for ArkhamFrame.

    Reconstructs email/message threads from fragmented sources,
    detects BCC patterns, forwarding chains, and communication gaps.
    """

    name = "comms"
    version = "0.1.0"
    description = "Email and message thread reconstruction"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Comms shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Comms Shard...")

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
            await self._event_bus.subscribe("ingest.document.processed", self._on_document_processed)
            await self._event_bus.subscribe("entities.extracted", self._on_entities_extracted)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.comms_shard = self
            logger.debug("Comms Shard registered on app.state")

        logger.info("Comms Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Comms Shard...")
        logger.info("Comms Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_document_processed(self, event: Dict[str, Any]) -> None:
        """Handle ingest.document.processed events for thread extraction."""
        doc_id = event.get("document_id")
        doc_type = event.get("document_type")

        if doc_type != "email":
            return

        logger.info(f"Comms shard extracting thread for email document: {doc_id}")
        # Stub logic: In a real implementation, this would:
        # 1. Fetch document metadata
        # 2. Extract Message-ID, In-Reply-To
        # 3. Create or Update Thread and Message records
        # 4. Emit comms.thread.reconstructed event

    async def _on_entities_extracted(self, event: Dict[str, Any]) -> None:
        """Handle entities.extracted events."""
        logger.debug(f"Comms shard received entities.extracted: {event.get('document_id')}")

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Comms tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_comms")

            # -------------------------------------------------------
            # Threads table - reconstructed conversation threads
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comms.threads (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    subject TEXT NOT NULL DEFAULT '',
                    description TEXT DEFAULT '',
                    project_id TEXT,
                    status TEXT DEFAULT 'active',
                    first_message_at TIMESTAMP,
                    last_message_at TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    participant_count INTEGER DEFAULT 0,
                    has_gaps BOOLEAN DEFAULT FALSE,
                    has_bcc_pattern BOOLEAN DEFAULT FALSE,
                    has_coordination_flags BOOLEAN DEFAULT FALSE,
                    source_document_ids JSONB DEFAULT '[]',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Messages table - individual messages within threads
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comms.messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES arkham_comms.threads(id) ON DELETE CASCADE,
                    tenant_id UUID,
                    message_id_header TEXT,
                    in_reply_to TEXT,
                    subject TEXT DEFAULT '',
                    body_summary TEXT DEFAULT '',
                    sent_at TIMESTAMP,
                    received_at TIMESTAMP,
                    from_address TEXT DEFAULT '',
                    from_name TEXT,
                    to_addresses JSONB DEFAULT '[]',
                    cc_addresses JSONB DEFAULT '[]',
                    bcc_addresses JSONB DEFAULT '[]',
                    source_document_id TEXT,
                    page_reference TEXT,
                    extraction_method TEXT DEFAULT 'manual',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------------
            # Participants table - people identified across threads
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comms.participants (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    email_address TEXT NOT NULL,
                    display_name TEXT,
                    entity_id TEXT,
                    organisation TEXT,
                    role_notes TEXT DEFAULT '',
                    thread_count INTEGER DEFAULT 0,
                    message_count INTEGER DEFAULT 0,
                    bcc_appearances INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(email_address, tenant_id)
                )
            """)

            # -------------------------------------------------------
            # Gaps table - detected communication gaps/silences
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comms.gaps (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES arkham_comms.threads(id) ON DELETE CASCADE,
                    tenant_id UUID,
                    gap_type TEXT DEFAULT 'missing_reply',
                    description TEXT DEFAULT '',
                    gap_start TIMESTAMP,
                    gap_end TIMESTAMP,
                    gap_duration_hours REAL,
                    expected_sender TEXT,
                    preceding_message_id TEXT,
                    following_message_id TEXT,
                    significance TEXT DEFAULT 'medium',
                    notes TEXT DEFAULT '',
                    project_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Coordination flags table - BCC/forwarding chain patterns
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comms.coordination_flags (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES arkham_comms.threads(id) ON DELETE CASCADE,
                    tenant_id UUID,
                    flag_type TEXT DEFAULT 'bcc_chain',
                    description TEXT DEFAULT '',
                    participants_involved JSONB DEFAULT '[]',
                    supporting_message_ids JSONB DEFAULT '[]',
                    source_document_ids JSONB DEFAULT '[]',
                    confidence REAL DEFAULT 0.5,
                    significance TEXT DEFAULT 'medium',
                    legal_relevance TEXT DEFAULT '',
                    project_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Tenant_id migration for all tables
            await self._db.execute("""
                DO $$
                DECLARE
                    tables_to_update TEXT[] := ARRAY[
                        'threads', 'messages', 'participants', 'gaps', 'coordination_flags'
                    ];
                    tbl TEXT;
                BEGIN
                    FOREACH tbl IN ARRAY tables_to_update LOOP
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'arkham_comms'
                            AND table_name = tbl
                            AND column_name = 'tenant_id'
                        ) THEN
                            EXECUTE format('ALTER TABLE arkham_comms.%I ADD COLUMN tenant_id UUID', tbl);
                        END IF;
                    END LOOP;
                END $$;
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_threads_project ON arkham_comms.threads(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_threads_tenant ON arkham_comms.threads(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_messages_thread ON arkham_comms.messages(thread_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_messages_sent ON arkham_comms.messages(sent_at)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_messages_from ON arkham_comms.messages(from_address)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_participants_email ON arkham_comms.participants(email_address)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_participants_tenant ON arkham_comms.participants(tenant_id)"
            )
            await self._db.execute("CREATE INDEX IF NOT EXISTS idx_comms_gaps_thread ON arkham_comms.gaps(thread_id)")
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comms_flags_thread ON arkham_comms.coordination_flags(thread_id)"
            )

            logger.info("Comms database schema created")

        except Exception as e:
            logger.error(f"Failed to create Comms schema: {e}")
