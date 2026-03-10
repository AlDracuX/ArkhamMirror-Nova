"""Rules Shard - Procedural rules and deadline engine."""

import logging
from typing import Any, Dict, List, Optional

from arkham_frame.shard_interface import ArkhamShard

from .api import init_api, router
from .calculator import DeadlineCalculator
from .llm import RulesLLM
from .seeder import RuleSeeder

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
        self.calculator: Optional[DeadlineCalculator] = None
        self.seeder: Optional[RuleSeeder] = None
        self.rules_llm: Optional[RulesLLM] = None

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

        # Initialize domain components
        self.calculator = DeadlineCalculator(db=self._db, event_bus=self._event_bus)
        self.seeder = RuleSeeder()
        self.rules_llm = RulesLLM(llm_service=self._llm_service)

        # Initialize API with our instances
        init_api(
            db=self._db,
            event_bus=self._event_bus,
            llm_service=self._llm_service,
            shard=self,
            calculator=self.calculator,
            seeder=self.seeder,
            rules_llm=self.rules_llm,
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
        self.calculator = None
        self.seeder = None
        self.rules_llm = None
        logger.info("Rules Shard shutdown complete")

    def get_routes(self):
        """Return FastAPI router for this shard."""
        return router

    # --- Event Handlers ---

    async def _on_deadline_created(self, event: Dict[str, Any]) -> None:
        """Handle deadlines.created events for rule calculations."""
        deadline_id = event.get("deadline_id")
        rule_id = event.get("rule_id")
        trigger_date_str = event.get("trigger_date")
        trigger_type = event.get("trigger_type", "custom")

        logger.info(f"Rules shard processing deadline: {deadline_id}")

        if not rule_id or not trigger_date_str or not self.calculator:
            return

        try:
            from datetime import date as date_type

            trigger_date = (
                date_type.fromisoformat(trigger_date_str) if isinstance(trigger_date_str, str) else trigger_date_str
            )
            await self.calculator.calculate(rule_id, trigger_date, trigger_type)
        except Exception as e:
            logger.error(f"Failed to calculate deadline from event: {e}")

    async def _on_document_processed(self, event: Dict[str, Any]) -> None:
        """Handle documents.processed events for procedural triggers."""
        doc_id = event.get("document_id")
        doc_type = event.get("document_type")
        doc_text = event.get("text", "")

        if doc_type in ["order", "judgment", "claim"]:
            logger.info(f"Rules shard triggered by {doc_type} document: {doc_id}")

            # Extract dates from document using LLM (or regex fallback)
            if self.rules_llm and doc_text:
                try:
                    extracted = await self.rules_llm.extract_dates(doc_text)
                    for ed in extracted:
                        if ed.creates_deadline:
                            logger.info(f"Extracted deadline date {ed.date} from {doc_type}: {ed.description}")
                except Exception as e:
                    logger.error(f"Date extraction failed: {e}")

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
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID,
                    rule_number TEXT NOT NULL,
                    title TEXT NOT NULL,
                    jurisdiction TEXT,
                    statute TEXT,
                    section TEXT,
                    description TEXT,
                    text TEXT,
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
                    applicability_notes TEXT,
                    claim_types TEXT[] DEFAULT '{}',
                    precedent_refs TEXT[] DEFAULT '{}',
                    tags JSONB DEFAULT '[]',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: add new columns to existing deployments
            new_columns = [
                ("jurisdiction", "TEXT"),
                ("statute", "TEXT"),
                ("section", "TEXT"),
                ("text", "TEXT"),
                ("applicability_notes", "TEXT"),
                ("claim_types", "TEXT[] DEFAULT '{}'"),
                ("precedent_refs", "TEXT[] DEFAULT '{}'"),
            ]
            for col_name, col_type in new_columns:
                await self._db.execute(f"""
                    DO $$ BEGIN
                        ALTER TABLE arkham_rules.rules ADD COLUMN {col_name} {col_type};
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
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
