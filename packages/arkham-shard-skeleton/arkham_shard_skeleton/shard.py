"""Skeleton Shard - Legal argument and submission builder."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class SkeletonShard(ArkhamShard):
    """
    Skeleton shard for ArkhamFrame.

    Structures skeleton arguments and legal submissions in ET-compliant format.
    Builds argument trees from claim -> legal test -> evidence -> authority.
    """

    name = "skeleton"
    version = "0.1.0"
    description = "Legal argument and submission builder"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Skeleton shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Skeleton Shard...")

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
            await self._event_bus.subscribe("casemap.theory.updated", self._on_theory_updated)
            await self._event_bus.subscribe("claims.verified", self._on_claims_verified)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.skeleton_shard = self
            logger.debug("Skeleton Shard registered on app.state")

        logger.info("Skeleton Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Skeleton Shard...")
        logger.info("Skeleton Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_theory_updated(self, event: Dict[str, Any]) -> None:
        """Handle casemap.theory.updated events."""
        logger.debug(f"Skeleton shard received theory.updated: {event.get('theory_id')}")

    async def _on_claims_verified(self, event: Dict[str, Any]) -> None:
        """Handle claims.verified events."""
        logger.debug(f"Skeleton shard received claims.verified: {event.get('claim_id')}")

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Skeleton tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_skeleton")

            # -------------------------------------------------------
            # Argument Trees table
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_skeleton.argument_trees (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    title TEXT NOT NULL DEFAULT '',
                    project_id TEXT,
                    claim_id TEXT,
                    legal_test TEXT DEFAULT '',
                    evidence_refs JSONB DEFAULT '[]',
                    authority_ids JSONB DEFAULT '[]',
                    logic_summary TEXT DEFAULT '',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Authorities table
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_skeleton.authorities (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    citation TEXT NOT NULL DEFAULT '',
                    title TEXT DEFAULT '',
                    authority_type TEXT DEFAULT 'case_law',
                    ratio_decidendi TEXT DEFAULT '',
                    key_quotes JSONB DEFAULT '[]',
                    bundle_page INTEGER,
                    is_binding BOOLEAN DEFAULT TRUE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------------
            # Submissions table
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_skeleton.submissions (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    title TEXT NOT NULL DEFAULT '',
                    project_id TEXT,
                    submission_type TEXT DEFAULT 'skeleton_argument',
                    status TEXT DEFAULT 'draft',
                    content_structure JSONB DEFAULT '{}',
                    rendered_text TEXT,
                    bundle_references JSONB DEFAULT '{}',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Tenant_id migration / addition for all tables
            await self._db.execute("""
                DO $$
                DECLARE
                    tables_to_update TEXT[] := ARRAY[
                        'argument_trees', 'authorities', 'submissions'
                    ];
                    tbl TEXT;
                BEGIN
                    FOREACH tbl IN ARRAY tables_to_update LOOP
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'arkham_skeleton'
                            AND table_name = tbl
                            AND column_name = 'tenant_id'
                        ) THEN
                            EXECUTE format('ALTER TABLE arkham_skeleton.%I ADD COLUMN tenant_id UUID', tbl);
                        END IF;
                    END LOOP;
                END $$;
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_skeleton_args_project ON arkham_skeleton.argument_trees(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_skeleton_args_tenant ON arkham_skeleton.argument_trees(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_skeleton_authorities_tenant ON arkham_skeleton.authorities(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_skeleton_subs_project ON arkham_skeleton.submissions(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_skeleton_subs_tenant ON arkham_skeleton.submissions(tenant_id)"
            )

            logger.info("Skeleton database schema created")

        except Exception as e:
            logger.error(f"Failed to create Skeleton schema: {e}")
