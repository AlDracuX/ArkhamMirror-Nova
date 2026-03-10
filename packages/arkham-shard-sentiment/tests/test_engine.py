"""
Sentiment Shard - Engine Tests

Tests for SentimentEngine domain logic: tone classification, temporal patterns,
party comparison, and document analysis with DB persistence.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_sentiment.engine import SentimentEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_events():
    """Create a mock events service."""
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    """Create a mock LLM service."""
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_events, mock_llm):
    """Create a SentimentEngine with all mocked services."""
    return SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)


@pytest.fixture
def engine_no_llm(mock_db, mock_events):
    """Create a SentimentEngine without LLM (keyword-only mode)."""
    return SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=None)


# ---------------------------------------------------------------------------
# Tone Classification Tests
# ---------------------------------------------------------------------------


class TestClassifyToneCategories:
    """Test keyword+pattern tone classification."""

    def test_classify_tone_hostile_keywords(self, engine):
        """Hostile keywords detected and scored."""
        text = "Your threatening behaviour and aggressive demands are completely unacceptable."
        categories = engine.classify_tone_categories(text)

        hostile = next((c for c in categories if c["category"] == "hostile"), None)
        assert hostile is not None, "hostile category should be detected"
        assert hostile["score"] > 0
        assert len(hostile["evidence_segments"]) > 0

    def test_classify_tone_professional(self, engine):
        """Professional tone scored when formal language used."""
        text = "Please find enclosed our formal response. We acknowledge receipt of your correspondence."
        categories = engine.classify_tone_categories(text)

        professional = next((c for c in categories if c["category"] == "professional"), None)
        assert professional is not None, "professional category should be detected"
        assert professional["score"] > 0

    def test_classify_tone_evasive(self, engine):
        """Evasive tone detected from hedging language."""
        text = "We cannot recall the specifics. It is unclear what exactly occurred. We do not remember."
        categories = engine.classify_tone_categories(text)

        evasive = next((c for c in categories if c["category"] == "evasive"), None)
        assert evasive is not None, "evasive category should be detected"
        assert evasive["score"] > 0

    def test_classify_tone_condescending(self, engine):
        """Condescending tone detected from patronising patterns."""
        text = "Obviously you should have known. As I have already explained, this is simply basic procedure."
        categories = engine.classify_tone_categories(text)

        condescending = next((c for c in categories if c["category"] == "condescending"), None)
        assert condescending is not None, "condescending category should be detected"
        assert condescending["score"] > 0

    def test_classify_tone_supportive(self, engine):
        """Supportive tone detected from cooperative language."""
        text = "We are happy to assist and will cooperate fully. Thank you for your patience."
        categories = engine.classify_tone_categories(text)

        supportive = next((c for c in categories if c["category"] == "supportive"), None)
        assert supportive is not None, "supportive category should be detected"
        assert supportive["score"] > 0

    def test_classify_returns_all_categories(self, engine):
        """All five categories always present in output."""
        text = "Some neutral text about meetings."
        categories = engine.classify_tone_categories(text)

        category_names = {c["category"] for c in categories}
        assert category_names == {"hostile", "evasive", "condescending", "professional", "supportive"}

    def test_classify_scores_sum_reasonable(self, engine):
        """Individual category scores are between 0.0 and 1.0."""
        text = "We deny the allegations and reject your hostile claims."
        categories = engine.classify_tone_categories(text)

        for cat in categories:
            assert 0.0 <= cat["score"] <= 1.0, f"{cat['category']} score out of range: {cat['score']}"


# ---------------------------------------------------------------------------
# Temporal Pattern Tests
# ---------------------------------------------------------------------------


class TestTemporalPatterns:
    """Test tone-over-time pattern detection."""

    @pytest.mark.asyncio
    async def test_temporal_pattern_significant_shift(self, engine, mock_db):
        """A shift >0.3 between adjacent periods is flagged."""
        # Simulate DB returning sentiment results over time with a shift
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 1, tzinfo=timezone.utc), "overall_score": 0.6, "document_id": "d1"},
            {"analyzed_at": datetime(2024, 1, 15, tzinfo=timezone.utc), "overall_score": 0.5, "document_id": "d2"},
            {"analyzed_at": datetime(2024, 2, 1, tzinfo=timezone.utc), "overall_score": 0.1, "document_id": "d3"},
            {"analyzed_at": datetime(2024, 2, 15, tzinfo=timezone.utc), "overall_score": 0.0, "document_id": "d4"},
        ]

        patterns = await engine.detect_temporal_patterns(case_id="case-1")

        # Should detect at least one significant shift
        significant = [p for p in patterns if p.get("shift_magnitude", 0) > 0.3]
        assert len(significant) >= 1, "Should detect significant tone shift"
        assert significant[0]["shift_direction"] in ("negative", "positive")

    @pytest.mark.asyncio
    async def test_temporal_pattern_stable(self, engine, mock_db):
        """No shifts detected when scores are stable."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 1, tzinfo=timezone.utc), "overall_score": 0.5, "document_id": "d1"},
            {"analyzed_at": datetime(2024, 1, 15, tzinfo=timezone.utc), "overall_score": 0.48, "document_id": "d2"},
            {"analyzed_at": datetime(2024, 2, 1, tzinfo=timezone.utc), "overall_score": 0.52, "document_id": "d3"},
            {"analyzed_at": datetime(2024, 2, 15, tzinfo=timezone.utc), "overall_score": 0.49, "document_id": "d4"},
        ]

        patterns = await engine.detect_temporal_patterns(case_id="case-1")

        significant = [p for p in patterns if p.get("shift_magnitude", 0) > 0.3]
        assert len(significant) == 0, "No significant shifts in stable data"

    @pytest.mark.asyncio
    async def test_temporal_pattern_empty(self, engine, mock_db):
        """Empty result set returns empty patterns."""
        mock_db.fetch_all.return_value = []
        patterns = await engine.detect_temporal_patterns(case_id="case-1")
        assert patterns == []

    @pytest.mark.asyncio
    async def test_temporal_pattern_single_result(self, engine, mock_db):
        """Single result cannot produce shifts."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 1, tzinfo=timezone.utc), "overall_score": 0.5, "document_id": "d1"},
        ]
        patterns = await engine.detect_temporal_patterns(case_id="case-1")
        # One period, no shift possible
        significant = [p for p in patterns if p.get("shift_magnitude", 0) > 0.3]
        assert len(significant) == 0


# ---------------------------------------------------------------------------
# Party Comparison Tests
# ---------------------------------------------------------------------------


class TestCompareParties:
    """Test claimant vs respondent comparison."""

    @pytest.mark.asyncio
    async def test_compare_parties_divergence(self, engine, mock_db):
        """Different average scores produce non-zero divergence."""
        # First call: claimant results, second call: respondent results
        mock_db.fetch_all.side_effect = [
            # claimant
            [
                {"overall_score": 0.7, "document_id": "d1", "label": "positive"},
                {"overall_score": 0.6, "document_id": "d2", "label": "positive"},
            ],
            # respondent
            [
                {"overall_score": -0.3, "document_id": "d3", "label": "negative"},
                {"overall_score": -0.4, "document_id": "d4", "label": "negative"},
            ],
        ]

        result = await engine.compare_parties(case_id="case-1")

        assert result["claimant_avg"] == pytest.approx(0.65, abs=0.01)
        assert result["respondent_avg"] == pytest.approx(-0.35, abs=0.01)
        assert result["divergence"] > 0.5
        assert isinstance(result["key_differences"], list)

    @pytest.mark.asyncio
    async def test_compare_parties_no_data(self, engine, mock_db):
        """No data returns zeroed comparison."""
        mock_db.fetch_all.side_effect = [[], []]

        result = await engine.compare_parties(case_id="case-1")

        assert result["claimant_avg"] == 0.0
        assert result["respondent_avg"] == 0.0
        assert result["divergence"] == 0.0


# ---------------------------------------------------------------------------
# Document Analysis Tests
# ---------------------------------------------------------------------------


class TestAnalyzeDocument:
    """Test full document analysis pipeline."""

    @pytest.mark.asyncio
    async def test_analyze_stores_result(self, engine, mock_db, mock_events):
        """analyze_document persists result to DB and emits event."""
        text = "We deny the hostile allegations and reject the unfair claims."

        result = await engine.analyze_document(document_id="doc-1", text=text)

        # Verify structure
        assert result["document_id"] == "doc-1"
        assert "overall_score" in result
        assert "tone_categories" in result
        assert "keywords_found" in result

        # Verify DB write happened
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "arkham_sentiment" in call_args[0][0]

        # Verify event emission
        mock_events.emit.assert_called_once()
        event_name = mock_events.emit.call_args[0][0]
        assert event_name == "sentiment.analysis.completed"

    @pytest.mark.asyncio
    async def test_analyze_no_db(self, mock_events):
        """Analysis works without DB (no persistence)."""
        engine = SentimentEngine(db=None, event_bus=mock_events)
        text = "Fair and reasonable proposal."

        result = await engine.analyze_document(document_id="doc-1", text=text)

        assert result["document_id"] == "doc-1"
        assert result["overall_score"] > 0

    @pytest.mark.asyncio
    async def test_analyze_hostile_text(self, engine, mock_db, mock_events):
        """Hostile text produces negative score with hostile tone category."""
        text = "Your threatening and aggressive conduct amounts to intimidation."

        result = await engine.analyze_document(document_id="doc-2", text=text)

        assert result["overall_score"] < 0 or any(
            c["category"] == "hostile" and c["score"] > 0 for c in result["tone_categories"]
        )

    @pytest.mark.asyncio
    async def test_analyze_with_case_id(self, engine, mock_db, mock_events):
        """case_id is stored when provided."""
        text = "Normal text."

        result = await engine.analyze_document(document_id="doc-3", text=text, case_id="case-99")

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["case_id"] == "case-99"

    @pytest.mark.asyncio
    async def test_analyze_with_llm_enhancement(self, engine, mock_db, mock_events, mock_llm):
        """When LLM is available, tone classification is enhanced."""
        import json

        mock_llm.generate = AsyncMock(
            return_value=MagicMock(
                text=json.dumps(
                    {
                        "categories": [
                            {"category": "hostile", "score": 0.8, "evidence": ["threatening behaviour"]},
                            {"category": "professional", "score": 0.1, "evidence": []},
                        ]
                    }
                )
            )
        )

        text = "Your threatening behaviour is unacceptable."
        result = await engine.analyze_document(document_id="doc-4", text=text)

        assert result["document_id"] == "doc-4"
        # Should still have tone_categories from either keyword or LLM path
        assert "tone_categories" in result
