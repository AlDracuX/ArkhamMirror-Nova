"""Disclosure Shard - Disclosure request and gap tracker."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class DisclosureShard(ArkhamShard):
    """
    Disclosure shard for ArkhamFrame.

    Tracks disclosure requests, responses, gaps, and evasion scores
    across respondents in litigation proceedings.
    """

    name = "disclosure"
    version = "0.1.0"
    description = "Disclosure request and gap tracker"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Disclosure shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Disclosure Shard...")

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
            await self._event_bus.subscribe("document.processed", self._handle_document_processed)
            await self._event_bus.subscribe("case.updated", self._handle_case_updated)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.disclosure_shard = self
            logger.debug("Disclosure Shard registered on app.state")

        logger.info("Disclosure Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Disclosure Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("document.processed", self._handle_document_processed)
            await self._event_bus.unsubscribe("case.updated", self._handle_case_updated)
        logger.info("Disclosure Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _handle_document_processed(self, event: dict) -> None:
        """Handle document.processed events for linking documents to requests."""
        logger.debug(f"Disclosure received document.processed: {event}")

    async def _handle_case_updated(self, event: dict) -> None:
        """Handle case.updated events for refreshing disclosure state."""
        logger.debug(f"Disclosure received case.updated: {event}")

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Disclosure tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_disclosure")

            # --- disclosure_requests table (spec-compliant) ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_disclosure.disclosure_requests (
                    id UUID PRIMARY KEY,
                    case_id UUID,
                    category TEXT,
                    description TEXT,
                    requesting_party TEXT,
                    status TEXT DEFAULT 'pending',
                    deadline DATE NULL,
                    document_ids UUID[] DEFAULT '{}',
                    response_text TEXT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # --- Legacy tables (kept for migration compatibility) ---

            # --- responses table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_disclosure.responses (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    request_id TEXT NOT NULL,
                    response_text TEXT NOT NULL DEFAULT '',
                    document_ids TEXT[] DEFAULT '{}',
                    received_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- gaps table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_disclosure.gaps (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    request_id TEXT NOT NULL,
                    missing_items_description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- evasion_scores table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_disclosure.evasion_scores (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    respondent_id TEXT NOT NULL,
                    score NUMERIC(4,3) NOT NULL DEFAULT 0.0,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- Indexes ---
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_requests_case "
                "ON arkham_disclosure.disclosure_requests(case_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_requests_status "
                "ON arkham_disclosure.disclosure_requests(status)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_requests_category "
                "ON arkham_disclosure.disclosure_requests(category)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_requests_deadline "
                "ON arkham_disclosure.disclosure_requests(deadline)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_responses_request ON arkham_disclosure.responses(request_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_gaps_request ON arkham_disclosure.gaps(request_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_gaps_status ON arkham_disclosure.gaps(status)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_disclosure_evasion_respondent "
                "ON arkham_disclosure.evasion_scores(respondent_id)"
            )

            logger.info("Disclosure database schema created")

        except Exception as e:
            logger.error(f"Failed to create Disclosure schema: {e}")
