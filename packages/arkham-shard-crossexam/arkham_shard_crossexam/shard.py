"""CrossExam Shard - Cross-examination question trees and impeachment sequences."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class CrossExamShard(ArkhamShard):
    """
    CrossExam shard for ArkhamFrame.

    Cross-examination question trees and impeachment sequences
    """

    name = "crossexam"
    version = "0.1.0"
    description = "Cross-examination question trees and impeachment sequences"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the CrossExam shard with Frame services."""
        self._frame = frame

        logger.info("Initializing CrossExam Shard...")

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
            frame.app.state.crossexam_shard = self
            logger.debug("CrossExam Shard registered on app.state")

        logger.info("CrossExam Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down CrossExam Shard...")
        logger.info("CrossExam Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for CrossExam tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_crossexam")

            # Question Trees
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_crossexam.question_trees (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    witness_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    root_node_id TEXT,
                    status TEXT DEFAULT 'active',
                    project_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Question Nodes
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_crossexam.question_nodes (
                    id TEXT PRIMARY KEY,
                    tree_id TEXT NOT NULL REFERENCES arkham_crossexam.question_trees(id) ON DELETE CASCADE,
                    parent_id TEXT,
                    question_text TEXT NOT NULL,
                    expected_answer TEXT,
                    alternative_answer TEXT,
                    follow_up_expected_id TEXT,
                    follow_up_alternative_id TEXT,
                    damage_potential REAL DEFAULT 0.0,
                    damage_reasoning TEXT,
                    status TEXT DEFAULT 'pending',
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Impeachment Sequences
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_crossexam.impeachment_sequences (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    witness_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    conflict_description TEXT,
                    statement_claim_id TEXT,
                    document_evidence_id TEXT,
                    steps JSONB DEFAULT '[]',
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Damage Scores
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_crossexam.damage_scores (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    target_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    score REAL DEFAULT 0.0,
                    reasoning TEXT,
                    impacted_claims JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Ensure tenant_id exists in all tables
            tables = ["question_trees", "question_nodes", "impeachment_sequences", "damage_scores"]
            for table in tables:
                await self._db.execute(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'arkham_crossexam'
                              AND table_name = '{table}'
                              AND column_name = 'tenant_id'
                        ) THEN
                            ALTER TABLE arkham_crossexam.{table} ADD COLUMN tenant_id UUID;
                        END IF;
                    END $$;
                """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_crossexam_trees_witness ON arkham_crossexam.question_trees(witness_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_crossexam_trees_tenant ON arkham_crossexam.question_trees(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_crossexam_nodes_tree ON arkham_crossexam.question_nodes(tree_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_crossexam_impeachment_witness ON arkham_crossexam.impeachment_sequences(witness_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_crossexam_damage_target ON arkham_crossexam.damage_scores(target_id)"
            )

            logger.info("CrossExam database schema created")

        except Exception as e:
            logger.error(f"Failed to create CrossExam schema: {e}")
