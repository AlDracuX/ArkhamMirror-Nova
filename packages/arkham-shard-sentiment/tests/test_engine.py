"""
Sentiment Shard - Engine Tests

Tests for SentimentEngine domain logic: tone classification, temporal patterns,
party comparison, and document analysis with DB persistence.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_sentiment.engine import TONE_PATTERNS, SentimentEngine
from arkham_shard_sentiment.llm import SentimentLLM
from arkham_shard_sentiment.shard import SentimentShard

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
    async def test_analyze_stores_result(self, engine_no_llm, mock_db, mock_events):
        """analyze_document persists result to DB and emits event."""
        doc_id = str(uuid.uuid4())
        text = "We deny the hostile allegations and reject the unfair claims."

        result = await engine_no_llm.analyze_document(document_id=doc_id, text=text)

        # Verify structure
        assert result["document_id"] == doc_id
        assert "overall_score" in result
        assert "tone_categories" in result
        assert "keywords_found" in result

        # Verify DB write happened (valid UUID -> DB insert occurs)
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
    async def test_analyze_hostile_text(self, engine_no_llm, mock_db, mock_events):
        """Hostile text produces negative score with hostile tone category."""
        doc_id = str(uuid.uuid4())
        text = "Your threatening and aggressive conduct amounts to intimidation."

        result = await engine_no_llm.analyze_document(document_id=doc_id, text=text)

        assert result["overall_score"] < 0 or any(
            c["category"] == "hostile" and c["score"] > 0 for c in result["tone_categories"]
        )

    @pytest.mark.asyncio
    async def test_analyze_with_case_id(self, engine_no_llm, mock_db, mock_events):
        """case_id is stored when provided."""
        doc_id = str(uuid.uuid4())
        text = "Normal text."

        result = await engine_no_llm.analyze_document(document_id=doc_id, text=text, case_id="case-99")

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["case_id"] == "case-99"

    @pytest.mark.asyncio
    async def test_analyze_with_llm_enhancement(self, engine, mock_db, mock_events, mock_llm):
        """When LLM is available, tone classification is enhanced."""
        doc_id = str(uuid.uuid4())
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
        result = await engine.analyze_document(document_id=doc_id, text=text)

        assert result["document_id"] == doc_id
        # Should still have tone_categories from either keyword or LLM path
        assert "tone_categories" in result

    @pytest.mark.asyncio
    async def test_analyze_invalid_uuid_skips_db(self, engine_no_llm, mock_db, mock_events):
        """Non-UUID document_id still returns result but skips DB insert."""
        result = await engine_no_llm.analyze_document(document_id="not-a-uuid", text="fair text")

        assert result["document_id"] == "not-a-uuid"
        assert "overall_score" in result
        # DB execute should NOT be called because doc_uuid is None
        mock_db.execute.assert_not_called()
        # Event should still emit
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_empty_text(self, engine_no_llm, mock_db, mock_events):
        """Empty text returns neutral zero-score result."""
        doc_id = str(uuid.uuid4())
        result = await engine_no_llm.analyze_document(document_id=doc_id, text="")

        assert result["overall_score"] == 0.0
        assert result["label"] == "neutral"
        assert result["confidence"] == 0.0
        assert result["keywords_found"] == []

    @pytest.mark.asyncio
    async def test_analyze_whitespace_only(self, engine_no_llm, mock_db, mock_events):
        """Whitespace-only text treated as neutral."""
        doc_id = str(uuid.uuid4())
        result = await engine_no_llm.analyze_document(document_id=doc_id, text="   \n\t  ")

        assert result["overall_score"] == 0.0
        assert result["label"] == "neutral"

    @pytest.mark.asyncio
    async def test_analyze_no_event_bus(self, mock_db):
        """Analysis works without event bus (no event emission)."""
        engine = SentimentEngine(db=mock_db, event_bus=None, llm_service=None)
        doc_id = str(uuid.uuid4())
        result = await engine.analyze_document(document_id=doc_id, text="We deny everything")

        assert result["document_id"] == doc_id
        assert "overall_score" in result


# ---------------------------------------------------------------------------
# LLM Fallback and Error Path Tests
# ---------------------------------------------------------------------------


class TestLLMFallback:
    """Test LLM enhancement error handling and fallback."""

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_keywords(self, mock_db, mock_events):
        """When LLM raises, engine falls back to keyword baseline."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM service down"))

        engine = SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)
        doc_id = str(uuid.uuid4())
        result = await engine.analyze_document(document_id=doc_id, text="hostile threatening aggressive")

        # Should still return valid result from keyword fallback
        assert result["document_id"] == doc_id
        assert "tone_categories" in result
        assert len(result["tone_categories"]) == 5  # All 5 categories present

    @pytest.mark.asyncio
    async def test_llm_returns_empty_categories(self, mock_db, mock_events):
        """LLM returning empty categories list falls back to baseline."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(text=json.dumps({"categories": []})))

        engine = SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)
        doc_id = str(uuid.uuid4())
        result = await engine.analyze_document(document_id=doc_id, text="hostile threatening")

        assert "tone_categories" in result
        # Should fall back to baseline since LLM returned empty
        assert len(result["tone_categories"]) == 5

    @pytest.mark.asyncio
    async def test_llm_returns_malformed_json(self, mock_db, mock_events):
        """LLM returning non-JSON falls back to baseline."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(text="This is not JSON at all"))

        engine = SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)
        doc_id = str(uuid.uuid4())
        result = await engine.analyze_document(document_id=doc_id, text="hostile threatening")

        assert "tone_categories" in result
        assert len(result["tone_categories"]) == 5

    @pytest.mark.asyncio
    async def test_llm_returns_json_without_categories_key(self, mock_db, mock_events):
        """LLM returning JSON without 'categories' key falls back to baseline."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(text=json.dumps({"result": "something else"})))

        engine = SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)
        doc_id = str(uuid.uuid4())
        result = await engine.analyze_document(document_id=doc_id, text="hostile threatening")

        assert "tone_categories" in result
        assert len(result["tone_categories"]) == 5

    @pytest.mark.asyncio
    async def test_enhance_with_llm_no_service(self):
        """_enhance_with_llm returns baseline when no LLM service."""
        engine = SentimentEngine(db=None, event_bus=None, llm_service=None)
        baseline = [{"category": "hostile", "score": 0.5, "evidence_segments": []}]
        result = await engine._enhance_with_llm("text", baseline)
        assert result is baseline

    @pytest.mark.asyncio
    async def test_llm_merges_scores_correctly(self, mock_db, mock_events):
        """LLM scores merged 60/40 with keyword baseline."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=MagicMock(
                text=json.dumps(
                    {
                        "categories": [
                            {"category": "hostile", "score": 1.0, "evidence": ["threatening"]},
                            {"category": "evasive", "score": 0.0, "evidence": []},
                            {"category": "condescending", "score": 0.0, "evidence": []},
                            {"category": "professional", "score": 0.0, "evidence": []},
                            {"category": "supportive", "score": 0.0, "evidence": []},
                        ]
                    }
                )
            )
        )

        engine = SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)
        doc_id = str(uuid.uuid4())
        result = await engine.analyze_document(document_id=doc_id, text="threatening aggressive hostile unacceptable")

        hostile = next(c for c in result["tone_categories"] if c["category"] == "hostile")
        # LLM score=1.0 * 0.6 + keyword_score * 0.4, keyword_score > 0
        # So blended score should be > 0.6
        assert hostile["score"] >= 0.6


