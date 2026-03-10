"""Skeleton Shard - Legal argument and submission builder."""

import logging
from typing import Any, Dict

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .builder import SkeletonBuilder
from .llm import SkeletonLLMIntegration

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
        self.builder: SkeletonBuilder | None = None
        self.llm_integration: SkeletonLLMIntegration | None = None

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

        # Instantiate domain services
        self.builder = SkeletonBuilder(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
        )
        self.llm_integration = SkeletonLLMIntegration(llm_service=self._llm_service)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            builder=self.builder,
            llm_integration=self.llm_integration,
        )

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("casemap.theory.updated", self._on_theory_updated)
            await self._event_bus.subscribe("claims.verified", self._on_claims_verified)
            await self._event_bus.subscribe("oracle.authority.found", self._on_authority_found)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.skeleton_shard = self
            logger.debug("Skeleton Shard registered on app.state")

        logger.info("Skeleton Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Skeleton Shard...")
        self.builder = None
        self.llm_integration = None
        logger.info("Skeleton Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_theory_updated(self, event: Dict[str, Any]) -> None:
        """Handle casemap.theory.updated events.

        When a theory is updated in casemap, rebuild affected argument trees.
        """
        theory_id = event.get("theory_id")
        claim_id = event.get("claim_id")
        logger.debug(f"Skeleton shard received theory.updated: {theory_id}")
        if claim_id and self.builder:
            try:
                await self.builder.build_argument_tree(claim_id)
                logger.info(f"Rebuilt argument tree for claim {claim_id} after theory update")
            except Exception as e:
                logger.error(f"Failed to rebuild argument tree for claim {claim_id}: {e}")

    async def _on_claims_verified(self, event: Dict[str, Any]) -> None:
        """Handle claims.verified events.

        When a claim is verified, build its argument tree.
        """
        claim_id = event.get("claim_id")
        logger.debug(f"Skeleton shard received claims.verified: {claim_id}")
        if claim_id and self.builder:
            try:
                await self.builder.build_argument_tree(claim_id)
                logger.info(f"Built argument tree for verified claim {claim_id}")
            except Exception as e:
                logger.error(f"Failed to build argument tree for claim {claim_id}: {e}")

    async def _on_authority_found(self, event: Dict[str, Any]) -> None:
        """Handle oracle.authority.found events.

        When the oracle shard finds a new authority, link it to relevant trees.
        """
        authority_id = event.get("authority_id")
        tree_id = event.get("tree_id")
        logger.debug(f"Skeleton shard received oracle.authority.found: {authority_id}")
        if authority_id and tree_id and self.builder:
            try:
                await self.builder.link_authorities(tree_id, [authority_id])
                logger.info(f"Linked authority {authority_id} to tree {tree_id}")
            except Exception as e:
                logger.error(f"Failed to link authority {authority_id} to tree {tree_id}: {e}")

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
