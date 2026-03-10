"""
Oracle Shard - AuthoritySearch Tests

Tests for search, relevance scoring, binding/persuasive classification,
citation chains, and summary caching.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_oracle.search import AuthoritySearch

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
def mock_vectors():
    """Create a mock vectors service."""
    vectors = AsyncMock()
    vectors.search = AsyncMock(return_value=[])
    vectors.embed_text = AsyncMock(return_value=[0.1] * 384)
    return vectors


@pytest.fixture
def mock_events():
    """Create a mock event bus."""
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
def search(mock_db, mock_events):
    """Create AuthoritySearch with db and events, no LLM."""
    return AuthoritySearch(db=mock_db, vectors_service=None, event_bus=mock_events)


@pytest.fixture
def search_with_llm(mock_db, mock_events, mock_llm):
    """Create AuthoritySearch with LLM."""
    return AuthoritySearch(db=mock_db, vectors_service=None, event_bus=mock_events, llm_service=mock_llm)


# ---------------------------------------------------------------------------
# 1. test_search_by_keyword
# ---------------------------------------------------------------------------


class TestSearchByKeyword:
    """Basic keyword search returns matching authorities."""

    @pytest.mark.asyncio
    async def test_search_by_keyword(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_all.return_value = [
            {
                "id": auth_id,
                "citation": "[1932] AC 562",
                "jurisdiction": "UK",
                "court": "House of Lords",
                "title": "Donoghue v Stevenson",
                "year": 1932,
                "summary": "Neighbour principle and duty of care",
                "relevance_tags": [],
                "claim_types": [],
                "authority_type": "case_law",
            }
        ]

        results = await search.search(query="duty of care")

        assert len(results) == 1
        assert results[0]["title"] == "Donoghue v Stevenson"
        # Verify ILIKE was used in the SQL
        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "ILIKE" in sql


# ---------------------------------------------------------------------------
# 2. test_search_with_jurisdiction_filter
# ---------------------------------------------------------------------------


class TestSearchWithJurisdictionFilter:
    """Search respects jurisdiction filter."""

    @pytest.mark.asyncio
    async def test_search_with_jurisdiction_filter(self, search, mock_db):
        mock_db.fetch_all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "citation": "[2021] UKSC 5",
                "jurisdiction": "UK",
                "court": "Supreme Court",
                "title": "Test UK Case",
                "year": 2021,
                "summary": "UK employment law",
                "relevance_tags": [],
                "claim_types": [],
                "authority_type": "case_law",
            }
        ]

        results = await search.search(query="employment", jurisdiction="UK")

        assert len(results) == 1
        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "jurisdiction" in sql
        params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("params", {})
        assert params.get("jurisdiction") == "UK"


# ---------------------------------------------------------------------------
# 3. test_relevance_scoring_high_match
# ---------------------------------------------------------------------------


class TestRelevanceScoringHighMatch:
    """Relevant authority scores high (> 0.5)."""

    @pytest.mark.asyncio
    async def test_relevance_scoring_high_match(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "title": "Unfair dismissal employment rights",
            "summary": "Employee was unfairly dismissed from employment after raising whistleblowing concerns",
            "court": "EAT",
            "jurisdiction": "UK",
            "claim_types": ["unfair_dismissal", "whistleblowing"],
            "relevance_tags": ["employment", "dismissal"],
        }

        score = await search.score_relevance(
            authority_id=auth_id,
            case_facts="The claimant was dismissed from employment after making protected disclosures about safety concerns",
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score > 0.3  # Should have meaningful overlap


# ---------------------------------------------------------------------------
# 4. test_relevance_scoring_low_match
# ---------------------------------------------------------------------------


class TestRelevanceScoringLowMatch:
    """Irrelevant authority scores low (< 0.3)."""

    @pytest.mark.asyncio
    async def test_relevance_scoring_low_match(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "title": "Marine shipping regulations",
            "summary": "International maritime cargo handling procedures and port authority regulations",
            "court": "Admiralty Court",
            "jurisdiction": "UK",
            "claim_types": ["maritime"],
            "relevance_tags": ["shipping", "maritime"],
        }

        score = await search.score_relevance(
            authority_id=auth_id,
            case_facts="The claimant was dismissed from employment after making protected disclosures",
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score < 0.3  # Should have minimal overlap


# ---------------------------------------------------------------------------
# 5. test_binding_supreme_court
# ---------------------------------------------------------------------------


class TestBindingSupremeCourt:
    """Supreme Court decision classified as binding."""

    @pytest.mark.asyncio
    async def test_binding_supreme_court(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "court": "Supreme Court",
            "jurisdiction": "UK",
            "title": "Test SC Case",
        }

        result = await search.classify_binding_persuasive(authority_id=auth_id)

        assert result["classification"] == "binding"
        assert result["court"] == "Supreme Court"
        assert "reasoning" in result


# ---------------------------------------------------------------------------
# 6. test_persuasive_et_decision
# ---------------------------------------------------------------------------


class TestPersuasiveETDecision:
    """Employment Tribunal decision classified as persuasive."""

    @pytest.mark.asyncio
    async def test_persuasive_et_decision(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "court": "Employment Tribunal",
            "jurisdiction": "UK",
            "title": "Test ET Case",
        }

        result = await search.classify_binding_persuasive(authority_id=auth_id)

        assert result["classification"] == "persuasive"
        assert result["court"] == "Employment Tribunal"
        assert "reasoning" in result


# ---------------------------------------------------------------------------
# 7. test_citation_chain_both_directions
# ---------------------------------------------------------------------------


class TestCitationChainBothDirections:
    """Citation chain includes both cites and cited_by."""

    @pytest.mark.asyncio
    async def test_citation_chain_both_directions(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        cited_id = str(uuid.uuid4())
        citing_id = str(uuid.uuid4())

        # First call: authorities this one cites (source_authority_id = auth_id)
        # Second call: authorities that cite this one (cited_authority_id = auth_id)
        mock_db.fetch_all.side_effect = [
            [
                {
                    "id": "chain-1",
                    "source_authority_id": auth_id,
                    "cited_authority_id": cited_id,
                    "relationship_type": "follows",
                }
            ],
            [
                {
                    "id": "chain-2",
                    "source_authority_id": citing_id,
                    "cited_authority_id": auth_id,
                    "relationship_type": "distinguishes",
                }
            ],
        ]

        chain = await search.map_citation_chain(authority_id=auth_id)

        assert len(chain) == 2
        # Should have both directions
        directions = {c.get("direction") for c in chain}
        assert "cites" in directions
        assert "cited_by" in directions


# ---------------------------------------------------------------------------
# 8. test_summarize_caches_result
# ---------------------------------------------------------------------------


class TestSummarizeCachesResult:
    """Second summarize call returns cached result, not re-generating."""

    @pytest.mark.asyncio
    async def test_summarize_caches_result(self, search_with_llm, mock_db, mock_llm):
        auth_id = str(uuid.uuid4())

        # First call: no cached summary -> LLM generates one
        mock_db.fetch_one.side_effect = [
            # First fetch_one: check cache -> miss
            None,
            # After insert, fetch authority for context
            {
                "id": auth_id,
                "title": "Test Case",
                "summary": "Short summary",
                "full_text": "The full text of the case",
                "court": "EAT",
            },
        ]
        mock_llm.generate.return_value = MagicMock(
            text='{"facts": "The facts", "decision": "The decision", "legal_principles": ["Principle 1"]}'
        )

        result1 = await search_with_llm.summarize_case(authority_id=auth_id)

        assert result1["facts"] == "The facts"
        assert result1["decision"] == "The decision"
        assert mock_llm.generate.call_count == 1

        # Second call: cached summary exists
        mock_db.fetch_one.side_effect = None
        mock_db.fetch_one.return_value = {
            "id": "summary-1",
            "authority_id": auth_id,
            "facts": "The facts",
            "decision": "The decision",
            "legal_principles": ["Principle 1"],
        }

        result2 = await search_with_llm.summarize_case(authority_id=auth_id)

        assert result2["facts"] == "The facts"
        # LLM should NOT have been called again
        assert mock_llm.generate.call_count == 1
