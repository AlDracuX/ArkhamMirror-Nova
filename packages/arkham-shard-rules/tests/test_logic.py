"""
Rules Shard - Logic Tests

Tests for models, API handler logic, and procedural rule calculations.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_rules.models import (
    Breach,
    BreachSeverity,
    BreachStatus,
    Calculation,
    ComplianceCheck,
    ComplianceResult,
    DeadlineType,
    Rule,
    RuleCategory,
    TriggerType,
)
from arkham_shard_rules.shard import RulesShard
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_frame(mock_events, mock_db):
    frame = MagicMock()
    frame.database = mock_db
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "events": mock_events,
            "llm": None,
            "database": mock_db,
            "vectors": None,
            "documents": None,
        }.get(name)
    )
    return frame


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and enum values."""

    def test_rule_defaults(self):
        r = Rule(
            id="r1",
            rule_number="Rule 29",
            title="Case Management Orders",
            description="Tribunal may at any stage... make a case management order.",
            category=RuleCategory.CASE_MANAGEMENT,
            trigger_type=TriggerType.DATE_OF_ORDER,
        )
        assert r.id == "r1"
        assert r.rule_number == "Rule 29"
        assert r.is_mandatory is True
        assert r.deadline_type == DeadlineType.CALENDAR_DAYS

    def test_rule_category_enum(self):
        assert RuleCategory.INITIAL_CONSIDERATION == "initial_consideration"
        assert RuleCategory.CASE_MANAGEMENT == "case_management"
        assert RuleCategory.DISCLOSURE == "disclosure"
        assert RuleCategory.WITNESSES == "witnesses"
        assert RuleCategory.HEARING == "hearing"
        assert RuleCategory.JUDGMENT == "judgment"
        assert RuleCategory.APPEAL == "appeal"
        assert RuleCategory.COSTS == "costs"
        assert RuleCategory.UNLESS_ORDER == "unless_order"
        assert RuleCategory.STRIKE_OUT == "strike_out"
        assert RuleCategory.DEPOSIT_ORDER == "deposit_order"
        assert RuleCategory.DEFAULT_JUDGMENT == "default_judgment"

    def test_deadline_type_enum(self):
        assert DeadlineType.CALENDAR_DAYS == "calendar_days"
        assert DeadlineType.WORKING_DAYS == "working_days"
        assert DeadlineType.MONTHS == "months"
        assert DeadlineType.WEEKS == "weeks"

    def test_trigger_type_enum(self):
        assert TriggerType.DATE_OF_ORDER == "date_of_order"
        assert TriggerType.DATE_OF_JUDGMENT == "date_of_judgment"
        assert TriggerType.DATE_OF_HEARING == "date_of_hearing"
        assert TriggerType.DATE_OF_CLAIM == "date_of_claim"
        assert TriggerType.DATE_OF_RESPONSE == "date_of_response"
        assert TriggerType.DATE_OF_DISMISSAL == "date_of_dismissal"
        assert TriggerType.DATE_OF_DISCLOSURE_REQUEST == "date_of_disclosure_request"
        assert TriggerType.DATE_OF_NOTIFICATION == "date_of_notification"
        assert TriggerType.CUSTOM == "custom"

    def test_breach_severity_enum(self):
        assert BreachSeverity.MINOR == "minor"
        assert BreachSeverity.MODERATE == "moderate"
        assert BreachSeverity.SERIOUS == "serious"
        assert BreachSeverity.EGREGIOUS == "egregious"

    def test_breach_status_enum(self):
        assert BreachStatus.DETECTED == "detected"
        assert BreachStatus.NOTIFIED == "notified"
        assert BreachStatus.APPLICATION_DRAFTED == "application_drafted"
        assert BreachStatus.APPLICATION_FILED == "application_filed"
        assert BreachStatus.RESOLVED == "resolved"
        assert BreachStatus.DISMISSED == "dismissed"

    def test_compliance_result_enum(self):
        assert ComplianceResult.COMPLIANT == "compliant"
        assert ComplianceResult.NON_COMPLIANT == "non_compliant"
        assert ComplianceResult.BORDERLINE == "borderline"
        assert ComplianceResult.UNABLE_TO_ASSESS == "unable_to_assess"

    def test_calculation_model(self):
        c = Calculation(
            id="c1",
            rule_id="r1",
            rule_number="Rule 29",
            rule_title="Order",
            trigger_date=date(2024, 1, 1),
            trigger_type=TriggerType.DATE_OF_ORDER,
            deadline_date=date(2024, 1, 15),
            deadline_days=14,
            deadline_type=DeadlineType.CALENDAR_DAYS,
            description="Due in 14 days",
        )
        assert c.id == "c1"
        assert c.deadline_days == 14

    def test_breach_model(self):
        b = Breach(
            id="b1",
            rule_id="r1",
            rule_number="Rule 29",
            rule_title="Order",
            breaching_party="Respondent",
            breach_date=date(2024, 1, 16),
            deadline_date=date(2024, 1, 15),
            description="Failed to comply with order",
        )
        assert b.id == "b1"
        assert b.severity == BreachSeverity.MODERATE
        assert b.status == BreachStatus.DETECTED

    def test_compliance_check_model(self):
        cc = ComplianceCheck(
            id="cc1",
            document_id="doc1",
            submission_type="ET3 Response",
            rules_checked=["r1", "r2"],
            result=ComplianceResult.COMPLIANT,
        )
        assert cc.id == "cc1"
        assert cc.score == 0.0


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = RulesShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_rules" in executed_sql
        assert "arkham_rules.rules" in executed_sql
        assert "arkham_rules.calculations" in executed_sql
        assert "arkham_rules.breaches" in executed_sql
        assert "arkham_rules.compliance_checks" in executed_sql

    @pytest.mark.asyncio
    async def test_rules_table_columns(self, mock_frame, mock_db):
        shard = RulesShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        rules_ddl = next((s for s in ddl_calls if "rules" in s and "CREATE TABLE" in s), None)
        assert rules_ddl is not None
        assert "rule_number" in rules_ddl
        assert "trigger_type" in rules_ddl
        assert "deadline_days" in rules_ddl
        assert "strike_out_risk" in rules_ddl

    @pytest.mark.asyncio
    async def test_rules_table_new_columns(self, mock_frame, mock_db):
        """Verify new columns (jurisdiction, statute, section, claim_types, etc.) in DDL."""
        shard = RulesShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        rules_ddl = next((s for s in ddl_calls if "CREATE TABLE" in s and "arkham_rules.rules" in s), None)
        assert rules_ddl is not None
        assert "jurisdiction" in rules_ddl
        assert "statute" in rules_ddl
        assert "section" in rules_ddl
        assert "claim_types" in rules_ddl
        assert "precedent_refs" in rules_ddl
        assert "applicability_notes" in rules_ddl
        assert "UUID PRIMARY KEY" in rules_ddl
        assert "TIMESTAMPTZ" in rules_ddl

    @pytest.mark.asyncio
    async def test_breaches_table_columns(self, mock_frame, mock_db):
        shard = RulesShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        breaches_ddl = next((s for s in ddl_calls if "breaches" in s and "CREATE TABLE" in s), None)
        assert breaches_ddl is not None
        assert "breaching_party" in breaches_ddl
        assert "breach_date" in breaches_ddl
        assert "severity" in breaches_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = RulesShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 7


