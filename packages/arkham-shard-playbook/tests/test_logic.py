"""
Playbook Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_playbook.api import CreateStrategyRequest, create_strategy, get_strategy, list_objectives
from arkham_shard_playbook.models import EvidenceObjective, LitigationStrategy, StrategyScenario
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


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and defaults."""

    def test_litigation_strategy_defaults(self):
        s = LitigationStrategy(
            id="s1", project_id="proj1", title="Winning Strategy", description="How to win", status="active"
        )
        assert s.id == "s1"
        assert s.project_id == "proj1"
        assert s.title == "Winning Strategy"
        assert s.description == "How to win"
        assert s.status == "active"
        assert s.main_claims == []
        assert s.fallback_positions == []
        assert s.metadata == {}
        assert isinstance(s.created_at, datetime)

    def test_strategy_scenario_defaults(self):
        s = StrategyScenario(
            id="s1",
            strategy_id="strat1",
            name="Best Case",
            description="We win everything",
            probability=0.2,
            impact="High",
        )
        assert s.id == "s1"
        assert s.strategy_id == "strat1"
        assert s.name == "Best Case"
        assert s.description == "We win everything"
        assert s.probability == 0.2
        assert s.impact == "High"
        assert s.consequences == []

    def test_evidence_objective_defaults(self):
        o = EvidenceObjective(id="o1", project_id="proj1", evidence_id="ev1", objective_id="obj1", relevance_score=0.9)
        assert o.id == "o1"
        assert o.project_id == "proj1"
        assert o.evidence_id == "ev1"
        assert o.objective_id == "obj1"
        assert o.relevance_score == 0.9
        assert o.notes is None


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = PlaybookShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_playbook" in executed_sql
        assert "arkham_playbook.strategies" in executed_sql
        assert "arkham_playbook.scenarios" in executed_sql
        assert "arkham_playbook.evidence_objectives" in executed_sql

    @pytest.mark.asyncio
    async def test_strategies_table_columns(self, mock_frame, mock_db):
        shard = PlaybookShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        strat_ddl = next((s for s in ddl_calls if "strategies" in s and "CREATE TABLE" in s), None)
        assert strat_ddl is not None
        assert "tenant_id" in strat_ddl
        assert "project_id" in strat_ddl
        assert "title" in strat_ddl
        assert "description" in strat_ddl
        assert "status" in strat_ddl
        assert "main_claims" in strat_ddl

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

    def setup_method(self):
        """Reset module-level _db before each test."""
        import arkham_shard_playbook.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_strategy_no_db(self):
        self.api._db = None
        req = CreateStrategyRequest(project_id="p1", title="Title")
        with pytest.raises(HTTPException) as exc:
            await create_strategy(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_strategy_success(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateStrategyRequest(project_id="p1", title="Title", description="Desc")
        result = await create_strategy(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once_with("playbook.strategy.updated", {"strategy_id": result["id"]})

    @pytest.mark.asyncio
    async def test_get_strategy_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_strategy("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_strategy_success(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {
            "id": "strat1",
            "project_id": "proj1",
            "title": "Title",
            "description": "Desc",
        }
        mock_db.fetch_all.return_value = [
            {"id": "sc1", "strategy_id": "strat1", "name": "Scenario 1", "description": "Desc"}
        ]

        result = await get_strategy("strat1")
        assert result["id"] == "strat1"
        assert len(result["scenarios"]) == 1
        assert result["scenarios"][0]["id"] == "sc1"

    @pytest.mark.asyncio
    async def test_list_objectives(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "o1", "project_id": "proj1"}]

        result = await list_objectives("proj1")
        assert len(result) == 1
        assert result[0]["id"] == "o1"
