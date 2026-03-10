"""Oracle Shard - Legal research and authority search assistant."""

import logging
from typing import Any, Dict

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .search import AuthoritySearch

logger = logging.getLogger(__name__)


class OracleShard(ArkhamShard):
    """
    Oracle shard for ArkhamFrame.

    Legal research and authority search assistant
    """

    name = "oracle"
    version = "0.1.0"
    description = "Legal research and authority search assistant"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None
        self.authority_search: AuthoritySearch | None = None

    async def initialize(self, frame) -> None:
        """Initialize the Oracle shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Oracle Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Initialize domain services
        self.authority_search = AuthoritySearch(
            db=self._db,
            vectors_service=self._vectors_service,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
        )

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("casemap.theory.updated", self.handle_theory_updated)
            await self._event_bus.subscribe("claims.created", self.handle_claims_created)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            authority_search=self.authority_search,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.oracle_shard = self
            logger.debug("Oracle Shard registered on app.state")

        logger.info("Oracle Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Oracle Shard...")
        self.authority_search = None
        if self._event_bus:
            await self._event_bus.unsubscribe("casemap.theory.updated", self.handle_theory_updated)
            await self._event_bus.unsubscribe("claims.created", self.handle_claims_created)
        logger.info("Oracle Shard shutdown complete")

    async def handle_theory_updated(self, event_data: Dict[str, Any]) -> None:
        """Handle case theory updated event - research relevant authorities."""
        logger.info("Oracle Shard: Case theory updated, researching relevant authorities")
        if self.authority_search and self._event_bus:
            theory_text = event_data.get("theory", "") or event_data.get("description", "")
            if theory_text:
                results = await self.authority_search.search(query=theory_text)
                if results:
                    await self._event_bus.emit(
                        "oracle.authority.found",
                        {"authority_ids": [r.get("id") for r in results[:5]], "source": "theory_updated"},
                    )

    async def handle_claims_created(self, event_data: Dict[str, Any]) -> None:
        """Handle claims created event - map claims to legal tests."""
        logger.info("Oracle Shard: New claims created, mapping to legal tests")
        if self.authority_search and self._event_bus:
            claim_type = event_data.get("claim_type", "") or event_data.get("type", "")
            if claim_type:
                results = await self.authority_search.search(query=claim_type)
                if results:
                    await self._event_bus.emit(
                        "oracle.authority.found",
                        {"authority_ids": [r.get("id") for r in results[:5]], "source": "claims_created"},
                    )

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Oracle tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_oracle")

            # Primary table: legal_authorities (per spec)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_oracle.legal_authorities (
                    id UUID PRIMARY KEY,
                    citation TEXT UNIQUE,
                    jurisdiction TEXT,
                    court TEXT,
                    title TEXT,
                    year INT,
                    summary TEXT,
                    full_text TEXT NULL,
                    relevance_tags TEXT[] DEFAULT '{}',
                    claim_types TEXT[] DEFAULT '{}',
                    authority_type TEXT DEFAULT 'case_law',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Legacy tables kept for backward compatibility with existing data
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_oracle.research_sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    findings JSONB DEFAULT '[]',
                    authority_ids JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_oracle.case_summaries (
                    id TEXT PRIMARY KEY,
                    authority_id TEXT,
                    facts TEXT,
                    decision TEXT,
                    legal_principles JSONB DEFAULT '[]'
                )
            """)

            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_oracle.authority_chains (
                    id TEXT PRIMARY KEY,
                    source_authority_id TEXT,
                    cited_authority_id TEXT,
                    relationship_type TEXT
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_oracle_legal_authorities_citation "
                "ON arkham_oracle.legal_authorities(citation)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_oracle_legal_authorities_jurisdiction "
                "ON arkham_oracle.legal_authorities(jurisdiction)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_oracle_research_project ON arkham_oracle.research_sessions(project_id)"
            )

            logger.info("Oracle database schema created")

        except Exception as e:
            logger.error(f"Failed to create Oracle schema: {e}")