# ---------------------------------------------------------------------------
# API Logic Tests (unit-level, no HTTP layer)
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        """Reset module-level _db before each test."""
        import arkham_shard_rules.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_rules_no_db(self):
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_rules()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_rules(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "r1", "rule_number": "R1"}]
        result = await self.api.list_rules(category="case_management")
        assert len(result) == 1
        assert result[0]["id"] == "r1"
        assert "category" in mock_db.fetch_all.call_args[0][1]

    @pytest.mark.asyncio
    async def test_create_rule(self, mock_db):
        from arkham_shard_rules.api import RuleCreate, create_rule

        self.api._db = mock_db
        self.api._shard = None

        req = RuleCreate(rule_number="Rule 1", title="Title", category="case_management", trigger_type="date_of_order")
        result = await create_rule(req)
        assert "id" in result
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_calculations(self, mock_db):
        self.api._db = mock_db
        await self.api.list_calculations(project_id="p1")
        mock_db.fetch_all.assert_called_once()
        assert "project_id" in mock_db.fetch_all.call_args[0][1]

    @pytest.mark.asyncio
    async def test_list_breaches(self, mock_db):
        self.api._db = mock_db
        await self.api.list_breaches(project_id="p1", party="Respondent")
        mock_db.fetch_all.assert_called_once()
        params = mock_db.fetch_all.call_args[0][1]
        assert params["project_id"] == "p1"
        assert params["party"] == "Respondent"

    @pytest.mark.asyncio
    async def test_create_breach(self, mock_db, mock_events):
        from arkham_shard_rules.api import BreachCreate, create_breach

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        mock_db.fetch_one.return_value = {"rule_number": "R1", "title": "T1"}

        req = BreachCreate(
            rule_id="r1", breaching_party="Respondent", breach_date=date.today(), description="Missed deadline"
        )
        result = await create_breach(req)
        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "rules.breach.detected"

    @pytest.mark.asyncio
    async def test_create_breach_not_found(self, mock_db):
        from arkham_shard_rules.api import BreachCreate, create_breach

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        req = BreachCreate(
            rule_id="nonexistent", breaching_party="Respondent", breach_date=date.today(), description="Missed deadline"
        )
        with pytest.raises(HTTPException) as exc:
            await create_breach(req)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_compliance_checks(self, mock_db):
        self.api._db = mock_db
        await self.api.list_compliance_checks(project_id="p1")
        mock_db.fetch_all.assert_called_once()


