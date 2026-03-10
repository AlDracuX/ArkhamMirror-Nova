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
