"""Redline Shard - Document version comparison and semantic diff."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .engine import RedlineEngine
from .models import Comparison, ComparisonStatus

logger = logging.getLogger(__name__)


def _parse_json_field(value: Any, default: Any = None) -> Any:
    """Parse a JSON field that may already be parsed by the database driver."""
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return default if default is not None else []


class RedlineShard(ArkhamShard):
    """
    Redline shard for ArkhamFrame.

    Document version comparison and semantic diff.
    """

    name = "redline"
    version = "0.1.0"
    description = "Document version comparison and semantic diff"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None
        self.engine: RedlineEngine | None = None

    async def initialize(self, frame) -> None:
        """Initialize the Redline shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Redline Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Create engine
        self.engine = RedlineEngine(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
        )

        # Subscribe to events
        if self._event_bus:
            await self._event_bus.subscribe("documents.processed", self.handle_document_processed)
            await self._event_bus.subscribe("parse.completed", self.handle_parse_completed)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            engine=self.engine,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.redline_shard = self
            logger.debug("Redline Shard registered on app.state")

        logger.info("Redline Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Redline Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("documents.processed", self.handle_document_processed)
            await self._event_bus.unsubscribe("parse.completed", self.handle_parse_completed)
        self.engine = None
        logger.info("Redline Shard shutdown complete")

    async def handle_document_processed(self, event_data: Dict[str, Any]) -> None:
        """Handle document processed event."""
        payload = event_data.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id:
            logger.info(f"Redline Shard: Notified of document {doc_id}")

    async def handle_parse_completed(self, event_data: Dict[str, Any]) -> None:
        """Handle parse completed event."""
        payload = event_data.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id:
            logger.info(f"Redline Shard: Notified of parse complete for {doc_id}")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- CRUD helpers ---

    async def create_comparison(
        self,
        doc_a_id: str,
        doc_b_id: str,
        title: str = "",
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new comparison record in pending status."""
        comp_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        if self._db:
            await self._db.execute(
                """
                INSERT INTO arkham_redline.comparisons
                (id, case_id, doc_a_id, doc_b_id, title, status, diff_count,
                 additions, deletions, modifications, diffs, created_at, updated_at)
                VALUES (:id, :case_id, :doc_a_id, :doc_b_id, :title, :status,
                        0, 0, 0, 0, :diffs, :created_at, :updated_at)
                """,
                {
                    "id": comp_id,
                    "case_id": case_id,
                    "doc_a_id": doc_a_id,
                    "doc_b_id": doc_b_id,
                    "title": title,
                    "status": ComparisonStatus.PENDING,
                    "diffs": "[]",
                    "created_at": now,
                    "updated_at": now,
                },
            )

        if self._event_bus:
            await self._event_bus.emit(
                "redline.comparison.created",
                {"comparison_id": comp_id},
                source="redline-shard",
            )

        return {
            "id": comp_id,
            "case_id": case_id,
            "doc_a_id": doc_a_id,
            "doc_b_id": doc_b_id,
            "title": title,
            "status": ComparisonStatus.PENDING,
            "diff_count": 0,
            "additions": 0,
            "deletions": 0,
            "modifications": 0,
            "diffs": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    async def get_comparison(self, comp_id: str) -> Optional[Dict[str, Any]]:
        """Get a comparison by ID."""
        if not self._db:
            return None
        row = await self._db.fetch_one(
            "SELECT * FROM arkham_redline.comparisons WHERE id = :id",
            {"id": comp_id},
        )
        if not row:
            return None
        result = dict(row)
        result["diffs"] = _parse_json_field(result.get("diffs"), [])
        return result

    async def list_comparisons(
        self,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List comparisons with optional filters."""
        if not self._db:
            return []

        query = "SELECT * FROM arkham_redline.comparisons WHERE 1=1"
        params: Dict[str, Any] = {}

        if case_id:
            query += " AND case_id = :case_id"
            params["case_id"] = case_id
        if status:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY created_at DESC"

        rows = await self._db.fetch_all(query, params)
        results = []
        for row in rows:
            r = dict(row)
            r["diffs"] = _parse_json_field(r.get("diffs"), [])
            results.append(r)
        return results

    async def update_comparison(self, comp_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a comparison record."""
        if not self._db:
            return None

        # Validate status if provided
        if "status" in updates and updates["status"] not in ComparisonStatus.ALL:
            return None

        allowed_fields = {
            "title",
            "status",
            "diff_count",
            "additions",
            "deletions",
            "modifications",
            "diffs",
            "case_id",
        }
        set_clauses = []
        params: Dict[str, Any] = {"id": comp_id}

        for key, value in updates.items():
            if key in allowed_fields:
                if key == "diffs":
                    value = json.dumps(value) if isinstance(value, (list, dict)) else value
                set_clauses.append(f"{key} = :{key}")
                params[key] = value

        if not set_clauses:
            return await self.get_comparison(comp_id)

        set_clauses.append("updated_at = :updated_at")
        params["updated_at"] = datetime.now(timezone.utc)

        await self._db.execute(
            f"UPDATE arkham_redline.comparisons SET {', '.join(set_clauses)} WHERE id = :id",
            params,
        )

        return await self.get_comparison(comp_id)

    async def delete_comparison(self, comp_id: str) -> bool:
        """Delete a comparison record. Returns True if deleted."""
        if not self._db:
            return False
        await self._db.execute(
            "DELETE FROM arkham_redline.comparisons WHERE id = :id",
            {"id": comp_id},
        )
        return True

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Redline tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_redline")

            # Migration: drop legacy table if schema doesn't match (v1 had
            # base_document_id/target_document_id; v2 uses doc_a_id/doc_b_id
            # plus status, title, diffs, additions, deletions, modifications).
            await self._db.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'arkham_redline'
                        AND table_name = 'comparisons'
                        AND column_name = 'base_document_id'
                    ) THEN
                        DROP TABLE arkham_redline.comparisons;
                    END IF;
                END $$
            """)

            # Create comparisons table (v2 spec)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_redline.comparisons (
                    id UUID PRIMARY KEY,
                    case_id UUID,
                    doc_a_id UUID,
                    doc_b_id UUID,
                    title TEXT,
                    status TEXT DEFAULT 'pending',
                    diff_count INTEGER DEFAULT 0,
                    additions INTEGER DEFAULT 0,
                    deletions INTEGER DEFAULT 0,
                    modifications INTEGER DEFAULT 0,
                    diffs JSONB DEFAULT '[]',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_redline_comp_case ON arkham_redline.comparisons(case_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_redline_comp_status ON arkham_redline.comparisons(status)"
            )

            logger.info("Redline database schema created")

        except Exception as e:
            logger.error(f"Failed to create Redline schema: {e}")
