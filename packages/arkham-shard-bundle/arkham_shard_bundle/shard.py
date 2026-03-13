"""Bundle Shard - Tribunal hearing bundle builder."""

import logging
from typing import Any

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .compiler import BundleCompiler
from .llm import BundleLLMIntegration

logger = logging.getLogger(__name__)


class BundleShard(ArkhamShard):
    """
    Bundle shard for ArkhamFrame.

    Tribunal hearing bundle builder following ET Presidential Guidance.
    Provides continuous pagination, version snapshots, index generation,
    and LLM-assisted document ordering.
    """

    name = "bundle"
    version = "0.1.0"
    description = "Tribunal hearing bundle builder"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None
        self.compiler: BundleCompiler | None = None
        self.llm_integration: BundleLLMIntegration | None = None

    async def initialize(self, frame) -> None:
        """Initialize the Bundle shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Bundle Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Initialize domain services
        self.compiler = BundleCompiler(db=self._db, event_bus=self._event_bus)
        self.llm_integration = BundleLLMIntegration(llm_service=self._llm_service)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            compiler=self.compiler,
            llm_integration=self.llm_integration,
        )

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("documents.processed", self._handle_document_processed)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.bundle_shard = self
            logger.debug("Bundle Shard registered on app.state")

        logger.info("Bundle Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Bundle Shard...")

        # Unsubscribe from events
        if self._event_bus:
            try:
                await self._event_bus.unsubscribe("documents.processed", self._handle_document_processed)
            except Exception:
                pass

        self.compiler = None
        self.llm_integration = None

        logger.info("Bundle Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _handle_document_processed(self, event_data: dict[str, Any]) -> None:
        """
        Handle documents.processed events.

        Auto-suggests bundle placement for newly processed documents
        using LLM integration if available.
        """
        document_id = event_data.get("document_id")
        if not document_id:
            return

        logger.info(f"Document processed event received for: {document_id}")

        # If LLM is available, could auto-categorize the document for bundle placement
        # For now, just log. Full auto-placement would require knowing which bundle to target.
        if self.llm_integration and self.llm_integration.is_available:
            logger.info(f"LLM available - document {document_id} could be auto-categorized for bundle placement")

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Bundle tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_bundle")

            # --- bundles table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_bundle.bundles (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    title TEXT NOT NULL,
                    description TEXT,
                    project_id TEXT,
                    status TEXT DEFAULT 'draft',
                    total_pages INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    current_version_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # --- versions table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_bundle.versions (
                    id TEXT PRIMARY KEY,
                    bundle_id TEXT NOT NULL REFERENCES arkham_bundle.bundles(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL DEFAULT 1,
                    total_pages INTEGER DEFAULT 0,
                    document_count INTEGER DEFAULT 0,
                    change_notes TEXT,
                    index_id TEXT,
                    compiled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    compiled_by TEXT,
                    metadata JSONB DEFAULT '{}'
                )
            """)

            # --- pages table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_bundle.pages (
                    id TEXT PRIMARY KEY,
                    bundle_id TEXT NOT NULL REFERENCES arkham_bundle.bundles(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL REFERENCES arkham_bundle.versions(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL,
                    document_title TEXT,
                    document_filename TEXT,
                    position INTEGER NOT NULL,
                    document_page_count INTEGER DEFAULT 1,
                    bundle_page_start INTEGER NOT NULL,
                    bundle_page_end INTEGER NOT NULL,
                    document_status TEXT DEFAULT 'unknown',
                    section_label TEXT,
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- indices table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_bundle.indices (
                    id TEXT PRIMARY KEY,
                    bundle_id TEXT NOT NULL REFERENCES arkham_bundle.bundles(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL REFERENCES arkham_bundle.versions(id) ON DELETE CASCADE,
                    entries JSONB NOT NULL DEFAULT '[]',
                    document_count INTEGER DEFAULT 0,
                    total_pages INTEGER DEFAULT 0,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bundle_bundles_tenant ON arkham_bundle.bundles(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bundle_bundles_project ON arkham_bundle.bundles(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bundle_versions_bundle ON arkham_bundle.versions(bundle_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bundle_pages_version ON arkham_bundle.pages(version_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bundle_pages_doc ON arkham_bundle.pages(document_id)"
            )

            logger.info("Bundle database schema created")

        except Exception as e:
            logger.error(f"Failed to create Bundle schema: {e}")