# ---------------------------------------------------------------------------
# SentimentLLM Unit Tests
# ---------------------------------------------------------------------------


class TestSentimentLLM:
    """Test SentimentLLM class directly."""

    def test_is_available_with_service(self):
        llm = SentimentLLM(llm_service=MagicMock())
        assert llm.is_available is True

    def test_is_available_without_service(self):
        llm = SentimentLLM(llm_service=None)
        assert llm.is_available is False

    @pytest.mark.asyncio
    async def test_classify_tone_not_available(self):
        """classify_tone returns None when LLM not available."""
        llm = SentimentLLM(llm_service=None)
        result = await llm.classify_tone("some text")
        assert result is None

    @pytest.mark.asyncio
    async def test_classify_tone_success(self):
        """classify_tone parses valid LLM response."""
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(
            return_value={
                "text": json.dumps(
                    {
                        "categories": [
                            {"category": "hostile", "score": 0.8, "evidence": ["threatening"]},
                        ]
                    }
                )
            }
        )
        llm = SentimentLLM(llm_service=mock_service)
        result = await llm.classify_tone("threatening text")
        assert result is not None
        assert len(result) == 1
        assert result[0]["category"] == "hostile"

    @pytest.mark.asyncio
    async def test_classify_tone_llm_error(self):
        """classify_tone returns None on LLM error."""
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(side_effect=Exception("Connection refused"))
        llm = SentimentLLM(llm_service=mock_service)
        result = await llm.classify_tone("some text")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_raises_without_service(self):
        """_generate raises RuntimeError when no LLM service."""
        llm = SentimentLLM(llm_service=None)
        with pytest.raises(RuntimeError, match="LLM service not available"):
            await llm._generate("prompt", "system")

    @pytest.mark.asyncio
    async def test_generate_handles_object_response(self):
        """_generate handles response objects with .text attribute."""
        mock_service = MagicMock()
        response_obj = MagicMock()
        response_obj.text = "response text"
        response_obj.model = "test-model"
        mock_service.generate = AsyncMock(return_value=response_obj)

        llm = SentimentLLM(llm_service=mock_service)
        result = await llm._generate("prompt", "system")
        assert result["text"] == "response text"
        assert result["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_generate_handles_string_response(self):
        """_generate handles plain string responses."""
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(return_value="plain string")

        llm = SentimentLLM(llm_service=mock_service)
        result = await llm._generate("prompt", "system")
        assert result["text"] == "plain string"

    def test_parse_json_response_direct(self):
        """_parse_json_response handles direct JSON."""
        llm = SentimentLLM()
        result = llm._parse_json_response({"text": '{"key": "value"}'})
        assert result == {"key": "value"}

    def test_parse_json_response_markdown_block(self):
        """_parse_json_response extracts JSON from markdown code blocks."""
        llm = SentimentLLM()
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        result = llm._parse_json_response({"text": text})
        assert result == {"key": "value"}

    def test_parse_json_response_empty(self):
        """_parse_json_response returns None for empty text."""
        llm = SentimentLLM()
        assert llm._parse_json_response({"text": ""}) is None
        assert llm._parse_json_response({}) is None

    def test_parse_json_response_invalid(self):
        """_parse_json_response returns None for non-JSON text."""
        llm = SentimentLLM()
        assert llm._parse_json_response({"text": "not json at all"}) is None

    @pytest.mark.asyncio
    async def test_detect_tone_patterns_not_available(self):
        """detect_tone_patterns returns None when LLM not available."""
        llm = SentimentLLM(llm_service=None)
        result = await llm.detect_tone_patterns([{"period": "2024-01", "avg_score": 0.5}])
        assert result is None

    @pytest.mark.asyncio
    async def test_detect_tone_patterns_success(self):
        """detect_tone_patterns parses valid response."""
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(
            return_value={
                "text": json.dumps(
                    {
                        "patterns": [
                            {
                                "type": "escalation",
                                "description": "Tone became more hostile",
                                "period_from": "2024-01",
                                "period_to": "2024-03",
                                "significance": 0.8,
                            }
                        ],
                        "summary": "Clear escalation pattern",
                    }
                )
            }
        )
        llm = SentimentLLM(llm_service=mock_service)
        result = await llm.detect_tone_patterns(
            [
                {"period": "2024-01", "avg_score": 0.5, "text_samples": ["sample1"]},
                {"period": "2024-03", "avg_score": -0.3},
            ]
        )
        assert result is not None
        assert "patterns" in result
        assert len(result["patterns"]) == 1

    @pytest.mark.asyncio
    async def test_detect_tone_patterns_error(self):
        """detect_tone_patterns returns None on error."""
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(side_effect=Exception("LLM down"))
        llm = SentimentLLM(llm_service=mock_service)
        result = await llm.detect_tone_patterns([{"period": "2024-01", "avg_score": 0.5}])
        assert result is None

    @pytest.mark.asyncio
    async def test_classify_tone_truncates_long_text(self):
        """classify_tone truncates text to 4000 chars in prompt."""
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(return_value={"text": json.dumps({"categories": []})})
        llm = SentimentLLM(llm_service=mock_service)
        long_text = "a" * 10000
        await llm.classify_tone(long_text)

        # Verify the prompt was called (text gets truncated in the prompt template)
        call_args = mock_service.generate.call_args
        prompt = call_args.kwargs.get("prompt", call_args[1].get("prompt", ""))
        # The prompt should contain at most 4000 chars of the original text
        assert "a" * 4001 not in prompt


# ---------------------------------------------------------------------------
# Temporal Pattern Edge Cases
# ---------------------------------------------------------------------------


class TestTemporalPatternEdgeCases:
    """Edge cases for temporal pattern detection."""

    @pytest.fixture
    def engine(self, mock_db, mock_events):
        return SentimentEngine(db=mock_db, event_bus=mock_events, llm_service=None)

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_events(self):
        events = AsyncMock()
        events.emit = AsyncMock()
        return events

    @pytest.mark.asyncio
    async def test_temporal_no_db(self):
        """No DB returns empty list."""
        engine = SentimentEngine(db=None, event_bus=None, llm_service=None)
        result = await engine.detect_temporal_patterns(case_id="case-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_temporal_string_dates(self, engine, mock_db):
        """Handles string dates from DB (ISO format)."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": "2024-01-01T00:00:00+00:00", "overall_score": 0.5, "document_id": "d1"},
            {"analyzed_at": "2024-02-01T00:00:00+00:00", "overall_score": 0.4, "document_id": "d2"},
        ]
        patterns = await engine.detect_temporal_patterns(case_id="case-1")
        assert len(patterns) == 2
        assert patterns[0]["period"] == "2024-01"
        assert patterns[1]["period"] == "2024-02"

    @pytest.mark.asyncio
    async def test_temporal_same_period_averages(self, engine, mock_db):
        """Multiple results in same period are averaged."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 5, tzinfo=timezone.utc), "overall_score": 0.2, "document_id": "d1"},
            {"analyzed_at": datetime(2024, 1, 15, tzinfo=timezone.utc), "overall_score": 0.8, "document_id": "d2"},
        ]
        patterns = await engine.detect_temporal_patterns(case_id="case-1")
        assert len(patterns) == 1
        assert patterns[0]["avg_score"] == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_temporal_emits_event_on_significant_shift(self, engine, mock_db, mock_events):
        """Significant shift (>0.3) emits pattern detected event."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 1, tzinfo=timezone.utc), "overall_score": 0.8, "document_id": "d1"},
            {"analyzed_at": datetime(2024, 2, 1, tzinfo=timezone.utc), "overall_score": 0.1, "document_id": "d2"},
        ]
        await engine.detect_temporal_patterns(case_id="case-1")
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "sentiment.pattern.detected"

    @pytest.mark.asyncio
    async def test_temporal_no_event_on_small_shift(self, engine, mock_db, mock_events):
        """Small shifts do not emit events."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 1, tzinfo=timezone.utc), "overall_score": 0.5, "document_id": "d1"},
            {"analyzed_at": datetime(2024, 2, 1, tzinfo=timezone.utc), "overall_score": 0.45, "document_id": "d2"},
        ]
        await engine.detect_temporal_patterns(case_id="case-1")
        mock_events.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_temporal_first_period_always_stable(self, engine, mock_db):
        """First period always has shift_magnitude=0 and direction=stable."""
        mock_db.fetch_all.return_value = [
            {"analyzed_at": datetime(2024, 1, 1, tzinfo=timezone.utc), "overall_score": -0.5, "document_id": "d1"},
        ]
        patterns = await engine.detect_temporal_patterns(case_id="case-1")
        assert patterns[0]["shift_magnitude"] == 0.0
        assert patterns[0]["shift_direction"] == "stable"


