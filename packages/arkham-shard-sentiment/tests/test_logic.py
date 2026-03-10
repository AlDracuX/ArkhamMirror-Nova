"""
Sentiment Shard - Logic Tests

Tests for models and API handler logic for sentiment analysis, tone scores, and patterns.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_sentiment.models import (
    ComparatorDiff,
    SentimentAnalysis,
    SentimentPattern,
    ToneScore,
)
from arkham_shard_sentiment.shard import SentimentShard
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
    """Verify pydantic model construction."""

    def test_sentiment_analysis(self):
        sa = SentimentAnalysis(id="sa1", project_id="p1", summary="Positive tone", overall_sentiment=0.8)
        assert sa.id == "sa1"
        assert sa.overall_sentiment == 0.8

    def test_tone_score(self):
        ts = ToneScore(
            id="ts1", analysis_id="sa1", category="professionalism", score=0.9, reasoning="Formal language used"
        )
        assert ts.id == "ts1"
        assert ts.category == "professionalism"

    def test_sentiment_pattern(self):
        sp = SentimentPattern(
            id="sp1",
            project_id="p1",
            type="evasive_behavior",
            description="Repeated use of non-committal language",
            significance_score=0.7,
            analysis_ids=["sa1", "sa2"],
        )
        assert sp.id == "sp1"
        assert len(sp.analysis_ids) == 2

    def test_comparator_diff(self):
        cd = ComparatorDiff(
            id="cd1",
            project_id="p1",
            claimant_analysis_id="sa1",
            comparator_analysis_id="sa2",
            divergence_score=0.6,
            description="Different tone used for claimant vs comparator",
        )
        assert cd.id == "cd1"
        assert cd.divergence_score == 0.6


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_sentiment" in executed_sql
        assert "arkham_sentiment.analyses" in executed_sql
        assert "arkham_sentiment.tone_scores" in executed_sql
        assert "arkham_sentiment.patterns" in executed_sql
        assert "arkham_sentiment.comparator_diffs" in executed_sql

    @pytest.mark.asyncio
    async def test_analyses_columns(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        sa_ddl = next((s for s in ddl_calls if "analyses" in s and "CREATE TABLE" in s), None)
        assert sa_ddl is not None
        assert "overall_sentiment" in sa_ddl
        assert "project_id" in sa_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 3


# ---------------------------------------------------------------------------
# API Logic Tests (unit-level, no HTTP layer)
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        """Reset module-level _db before each test."""
        import arkham_shard_sentiment.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_analysis_no_db(self):
        self.api._db = None
        from arkham_shard_sentiment.api import CreateAnalysisRequest

        req = CreateAnalysisRequest(project_id="p1")
        with pytest.raises(HTTPException) as exc:
            await self.api.create_analysis(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_analysis(self, mock_db, mock_events):
        from arkham_shard_sentiment.api import CreateAnalysisRequest, create_analysis

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateAnalysisRequest(project_id="p1", document_id="doc1")
        result = await create_analysis(req)
        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "sentiment.analysis.created"

    @pytest.mark.asyncio
    async def test_get_analysis(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "sa1", "project_id": "p1", "summary": "T1", "overall_sentiment": 0.5}
        mock_db.fetch_all.return_value = [{"id": "ts1", "analysis_id": "sa1", "category": "C1", "score": 0.9}]

        result = await self.api.get_analysis("sa1")
        assert result["id"] == "sa1"
        assert len(result["tone_scores"]) == 1

    @pytest.mark.asyncio
    async def test_get_analysis_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_analysis("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_patterns(self, mock_db):
        self.api._db = mock_db
        await self.api.list_patterns(project_id="p1")
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_comparator_diffs(self, mock_db):
        self.api._db = mock_db
        await self.api.list_comparator_diffs(project_id="p1")
        mock_db.fetch_all.assert_called_once()
