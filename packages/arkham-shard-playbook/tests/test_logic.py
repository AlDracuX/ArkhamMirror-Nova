"""
Playbook Shard - Logic Tests

Tests for models, API handler logic, and simulation.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_playbook.models import VALID_PRIORITIES, VALID_STATUSES, Play, SimulationResult
from arkham_shard_playbook.shard import PlaybookShard
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


@pytest.fixture
def api_module(mock_db, mock_events):
    """Return the api module with globals wired up."""
    import arkham_shard_playbook.api as api_mod

    api_mod._db = mock_db
    api_mod._event_bus = mock_events
    api_mod._llm_service = None
    api_mod._shard = None
    yield api_mod
    # Reset after test
    api_mod._db = None
    api_mod._event_bus = None
    api_mod._llm_service = None
    api_mod._shard = None


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and defaults."""

    def test_play_defaults(self):
        p = Play(id="p1", name="Test Play")
        assert p.id == "p1"
        assert p.name == "Test Play"
        assert p.status == "draft"
        assert p.priority == "medium"
        assert p.steps == []
        assert p.triggers == []
        assert p.expected_outcomes == []
        assert p.contingencies == []
        assert p.scenario == ""
        assert p.description == ""
        assert p.case_id is None

    def test_play_with_all_fields(self):
        steps = [{"order": 1, "action": "File motion"}]
        triggers = [{"type": "deadline", "value": "2026-04-01"}]
        outcomes = [{"description": "Motion granted"}]
        contingencies = [{"if": "denied", "then": "appeal"}]

        p = Play(
            id="p2",
            case_id="case-123",
            name="Full Play",
            scenario="Best case",
            description="A detailed play",
            steps=steps,
            triggers=triggers,
            expected_outcomes=outcomes,
            contingencies=contingencies,
            priority="critical",
            status="active",
        )
        assert p.case_id == "case-123"
        assert p.priority == "critical"
        assert p.status == "active"
        assert len(p.steps) == 1
        assert p.steps[0]["order"] == 1

    def test_simulation_result_structure(self):
        sim = SimulationResult(
            play_id="p1",
            scenario="Attack scenario",
            steps=[{"order": 1, "action": "step1"}],
            risk_assessment="medium",
            estimated_outcomes=[{"desc": "win"}],
        )
        assert sim.play_id == "p1"
        assert sim.risk_assessment == "medium"
        assert len(sim.steps) == 1
        assert len(sim.estimated_outcomes) == 1