# ---------------------------------------------------------------------------
# Compare Parties Edge Cases
# ---------------------------------------------------------------------------


class TestComparePartiesEdgeCases:
    """Edge cases for party comparison."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.mark.asyncio
    async def test_compare_no_db(self):
        """No DB returns zeroed defaults."""
        engine = SentimentEngine(db=None, event_bus=None, llm_service=None)
        result = await engine.compare_parties(case_id="case-1")
        assert result["claimant_avg"] == 0.0
        assert result["respondent_avg"] == 0.0
        assert result["divergence"] == 0.0
        assert result["key_differences"] == []

    @pytest.mark.asyncio
    async def test_compare_only_claimant(self, mock_db):
        """Only claimant data returns claimant avg with zero respondent."""
        mock_db.fetch_all.side_effect = [
            [{"overall_score": 0.5, "document_id": "d1", "label": "positive"}],
            [],
        ]
        engine = SentimentEngine(db=mock_db, event_bus=None, llm_service=None)
        result = await engine.compare_parties(case_id="case-1")
        assert result["claimant_avg"] == 0.5
        assert result["respondent_avg"] == 0.0
        assert result["divergence"] == 0.5

    @pytest.mark.asyncio
    async def test_compare_only_respondent(self, mock_db):
        """Only respondent data returns respondent avg with zero claimant."""
        mock_db.fetch_all.side_effect = [
            [],
            [{"overall_score": -0.4, "document_id": "d1", "label": "negative"}],
        ]
        engine = SentimentEngine(db=mock_db, event_bus=None, llm_service=None)
        result = await engine.compare_parties(case_id="case-1")
        assert result["claimant_avg"] == 0.0
        assert result["respondent_avg"] == -0.4
        assert result["divergence"] == 0.4

    @pytest.mark.asyncio
    async def test_compare_small_divergence_no_narrative(self, mock_db):
        """Divergence <= 0.3 produces no key_differences narrative."""
        mock_db.fetch_all.side_effect = [
            [{"overall_score": 0.3, "document_id": "d1", "label": "positive"}],
            [{"overall_score": 0.2, "document_id": "d2", "label": "neutral"}],
        ]
        engine = SentimentEngine(db=mock_db, event_bus=None, llm_service=None)
        result = await engine.compare_parties(case_id="case-1")
        # Divergence 0.1 => no "significantly more positive" narrative
        narratives = [d for d in result["key_differences"] if "significantly" in d.lower()]
        assert len(narratives) == 0

    @pytest.mark.asyncio
    async def test_compare_label_divergence_reported(self, mock_db):
        """Different labels between parties are reported."""
        mock_db.fetch_all.side_effect = [
            [{"overall_score": 0.5, "document_id": "d1", "label": "positive"}],
            [{"overall_score": 0.4, "document_id": "d2", "label": "neutral"}],
        ]
        engine = SentimentEngine(db=mock_db, event_bus=None, llm_service=None)
        result = await engine.compare_parties(case_id="case-1")
        # Should have label divergence entry
        label_diffs = [d for d in result["key_differences"] if "Label divergence" in d]
        assert len(label_diffs) == 1


# ---------------------------------------------------------------------------
# Tone Classification Boundary Tests
# ---------------------------------------------------------------------------


class TestToneClassificationBoundary:
    """Boundary and edge-case tests for classify_tone_categories."""

    @pytest.fixture
    def engine(self):
        return SentimentEngine(db=None, event_bus=None, llm_service=None)

    def test_empty_text(self, engine):
        """Empty text returns all categories with zero scores."""
        categories = engine.classify_tone_categories("")
        assert len(categories) == 5
        for cat in categories:
            assert cat["score"] == 0.0
            assert cat["evidence_segments"] == []

    def test_very_long_text(self, engine):
        """Very long text doesn't crash or timeout."""
        text = "threatening hostile aggressive " * 1000
        categories = engine.classify_tone_categories(text)
        hostile = next(c for c in categories if c["category"] == "hostile")
        # Keywords are unique set matches + pattern matches; score is capped at 1.0
        assert hostile["score"] > 0
        assert hostile["score"] <= 1.0

    def test_score_capped_at_one(self, engine):
        """Score never exceeds 1.0 even with many keyword hits."""
        text = " ".join(
            [
                "threatening",
                "aggressive",
                "hostile",
                "intimidation",
                "unacceptable",
                "outrageous",
                "disgraceful",
                "appalling",
                "abusive",
                "bullying",
            ]
        )
        categories = engine.classify_tone_categories(text)
        for cat in categories:
            assert cat["score"] <= 1.0

    def test_mixed_tones_detected(self, engine):
        """Text with multiple tones detected simultaneously."""
        text = (
            "We acknowledge receipt of your correspondence. "
            "However, your threatening demands are completely unacceptable."
        )
        categories = engine.classify_tone_categories(text)

        professional = next(c for c in categories if c["category"] == "professional")
        hostile = next(c for c in categories if c["category"] == "hostile")
        assert professional["score"] > 0
        assert hostile["score"] > 0

    def test_case_insensitive_keywords(self, engine):
        """Keyword matching is case-insensitive."""
        text = "THREATENING AGGRESSIVE HOSTILE"
        categories = engine.classify_tone_categories(text)
        hostile = next(c for c in categories if c["category"] == "hostile")
        assert hostile["score"] > 0

    def test_pattern_matching_works(self, engine):
        """Regex patterns detect multi-word phrases."""
        text = "You will face serious consequences for this."
        categories = engine.classify_tone_categories(text)
        hostile = next(c for c in categories if c["category"] == "hostile")
        assert hostile["score"] > 0
        assert len(hostile["evidence_segments"]) > 0

    def test_evasive_multi_word_patterns(self, engine):
        """Multi-word evasive phrases detected."""
        text = "To the best of our recollection, we cannot say what happened."
        categories = engine.classify_tone_categories(text)
        evasive = next(c for c in categories if c["category"] == "evasive")
        assert evasive["score"] > 0

    def test_all_tone_patterns_have_required_keys(self):
        """TONE_PATTERNS dictionary has required structure."""
        for category, definition in TONE_PATTERNS.items():
            assert "keywords" in definition, f"{category} missing keywords"
            assert "patterns" in definition, f"{category} missing patterns"
            assert isinstance(definition["keywords"], frozenset)
            assert isinstance(definition["patterns"], list)


