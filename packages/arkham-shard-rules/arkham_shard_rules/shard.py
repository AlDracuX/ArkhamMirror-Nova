"""Rules Shard - Procedural rules and deadline engine."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router

logger = logging.getLogger(__name__)


class RulesShard(ArkhamShard):
    """
    Rules shard for ArkhamFrame.

    Encodes Employment Tribunal Rules of Procedure, Practice Directions,
    and key case management principles. Auto-calculates deadlines from
    trigger events.
    """

    name = "rules"
    version = "0.1.0"
    description = "Procedural rules and deadline engine"

    def __init__(self):
        super().__init__()  # Auto-loads manifest from shard.yaml
        self._frame = None
        self._db = None
        self._event_bus = None
        self._llm_service = None
        self._vectors_service = None

    async def initialize(self, frame) -> None:
        """Initialize the Rules shard with Frame services."""
        self._frame = frame

        logger.info("Initializing Rules Shard...")

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
            await self._event_bus.subscribe("deadlines.created", self._on_deadline_created)
            await self._event_bus.subscribe("documents.processed", self._on_document_processed)

        # Register self in app state for API access
        if hasattr(frame, "app") and frame.app:
            frame.app.state.rules_shard = self
            logger.debug("Rules Shard registered on app.state")

        logger.info("Rules Shard initialized")

    async def shutdown(self) -> None:
        """Clean up shard resources."""
        logger.info("Shutting down Rules Shard...")
        logger.info("Rules Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_deadline_created(self, event: Dict[str, Any]) -> None:
        """Handle deadlines.created events for rule calculations."""
        deadline_id = event.get("deadline_id")
        logger.info(f"Rules shard processing deadline: {deadline_id}")
        # Stub logic:
        # 1. Fetch deadline details
        # 2. Match against Rules (e.g. Rule 29, 38)
        # 3. Perform offset calculation
        # 4. Update deadline or create Breach if missed

    async def _on_document_processed(self, event: Dict[str, Any]) -> None:
        """Handle documents.processed events for procedural triggers."""
        doc_id = event.get("document_id")
        doc_type = event.get("document_type")

        if doc_type in ["order", "judgment", "claim"]:
            logger.info(f"Rules shard triggered by {doc_type} document: {doc_id}")
            # Stub logic:
            # 1. Extract dates from document
            # 2. Trigger automatic deadline calculations
            # 3. Emit rules.deadline.calculated event

    # --- Database Schema ---

    async def _create_schema(self) -> None:
        """Create database schema for Rules tables."""
        if not self._db:
            logger.warning("Database service not available - persistence disabled")
            return

        try:
            # Create schema
            await self._db.execute("CREATE SCHEMA IF NOT EXISTS arkham_rules")

            # -------------------------------------------------------
            # Rules table - encoded procedural rules
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_rules.rules (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    rule_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    trigger_type TEXT,
                    deadline_days INTEGER,
                    deadline_type TEXT DEFAULT 'calendar_days',
                    statutory_source TEXT,
                    applies_to TEXT DEFAULT 'both',
                    is_mandatory BOOLEAN DEFAULT TRUE,
                    consequence_of_breach TEXT,
                    strike_out_risk BOOLEAN DEFAULT FALSE,
                    unless_order_applicable BOOLEAN DEFAULT FALSE,
                    notes TEXT,
                    tags JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # -------------------------------------------------------
            # Calculations table - computed deadlines
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_rules.calculations (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    rule_id TEXT NOT NULL REFERENCES arkham_rules.rules(id),
                    rule_number TEXT,
                    rule_title TEXT,
                    trigger_date DATE NOT NULL,
                    trigger_type TEXT,
                    deadline_date DATE NOT NULL,
                    deadline_days INTEGER,
                    deadline_type TEXT,
                    description TEXT,
                    project_id TEXT,
                    document_id TEXT,
                    respondent TEXT,
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Breaches table - logged procedural breaches
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_rules.breaches (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    rule_id TEXT NOT NULL REFERENCES arkham_rules.rules(id),
                    rule_number TEXT,
                    rule_title TEXT,
                    breaching_party TEXT NOT NULL,
                    breach_date DATE NOT NULL,
                    deadline_date DATE,
                    description TEXT,
                    severity TEXT DEFAULT 'moderate',
                    status TEXT DEFAULT 'detected',
                    document_evidence JSONB DEFAULT '[]',
                    suggested_remedy TEXT,
                    application_text TEXT,
                    project_id TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # -------------------------------------------------------
            # Compliance Checks table
            # -------------------------------------------------------
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS arkham_rules.compliance_checks (
                    id TEXT PRIMARY KEY,
                    tenant_id UUID,
                    document_id TEXT,
                    submission_type TEXT,
                    rules_checked JSONB DEFAULT '[]',
                    result TEXT DEFAULT 'compliant',
                    issues_found JSONB DEFAULT '[]',
                    warnings JSONB DEFAULT '[]',
                    passed_checks JSONB DEFAULT '[]',
                    recommendations JSONB DEFAULT '[]',
                    score REAL DEFAULT 0.0,
                    project_id TEXT,
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Tenant_id migration / addition for all tables
            await self._db.execute("""
                DO $$
                DECLARE
                    tables_to_update TEXT[] := ARRAY[
                        'rules', 'calculations', 'breaches', 'compliance_checks'
                    ];
                    tbl TEXT;
                BEGIN
                    FOREACH tbl IN ARRAY tables_to_update LOOP
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'arkham_rules'
                            AND table_name = tbl
                            AND column_name = 'tenant_id'
                        ) THEN
                            EXECUTE format('ALTER TABLE arkham_rules.%I ADD COLUMN tenant_id UUID', tbl);
                        END IF;
                    END LOOP;
                END $$;
            """)

            # Indexes
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_rule_number ON arkham_rules.rules(rule_number)"
            )
            await self._db.execute("CREATE INDEX IF NOT EXISTS idx_rules_tenant ON arkham_rules.rules(tenant_id)")
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_calcs_project ON arkham_rules.calculations(project_id)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_calcs_deadline ON arkham_rules.calculations(deadline_date)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_breaches_party ON arkham_rules.breaches(breaching_party)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_breaches_status ON arkham_rules.breaches(status)"
            )
            await self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rules_checks_project ON arkham_rules.compliance_checks(project_id)"
            )

            logger.info("Rules database schema created")

        except Exception as e:
            logger.error(f"Failed to create Rules schema: {e}")
