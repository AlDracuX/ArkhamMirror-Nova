"""
Costs Shard - Logic Tests

Tests for models and API handler logic for time tracking, expenses, and conduct.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_costs.models import (
    ApplicationStatus,
    ConductLog,
    ConductType,
    CostApplication,
    Expense,
    TimeEntry,
)
from arkham_shard_costs.shard import CostsShard
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

    def test_time_entry_defaults(self):
        te = TimeEntry(id="te1", activity="Reviewing ET1", duration_minutes=60, activity_date=date(2024, 1, 1))
        assert te.id == "te1"
        assert te.duration_minutes == 60

    def test_conduct_type_enum(self):

        assert ConductType.DELAY == "delay"
        assert ConductType.EVASION == "evasion"
        assert ConductType.VEXATIOUS == "vexatious"
        assert ConductType.ABUSIVE == "abusive"
        assert ConductType.DISRUPTIVE == "disruptive"
        assert ConductType.BREACH_OF_ORDER == "breach_of_order"
        assert ConductType.OTHER == "other"

    def test_application_status_enum(self):
        assert ApplicationStatus.DRAFT == "draft"
        assert ApplicationStatus.FILED == "filed"
        assert ApplicationStatus.GRANTED == "granted"
        assert ApplicationStatus.REFUSED == "refused"
        assert ApplicationStatus.WITHDRAWN == "withdrawn"

    def test_expense_defaults(self):
        e = Expense(id="e1", description="Tribunal hearing fee", amount=250.0, expense_date=date(2024, 1, 1))
        assert e.id == "e1"
        assert e.amount == 250.0
        assert e.currency == "GBP"

    def test_conduct_log_defaults(self):
        cl = ConductLog(
            id="cl1",
            party_name="Respondent",
            conduct_type=ConductType.DELAY,
            description="Late response to disclosure request",
            occurred_at=datetime.now(),
        )
        assert cl.id == "cl1"
        assert cl.significance == "medium"
        assert cl.legal_reference == "Rule 76(1)(a)"

    def test_cost_application_defaults(self):
        ca = CostApplication(id="ca1", title="Application against Respondent")
        assert ca.id == "ca1"
        assert ca.status == ApplicationStatus.DRAFT
        assert ca.total_amount_claimed == 0.0


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = CostsShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_costs" in executed_sql
        assert "arkham_costs.time_entries" in executed_sql
        assert "arkham_costs.expenses" in executed_sql
        assert "arkham_costs.conduct_log" in executed_sql
        assert "arkham_costs.applications" in executed_sql

    @pytest.mark.asyncio
    async def test_time_entries_columns(self, mock_frame, mock_db):
        shard = CostsShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        te_ddl = next((s for s in ddl_calls if "time_entries" in s and "CREATE TABLE" in s), None)
        assert te_ddl is not None
        assert "duration_minutes" in te_ddl
        assert "activity_date" in te_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = CostsShard()
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
        import arkham_shard_costs.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_time_entries_no_db(self):
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_time_entries()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_time_entry(self, mock_db):
        from arkham_shard_costs.api import TimeEntryCreate, create_time_entry

        self.api._db = mock_db
        self.api._shard = None

        req = TimeEntryCreate(activity="Drafting", duration_minutes=30, activity_date=date.today())
        result = await create_time_entry(req)
        assert "id" in result
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_expenses(self, mock_db):
        self.api._db = mock_db
        await self.api.list_expenses(project_id="p1")
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_expense(self, mock_db):
        from arkham_shard_costs.api import ExpenseCreate, create_expense

        self.api._db = mock_db
        self.api._shard = None

        req = ExpenseCreate(description="Travel", amount=15.50, expense_date=date.today())
        result = await create_expense(req)
        assert "id" in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_conduct_log(self, mock_db):
        self.api._db = mock_db
        await self.api.list_conduct_log(project_id="p1")
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_conduct_log(self, mock_db, mock_events):
        from arkham_shard_costs.api import ConductLogCreate, create_conduct_log

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = ConductLogCreate(party_name="Respondent", conduct_type="delay", occurred_at=datetime.now())
        result = await create_conduct_log(req)
        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "costs.conduct.logged"

    @pytest.mark.asyncio
    async def test_list_applications(self, mock_db):
        self.api._db = mock_db
        await self.api.list_applications(project_id="p1")
        mock_db.fetch_all.assert_called_once()
