"""
Tests for CredibilityShard.compute_credibility_score() method.

TDD: Tests define the contract for the witness credibility scoring
that integrates cross-shard DB queries with the CredibilityEngine.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_credibility.shard import CredibilityShard


@pytest.fixture
def mock_frame():
    """Create a mock ArkhamFrame instance."""
    frame = MagicMock()
    frame.database = MagicMock()
    frame.events = MagicMock()
    frame.llm = None
    frame.vectors = None

    frame.database.execute = AsyncMock()
    frame.database.fetch_one = AsyncMock()
    frame.database.fetch_all = AsyncMock()

    frame.events.subscribe = AsyncMock()
    frame.events.unsubscribe = AsyncMock()
    frame.events.emit = AsyncMock()

    return frame


@pytest.fixture
async def shard(mock_frame):
    """Create an initialized CredibilityShard instance."""
    shard = CredibilityShard()
    await shard.initialize(mock_frame)
    return shard


def _make_claim_row(claim_id, text, status="unverified", entity_ids=None, source_doc="doc-1"):
    """Helper to create a mock claims table row."""
    return {
        "id": claim_id,
        "text": text,
        "status": status,
        "entity_ids": json.dumps(entity_ids or []),
        "source_document_id": source_doc,
        "source_context": text,
        "confidence": 1.0,
    }


def _make_contradiction_row(doc_a, doc_b, claim_a, claim_b, severity="high"):
    """Helper to create a mock contradictions table row."""
    return {
        "id": f"contra-{doc_a}-{doc_b}",
        "doc_a_id": doc_a,
        "doc_b_id": doc_b,
        "claim_a": claim_a,
        "claim_b": claim_b,
        "severity": severity,
        "contradiction_type": "factual",
        "confidence_score": 0.9,
    }


def _make_mention_row(entity_id, document_id, mention_text):
    """Helper to create a mock entity_mentions table row."""
    return {
        "id": f"mention-{entity_id}-{document_id}",
        "entity_id": entity_id,
        "document_id": document_id,
        "mention_text": mention_text,
        "confidence": 1.0,
    }


def _make_timeline_event(doc_id, text, date_start, entities=None):
    """Helper to create a mock timeline_events table row."""
    return {
        "id": f"event-{doc_id}",
        "document_id": doc_id,
        "text": text,
        "date_start": date_start,
        "entities": json.dumps(entities or []),
        "event_type": "incident",
    }


# =============================================================================
# BASIC CONTRACT
# =============================================================================


class TestComputeCredibilityScoreContract:
    """Test the method signature and return structure."""

    @pytest.mark.asyncio
    async def test_returns_dict(self, shard, mock_frame):
        """Method should return a dict."""
        mock_frame.database.fetch_all.return_value = []
        result = await shard.compute_credibility_score("witness-1")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_returns_required_keys(self, shard, mock_frame):
        """Result dict must contain overall_score, factors, level, confidence."""
        mock_frame.database.fetch_all.return_value = []
        result = await shard.compute_credibility_score("witness-1")
        assert "overall_score" in result
        assert "factors" in result
        assert "level" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_overall_score_range(self, shard, mock_frame):
        """Overall score must be 0-100."""
        mock_frame.database.fetch_all.return_value = []
        result = await shard.compute_credibility_score("witness-1")
        assert 0 <= result["overall_score"] <= 100

    @pytest.mark.asyncio
    async def test_confidence_values(self, shard, mock_frame):
        """Confidence must be low, medium, or high."""
        mock_frame.database.fetch_all.return_value = []
        result = await shard.compute_credibility_score("witness-1")
        assert result["confidence"] in ("low", "medium", "high")


# =============================================================================
# DATA GATHERING
# =============================================================================


class TestDataGathering:
    """Test that the method queries the right cross-shard tables."""

    @pytest.mark.asyncio
    async def test_queries_claims_for_witness(self, shard, mock_frame):
        """Should query arkham_claims for claims linked to witness entity."""
        mock_frame.database.fetch_all.return_value = []
        await shard.compute_credibility_score("witness-1")

        # Should have called fetch_all at least once with a claims-related query
        calls = mock_frame.database.fetch_all.call_args_list
        claims_query_found = any("arkham_claims" in str(c) for c in calls)
        assert claims_query_found, f"No claims query found in calls: {calls}"

    @pytest.mark.asyncio
    async def test_queries_entity_mentions(self, shard, mock_frame):
        """Should query arkham_entity_mentions for witness mention density."""
        mock_frame.database.fetch_all.return_value = []
        await shard.compute_credibility_score("witness-1")

        calls = mock_frame.database.fetch_all.call_args_list
        mentions_query_found = any("arkham_entity_mentions" in str(c) for c in calls)
        assert mentions_query_found, f"No mentions query found in calls: {calls}"

    @pytest.mark.asyncio
    async def test_queries_timeline_events(self, shard, mock_frame):
        """Should query arkham_timeline_events for witness-related events."""
        mock_frame.database.fetch_all.return_value = []
        await shard.compute_credibility_score("witness-1")

        calls = mock_frame.database.fetch_all.call_args_list
        timeline_query_found = any("arkham_timeline_events" in str(c) for c in calls)
        assert timeline_query_found, f"No timeline query found in calls: {calls}"


# =============================================================================
# SCORING WITH DATA
# =============================================================================


class TestScoringWithData:
    """Test scoring behavior when data is returned from queries."""

    @pytest.mark.asyncio
    async def test_verified_claims_boost_score(self, shard, mock_frame):
        """Witness with all verified claims should get higher score."""
        claims = [
            _make_claim_row("c1", "The meeting was on 14 March 2024.", "verified", ["witness-1"]),
            _make_claim_row("c2", "I submitted the complaint on 12 March 2024.", "verified", ["witness-1"]),
        ]
        mock_frame.database.fetch_all.side_effect = [
            claims,  # claims query
            [],  # contradictions query
            [_make_mention_row("witness-1", "doc-1", "John Smith")],  # mentions query
            [_make_timeline_event("doc-1", "Meeting", "2024-03-14")],  # timeline query
        ]
        result = await shard.compute_credibility_score("witness-1")
        assert result["overall_score"] >= 30  # Should be meaningfully positive

    @pytest.mark.asyncio
    async def test_contradictions_reduce_score(self, shard, mock_frame):
        """Witness with contradictions should get lower score."""
        claims = [
            _make_claim_row("c1", "I was at the meeting.", "unverified", ["witness-1"], "doc-1"),
            _make_claim_row("c2", "I was not at the meeting.", "unverified", ["witness-1"], "doc-2"),
        ]
        contradictions = [
            _make_contradiction_row("doc-1", "doc-2", "I was at the meeting", "I was not at the meeting"),
        ]
        mock_frame.database.fetch_all.side_effect = [
            claims,  # claims query
            contradictions,  # contradictions query
            [],  # mentions query
            [],  # timeline query
        ]
        result = await shard.compute_credibility_score("witness-1")
        # With contradictions, should not score very high
        assert result["overall_score"] <= 70


# =============================================================================
# CONFIDENCE LEVELS
# =============================================================================


class TestConfidenceLevels:
    """Test confidence level determination based on data availability."""

    @pytest.mark.asyncio
    async def test_low_confidence_with_no_data(self, shard, mock_frame):
        """No data should yield low confidence."""
        mock_frame.database.fetch_all.return_value = []
        result = await shard.compute_credibility_score("witness-1")
        assert result["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_medium_confidence_with_some_data(self, shard, mock_frame):
        """3-9 data points should yield medium confidence."""
        claims = [
            _make_claim_row(f"c{i}", f"Claim {i} on {i} March 2024.", "verified", ["witness-1"]) for i in range(5)
        ]
        mock_frame.database.fetch_all.side_effect = [
            claims,  # claims query
            [],  # contradictions query
            [],  # mentions query
            [],  # timeline query
        ]
        result = await shard.compute_credibility_score("witness-1")
        assert result["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_high_confidence_with_much_data(self, shard, mock_frame):
        """10+ data points should yield high confidence."""
        claims = [
            _make_claim_row(f"c{i}", f"Claim {i} about event on {i + 1} March 2024.", "verified", ["witness-1"])
            for i in range(10)
        ]
        mentions = [_make_mention_row("witness-1", f"doc-{i}", f"Witness mentioned {i}") for i in range(5)]
        mock_frame.database.fetch_all.side_effect = [
            claims,  # claims query
            [],  # contradictions query
            mentions,  # mentions query
            [],  # timeline query
        ]
        result = await shard.compute_credibility_score("witness-1")
        assert result["confidence"] == "high"


# =============================================================================
# ERROR HANDLING
# =============================================================================


class TestErrorHandling:
    """Test graceful error handling."""

    @pytest.mark.asyncio
    async def test_no_database_returns_defaults(self, mock_frame):
        """If database is None, should return default scores."""
        shard = CredibilityShard()
        await shard.initialize(mock_frame)
        shard._db = None
        result = await shard.compute_credibility_score("witness-1")
        assert result["overall_score"] == 0
        assert result["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_database_error_returns_defaults(self, shard, mock_frame):
        """If database queries fail, should degrade gracefully with zero scores."""
        mock_frame.database.fetch_all.side_effect = Exception("DB connection lost")
        result = await shard.compute_credibility_score("witness-1")
        assert result["overall_score"] == 0
        assert result["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_emits_event_on_success(self, shard, mock_frame):
        """Should emit credibility event after scoring."""
        mock_frame.database.fetch_all.return_value = []
        await shard.compute_credibility_score("witness-1")
        # Check that emit was called with a credibility-related event
        emit_calls = mock_frame.events.emit.call_args_list
        event_names = [str(c) for c in emit_calls]
        credibility_event_found = any("credibility" in str(c) for c in emit_calls)
        assert credibility_event_found

    @pytest.mark.asyncio
    async def test_stores_assessment_in_database(self, shard, mock_frame):
        """Should store the computed score as a CredibilityAssessment."""
        claims = [
            _make_claim_row("c1", "Meeting on 14 March 2024.", "verified", ["witness-1"]),
        ]
        mock_frame.database.fetch_all.side_effect = [
            claims,  # claims query
            [],  # contradictions query
            [],  # mentions query
            [],  # timeline query
        ]
        result = await shard.compute_credibility_score("witness-1")
        # Should have called execute for the INSERT
        execute_calls = mock_frame.database.execute.call_args_list
        insert_found = any("INSERT" in str(c) for c in execute_calls)
        assert insert_found, "No INSERT call found -- assessment not stored"
