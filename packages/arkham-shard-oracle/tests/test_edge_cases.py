"""
Oracle Shard - Edge Case Tests

Tests for boundary conditions, error paths, fallback logic,
LLM integration, event handlers, and court hierarchy coverage.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_oracle.llm import OracleLLM, _parse_json_response
from arkham_shard_oracle.search import (
    BINDING_THRESHOLD,
    UK_COURT_HIERARCHY,
    AuthoritySearch,
)
from arkham_shard_oracle.shard import OracleShard

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def mock_vectors():
    vectors = AsyncMock()
    vectors.search = AsyncMock(return_value=[])
    return vectors


@pytest.fixture
def search(mock_db, mock_events):
    return AuthoritySearch(db=mock_db, event_bus=mock_events)


@pytest.fixture
def search_with_llm(mock_db, mock_events, mock_llm):
    return AuthoritySearch(db=mock_db, event_bus=mock_events, llm_service=mock_llm)


@pytest.fixture
def search_with_vectors(mock_db, mock_events, mock_vectors):
    return AuthoritySearch(db=mock_db, vectors_service=mock_vectors, event_bus=mock_events)


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
        }.get(name)
    )
    return frame


# ---------------------------------------------------------------------------
# Court Hierarchy Classification - Full Coverage
# ---------------------------------------------------------------------------


class TestCourtHierarchyFullCoverage:
    """Test binding/persuasive classification for every court in the hierarchy."""

    @pytest.mark.asyncio
    async def test_eat_is_binding(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": "EAT"}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["classification"] == "binding"
        assert result["court"] == "EAT"

    @pytest.mark.asyncio
    async def test_court_of_appeal_is_binding(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": "Court of Appeal"}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["classification"] == "binding"

    @pytest.mark.asyncio
    async def test_house_of_lords_is_binding(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": "House of Lords"}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["classification"] == "binding"

    @pytest.mark.asyncio
    async def test_high_court_is_binding(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": "High Court"}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["classification"] == "binding"

    @pytest.mark.asyncio
    async def test_et_abbreviation_is_persuasive(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": "ET"}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["classification"] == "persuasive"

    @pytest.mark.asyncio
    async def test_unknown_court_is_persuasive(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": "County Court"}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["classification"] == "persuasive"
        assert "not in the standard UK employment court hierarchy" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_classify_authority_not_found(self, search, mock_db):
        mock_db.fetch_one.return_value = None

        result = await search.classify_binding_persuasive("nonexistent")
        assert result["classification"] == "unknown"
        assert "not found" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_classify_null_court(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id, "court": None}

        result = await search.classify_binding_persuasive(auth_id)
        assert result["court"] == "Unknown"
        assert result["classification"] == "persuasive"

    def test_hierarchy_ranks_correct(self):
        """Verify court hierarchy rank ordering is correct."""
        assert UK_COURT_HIERARCHY["Supreme Court"] == 5
        assert UK_COURT_HIERARCHY["House of Lords"] == 5
        assert UK_COURT_HIERARCHY["Court of Appeal"] == 4
        assert UK_COURT_HIERARCHY["EAT"] == 3
        assert UK_COURT_HIERARCHY["Employment Appeal Tribunal"] == 3
        assert UK_COURT_HIERARCHY["High Court"] == 3
        assert UK_COURT_HIERARCHY["Employment Tribunal"] == 1
        assert UK_COURT_HIERARCHY["ET"] == 1

    def test_binding_threshold_is_three(self):
        assert BINDING_THRESHOLD == 3


# ---------------------------------------------------------------------------
# Relevance Scoring - Edge Cases
# ---------------------------------------------------------------------------


class TestRelevanceScoringEdgeCases:
    """Edge cases for keyword overlap scoring."""

    @pytest.mark.asyncio
    async def test_relevance_authority_not_found(self, search, mock_db):
        mock_db.fetch_one.return_value = None
        score = await search.score_relevance("nonexistent", "some facts")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_relevance_empty_case_facts(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "title": "Some case",
            "summary": "Some summary",
            "court": "EAT",
            "claim_types": [],
            "relevance_tags": [],
        }
        score = await search.score_relevance(auth_id, "")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_relevance_empty_authority_text(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "title": "",
            "summary": "",
            "court": "",
            "claim_types": [],
            "relevance_tags": [],
        }
        score = await search.score_relevance(auth_id, "employment dismissal claims")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_relevance_identical_text_high_score(self, search, mock_db):
        auth_id = str(uuid.uuid4())
        text = "unfair dismissal employment rights whistleblowing protected disclosures"
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "title": text,
            "summary": text,
            "court": "EAT",
            "claim_types": ["unfair_dismissal"],
            "relevance_tags": ["employment"],
        }
        score = await search.score_relevance(auth_id, text)
        assert score > 0.5

    @pytest.mark.asyncio
    async def test_relevance_with_llm_fallback(self, search_with_llm, mock_db, mock_llm):
        """LLM returns 0.0 score, falls back to keyword overlap."""
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "title": "Maritime shipping law",
            "summary": "Cargo handling",
            "court": "Admiralty",
            "claim_types": [],
            "relevance_tags": [],
        }
        mock_llm.generate.return_value = MagicMock(text='{"score": 0.0, "reasoning": "Not relevant"}')

        score = await search_with_llm.score_relevance(auth_id, "employment unfair dismissal")
        # Should use keyword fallback since LLM returned 0.0
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Vector Search - Fallback Path
# ---------------------------------------------------------------------------


class TestVectorSearchFallback:
    """Test vector search with fallback to SQL."""

    @pytest.mark.asyncio
    async def test_vector_search_success(self, search_with_vectors, mock_db, mock_vectors):
        auth_id = str(uuid.uuid4())
        mock_vectors.search.return_value = [{"id": auth_id, "metadata": {}}]
        mock_db.fetch_all.return_value = [{"id": auth_id, "title": "Found via vectors", "jurisdiction": "UK"}]

        results = await search_with_vectors.search(query="test query")
        mock_vectors.search.assert_called_once()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_vector_search_fallback_on_error(self, search_with_vectors, mock_db, mock_vectors):
        mock_vectors.search.side_effect = Exception("Vector service down")
        mock_db.fetch_all.return_value = [{"id": str(uuid.uuid4()), "title": "SQL fallback result"}]

        results = await search_with_vectors.search(query="test")
        assert len(results) == 1
        assert results[0]["title"] == "SQL fallback result"

    @pytest.mark.asyncio
    async def test_vector_search_empty_results_fallback(self, search_with_vectors, mock_db, mock_vectors):
        mock_vectors.search.return_value = []
        mock_db.fetch_all.return_value = [{"id": str(uuid.uuid4()), "title": "SQL result"}]

        results = await search_with_vectors.search(query="test")
        # Empty vector results should fall back to SQL
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_vector_search_with_metadata_ids(self, search_with_vectors, mock_db, mock_vectors):
        auth_id = str(uuid.uuid4())
        mock_vectors.search.return_value = [{"metadata": {"id": auth_id}}]
        mock_db.fetch_all.return_value = [{"id": auth_id, "title": "Metadata ID"}]

        results = await search_with_vectors.search(query="test")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Citation Chain - Edge Cases
# ---------------------------------------------------------------------------


class TestCitationChainEdgeCases:
    @pytest.mark.asyncio
    async def test_citation_chain_empty(self, search, mock_db):
        mock_db.fetch_all.side_effect = [[], []]
        chain = await search.map_citation_chain("some-id")
        assert chain == []

    @pytest.mark.asyncio
    async def test_citation_chain_only_cites(self, search, mock_db):
        mock_db.fetch_all.side_effect = [
            [{"id": "c1", "source_authority_id": "a", "cited_authority_id": "b", "relationship_type": "follows"}],
            [],
        ]
        chain = await search.map_citation_chain("a")
        assert len(chain) == 1
        assert chain[0]["direction"] == "cites"

    @pytest.mark.asyncio
    async def test_citation_chain_only_cited_by(self, search, mock_db):
        mock_db.fetch_all.side_effect = [
            [],
            [{"id": "c2", "source_authority_id": "x", "cited_authority_id": "a", "relationship_type": "applies"}],
        ]
        chain = await search.map_citation_chain("a")
        assert len(chain) == 1
        assert chain[0]["direction"] == "cited_by"


# ---------------------------------------------------------------------------
# Summarize - Edge Cases
# ---------------------------------------------------------------------------


class TestSummarizeEdgeCases:
    @pytest.mark.asyncio
    async def test_summarize_no_llm_returns_empty(self, search, mock_db):
        mock_db.fetch_one.return_value = None  # No cache
        result = await search.summarize_case("some-id")
        assert result == {"facts": "", "decision": "", "legal_principles": []}

    @pytest.mark.asyncio
    async def test_summarize_authority_not_found(self, search_with_llm, mock_db):
        mock_db.fetch_one.side_effect = [None, None]  # No cache, no authority
        result = await search_with_llm.summarize_case("nonexistent")
        assert result == {"facts": "", "decision": "", "legal_principles": []}

    @pytest.mark.asyncio
    async def test_summarize_cache_insert_failure(self, search_with_llm, mock_db, mock_llm):
        """Cache insert failure should not prevent returning the result."""
        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.side_effect = [
            None,  # No cache
            {"id": auth_id, "title": "Test", "summary": "Sum", "full_text": None, "court": "EAT", "citation": "X"},
        ]
        mock_llm.generate.return_value = MagicMock(
            text='{"facts": "The facts", "decision": "The decision", "legal_principles": ["P1"]}'
        )
        mock_db.execute.side_effect = Exception("DB write failed")

        result = await search_with_llm.summarize_case(auth_id)
        assert result["facts"] == "The facts"
        assert result["decision"] == "The decision"


# ---------------------------------------------------------------------------
# LLM Module - Direct Tests
# ---------------------------------------------------------------------------


class TestOracleLLMDirect:
    def test_llm_not_available_when_none(self):
        llm = OracleLLM(llm_service=None)
        assert llm.available is False

    def test_llm_available_when_service_set(self, mock_llm):
        llm = OracleLLM(llm_service=mock_llm)
        assert llm.available is True

    @pytest.mark.asyncio
    async def test_summarize_no_service(self):
        llm = OracleLLM(llm_service=None)
        result = await llm.summarize_case(title="Test")
        assert result.facts == ""
        assert result.decision == ""

    @pytest.mark.asyncio
    async def test_score_relevance_no_service(self):
        llm = OracleLLM(llm_service=None)
        result = await llm.score_relevance(title="Test", case_facts="facts")
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_research_no_service(self):
        llm = OracleLLM(llm_service=None)
        result = await llm.research(query="test")
        assert result.analysis == ""
        assert result.key_authorities == []

    @pytest.mark.asyncio
    async def test_summarize_llm_exception(self, mock_llm):
        mock_llm.generate.side_effect = Exception("LLM timeout")
        llm = OracleLLM(llm_service=mock_llm)
        result = await llm.summarize_case(title="Test", text="Some text")
        assert result.facts == ""

    @pytest.mark.asyncio
    async def test_score_relevance_llm_exception(self, mock_llm):
        mock_llm.generate.side_effect = Exception("LLM error")
        llm = OracleLLM(llm_service=mock_llm)
        result = await llm.score_relevance(title="Test", case_facts="facts")
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_research_llm_exception(self, mock_llm):
        mock_llm.generate.side_effect = Exception("LLM error")
        llm = OracleLLM(llm_service=mock_llm)
        result = await llm.research(query="test")
        assert result.analysis == ""

    @pytest.mark.asyncio
    async def test_score_relevance_clamps_to_range(self, mock_llm):
        mock_llm.generate.return_value = MagicMock(text='{"score": 1.5, "reasoning": "Very relevant"}')
        llm = OracleLLM(llm_service=mock_llm)
        result = await llm.score_relevance(title="Test", case_facts="facts")
        assert result.score <= 1.0

    @pytest.mark.asyncio
    async def test_score_relevance_negative_clamped(self, mock_llm):
        mock_llm.generate.return_value = MagicMock(text='{"score": -0.5, "reasoning": "Negative"}')
        llm = OracleLLM(llm_service=mock_llm)
        result = await llm.score_relevance(title="Test", case_facts="facts")
        assert result.score >= 0.0

    @pytest.mark.asyncio
    async def test_research_success(self, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            text='{"analysis": "Full analysis", "key_authorities": ["Case A"], "legal_principles": ["P1"], "recommendations": ["R1"]}'
        )
        llm = OracleLLM(llm_service=mock_llm)
        result = await llm.research(query="employment discrimination")
        assert result.analysis == "Full analysis"
        assert result.key_authorities == ["Case A"]
        assert result.legal_principles == ["P1"]
        assert result.recommendations == ["R1"]


# ---------------------------------------------------------------------------
# JSON Parsing - Edge Cases
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_empty_string(self):
        assert _parse_json_response("") == {}

    def test_valid_json(self):
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_markdown_code_block(self):
        text = '```json\n{"facts": "some facts"}\n```'
        result = _parse_json_response(text)
        assert result == {"facts": "some facts"}

    def test_json_in_plain_code_block(self):
        text = '```\n{"score": 0.5}\n```'
        result = _parse_json_response(text)
        assert result == {"score": 0.5}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"score": 0.8, "reasoning": "test"} end'
        result = _parse_json_response(text)
        assert result["score"] == 0.8

    def test_completely_invalid_json(self):
        result = _parse_json_response("This is not JSON at all")
        assert result == {}

    def test_none_equivalent(self):
        result = _parse_json_response("")
        assert result == {}


# ---------------------------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------------------------


class TestEventHandlers:
    @pytest.mark.asyncio
    async def test_theory_updated_triggers_search(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        mock_db.fetch_all.return_value = [
            {"id": "auth-1", "title": "Case 1"},
            {"id": "auth-2", "title": "Case 2"},
        ]

        await shard.handle_theory_updated({"theory": "discrimination claim theory"})

        mock_events.emit.assert_called()
        call_args = mock_events.emit.call_args
        assert call_args.args[0] == "oracle.authority.found"

    @pytest.mark.asyncio
    async def test_theory_updated_empty_theory(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        await shard.handle_theory_updated({"theory": ""})
        # Should not emit if theory is empty
        emit_calls = [c for c in mock_events.emit.call_args_list if c.args[0] == "oracle.authority.found"]
        assert len(emit_calls) == 0

    @pytest.mark.asyncio
    async def test_theory_updated_no_results(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        mock_db.fetch_all.return_value = []

        await shard.handle_theory_updated({"theory": "some theory"})
        emit_calls = [c for c in mock_events.emit.call_args_list if c.args[0] == "oracle.authority.found"]
        assert len(emit_calls) == 0

    @pytest.mark.asyncio
    async def test_claims_created_triggers_search(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        mock_db.fetch_all.return_value = [{"id": "auth-1", "title": "Relevant case"}]

        await shard.handle_claims_created({"claim_type": "unfair_dismissal"})

        emit_calls = [c for c in mock_events.emit.call_args_list if c.args[0] == "oracle.authority.found"]
        assert len(emit_calls) == 1

    @pytest.mark.asyncio
    async def test_claims_created_empty_type(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        await shard.handle_claims_created({"claim_type": ""})
        emit_calls = [c for c in mock_events.emit.call_args_list if c.args[0] == "oracle.authority.found"]
        assert len(emit_calls) == 0

    @pytest.mark.asyncio
    async def test_theory_updated_uses_description_fallback(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        mock_db.fetch_all.return_value = [{"id": "auth-1"}]

        await shard.handle_theory_updated({"description": "alternative key"})
        emit_calls = [c for c in mock_events.emit.call_args_list if c.args[0] == "oracle.authority.found"]
        assert len(emit_calls) == 1

    @pytest.mark.asyncio
    async def test_claims_created_uses_type_fallback(self, mock_frame, mock_events, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        mock_db.fetch_all.return_value = [{"id": "auth-1"}]

        await shard.handle_claims_created({"type": "discrimination"})
        emit_calls = [c for c in mock_events.emit.call_args_list if c.args[0] == "oracle.authority.found"]
        assert len(emit_calls) == 1


# ---------------------------------------------------------------------------
# Research Endpoint Fallback
# ---------------------------------------------------------------------------


class TestResearchFallback:
    @pytest.mark.asyncio
    async def test_research_without_llm(self, search, mock_db):
        mock_db.fetch_all.return_value = [
            {"id": "a1", "citation": "[2020] UKEAT 1", "title": "Relevant Case"},
            {"id": "a2", "citation": "[2019] UKSC 2", "title": "Another Case"},
        ]

        result = await search.research(query="employment law")
        assert "2" in result["analysis"]  # mentions count
        assert len(result["key_authorities"]) == 2
        assert "Enable LLM" in result["recommendations"][0]

    @pytest.mark.asyncio
    async def test_research_with_llm_emits_event(self, search_with_llm, mock_db, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            text='{"analysis": "Analysis", "key_authorities": [], "legal_principles": [], "recommendations": []}'
        )
        search_with_llm._events = AsyncMock()
        search_with_llm._events.emit = AsyncMock()

        result = await search_with_llm.research(query="test")
        assert result["analysis"] == "Analysis"
        search_with_llm._events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_research_event_emission_failure_handled(self, search_with_llm, mock_db, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            text='{"analysis": "OK", "key_authorities": [], "legal_principles": [], "recommendations": []}'
        )
        search_with_llm._events = AsyncMock()
        search_with_llm._events.emit.side_effect = Exception("Event bus down")

        # Should not raise despite event emission failure
        result = await search_with_llm.research(query="test")
        assert result["analysis"] == "OK"


# ---------------------------------------------------------------------------
# Keyword Overlap Scoring - Boundary Conditions
# ---------------------------------------------------------------------------


class TestKeywordOverlapBoundary:
    def test_overlap_both_empty(self, search):
        score = search._keyword_overlap_score(
            {"title": "", "summary": "", "claim_types": [], "relevance_tags": []},
            "",
        )
        assert score == 0.0

    def test_overlap_short_words_filtered(self, search):
        """Words with length <= 2 are filtered out."""
        score = search._keyword_overlap_score(
            {"title": "is a to", "summary": "be or", "claim_types": [], "relevance_tags": []},
            "is a to be or",
        )
        assert score == 0.0

    def test_overlap_perfect_match(self, search):
        text = "employment discrimination unfair dismissal whistleblowing"
        score = search._keyword_overlap_score(
            {"title": text, "summary": "", "claim_types": [], "relevance_tags": []},
            text,
        )
        assert score > 0.8

    def test_overlap_claim_types_contribute(self, search):
        score = search._keyword_overlap_score(
            {
                "title": "Something different",
                "summary": "Another topic",
                "claim_types": ["unfair_dismissal"],
                "relevance_tags": ["employment"],
            },
            "unfair_dismissal employment",
        )
        assert score > 0.0

    def test_overlap_none_claim_types_handled(self, search):
        """None claim_types/relevance_tags should not crash."""
        score = search._keyword_overlap_score(
            {"title": "Test", "summary": "Test", "claim_types": None, "relevance_tags": None},
            "Test",
        )
        assert isinstance(score, float)
