"""Comparator Shard - Equality Act s.13/s.26 treatment comparison matrix."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

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

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.comparator_shard = self
            logger.debug("Comparator Shard registered on app.state")

        logger.info("Comparator Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Comparator Shard...")
        logger.info("Comparator Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

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
            # Named actual or hypothetical comparators for discrimination analysis
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
            # Discrete workplace events or policy applications to be compared
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
            # How each subject (claimant or named comparator) was treated per incident.
            # subject_id = 'claimant' or a comparator UUID.
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
            # Recorded findings of less favourable treatment (s.13/s.26 evidence)
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

            logger.info("Comparator database schema created")

        except Exception as e:
            logger.error(f"Failed to create Comparator schema: {e}")
