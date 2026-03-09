"""AuditTrail Shard - Immutable system action log."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class AuditTrailShard(ArkhamShard):
    """
    AuditTrail shard for ArkhamFrame.

    Immutable system action log
    """

    name = "audit-trail"
    version = "0.1.0"
    description = "Immutable system action log"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the AuditTrail shard with Frame services."""
        self._frame = frame

        logger.info("Initializing AuditTrail Shard...")

        # Get Frame services
        self._db = frame.database
        self._event_bus = frame.get_service("events")
        self._llm_service = frame.get_service("llm")
        self._vectors_service = frame.get_service("vectors")

        # Create database schema
        await self._create_schema()

        # Subscribe to ALL events via wildcard
        if self._event_bus:
            await self._event_bus.subscribe("*", self._on_event)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
        )

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.audit_trail_shard = self
            logger.debug("AuditTrail Shard registered on app.state")

        logger.info("AuditTrail Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down AuditTrail Shard...")
        if self._event_bus:
            await self._event_bus.unsubscribe("*", self._on_event)
        logger.info("AuditTrail Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_event(self, event_data: dict) -> None:
        """Log every platform event into the audit trail."""
        if not self._db:
            return

        try:
            import json
            import uuid

            event_type = event_data.get("event_type", "unknown")
            # Skip audit-trail's own internal events if any (prevent loop)
            if event_type.startswith("audit."):
                return

            payload = event_data.get("payload", {})
            source = event_data.get("source", "system")

            action_id = str(uuid.uuid4())
            tenant_id = self.get_tenant_id_or_none()

            await self._db.execute(
                """
                INSERT INTO arkham_audit_trail.actions
                (id, tenant_id, action_type, shard, entity_id, description, payload)
                VALUES (:id, :tenant_id, :type, :shard, :entity, :desc, :payload)
                """,
                {
                    "id": action_id,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "type": event_type,
                    "shard": source,
                    "entity": payload.get("id") or payload.get("document_id") or payload.get("item_id"),
                    "desc": f"Automated log for event {event_type}",
                    "payload": json.dumps(payload),
                },
            )
        except Exception as e:
            logger.warning(f"AuditTrail: failed to log event: {e}")

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for AuditTrail tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_audit_trail")

            # Actions table (immutable log)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_audit_trail.actions (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    user_id TEXT,
                    action_type TEXT NOT NULL,
                    shard TEXT,
                    entity_id TEXT,
                    description TEXT,
                    payload JSONB DEFAULT '{}',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Sessions table
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_audit_trail.sessions (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    user_id TEXT,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)

            # Exports table
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_audit_trail.exports (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    user_id TEXT,
                    export_format TEXT NOT NULL,
                    filters_applied JSONB DEFAULT '{}',
                    row_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_actions_tenant ON arkham_audit_trail.actions(tenant_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_actions_user ON arkham_audit_trail.actions(user_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_actions_type ON arkham_audit_trail.actions(action_type)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_actions_time ON arkham_audit_trail.actions(timestamp)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_exports_tenant ON arkham_audit_trail.exports(tenant_id)"
            )

            logger.info("AuditTrail database schema created")

        except Exception as e:
            logger.error(f"Failed to create AuditTrail schema: {e}")
