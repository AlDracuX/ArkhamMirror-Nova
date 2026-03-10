"""
Strategist Shard - Strategy CRUD & Evaluate Tests

Tests for the strategies table CRUD operations and SWOT evaluation logic.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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


@pytest.fixture
def api_mod():
    """Import and return the api module, resetting globals each time."""
    import arkham_shard_strategist.api as mod

    mod._db = None
    mod._event_bus = None
    mod._llm_service = None
    mod._shard = None
    return mod


@pytest.fixture
def wired_api(api_mod, mock_db, mock_events):
    """API module with db and events wired up."""
    api_mod._db = mock_db
    api_mod._event_bus = mock_events
    api_mod._shard = None
    return api_mod


# ---------------------------------------------------------------------------
# Schema Tests - strategies table
# ---------------------------------------------------------------------------


class TestStrategiesSchema:
    """Verify the strategies table is created during initialize()."""

    @pytest.mark.asyncio
    async def test_strategies_table_created(self, mock_frame, mock_db):
        shard = StrategistShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)
        assert "arkham_strategist.strategies" in executed_sql

    @pytest.mark.asyncio
    async def test_strategies_table_has_swot_columns(self, mock_frame, mock_db):
        shard = StrategistShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        strat_ddl = next((s for s in ddl_calls if "strategies" in s and "CREATE TABLE" in s), None)
        assert strat_ddl is not None, "strategies CREATE TABLE not found"
        for col in ["strengths", "weaknesses", "risks", "opportunities", "recommended", "confidence_score"]:
            assert col in strat_ddl, f"Column {col} missing from strategies DDL"


# ---------------------------------------------------------------------------
# Strategy CRUD Tests
# ---------------------------------------------------------------------------


class TestStrategyCRUD:
    """Test strategy creation, retrieval, update, delete."""

    @pytest.mark.asyncio
    async def test_create_strategy_with_swot_fields(self, wired_api, mock_db):
        from arkham_shard_strategist.api import CreateStrategyRequest, create_strategy

        req = CreateStrategyRequest(
            case_id=str(uuid.uuid4()),
            name="Direct confrontation",
            approach="Challenge respondent's evidence directly",
            summary="Head-on strategy",
            strengths=["Strong documentary evidence", "Clear timeline"],
            weaknesses=["Relies on witness availability"],
            risks=["Witness may not attend"],
            opportunities=["Respondent's inconsistent statements"],
        )
        result = await create_strategy(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("values", call_args[0][1])
        # Verify SWOT data is passed through
        assert params["name"] == "Direct confrontation"

    @pytest.mark.asyncio
    async def test_get_strategy_not_found(self, wired_api, mock_db):
        from arkham_shard_strategist.api import get_strategy

        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await get_strategy("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_strategy_success(self, wired_api, mock_db):
        from arkham_shard_strategist.api import get_strategy

        strategy_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": strategy_id,
            "case_id": str(uuid.uuid4()),
            "name": "Test Strategy",
            "approach": "Test approach",
            "summary": "Test summary",
            "strengths": ["s1", "s2"],
            "weaknesses": ["w1"],
            "risks": [],
            "opportunities": ["o1"],
            "recommended": False,
            "confidence_score": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await get_strategy(strategy_id)
        assert result["id"] == strategy_id
        assert result["name"] == "Test Strategy"

    @pytest.mark.asyncio
    async def test_list_strategies_filter_by_recommended(self, wired_api, mock_db):
        from arkham_shard_strategist.api import list_strategies

        case_id = str(uuid.uuid4())
        mock_db.fetch_all.return_value = [
            {"id": "s1", "name": "Recommended", "recommended": True},
        ]

        result = await list_strategies(case_id=case_id, recommended=True)
        assert len(result) == 1
        # Verify the query included recommended filter
        call_args = mock_db.fetch_all.call_args
        query = call_args[0][0]
        assert "recommended" in query

    @pytest.mark.asyncio
    async def test_delete_strategy(self, wired_api, mock_db):
        from arkham_shard_strategist.api import delete_strategy

        mock_db.fetch_one.return_value = {"id": "s1"}
        result = await delete_strategy("s1")
        assert result["deleted"] is True


# ---------------------------------------------------------------------------
# Evaluate Endpoint Tests
# ---------------------------------------------------------------------------


class TestEvaluateStrategy:
    """Test the /evaluate endpoint SWOT analysis logic."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_swot_summary(self, wired_api, mock_db):
        from arkham_shard_strategist.api import EvaluateRequest, evaluate_strategy

        strategy_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": strategy_id,
            "name": "Test",
            "strengths": ["s1", "s2", "s3"],
            "weaknesses": ["w1"],
            "risks": ["r1", "r2"],
            "opportunities": ["o1", "o2"],
            "recommended": False,
            "confidence_score": None,
        }

        req = EvaluateRequest(strategy_id=strategy_id)
        result = await evaluate_strategy(req)

        assert result["strategy_id"] == strategy_id
        assert "swot" in result
        assert result["swot"]["strengths"] == ["s1", "s2", "s3"]
        assert result["swot"]["weaknesses"] == ["w1"]
        assert result["swot"]["risks"] == ["r1", "r2"]
        assert result["swot"]["opportunities"] == ["o1", "o2"]

    @pytest.mark.asyncio
    async def test_evaluate_recommend_proceed_when_more_strengths(self, wired_api, mock_db):
        """More strengths than weaknesses should recommend 'proceed'."""
        from arkham_shard_strategist.api import EvaluateRequest, evaluate_strategy

        strategy_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": strategy_id,
            "name": "Strong strategy",
            "strengths": ["s1", "s2", "s3"],
            "weaknesses": ["w1"],
            "risks": [],
            "opportunities": [],
            "recommended": False,
            "confidence_score": None,
        }

        result = await evaluate_strategy(EvaluateRequest(strategy_id=strategy_id))
        assert result["recommendation"] == "proceed"
        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_evaluate_recommend_revise_when_equal(self, wired_api, mock_db):
        """Equal strengths and weaknesses should recommend 'revise'."""
        from arkham_shard_strategist.api import EvaluateRequest, evaluate_strategy

        strategy_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": strategy_id,
            "name": "Balanced strategy",
            "strengths": ["s1", "s2"],
            "weaknesses": ["w1", "w2"],
            "risks": [],
            "opportunities": [],
            "recommended": False,
            "confidence_score": None,
        }

        result = await evaluate_strategy(EvaluateRequest(strategy_id=strategy_id))
        assert result["recommendation"] == "revise"

    @pytest.mark.asyncio
    async def test_evaluate_recommend_abandon_when_more_weaknesses(self, wired_api, mock_db):
        """More weaknesses than strengths should recommend 'abandon'."""
        from arkham_shard_strategist.api import EvaluateRequest, evaluate_strategy

        strategy_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": strategy_id,
            "name": "Weak strategy",
            "strengths": ["s1"],
            "weaknesses": ["w1", "w2", "w3"],
            "risks": ["r1"],
            "opportunities": [],
            "recommended": False,
            "confidence_score": None,
        }

        result = await evaluate_strategy(EvaluateRequest(strategy_id=strategy_id))
        assert result["recommendation"] == "abandon"

    @pytest.mark.asyncio
    async def test_evaluate_confidence_in_valid_range(self, wired_api, mock_db):
        """Confidence score must be between 0.0 and 1.0."""
        from arkham_shard_strategist.api import EvaluateRequest, evaluate_strategy

        strategy_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": strategy_id,
            "name": "Test",
            "strengths": ["s1"] * 20,
            "weaknesses": [],
            "risks": [],
            "opportunities": [],
            "recommended": False,
            "confidence_score": None,
        }

        result = await evaluate_strategy(EvaluateRequest(strategy_id=strategy_id))
        assert 0.0 <= result["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_evaluate_not_found(self, wired_api, mock_db):
        from arkham_shard_strategist.api import EvaluateRequest, evaluate_strategy

        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await evaluate_strategy(EvaluateRequest(strategy_id="nope"))
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Confidence Score Validation
# ---------------------------------------------------------------------------


class TestConfidenceScoreValidation:
    """Test that confidence_score is properly validated."""

    def test_confidence_score_valid_range(self):
        from arkham_shard_strategist.models import Strategy

        s = Strategy(
            id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            name="Test",
            approach="Test",
            confidence_score=0.75,
        )
        assert s.confidence_score == 0.75

    def test_confidence_score_null_allowed(self):
        from arkham_shard_strategist.models import Strategy

        s = Strategy(
            id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            name="Test",
            approach="Test",
            confidence_score=None,
        )
        assert s.confidence_score is None

    def test_confidence_score_boundary_zero(self):
        from arkham_shard_strategist.models import Strategy

        s = Strategy(
            id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            name="Test",
            approach="Test",
            confidence_score=0.0,
        )
        assert s.confidence_score == 0.0

    def test_confidence_score_boundary_one(self):
        from arkham_shard_strategist.models import Strategy

        s = Strategy(
            id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            name="Test",
            approach="Test",
            confidence_score=1.0,
        )
        assert s.confidence_score == 1.0

    def test_confidence_score_out_of_range_raises(self):
        from arkham_shard_strategist.models import Strategy
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Strategy(
                id=str(uuid.uuid4()),
                case_id=str(uuid.uuid4()),
                name="Test",
                approach="Test",
                confidence_score=1.5,
            )

        with pytest.raises(ValidationError):
            Strategy(
                id=str(uuid.uuid4()),
                case_id=str(uuid.uuid4()),
                name="Test",
                approach="Test",
                confidence_score=-0.1,
            )
