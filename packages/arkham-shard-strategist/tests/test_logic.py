"""
Strategist Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_strategist.api import (
    CreatePredictionRequest,
    create_prediction,
    get_prediction,
    list_reports,
    list_tactical_models,
)
from arkham_shard_strategist.models import CounterArgument, RedTeamReport, StrategicPrediction, TacticalModel
from arkham_shard_strategist.shard import StrategistShard
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

    def test_strategic_prediction_defaults(self):
        p = StrategicPrediction(
            id="p1",
            project_id="proj1",
            predicted_argument="The moon is cheese",
            confidence=0.1,
            reasoning="I dreamt it",
        )
        assert p.id == "p1"
        assert p.project_id == "proj1"
        assert p.predicted_argument == "The moon is cheese"
        assert p.confidence == 0.1
        assert p.reasoning == "I dreamt it"
        assert p.metadata == {}
        assert isinstance(p.created_at, datetime)

    def test_counter_argument_defaults(self):
        c = CounterArgument(
            id="c1", prediction_id="p1", argument="No it is not", rebuttal_strategy="Scientific evidence"
        )
        assert c.id == "c1"
        assert c.prediction_id == "p1"
        assert c.argument == "No it is not"
        assert c.rebuttal_strategy == "Scientific evidence"
        assert c.evidence_ids == []

    def test_red_team_report_defaults(self):
        r = RedTeamReport(id="r1", project_id="proj1", target_id="doc1", overall_risk_score=0.8)
        assert r.id == "r1"
        assert r.project_id == "proj1"
        assert r.target_id == "doc1"
        assert r.overall_risk_score == 0.8
        assert r.weaknesses == []
        assert r.recommendations == []
        assert isinstance(r.created_at, datetime)

    def test_tactical_model_defaults(self):
        t = TacticalModel(id="t1", project_id="proj1", respondent_id="resp1")
        assert t.id == "t1"
        assert t.project_id == "proj1"
        assert t.respondent_id == "resp1"
        assert t.likely_tactics == []
        assert t.counter_measures == []
        assert t.metadata == {}


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = StrategistShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_strategist" in executed_sql
        assert "arkham_strategist.predictions" in executed_sql
        assert "arkham_strategist.counterarguments" in executed_sql
        assert "arkham_strategist.red_team_reports" in executed_sql
        assert "arkham_strategist.tactical_models" in executed_sql

    @pytest.mark.asyncio
    async def test_predictions_table_columns(self, mock_frame, mock_db):
        shard = StrategistShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        pred_ddl = next((s for s in ddl_calls if "predictions" in s and "CREATE TABLE" in s), None)
        assert pred_ddl is not None
        assert "tenant_id" in pred_ddl
        assert "project_id" in pred_ddl
        assert "claim_id" in pred_ddl
        assert "respondent_id" in pred_ddl
        assert "predicted_argument" in pred_ddl
        assert "confidence" in pred_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = StrategistShard()
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
        import arkham_shard_strategist.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_prediction_no_db(self):
        self.api._db = None
        req = CreatePredictionRequest(project_id="p1")
        with pytest.raises(HTTPException) as exc:
            await create_prediction(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_prediction_success(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreatePredictionRequest(project_id="p1", claim_id="c1", respondent_id="r1")
        result = await create_prediction(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once_with("strategist.prediction.generated", {"prediction_id": result["id"]})

    @pytest.mark.asyncio
    async def test_get_prediction_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_prediction("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_prediction_success(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {
            "id": "pred1",
            "project_id": "proj1",
            "predicted_argument": "arg",
            "confidence": 0.5,
            "reasoning": "reason",
        }
        mock_db.fetch_all.return_value = [
            {"id": "c1", "prediction_id": "pred1", "argument": "counter", "rebuttal_strategy": "strat"}
        ]

        result = await get_prediction("pred1")
        assert result["id"] == "pred1"
        assert len(result["counter_arguments"]) == 1
        assert result["counter_arguments"][0]["id"] == "c1"

    @pytest.mark.asyncio
    async def test_list_reports(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "r1", "project_id": "proj1"}]

        result = await list_reports("proj1")
        assert len(result) == 1
        assert result[0]["id"] == "r1"

    @pytest.mark.asyncio
    async def test_list_tactical_models(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "t1", "project_id": "proj1"}]

        result = await list_tactical_models("proj1")
        assert len(result) == 1
        assert result[0]["id"] == "t1"