# ---------------------------------------------------------------------------
# Event Handler Tests
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Test shard event handler methods."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_events(self):
        events = AsyncMock()
        events.emit = AsyncMock()
        events.subscribe = AsyncMock()
        events.unsubscribe = AsyncMock()
        return events

    @pytest.fixture
    def mock_frame(self, mock_events, mock_db):
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {
                "events": mock_events,
                "llm": None,
                "vectors": None,
            }.get(name)
        )
        return frame

    @pytest.mark.asyncio
    async def test_handle_document_processed_with_text(self, mock_frame, mock_db):
        """Event handler triggers analysis when text is provided."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        # Reset execute mock from schema creation
        mock_db.execute.reset_mock()

        doc_id = str(uuid.uuid4())
        await shard.handle_document_processed(
            {"payload": {"document_id": doc_id, "text": "fair and reasonable", "case_id": "c1"}}
        )
        # Should have called execute for the DB insert
        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_handle_document_processed_no_text(self, mock_frame, mock_db):
        """Event handler skips analysis when text is empty."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        await shard.handle_document_processed({"payload": {"document_id": "doc-1", "text": "", "case_id": "c1"}})
        # No DB write expected (empty text + non-UUID doc = no insert)
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_document_processed_no_doc_id(self, mock_frame, mock_db):
        """Event handler skips when document_id is missing."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        await shard.handle_document_processed({"payload": {"text": "some text", "case_id": "c1"}})
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_document_processed_engine_error(self, mock_frame, mock_db):
        """Event handler catches engine errors gracefully."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)

        # Make DB raise to simulate engine error
        mock_db.execute.side_effect = RuntimeError("DB down")

        doc_id = str(uuid.uuid4())
        # Should not raise
        await shard.handle_document_processed(
            {"payload": {"document_id": doc_id, "text": "some text", "case_id": "c1"}}
        )

    @pytest.mark.asyncio
    async def test_handle_thread_reconstructed(self, mock_frame):
        """Thread reconstructed handler logs without error."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        # Should not raise
        await shard.handle_thread_reconstructed({"payload": {"thread_id": "t1"}})

    @pytest.mark.asyncio
    async def test_handle_thread_reconstructed_no_id(self, mock_frame):
        """Thread handler with missing thread_id is graceful."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        await shard.handle_thread_reconstructed({"payload": {}})

    @pytest.mark.asyncio
    async def test_shutdown_unsubscribes_events(self, mock_frame, mock_events):
        """Shutdown unsubscribes from both events."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        await shard.shutdown()

        assert mock_events.unsubscribe.call_count == 2
        unsub_events = [c[0][0] for c in mock_events.unsubscribe.call_args_list]
        assert "documents.processed" in unsub_events
        assert "comms.thread.reconstructed" in unsub_events

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up_engine(self, mock_frame):
        """Shutdown sets engine and llm_integration to None."""
        shard = SentimentShard()
        await shard.initialize(mock_frame)
        assert shard.engine is not None

        await shard.shutdown()
        assert shard.engine is None
        assert shard.llm_integration is None
