"""Comparator Shard - Equality Act s.13/s.26 treatment comparison matrix."""

import logging
from typing import Any

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .engine import ComparatorEngine
from .llm import ComparatorLLM

logger = logging.getLogger(__name__)


class ComparatorShard(ArkhamShard):
    """
    Comparator shard for ArkhamFrame.

    Equality Act s.13/s.26 treatment comparison matrix.
    Maps how claimant and named comparators were treated across incidents.
    """

    name = "comparator"
    version = "0.1.0"
    description = "Equality Act s.13/s.26 treatment comparison matrix"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None
        self.engine: ComparatorEngine | None = None
        self.llm: ComparatorLLM | None = None

    async def initialize(self, frame) -> None:
        """Initialize the Comparator shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Comparator Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Instantiate domain components
        self.engine = ComparatorEngine(db=self._db, event_bus=self._event_bus)
        self.llm = ComparatorLLM(llm_service=self._llm_service)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            engine=self.engine,
            comparator_llm=self.llm,
        )

        # Subscribe to cross-shard events
        if self._event_bus:
            try:
                # EventBus.subscribe is synchronous in the frame
                result = self._event_bus.subscribe("entities.extracted", self._handle_entities_extracted)
                if hasattr(result, "__await__"):
                    await result
                result = self._event_bus.subscribe("documents.processed", self._handle_documents_processed)
                if hasattr(result, "__await__"):
                    await result
                logger.info("Comparator Shard subscribed to entities.extracted and documents.processed")
            except Exception as e:
                logger.warning(f"Event subscription failed (non-fatal): {e}")

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.comparator_shard = self
            logger.debug("Comparator Shard registered on app.state")

        logger.info("Comparator Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Comparator Shard...")
        self.engine = None
        self.llm = None
        logger.info("Comparator Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _handle_entities_extracted(self, event_data: dict) -> None:
        """Handle entities.extracted events from other shards.

        When entities are extracted from documents, check if any relate to
        named individuals who could be comparators.
        """
        logger.info(f"Comparator shard received entities.extracted: {event_data.get('source', 'unknown')}")
        # Future: auto-create comparator suggestions from extracted person entities
        if self._event_bus:
            await self._event_bus.emit(
                "comparator.entities.received",
                {"source_event": "entities.extracted", "entity_count": len(event_data.get("entities", []))},
                source="comparator-shard",
            )

    async def _handle_documents_processed(self, event_data: dict) -> None:
        """Handle documents.processed events from other shards.

        When new documents are processed, check if they contain evidence of
        differential treatment relevant to existing incidents.
        """
        logger.info(f"Comparator shard received documents.processed: {event_data.get('document_id', 'unknown')}")
        # Future: auto-scan for treatment evidence in processed documents
        if self._event_bus:
            await self._event_bus.emit(
                "comparator.documents.received",
                {"source_event": "documents.processed", "document_id": event_data.get("document_id")},
                source="comparator-shard",
            )

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Comparator tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_comparator")

            # --- comparators table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comparator.comparators (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    name TEXT NOT NULL,
                    characteristic TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_comparators_tenant "
                "ON arkham_comparator.comparators(tenant_id)"
            )

            # --- incidents table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comparator.incidents (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    date TIMESTAMP,
                    description TEXT NOT NULL DEFAULT '',
                    project_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_incidents_tenant ON arkham_comparator.incidents(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_incidents_project ON arkham_comparator.incidents(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_incidents_date ON arkham_comparator.incidents(date)"
            )

            # --- treatments table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comparator.treatments (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    incident_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    treatment_description TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL DEFAULT 'unknown',
                    evidence_ids TEXT[] DEFAULT ARRAY[]::TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_treatments_incident "
                "ON arkham_comparator.treatments(incident_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_treatments_subject "
                "ON arkham_comparator.treatments(subject_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_treatments_tenant ON arkham_comparator.treatments(tenant_id)"
            )

            # --- divergences table ---
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comparator.divergences (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    incident_id TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    significance_score FLOAT NOT NULL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_divergences_incident "
                "ON arkham_comparator.divergences(incident_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_divergences_tenant "
                "ON arkham_comparator.divergences(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_divergences_score "
                "ON arkham_comparator.divergences(significance_score DESC)"
            )

            # --- legal_elements table ---
            # Tracks evidence mapped to s.13/s.26 legal elements per case
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_comparator.legal_elements (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    element_type TEXT NOT NULL,
                    element_name TEXT NOT NULL,
                    evidence_ref TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_comparator_legal_elements_case "
                "ON arkham_comparator.legal_elements(case_id, element_type)"
            )

            logger.info("Comparator database schema created")

        except Exception as e:
            logger.error(f"Failed to create Comparator schema: {e}")
