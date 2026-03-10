"""
Sentiment Shard - Logic Tests

Tests for models, scoring logic, and API handler logic for sentiment analysis.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_sentiment.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ComparatorDiff,
    CreateResultRequest,
    SentimentAnalysis,
    SentimentLabel,
    SentimentPattern,
    SentimentResult,
    ToneScore,
    UpdateResultRequest,
    analyze_sentiment,
    score_to_label,
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

    def test_sentiment_result_defaults(self):
        sr = SentimentResult(document_id="doc1")
        assert sr.document_id == "doc1"
        assert sr.overall_score == 0.0
        assert sr.label == "neutral"
        assert sr.confidence == 0.0
        assert sr.passages == []
        assert sr.entity_sentiments == {}
        assert sr.id is not None

    def test_sentiment_result_full(self):
        sr = SentimentResult(
            id="r1",
            document_id="doc1",
            case_id="case1",
            overall_score=0.75,
            label="positive",
            confidence=0.8,
            passages=["Good work"],
            entity_sentiments={"claimant": 0.5},
        )
        assert sr.overall_score == 0.75
        assert sr.case_id == "case1"
        assert len(sr.passages) == 1

    def test_create_result_request(self):
        req = CreateResultRequest(document_id="doc1", overall_score=0.5, label="positive")
        assert req.document_id == "doc1"
        assert req.confidence == 0.0

    def test_update_result_request_partial(self):
        req = UpdateResultRequest(overall_score=0.9)
        assert req.overall_score == 0.9
        assert req.label is None

    def test_analyze_request(self):
        req = AnalyzeRequest(document_id="doc1", text="This is fair and reasonable")
        assert req.text == "This is fair and reasonable"

    def test_sentiment_analysis_legacy(self):
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
# Scoring Logic Tests
# ---------------------------------------------------------------------------


class TestScoringLogic:
    """Test the keyword-based sentiment scoring."""

    def test_positive_text_scores_positive(self):
        result = analyze_sentiment("The response was fair and reasonable, and we agree with the proposal")
        assert result["score"] > 0
        assert result["label"] in ("positive", "very_positive")

    def test_negative_text_scores_negative(self):
        result = analyze_sentiment("We deny the claim and reject the hostile allegations of breach")
        assert result["score"] < 0
        assert result["label"] in ("negative", "very_negative")

    def test_neutral_text(self):
        result = analyze_sentiment("The meeting was held on Tuesday at the office")
        assert result["score"] == 0.0
        assert result["label"] == "neutral"

    def test_mixed_text_balanced(self):
        result = analyze_sentiment("We agree with the fair assessment but deny the hostile claims")
        # agree, fair = 2 positive; deny, hostile = 2 negative => score = 0
        assert result["score"] == 0.0
        assert result["label"] == "neutral"

    def test_score_range(self):
        """Score must always be between -1.0 and 1.0."""
        result = analyze_sentiment("deny deny deny deny deny")
        assert -1.0 <= result["score"] <= 1.0
        result2 = analyze_sentiment("agree agree agree agree agree")
        assert -1.0 <= result2["score"] <= 1.0

    def test_empty_text(self):
        result = analyze_sentiment("")
        assert result["score"] == 0.0
        assert result["label"] == "neutral"
        assert result["confidence"] == 0.0

    def test_key_passages_extraction(self):
        result = analyze_sentiment("The weather is nice. We deny the allegations. The sky is blue.")
        assert len(result["key_passages"]) >= 1
        assert any("deny" in p.lower() for p in result["key_passages"])

    def test_confidence_increases_with_sentiment_words(self):
        low_conf = analyze_sentiment("The cat sat on the mat and we agree")
        high_conf = analyze_sentiment("agree fair reasonable correct proper appropriate")
        assert high_conf["confidence"] > low_conf["confidence"]


class TestLabelAssignment:
    """Test score_to_label mapping."""

    def test_very_negative(self):
        assert score_to_label(-0.8) == SentimentLabel.VERY_NEGATIVE
        assert score_to_label(-1.0) == SentimentLabel.VERY_NEGATIVE
        assert score_to_label(-0.6) == SentimentLabel.VERY_NEGATIVE

    def test_negative(self):
        assert score_to_label(-0.4) == SentimentLabel.NEGATIVE
        assert score_to_label(-0.2) == SentimentLabel.NEGATIVE

    def test_neutral(self):
        assert score_to_label(0.0) == SentimentLabel.NEUTRAL
        assert score_to_label(0.1) == SentimentLabel.NEUTRAL
        assert score_to_label(-0.1) == SentimentLabel.NEUTRAL

    def test_positive(self):
        assert score_to_label(0.4) == SentimentLabel.POSITIVE
        assert score_to_label(0.6) == SentimentLabel.POSITIVE

    def test_very_positive(self):
        assert score_to_label(0.8) == SentimentLabel.VERY_POSITIVE
        assert score_to_label(1.0) == SentimentLabel.VERY_POSITIVE


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_sentiment_results_table_created(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)
        assert "arkham_sentiment.sentiment_results" in executed_sql

    @pytest.mark.asyncio
    async def test_schema_created(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)
        assert "CREATE SCHEMA IF NOT EXISTS arkham_sentiment" in executed_sql

    @pytest.mark.asyncio
    async def test_legacy_tables_created(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)
        assert "arkham_sentiment.analyses" in executed_sql
        assert "arkham_sentiment.tone_scores" in executed_sql
        assert "arkham_sentiment.patterns" in executed_sql
        assert "arkham_sentiment.comparator_diffs" in executed_sql

    @pytest.mark.asyncio
    async def test_sentiment_results_columns(self, mock_frame, mock_db):
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        sr_ddl = next((s for s in ddl_calls if "sentiment_results" in s and "CREATE TABLE" in s), None)
        assert sr_ddl is not None
        for col in ["document_id", "case_id", "overall_score", "label", "confidence", "passages", "entity_sentiments"]:
            assert col in sr_ddl, f"Column {col} missing from sentiment_results DDL"

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
    async def test_create_result_no_db(self):
        self.api._db = None
        req = CreateResultRequest(document_id="doc1")
        with pytest.raises(HTTPException) as exc:
            await self.api.create_result(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_result(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateResultRequest(document_id="doc1", overall_score=0.5, label="positive")
        result = await self.api.create_result(req)
        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_result(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {
            "id": "r1",
            "document_id": "doc1",
            "overall_score": 0.5,
            "label": "positive",
            "passages": "[]",
            "entity_sentiments": "{}",
        }

        result = await self.api.get_result("r1")
        assert result["id"] == "r1"
        assert result["passages"] == []

    @pytest.mark.asyncio
    async def test_get_result_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_result("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_results_with_filters(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = []
        result = await self.api.list_results(document_id="doc1", label="positive")
        assert result == []
        # Verify the query included filters
        call_args = mock_db.fetch_all.call_args
        query = call_args[0][0]
        assert "document_id" in query
        assert "label" in query

    @pytest.mark.asyncio
    async def test_update_result(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "r1"}

        req = UpdateResultRequest(overall_score=0.9, label="very_positive")
        result = await self.api.update_result("r1", req)
        assert result["updated"] is True
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_result_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        req = UpdateResultRequest(overall_score=0.9)
        with pytest.raises(HTTPException) as exc:
            await self.api.update_result("nonexistent", req)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_result(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "r1"}

        result = await self.api.delete_result("r1")
        assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_result_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.delete_result("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_analyze_endpoint(self):
        """Test the analyze endpoint returns proper structure."""
        from arkham_shard_sentiment.api import analyze_text

        req = AnalyzeRequest(document_id="doc1", text="The proposal is fair and we agree with the terms")
        result = await analyze_text(req)
        assert result.document_id == "doc1"
        assert result.score > 0
        assert result.label in ("positive", "very_positive")
        assert result.confidence > 0
        assert isinstance(result.key_passages, list)

    @pytest.mark.asyncio
    async def test_analyze_negative(self):
        """Test analyze with negative text."""
        from arkham_shard_sentiment.api import analyze_text

        req = AnalyzeRequest(document_id="doc2", text="We reject and deny all hostile claims of breach")
        result = await analyze_text(req)
        assert result.score < 0
        assert result.label in ("negative", "very_negative")

    # Legacy endpoint tests

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