# ---------------------------------------------------------------------------
# Status Transition Tests
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    """Verify valid statuses and priorities."""

    def test_valid_statuses(self):
        assert VALID_STATUSES == {"draft", "active", "executed", "archived"}

    def test_valid_priorities(self):
        assert VALID_PRIORITIES == {"low", "medium", "high", "critical"}

    @pytest.mark.parametrize("status", ["draft", "active", "executed", "archived"])
    def test_play_accepts_valid_status(self, status):
        p = Play(id="p1", name="Test", status=status)
        assert p.status == status

    @pytest.mark.parametrize("priority", ["low", "medium", "high", "critical"])
    def test_play_accepts_valid_priority(self, priority):
        p = Play(id="p1", name="Test", priority=priority)
        assert p.priority == priority


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_plays_table_created(self, mock_frame, mock_db):
        shard = PlaybookShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_playbook" in executed_sql
        assert "arkham_playbook.plays" in executed_sql

    @pytest.mark.asyncio
    async def test_plays_table_columns(self, mock_frame, mock_db):
        shard = PlaybookShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        plays_ddl = next((s for s in ddl_calls if "plays" in s and "CREATE TABLE" in s), None)
        assert plays_ddl is not None
        for col in [
            "id",
            "case_id",
            "name",
            "scenario",
            "description",
            "steps",
            "triggers",
            "expected_outcomes",
            "contingencies",
            "priority",
            "status",
            "created_at",
            "updated_at",
        ]:
            assert col in plays_ddl, f"Column '{col}' missing from plays DDL"

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = PlaybookShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 2


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    @pytest.mark.asyncio
    async def test_create_play_no_db(self, api_module):
        api_module._db = None
        req = api_module.CreatePlayRequest(name="Test", scenario="Test scenario")
        with pytest.raises(HTTPException) as exc:
            await api_module.create_play(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_play_success(self, api_module, mock_db, mock_events):
        req = api_module.CreatePlayRequest(
            name="Test Play",
            scenario="Test scenario",
            case_id="case-1",
            priority="high",
        )
        result = await api_module.create_play(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_play_invalid_priority(self, api_module, mock_db):
        req = api_module.CreatePlayRequest(name="Test", scenario="Scenario", priority="ultra")
        with pytest.raises(HTTPException) as exc:
            await api_module.create_play(req)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_play_invalid_status(self, api_module, mock_db):
        req = api_module.CreatePlayRequest(name="Test", scenario="Scenario", status="deleted")
        with pytest.raises(HTTPException) as exc:
            await api_module.create_play(req)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_get_play_not_found(self, api_module, mock_db):
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await api_module.get_play("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_play_success(self, api_module, mock_db):
        mock_db.fetch_one.return_value = {
            "id": "play1",
            "case_id": "case-1",
            "name": "Test Play",
            "scenario": "Scenario",
            "description": "",
            "steps": "[]",
            "triggers": "[]",
            "expected_outcomes": "[]",
            "contingencies": "[]",
            "priority": "medium",
            "status": "draft",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        result = await api_module.get_play("play1")
        assert result["id"] == "play1"
        assert result["name"] == "Test Play"

    @pytest.mark.asyncio
    async def test_list_plays_empty(self, api_module, mock_db):
        mock_db.fetch_all.return_value = []
        result = await api_module.list_plays()
        assert result == []

    @pytest.mark.asyncio
    async def test_delete_play_not_found(self, api_module, mock_db):
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await api_module.delete_play("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_simulate_play_not_found(self, api_module, mock_db):
        mock_db.fetch_one.return_value = None
        req = api_module.SimulateRequest(play_id="nonexistent")
        with pytest.raises(HTTPException) as exc:
            await api_module.simulate_play(req)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_simulate_play_success(self, api_module, mock_db):
        mock_db.fetch_one.return_value = {
            "id": "play1",
            "case_id": "case-1",
            "name": "Test Play",
            "scenario": "Win scenario",
            "description": "Desc",
            "steps": json.dumps(
                [
                    {"order": 1, "action": "File motion"},
                    {"order": 2, "action": "Present evidence"},
                ]
            ),
            "triggers": "[]",
            "expected_outcomes": json.dumps([{"description": "Motion granted"}]),
            "contingencies": json.dumps([{"if": "denied", "then": "appeal"}]),
            "priority": "high",
            "status": "active",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        req = api_module.SimulateRequest(play_id="play1")
        result = await api_module.simulate_play(req)

        assert result["play_id"] == "play1"
        assert result["scenario"] == "Win scenario"
        assert len(result["steps"]) == 2
        assert result["risk_assessment"] in ("low", "medium", "high")
        assert isinstance(result["estimated_outcomes"], list)

    @pytest.mark.asyncio
    async def test_simulate_step_ordering(self, api_module, mock_db):
        """Verify simulation preserves step ordering."""
        steps = [
            {"order": 3, "action": "Third"},
            {"order": 1, "action": "First"},
            {"order": 2, "action": "Second"},
        ]
        mock_db.fetch_one.return_value = {
            "id": "play1",
            "case_id": None,
            "name": "Ordering Test",
            "scenario": "Test",
            "description": "",
            "steps": json.dumps(steps),
            "triggers": "[]",
            "expected_outcomes": "[]",
            "contingencies": "[]",
            "priority": "medium",
            "status": "draft",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        req = api_module.SimulateRequest(play_id="play1")
        result = await api_module.simulate_play(req)

        # Steps should be sorted by order
        result_steps = result["steps"]
        orders = [s.get("order", 0) for s in result_steps]
        assert orders == sorted(orders), f"Steps not sorted by order: {orders}"
