"""
Costs Shard - Logic Tests

Tests for models and API handler logic for time tracking, expenses, conduct,
and cost items (CRUD + summary).
All external dependencies are mocked.
"""

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_costs.models import (
    ApplicationStatus,
    ConductLog,
    ConductType,
    CostApplication,
    CostItem,
    Expense,
    TimeEntry,
)
from arkham_shard_costs.shard import CostsShard
from fastapi import HTTPException
from pydantic import ValidationError

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

    def test_cost_item_defaults(self):
        """CostItem should default currency to GBP and status to claimed."""
        ci = CostItem(
            id="ci1",
            case_id="case-1",
            category="travel",
            description="Train to Bristol",
            amount=Decimal("45.50"),
            date=date(2024, 6, 1),
            claimant="Alex Dalton",
        )
        assert ci.id == "ci1"
        assert ci.currency == "GBP"
        assert ci.status == "claimed"
        assert ci.evidence_doc_id is None
        assert ci.amount == Decimal("45.50")


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
        assert "arkham_costs.cost_items" in executed_sql

    @pytest.mark.asyncio
    async def test_cost_items_table_columns(self, mock_frame, mock_db):
        """Verify cost_items DDL contains all required columns."""
        shard = CostsShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        ci_ddl = next((s for s in ddl_calls if "cost_items" in s and "CREATE TABLE" in s), None)
        assert ci_ddl is not None, "cost_items CREATE TABLE not found"
        for col in ["case_id", "category", "description", "amount", "currency", "date", "claimant", "status"]:
            assert col in ci_ddl, f"Column {col} missing from cost_items DDL"

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

    @pytest.mark.asyncio
    async def test_case_updated_event_subscription(self, mock_frame, mock_events):
        """Verify shard subscribes to case.updated event."""
        shard = CostsShard()
        await shard.initialize(mock_frame)

        subscribed_events = [call.args[0] for call in mock_events.subscribe.call_args_list]
        assert "case.updated" in subscribed_events


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


# ---------------------------------------------------------------------------
# Cost Items CRUD Tests
# ---------------------------------------------------------------------------


class TestCostItemsCRUD:
    """Test cost_items CRUD endpoints."""

    def setup_method(self):
        import arkham_shard_costs.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_cost_item(self, mock_db):
        """Test creating a cost item returns id and status."""
        from arkham_shard_costs.api import CostItemCreate, create_cost_item

        self.api._db = mock_db
        self.api._shard = None

        req = CostItemCreate(
            case_id="case-1",
            category="travel",
            description="Train to Bristol",
            amount=Decimal("45.50"),
            date=date(2024, 6, 1),
            claimant="Alex Dalton",
        )
        result = await create_cost_item(req)
        assert "id" in result
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_cost_item_defaults_gbp(self, mock_db):
        """Test that currency defaults to GBP when not specified."""
        from arkham_shard_costs.api import CostItemCreate

        req = CostItemCreate(
            case_id="case-1",
            category="accommodation",
            description="Hotel near tribunal",
            amount=Decimal("120.00"),
            date=date(2024, 6, 1),
            claimant="Alex Dalton",
        )
        assert req.currency == "GBP"

    @pytest.mark.asyncio
    async def test_create_cost_item_amount_must_be_positive(self):
        """Test that negative amounts are rejected by validation."""
        from arkham_shard_costs.api import CostItemCreate

        with pytest.raises(ValidationError):
            CostItemCreate(
                case_id="case-1",
                category="travel",
                description="Invalid item",
                amount=Decimal("-10.00"),
                date=date(2024, 6, 1),
                claimant="Alex Dalton",
            )

    @pytest.mark.asyncio
    async def test_create_cost_item_zero_amount_rejected(self):
        """Test that zero amount is rejected by validation."""
        from arkham_shard_costs.api import CostItemCreate

        with pytest.raises(ValidationError):
            CostItemCreate(
                case_id="case-1",
                category="travel",
                description="Zero amount",
                amount=Decimal("0.00"),
                date=date(2024, 6, 1),
                claimant="Alex Dalton",
            )

    @pytest.mark.asyncio
    async def test_list_cost_items_with_filters(self, mock_db):
        """Test listing cost items with category and status filters."""
        self.api._db = mock_db
        mock_db.fetch_all.return_value = []

        await self.api.list_cost_items(case_id="case-1", category="travel", status="claimed")
        mock_db.fetch_all.assert_called_once()
        call_args = mock_db.fetch_all.call_args
        query = call_args[0][0]
        _params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("values", {})
        assert "case_id" in query
        assert "category" in query
        assert "status" in query

    @pytest.mark.asyncio
    async def test_get_cost_item(self, mock_db):
        """Test getting a single cost item by id."""
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {
            "id": "item-1",
            "case_id": "case-1",
            "category": "travel",
            "description": "Train",
            "amount": 45.50,
            "currency": "GBP",
            "date": date(2024, 6, 1),
            "claimant": "Alex",
            "evidence_doc_id": None,
            "status": "claimed",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        result = await self.api.get_cost_item("item-1")
        assert result["id"] == "item-1"
        mock_db.fetch_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cost_item_not_found(self, mock_db):
        """Test 404 when cost item does not exist."""
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await self.api.get_cost_item("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_cost_item(self, mock_db):
        """Test updating a cost item."""
        from arkham_shard_costs.api import CostItemUpdate

        self.api._db = mock_db
        # Simulate existing row for the update check
        mock_db.fetch_one.return_value = {"id": "item-1"}

        update = CostItemUpdate(description="Updated train to Bristol", amount=Decimal("50.00"))
        result = await self.api.update_cost_item("item-1", update)
        assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_cost_item_not_found(self, mock_db):
        """Test 404 when updating nonexistent cost item."""
        from arkham_shard_costs.api import CostItemUpdate

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await self.api.update_cost_item("nonexistent", CostItemUpdate(description="x"))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_cost_item(self, mock_db):
        """Test deleting a cost item."""
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "item-1"}

        result = await self.api.delete_cost_item("item-1")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_cost_item_not_found(self, mock_db):
        """Test 404 when deleting nonexistent cost item."""
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await self.api.delete_cost_item("nonexistent")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Cost Items Summary Tests
# ---------------------------------------------------------------------------


class TestCostItemsSummary:
    """Test the /summary endpoint logic."""

    def setup_method(self):
        import arkham_shard_costs.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_summary_calculation(self, mock_db):
        """Test summary groups by category with totals and counts."""
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [
            {"category": "travel", "total": 234.56, "count": 3},
            {"category": "accommodation", "total": 1000.00, "count": 2},
        ]

        result = await self.api.get_cost_items_summary()
        assert "categories" in result
        assert len(result["categories"]) == 2
        assert result["grand_total"] == pytest.approx(1234.56)
        assert result["categories"][0]["category"] == "travel"
        assert result["categories"][0]["total"] == pytest.approx(234.56)
        assert result["categories"][0]["count"] == 3

    @pytest.mark.asyncio
    async def test_summary_empty(self, mock_db):
        """Test summary with no cost items returns empty list and zero total."""
        self.api._db = mock_db
        mock_db.fetch_all.return_value = []

        result = await self.api.get_cost_items_summary()
        assert result["categories"] == []
        assert result["grand_total"] == 0.0

    @pytest.mark.asyncio
    async def test_summary_no_db(self):
        """Test summary raises 503 when db is unavailable."""
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_cost_items_summary()
        assert exc.value.status_code == 503