# ---------------------------------------------------------------------------
# New CRUD + Domain Endpoint Tests
# ---------------------------------------------------------------------------


class TestRuleCRUD:
    """Test the full CRUD lifecycle and domain endpoints for rules."""

    def setup_method(self):
        import arkham_shard_rules.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_rule_with_all_fields(self, mock_db):
        """Test rule creation with all fields including claim_types, precedent_refs, jurisdiction."""
        from arkham_shard_rules.api import RuleCreate, create_rule

        self.api._db = mock_db
        self.api._shard = None

        req = RuleCreate(
            rule_number="Rule 38",
            title="Unless Orders",
            jurisdiction="England & Wales",
            statute="Employment Tribunals Rules of Procedure 2013",
            section="38",
            description="Unless orders and automatic strike-out",
            text="An order may specify that unless the order is complied with by the date specified...",
            category="unless_order",
            trigger_type="date_of_order",
            deadline_days=14,
            deadline_type="calendar_days",
            statutory_source="SI 2013/1237",
            applies_to="both",
            is_mandatory=True,
            consequence_of_breach="Automatic strike-out of claim or response",
            strike_out_risk=True,
            unless_order_applicable=True,
            notes="Critical compliance rule",
            applicability_notes="Applies when party fails to comply with tribunal order",
            claim_types=["unfair_dismissal", "discrimination", "whistleblowing"],
            precedent_refs=["Thind v Salvesen Logistics [2010]", "Marcan Shipping v Kefalas [2007]"],
            tags=["compliance", "strike-out"],
        )
        result = await create_rule(req)
        assert "id" in result
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()

        # Verify the params passed include all new fields
        call_params = mock_db.execute.call_args[0][1]
        assert call_params["jurisdiction"] == "England & Wales"
        assert call_params["statute"] == "Employment Tribunals Rules of Procedure 2013"
        assert call_params["section"] == "38"
        assert (
            call_params["text"]
            == "An order may specify that unless the order is complied with by the date specified..."
        )
        assert call_params["applicability_notes"] == "Applies when party fails to comply with tribunal order"
        assert call_params["claim_types"] == ["unfair_dismissal", "discrimination", "whistleblowing"]
        assert call_params["precedent_refs"] == [
            "Thind v Salvesen Logistics [2010]",
            "Marcan Shipping v Kefalas [2007]",
        ]

    @pytest.mark.asyncio
    async def test_applicable_rules_filtering_by_claim_type(self, mock_db):
        """Test GET /applicable returns rules matching claim_type in claim_types array."""
        from arkham_shard_rules.api import get_applicable_rules

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [
            {
                "id": "r1",
                "title": "Unless Orders",
                "jurisdiction": "England & Wales",
                "claim_types": ["unfair_dismissal", "discrimination"],
            },
            {
                "id": "r2",
                "title": "Time Limits",
                "jurisdiction": "England & Wales",
                "claim_types": ["unfair_dismissal"],
            },
        ]

        result = await get_applicable_rules(claim_type="unfair_dismissal")
        assert len(result) == 2
        assert result[0]["id"] == "r1"
        assert result[1]["id"] == "r2"

        # Verify the query uses ANY(claim_types)
        query_sql = mock_db.fetch_all.call_args[0][0]
        assert "ANY(claim_types)" in query_sql
        query_params = mock_db.fetch_all.call_args[0][1]
        assert query_params["claim_type"] == "unfair_dismissal"

    @pytest.mark.asyncio
    async def test_jurisdiction_filtering(self, mock_db):
        """Test list_rules filters by jurisdiction parameter."""
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [
            {"id": "r1", "title": "Rule A", "jurisdiction": "Scotland"},
        ]

        result = await self.api.list_rules(jurisdiction="Scotland")
        assert len(result) == 1
        assert result[0]["jurisdiction"] == "Scotland"

        query_sql = mock_db.fetch_all.call_args[0][0]
        assert "jurisdiction = :jurisdiction" in query_sql
        query_params = mock_db.fetch_all.call_args[0][1]
        assert query_params["jurisdiction"] == "Scotland"

    @pytest.mark.asyncio
    async def test_statute_filtering(self, mock_db):
        """Test list_rules filters by statute parameter."""
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [
            {"id": "r1", "title": "Rule A", "statute": "Equality Act 2010"},
        ]

        result = await self.api.list_rules(statute="Equality Act 2010")
        assert len(result) == 1

        query_params = mock_db.fetch_all.call_args[0][1]
        assert query_params["statute"] == "Equality Act 2010"

    @pytest.mark.asyncio
    async def test_empty_claim_types_array_handling(self, mock_db):
        """Test that creating a rule with empty claim_types defaults correctly."""
        from arkham_shard_rules.api import RuleCreate, create_rule

        self.api._db = mock_db
        self.api._shard = None

        req = RuleCreate(
            title="General Rule",
            # claim_types not provided — should default to empty list
        )
        assert req.claim_types == []
        assert req.precedent_refs == []

        result = await create_rule(req)
        assert result["status"] == "created"

        call_params = mock_db.execute.call_args[0][1]
        assert call_params["claim_types"] == []
        assert call_params["precedent_refs"] == []

    @pytest.mark.asyncio
    async def test_update_rule_preserves_unchanged_fields(self, mock_db):
        """Test that PUT only updates provided fields, preserving others."""
        from arkham_shard_rules.api import RuleUpdate, update_rule

        self.api._db = mock_db

        # Existing rule in DB
        existing_rule = {
            "id": "r1",
            "title": "Original Title",
            "jurisdiction": "England & Wales",
            "statute": "ET Rules 2013",
            "section": "29",
            "claim_types": ["unfair_dismissal"],
            "precedent_refs": ["Case A"],
            "notes": "Original notes",
        }
        mock_db.fetch_one.return_value = existing_rule

        # Only update title
        req = RuleUpdate(title="Updated Title")
        result = await update_rule("r1", req)

        # Verify only 'title' and 'updated_at' are in the SET clause
        update_sql = mock_db.execute.call_args[0][0]
        assert "title = :title" in update_sql
        assert "updated_at = CURRENT_TIMESTAMP" in update_sql

        # Verify jurisdiction, statute, etc. are NOT in the update params
        update_params = mock_db.execute.call_args[0][1]
        assert update_params["title"] == "Updated Title"
        assert "jurisdiction" not in update_params
        assert "statute" not in update_params
        assert "claim_types" not in update_params

    @pytest.mark.asyncio
    async def test_get_single_rule(self, mock_db):
        """Test GET /rules/{id} returns a single rule."""
        from arkham_shard_rules.api import get_rule

        self.api._db = mock_db
        mock_db.fetch_one.return_value = {
            "id": "r1",
            "title": "Test Rule",
            "jurisdiction": "England & Wales",
        }

        result = await get_rule("r1")
        assert result["id"] == "r1"
        assert result["title"] == "Test Rule"

    @pytest.mark.asyncio
    async def test_get_single_rule_not_found(self, mock_db):
        """Test GET /rules/{id} returns 404 for missing rule."""
        from arkham_shard_rules.api import get_rule

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_rule("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_rule(self, mock_db):
        """Test DELETE /rules/{id} removes a rule."""
        from arkham_shard_rules.api import delete_rule

        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "r1"}

        result = await delete_rule("r1")
        assert result["id"] == "r1"
        assert result["status"] == "deleted"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(self, mock_db):
        """Test DELETE /rules/{id} returns 404 for missing rule."""
        from arkham_shard_rules.api import delete_rule

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await delete_rule("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_rule_not_found(self, mock_db):
        """Test PUT /rules/{id} returns 404 for missing rule."""
        from arkham_shard_rules.api import RuleUpdate, update_rule

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        req = RuleUpdate(title="New Title")
        with pytest.raises(HTTPException) as exc:
            await update_rule("nonexistent", req)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_applicable_rules_no_db(self, mock_db):
        """Test GET /applicable returns 503 when DB unavailable."""
        from arkham_shard_rules.api import get_applicable_rules

        self.api._db = None

        with pytest.raises(HTTPException) as exc:
            await get_applicable_rules(claim_type="unfair_dismissal")
        assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# DeadlineCalculator Tests
# ---------------------------------------------------------------------------


class TestDeadlineCalculator:
    """Tests for DeadlineCalculator domain logic."""

    def setup_method(self):
        from arkham_shard_rules.calculator import DeadlineCalculator

        self.calc = DeadlineCalculator()

    def test_add_working_days_skips_weekends(self):
        """Friday + 3 working days = Wednesday."""
        friday = date(2026, 3, 6)  # Friday
        result = self.calc.add_working_days(friday, 3)
        assert result == date(2026, 3, 11)  # Wednesday
        assert result.weekday() == 2  # Wednesday

    def test_add_working_days_skips_bank_holidays(self):
        """Working days skip UK bank holidays."""
        # 2026-04-02 is Thursday before Good Friday (2026-04-03) and Easter Monday (2026-04-06)
        thursday_before_easter = date(2026, 4, 2)
        result = self.calc.add_working_days(thursday_before_easter, 1)
        # Next working day after Thursday is Tuesday 7th April (skips Good Friday, Sat, Sun, Easter Monday)
        assert result == date(2026, 4, 7)

    def test_add_calendar_days_28(self):
        """Rule 4: 28 calendar days from trigger date."""
        trigger = date(2026, 1, 1)
        result = self.calc.add_calendar_days(trigger, 28)
        assert result == date(2026, 1, 29)

    @pytest.mark.asyncio
    async def test_calculate_deadline_calendar_days(self, mock_db):
        """Calculate deadline using calendar_days type."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        mock_db.fetch_one.return_value = {
            "id": "r1",
            "rule_number": "Rule 4",
            "title": "Time Limits",
            "deadline_days": 28,
            "deadline_type": "calendar_days",
        }

        result = await calc.calculate("r1", date(2026, 1, 1), "date_of_order")
        assert result["deadline_date"] == "2026-01-29"
        assert result["rule_number"] == "Rule 4"
        assert result["deadline_days"] == 28
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_detect_breach_missed_deadline(self, mock_db):
        """Detect breaches for missed deadlines."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        mock_db.fetch_all.return_value = [
            {
                "id": "calc1",
                "rule_id": "r1",
                "rule_number": "Rule 16",
                "rule_title": "Response to Claim",
                "deadline_date": date(2026, 1, 1),
                "metadata": {},
            },
        ]

        breaches = await calc.detect_breaches("project-1")
        assert len(breaches) == 1
        assert breaches[0]["rule_number"] == "Rule 16"
        assert breaches[0]["severity"] == "moderate"
        assert breaches[0]["status"] == "detected"

    @pytest.mark.asyncio
    async def test_detect_breach_no_breach_when_completed(self, mock_db):
        """No breach when calculation is marked completed."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        # Completed calculations should not appear in results
        # because the SQL query filters on (metadata->>'completed') IS NULL
        mock_db.fetch_all.return_value = []

        breaches = await calc.detect_breaches("project-1")
        assert len(breaches) == 0

    @pytest.mark.asyncio
    async def test_compliance_check_et3_response(self, mock_db):
        """Compliance check for ET3 response submission."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        # Rules matching the submission type
        mock_db.fetch_all.return_value = [
            {
                "id": "r1",
                "rule_number": "Rule 16",
                "title": "Response to Claim",
                "is_mandatory": True,
            },
        ]

        # Calculation exists and is compliant (deadline not passed)
        mock_db.fetch_one.return_value = {
            "rule_id": "r1",
            "document_id": "doc1",
            "deadline_date": date(2099, 1, 1),  # far future
            "metadata": {},
        }

        result = await calc.check_compliance("doc1", "date_of_claim")
        assert result["result"] == "compliant"
        assert len(result["passed_checks"]) == 1
        assert result["score"] == 1.0

    @pytest.mark.asyncio
    async def test_unless_order_risk_high_severity(self, mock_db):
        """Unless order risk is high for egregious breach with strike-out risk."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        # Setup breach
        mock_db.fetch_one.side_effect = [
            # First call: fetch breach
            {
                "id": "b1",
                "rule_id": "r1",
                "breaching_party": "Respondent",
                "severity": "egregious",
                "project_id": "p1",
            },
            # Second call: fetch rule
            {
                "id": "r1",
                "is_mandatory": True,
                "strike_out_risk": True,
                "unless_order_applicable": True,
            },
            # Third call: count prior breaches
            {"count": 4},
        ]

        result = await calc.assess_unless_order_risk("b1")
        assert result["risk_level"] == "high"
        assert result["risk_score"] >= 0.7
        assert result["strike_out_risk"] is True
        assert result["prior_breach_count"] == 4


# ---------------------------------------------------------------------------
# RuleSeeder Tests
# ---------------------------------------------------------------------------


class TestRuleSeeder:
    """Tests for RuleSeeder."""

    @pytest.mark.asyncio
    async def test_seed_creates_all_rules(self, mock_db):
        """Seed inserts all ET rules."""
        from arkham_shard_rules.seeder import RuleSeeder

        seeder = RuleSeeder()
        count = await seeder.seed(mock_db)

        assert count == len(seeder.ET_RULES)
        assert count >= 17  # at minimum the key rules
        assert mock_db.execute.call_count == count

        # Verify at least Rule 1, Rule 37, Rule 76 are present
        rule_numbers = [r["rule_number"] for r in seeder.ET_RULES]
        assert "Rule 1" in rule_numbers
        assert "Rule 37" in rule_numbers
        assert "Rule 76" in rule_numbers

    @pytest.mark.asyncio
    async def test_seed_no_db_raises(self):
        """Seed raises RuntimeError when no DB is provided."""
        from arkham_shard_rules.seeder import RuleSeeder

        seeder = RuleSeeder()
        with pytest.raises(RuntimeError, match="Database not available"):
            await seeder.seed(None)

    def test_seeder_rules_have_required_fields(self):
        """Every seeded rule has required fields."""
        from arkham_shard_rules.seeder import RuleSeeder

        seeder = RuleSeeder()
        for rule in seeder.ET_RULES:
            assert "rule_number" in rule, f"Missing rule_number in {rule}"
            assert "title" in rule, f"Missing title in {rule}"
            assert "description" in rule, f"Missing description in {rule}"
            assert "category" in rule, f"Missing category in {rule}"

    @pytest.mark.asyncio
    async def test_seed_upsert_sql_contains_on_conflict(self, mock_db):
        """Verify seed uses ON CONFLICT for idempotent upsert."""
        from arkham_shard_rules.seeder import RuleSeeder

        seeder = RuleSeeder()
        await seeder.seed(mock_db)

        sql = mock_db.execute.call_args_list[0][0][0]
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql

    def test_seeder_includes_practice_directions(self):
        """Verify seeder includes practice direction entries."""
        from arkham_shard_rules.seeder import RuleSeeder

        seeder = RuleSeeder()
        pd_rules = [r for r in seeder.ET_RULES if r["rule_number"].startswith("PD")]
        assert len(pd_rules) >= 2, "Should include at least 2 practice directions"


# ---------------------------------------------------------------------------
# Additional DeadlineCalculator Edge Case Tests
# ---------------------------------------------------------------------------


class TestDeadlineCalculatorEdgeCases:
    """Edge-case tests for DeadlineCalculator."""

    def setup_method(self):
        from arkham_shard_rules.calculator import DeadlineCalculator

        self.calc = DeadlineCalculator()

    def test_add_working_days_zero(self):
        """Zero working days returns the same date."""
        start = date(2026, 3, 9)  # Monday
        assert self.calc.add_working_days(start, 0) == start

    def test_add_working_days_one(self):
        """One working day from Monday = Tuesday."""
        monday = date(2026, 3, 9)
        result = self.calc.add_working_days(monday, 1)
        assert result == date(2026, 3, 10)

    def test_add_working_days_across_full_week(self):
        """5 working days from Monday = next Monday."""
        monday = date(2026, 3, 9)
        result = self.calc.add_working_days(monday, 5)
        assert result == date(2026, 3, 16)  # Next Monday

    def test_add_weeks(self):
        """Weeks arithmetic adds N*7 days."""
        start = date(2026, 1, 1)
        result = self.calc.add_weeks(start, 2)
        assert result == date(2026, 1, 15)

    def test_add_months_standard(self):
        """Months arithmetic preserves day of month."""
        start = date(2026, 1, 15)
        result = self.calc.add_months(start, 3)
        assert result == date(2026, 4, 15)

    def test_add_months_end_of_month_clamping(self):
        """Adding months clamps to end-of-month (e.g. Jan 31 + 1 month = Feb 28)."""
        start = date(2026, 1, 31)
        result = self.calc.add_months(start, 1)
        assert result == date(2026, 2, 28)

    def test_add_months_across_year(self):
        """Months arithmetic crosses year boundary correctly."""
        start = date(2026, 11, 15)
        result = self.calc.add_months(start, 3)
        assert result == date(2027, 2, 15)

    def test_compute_deadline_working_days(self):
        """compute_deadline dispatches to add_working_days."""
        friday = date(2026, 3, 6)
        result = self.calc.compute_deadline(friday, 3, "working_days")
        assert result == date(2026, 3, 11)

    def test_compute_deadline_weeks(self):
        """compute_deadline dispatches to add_weeks."""
        start = date(2026, 1, 1)
        result = self.calc.compute_deadline(start, 2, "weeks")
        assert result == date(2026, 1, 15)

    def test_compute_deadline_months(self):
        """compute_deadline dispatches to add_months."""
        start = date(2026, 1, 15)
        result = self.calc.compute_deadline(start, 3, "months")
        assert result == date(2026, 4, 15)

    def test_compute_deadline_defaults_to_calendar(self):
        """Unknown deadline_type defaults to calendar_days."""
        start = date(2026, 1, 1)
        result = self.calc.compute_deadline(start, 14, "unknown_type")
        assert result == date(2026, 1, 15)

    @pytest.mark.asyncio
    async def test_calculate_no_db_raises(self):
        """calculate() raises RuntimeError when no DB available."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=None)
        with pytest.raises(RuntimeError, match="Database not available"):
            await calc.calculate("r1", date(2026, 1, 1), "custom")

    @pytest.mark.asyncio
    async def test_calculate_rule_not_found(self, mock_db):
        """calculate() raises ValueError for missing rule."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)
        mock_db.fetch_one.return_value = None

        with pytest.raises(ValueError, match="Rule not found"):
            await calc.calculate("nonexistent", date(2026, 1, 1), "custom")

    @pytest.mark.asyncio
    async def test_calculate_rule_no_deadline_days(self, mock_db):
        """calculate() raises ValueError when rule has no deadline_days."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)
        mock_db.fetch_one.return_value = {
            "id": "r1",
            "rule_number": "Rule 1",
            "title": "Overriding Objective",
            "deadline_days": None,
            "deadline_type": "calendar_days",
        }

        with pytest.raises(ValueError, match="no deadline_days"):
            await calc.calculate("r1", date(2026, 1, 1), "custom")

    @pytest.mark.asyncio
    async def test_calculate_with_event_bus(self, mock_db, mock_events):
        """calculate() emits rules.deadline.calculated event."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db, event_bus=mock_events)
        mock_db.fetch_one.return_value = {
            "id": "r1",
            "rule_number": "Rule 16",
            "title": "Response to Claim",
            "deadline_days": 28,
            "deadline_type": "calendar_days",
        }

        result = await calc.calculate("r1", date(2026, 1, 1), "date_of_claim")
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "rules.deadline.calculated"
        event_data = mock_events.emit.call_args[0][1]
        assert event_data["rule_id"] == "r1"

    @pytest.mark.asyncio
    async def test_detect_breaches_emits_events(self, mock_db, mock_events):
        """detect_breaches() emits rules.breach.detected for each breach."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "id": "calc1",
                "rule_id": "r1",
                "rule_number": "Rule 16",
                "rule_title": "Response",
                "deadline_date": date(2025, 1, 1),
                "metadata": {},
            },
            {
                "id": "calc2",
                "rule_id": "r2",
                "rule_number": "Rule 27",
                "rule_title": "Disclosure",
                "deadline_date": date(2025, 2, 1),
                "metadata": {},
            },
        ]

        breaches = await calc.detect_breaches("project-1")
        assert len(breaches) == 2
        assert mock_events.emit.call_count == 2

    @pytest.mark.asyncio
    async def test_unless_order_risk_low_severity(self, mock_db):
        """Unless order risk is low for minor breach."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)
        mock_db.fetch_one.side_effect = [
            {
                "id": "b1",
                "rule_id": "r1",
                "breaching_party": "Respondent",
                "severity": "minor",
                "project_id": "p1",
            },
            {
                "id": "r1",
                "is_mandatory": False,
                "strike_out_risk": False,
                "unless_order_applicable": False,
            },
            {"count": 0},
        ]

        result = await calc.assess_unless_order_risk("b1")
        assert result["risk_level"] == "low"
        assert result["risk_score"] <= 0.4

    @pytest.mark.asyncio
    async def test_unless_order_risk_breach_not_found(self, mock_db):
        """assess_unless_order_risk raises ValueError for missing breach."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)
        mock_db.fetch_one.return_value = None

        with pytest.raises(ValueError, match="Breach not found"):
            await calc.assess_unless_order_risk("nonexistent")

    @pytest.mark.asyncio
    async def test_compliance_check_non_compliant(self, mock_db):
        """Compliance check returns non_compliant when deadline is missed."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        mock_db.fetch_all.return_value = [
            {
                "id": "r1",
                "rule_number": "Rule 16",
                "title": "Response to Claim",
                "is_mandatory": True,
            },
        ]

        mock_db.fetch_one.return_value = {
            "rule_id": "r1",
            "document_id": "doc1",
            "deadline_date": date(2020, 1, 1),  # past
            "metadata": {},
        }

        result = await calc.check_compliance("doc1", "date_of_claim")
        assert result["result"] == "non_compliant"
        assert len(result["issues_found"]) == 1
        assert result["score"] == 0.0

    @pytest.mark.asyncio
    async def test_compliance_check_borderline(self, mock_db):
        """Compliance check returns borderline when mandatory rule has no calculation."""
        from arkham_shard_rules.calculator import DeadlineCalculator

        calc = DeadlineCalculator(db=mock_db)

        mock_db.fetch_all.return_value = [
            {
                "id": "r1",
                "rule_number": "Rule 16",
                "title": "Response to Claim",
                "is_mandatory": True,
            },
        ]

        mock_db.fetch_one.return_value = None  # No calculation found

        result = await calc.check_compliance("doc1", "date_of_claim")
        assert result["result"] == "borderline"
        assert len(result["warnings"]) == 1


# ---------------------------------------------------------------------------
# RulesLLM Tests
# ---------------------------------------------------------------------------


class TestRulesLLM:
    """Tests for RulesLLM integration."""

    def test_llm_not_available(self):
        """RulesLLM.available returns False when no LLM service."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM(llm_service=None)
        assert llm.available is False

    def test_llm_available(self):
        """RulesLLM.available returns True when LLM service exists."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM(llm_service=MagicMock())
        assert llm.available is True

    @pytest.mark.asyncio
    async def test_extract_dates_no_llm_falls_back(self):
        """extract_dates falls back to regex when no LLM."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM(llm_service=None)
        text = "The hearing is listed for 15 March 2026. Disclosure by 1 February 2026."
        dates = await llm.extract_dates(text)
        assert len(dates) >= 2
        assert any("2026-03-15" in d.date for d in dates)
        assert any("2026-02-01" in d.date for d in dates)

    @pytest.mark.asyncio
    async def test_extract_dates_regex_numeric(self):
        """Regex extraction handles DD/MM/YYYY format."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM(llm_service=None)
        text = "Comply by 15/03/2026."
        dates = await llm.extract_dates(text)
        assert len(dates) >= 1
        assert dates[0].date == "2026-03-15"

    @pytest.mark.asyncio
    async def test_extract_dates_deadline_detection(self):
        """Regex extraction detects deadline keywords in context."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM(llm_service=None)
        text = "You must comply by no later than 20 March 2026."
        dates = await llm.extract_dates(text)
        assert len(dates) >= 1
        assert dates[0].creates_deadline is True

    @pytest.mark.asyncio
    async def test_suggest_rules_no_llm(self):
        """suggest_rules returns empty list when no LLM."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM(llm_service=None)
        result = await llm.suggest_rules("Respondent missed disclosure deadline")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_dates_with_llm(self):
        """extract_dates calls LLM and parses JSON response."""
        from arkham_shard_rules.llm import RulesLLM

        mock_llm_service = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            [
                {
                    "date": "2026-03-15",
                    "description": "Hearing date",
                    "rule_reference": "Rule 29",
                    "creates_deadline": True,
                    "deadline_for": "both",
                    "notes": "Final hearing",
                }
            ]
        )
        mock_llm_service.generate = AsyncMock(return_value=mock_response)

        llm = RulesLLM(llm_service=mock_llm_service)
        dates = await llm.extract_dates("Order listing hearing for 15 March 2026")

        assert len(dates) == 1
        assert dates[0].date == "2026-03-15"
        assert dates[0].rule_reference == "Rule 29"
        assert dates[0].creates_deadline is True
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_suggest_rules_with_llm(self):
        """suggest_rules calls LLM and parses JSON response."""
        from arkham_shard_rules.llm import RulesLLM

        mock_llm_service = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            [
                {
                    "rule_number": "Rule 37",
                    "title": "Strike Out",
                    "relevance": "Respondent conduct is scandalous",
                    "deadline_days": None,
                    "deadline_type": "calendar_days",
                    "risk": "Claim struck out",
                }
            ]
        )
        mock_llm_service.generate = AsyncMock(return_value=mock_response)

        llm = RulesLLM(llm_service=mock_llm_service)
        rules = await llm.suggest_rules("Respondent acting vexatiously")

        assert len(rules) == 1
        assert rules[0].rule_number == "Rule 37"
        assert rules[0].title == "Strike Out"

    def test_parse_json_handles_markdown_fences(self):
        """JSON parser strips markdown code fences."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM()
        result = llm._parse_json_response('```json\n[{"key": "value"}]\n```')
        assert len(result) == 1
        assert result[0]["key"] == "value"

    def test_parse_json_handles_empty(self):
        """JSON parser returns empty list for empty input."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM()
        assert llm._parse_json_response("") == []
        assert llm._parse_json_response(None) == []

    def test_parse_json_handles_malformed(self):
        """JSON parser returns empty list for non-JSON."""
        from arkham_shard_rules.llm import RulesLLM

        llm = RulesLLM()
        assert llm._parse_json_response("not json at all") == []


# ---------------------------------------------------------------------------
# Event Handler Tests
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Test shard event handler methods."""

    @pytest.mark.asyncio
    async def test_on_deadline_created(self, mock_frame, mock_db):
        """Shard handles deadlines.created event by calculating deadline."""
        shard = RulesShard()
        await shard.initialize(mock_frame)

        mock_db.fetch_one.return_value = {
            "id": "r1",
            "rule_number": "Rule 4",
            "title": "Time Limits",
            "deadline_days": 28,
            "deadline_type": "calendar_days",
        }

        event = {
            "deadline_id": "d1",
            "rule_id": "r1",
            "trigger_date": "2026-01-01",
            "trigger_type": "date_of_order",
        }
        await shard._on_deadline_created(event)
        # Should have called calculate, which executes an INSERT
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_on_deadline_created_missing_rule_id(self, mock_frame, mock_db):
        """Shard silently skips event without rule_id."""
        shard = RulesShard()
        await shard.initialize(mock_frame)

        initial_call_count = mock_db.execute.call_count
        event = {"deadline_id": "d1", "trigger_date": "2026-01-01"}
        await shard._on_deadline_created(event)
        # No additional DB calls beyond schema creation
        assert mock_db.execute.call_count == initial_call_count

    @pytest.mark.asyncio
    async def test_on_document_processed_order(self, mock_frame, mock_db):
        """Shard handles document.processed for order document types."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "[]"
        mock_llm.generate = AsyncMock(return_value=mock_response)

        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {
                "events": AsyncMock(subscribe=AsyncMock()),
                "llm": mock_llm,
                "vectors": None,
            }.get(name)
        )

        shard = RulesShard()
        await shard.initialize(frame)

        event = {
            "document_id": "doc1",
            "document_type": "order",
            "text": "Order dated 15 March 2026.",
        }
        # Should not raise
        await shard._on_document_processed(event)

    @pytest.mark.asyncio
    async def test_on_document_processed_ignores_non_order(self, mock_frame, mock_db):
        """Shard ignores document types that are not order/judgment/claim."""
        shard = RulesShard()
        await shard.initialize(mock_frame)

        event = {
            "document_id": "doc1",
            "document_type": "email",
            "text": "Some email content.",
        }
        # Should return early without processing
        await shard._on_document_processed(event)
