"""
RespondentIntel Shard - Engine Edge Case Tests

Covers: DB failure paths, LLM failure fallback, malformed JSON,
no-DB engine, event handler edge cases, heuristic edge cases,
_parse_json_safe, API 503 paths, rule-based assessment variants.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_respondent_intel.engine import (
    RespondentIntelEngine,
    _parse_json_field,
    _parse_json_safe,
)

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
def mock_event_bus():
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_event_bus, mock_llm):
    return RespondentIntelEngine(db=mock_db, event_bus=mock_event_bus, llm_service=mock_llm)


@pytest.fixture
def engine_no_llm(mock_db, mock_event_bus):
    return RespondentIntelEngine(db=mock_db, event_bus=mock_event_bus, llm_service=None)


@pytest.fixture
def engine_no_db(mock_event_bus, mock_llm):
    return RespondentIntelEngine(db=None, event_bus=mock_event_bus, llm_service=mock_llm)


@pytest.fixture
def engine_bare():
    """Engine with no services at all."""
    return RespondentIntelEngine(db=None, event_bus=None, llm_service=None)


# ---------------------------------------------------------------------------
# _parse_json_safe tests
# ---------------------------------------------------------------------------


class TestParseJsonSafe:
    """Edge cases for the JSON parsing helper."""

    def test_empty_string_returns_default(self):
        assert _parse_json_safe("", {"fallback": True}) == {"fallback": True}

    def test_none_returns_default(self):
        assert _parse_json_safe(None, []) == []

    def test_plain_json_object(self):
        assert _parse_json_safe('{"key": "value"}', {}) == {"key": "value"}

    def test_plain_json_array(self):
        assert _parse_json_safe("[1, 2, 3]", []) == [1, 2, 3]

    def test_markdown_fenced_json(self):
        text = '```json\n{"key": "value"}\n```'
        assert _parse_json_safe(text, {}) == {"key": "value"}

    def test_markdown_fenced_no_language(self):
        text = '```\n{"key": "value"}\n```'
        assert _parse_json_safe(text, {}) == {"key": "value"}

    def test_invalid_json_returns_default(self):
        assert _parse_json_safe("not json at all", "default") == "default"

    def test_malformed_json_returns_default(self):
        assert _parse_json_safe('{"key": broken}', []) == []


# ---------------------------------------------------------------------------
# _parse_json_field tests
# ---------------------------------------------------------------------------


class TestParseJsonField:
    """Edge cases for the JSON field parser."""

    def test_already_list(self):
        assert _parse_json_field(["a", "b"]) == ["a", "b"]

    def test_json_string(self):
        assert _parse_json_field('["a", "b"]') == ["a", "b"]

    def test_invalid_string(self):
        assert _parse_json_field("not json") == []

    def test_json_dict_returns_empty(self):
        """A dict is not a list, so should return empty."""
        assert _parse_json_field('{"key": "val"}') == []

    def test_none_returns_empty(self):
        assert _parse_json_field(None) == []

    def test_integer_returns_empty(self):
        assert _parse_json_field(42) == []


# ---------------------------------------------------------------------------
# build_profile — DB failure paths
# ---------------------------------------------------------------------------


class TestBuildProfileDBFailures:
    """Test build_profile when DB operations fail."""

    @pytest.mark.asyncio
    async def test_entity_mentions_db_exception(self, engine, mock_db):
        """DB exception in _fetch_entity_mentions returns empty profile."""
        case_id = str(uuid.uuid4())
        mock_db.fetch_all.side_effect = Exception("Connection refused")

        result = await engine.build_profile(case_id=case_id, respondent_name="Failing Person")

        # Should return empty profile, not raise
        assert result["respondent_name"] == "Failing Person"
        assert result["positions"] == []
        assert result["documents"] == []

    @pytest.mark.asyncio
    async def test_build_profile_no_db(self, engine_no_db):
        """Engine with no DB returns empty profile."""
        result = await engine_no_db.build_profile(case_id=str(uuid.uuid4()), respondent_name="No DB Person")

        assert result["respondent_name"] == "No DB Person"
        assert result["positions"] == []
        assert result["documents"] == []

    @pytest.mark.asyncio
    async def test_build_profile_deduplicates_documents(self, engine, mock_db):
        """Duplicate document_ids from multiple mentions are deduplicated."""
        case_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_db.fetch_all.side_effect = [
            # Same doc_id in both mentions
            [
                {"document_id": doc_id, "entity_text": "A", "context": "ctx1", "document_date": None},
                {"document_id": doc_id, "entity_text": "A", "context": "ctx2", "document_date": None},
            ],
            [],  # existing positions
        ]

        llm_resp = MagicMock()
        llm_resp.text = '{"background": "bg", "role": "r", "positions": []}'
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.build_profile(case_id=case_id, respondent_name="A")

        assert len(result["documents"]) == 1
        assert result["documents"][0] == doc_id


# ---------------------------------------------------------------------------
# build_profile — LLM failure paths
# ---------------------------------------------------------------------------


class TestBuildProfileLLMFailures:
    """Test build_profile LLM error handling and fallback."""

    @pytest.mark.asyncio
    async def test_llm_generate_exception_falls_back(self, engine, mock_db):
        """LLM exception triggers rule-based fallback."""
        case_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_db.fetch_all.side_effect = [
            [
                {
                    "document_id": doc_id,
                    "entity_text": "Smith",
                    "context": "Smith was the decision maker in the process.",
                    "document_date": datetime(2024, 5, 1, tzinfo=timezone.utc),
                },
            ],
            [],
        ]
        engine._llm_service.generate.side_effect = Exception("LLM timeout")

        result = await engine.build_profile(case_id=case_id, respondent_name="Smith")

        # Should still get a result via rule-based fallback
        assert result["respondent_name"] == "Smith"
        assert len(result["documents"]) == 1
        # Rule-based background uses context
        assert "decision maker" in result["background"]

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self, engine, mock_db):
        """LLM returning non-JSON text falls back to default."""
        case_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_db.fetch_all.side_effect = [
            [
                {
                    "document_id": doc_id,
                    "entity_text": "Jones",
                    "context": "Jones oversaw the disciplinary hearing.",
                    "document_date": None,
                },
            ],
            [],
        ]

        llm_resp = MagicMock()
        llm_resp.text = "I cannot produce valid JSON for this request."
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.build_profile(case_id=case_id, respondent_name="Jones")

        # Should still return a profile (with default background from fallback)
        assert result["respondent_name"] == "Jones"
        assert result["profile_id"] is not None

    @pytest.mark.asyncio
    async def test_llm_response_without_text_attribute(self, engine, mock_db):
        """LLM response that has no .text attribute uses str() fallback."""
        case_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_db.fetch_all.side_effect = [
            [
                {
                    "document_id": doc_id,
                    "entity_text": "X",
                    "context": "X context.",
                    "document_date": None,
                },
            ],
            [],
        ]

        # Response without .text attribute
        llm_resp = '{"background": "via str", "role": "Manager", "positions": []}'
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.build_profile(case_id=case_id, respondent_name="X")

        assert result["respondent_name"] == "X"
        assert result["background"] == "via str"


# ---------------------------------------------------------------------------
# track_positions — edge cases
# ---------------------------------------------------------------------------


class TestTrackPositionsEdgeCases:
    """Edge cases for track_positions."""

    @pytest.mark.asyncio
    async def test_track_positions_no_db(self, engine_no_db):
        """No DB returns empty list."""
        result = await engine_no_db.track_positions("any-id")
        assert result == []

    @pytest.mark.asyncio
    async def test_track_positions_db_exception(self, engine, mock_db):
        """DB exception returns empty list."""
        mock_db.fetch_all.side_effect = Exception("DB down")

        result = await engine.track_positions("any-id")
        assert result == []

    @pytest.mark.asyncio
    async def test_track_positions_with_none_dates(self, engine, mock_db):
        """Positions with None dates are handled gracefully."""
        mock_db.fetch_all.return_value = [
            {"document_id": "d1", "position": "Pos A", "date": None, "context": "ctx"},
            {
                "document_id": "d2",
                "position": "Pos B",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
        ]

        result = await engine.track_positions("pid")

        assert len(result) == 2
        # None-dated should sort before dated (datetime.min)
        assert result[0]["date"] is None
        assert result[1]["date"] == datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# detect_inconsistencies — edge cases
# ---------------------------------------------------------------------------


class TestDetectInconsistenciesEdgeCases:
    """Edge cases for detect_inconsistencies."""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, engine_no_db):
        """No DB returns empty list."""
        result = await engine_no_db.detect_inconsistencies("any-id")
        assert result == []

    @pytest.mark.asyncio
    async def test_db_exception_returns_empty(self, engine, mock_db):
        """DB exception returns empty list."""
        mock_db.fetch_all.side_effect = Exception("Query failed")
        result = await engine.detect_inconsistencies("any-id")
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_heuristic(self, engine, mock_db):
        """LLM exception triggers heuristic fallback for inconsistency detection."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "The claimant was not given a warning before dismissal",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ET3",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "The claimant was given a formal warning before dismissal",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "Witness",
            },
        ]
        engine._llm_service.generate.side_effect = Exception("LLM unavailable")

        result = await engine.detect_inconsistencies(profile_id)

        # Heuristic should still catch the "not given" vs "given" contradiction
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_llm_returns_non_list_json(self, engine, mock_db):
        """LLM returning a dict instead of list returns empty."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "Position A",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "Position B",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
        ]

        llm_resp = MagicMock()
        llm_resp.text = '{"error": "unexpected format"}'
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.detect_inconsistencies(profile_id)
        assert result == []

    @pytest.mark.asyncio
    async def test_event_emitted_on_inconsistency(self, engine, mock_db, mock_event_bus):
        """Event bus emit is called when inconsistencies are found."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "The claimant was not given a warning",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ET3",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "The claimant was given a formal warning",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "Witness",
            },
        ]

        llm_resp = MagicMock()
        llm_resp.text = '[{"position_a": "p1", "position_b": "p2", "inconsistency": "warning contradiction"}]'
        engine._llm_service.generate.return_value = llm_resp

        await engine.detect_inconsistencies(profile_id)

        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args
        assert call_args[0][0] == "respondent.inconsistency.detected"
        assert call_args[0][1]["profile_id"] == profile_id
        assert call_args[0][1]["count"] == 1

    @pytest.mark.asyncio
    async def test_event_emit_failure_does_not_raise(self, engine, mock_db, mock_event_bus):
        """Event bus failure during emit does not propagate exception."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "Not given notice",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ET3",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "Was given notice",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "Witness",
            },
        ]

        llm_resp = MagicMock()
        llm_resp.text = '[{"position_a": "p1", "position_b": "p2", "inconsistency": "notice contradiction"}]'
        engine._llm_service.generate.return_value = llm_resp
        mock_event_bus.emit.side_effect = Exception("Event bus broken")

        # Should not raise
        result = await engine.detect_inconsistencies(profile_id)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# Heuristic inconsistency detection edge cases
# ---------------------------------------------------------------------------


class TestHeuristicInconsistencyEdgeCases:
    """Edge cases for the keyword-based heuristic detector."""

    @pytest.mark.asyncio
    async def test_heuristic_no_overlap_no_inconsistency(self, engine_no_llm, mock_db):
        """Positions with no word overlap are not flagged."""
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "The sky is blue today",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "Oranges were not available at market",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
        ]

        result = await engine_no_llm.detect_inconsistencies("pid")
        assert result == []

    @pytest.mark.asyncio
    async def test_heuristic_never_always_contradiction(self, engine_no_llm, mock_db):
        """never/always negation pair is detected."""
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "The claimant never followed the procedure correctly",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "The claimant always followed the procedure correctly",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
        ]

        result = await engine_no_llm.detect_inconsistencies("pid")
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_heuristic_denied_confirmed_contradiction(self, engine_no_llm, mock_db):
        """denied/confirmed negation pair is detected."""
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "The respondent denied having any involvement in the process",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "The respondent confirmed having involvement in the process",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
        ]

        result = await engine_no_llm.detect_inconsistencies("pid")
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_heuristic_did_not_vs_did(self, engine_no_llm, mock_db):
        """did not/did negation pair is detected."""
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "position": "The manager did not attend the meeting about the claimant",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
            {
                "id": "p2",
                "document_id": "d2",
                "position": "The manager did attend the meeting about the claimant",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "context": "ctx",
            },
        ]

        result = await engine_no_llm.detect_inconsistencies("pid")
        assert len(result) >= 1

    def test_word_overlap_empty_strings(self):
        """Word overlap returns 0.0 for empty strings."""
        assert RespondentIntelEngine._word_overlap("", "") == 0.0
        assert RespondentIntelEngine._word_overlap("hello", "") == 0.0
        assert RespondentIntelEngine._word_overlap("", "hello") == 0.0

    def test_word_overlap_identical_strings(self):
        """Identical strings have overlap of 1.0."""
        assert RespondentIntelEngine._word_overlap("hello world", "hello world") == 1.0

    def test_word_overlap_partial(self):
        """Partial overlap returns value between 0 and 1."""
        overlap = RespondentIntelEngine._word_overlap("the cat sat", "the dog sat")
        assert 0.0 < overlap < 1.0


# ---------------------------------------------------------------------------
# assess_strengths_weaknesses — edge cases
# ---------------------------------------------------------------------------


class TestAssessEdgeCases:
    """Edge cases for assess_strengths_weaknesses."""

    @pytest.mark.asyncio
    async def test_assess_no_db(self, engine_no_db):
        """No DB returns empty assessment."""
        result = await engine_no_db.assess_strengths_weaknesses("any-id")
        assert result == {"strengths": [], "weaknesses": []}

    @pytest.mark.asyncio
    async def test_assess_db_fetch_profile_exception(self, engine, mock_db):
        """DB exception on profile fetch returns empty."""
        mock_db.fetch_one.side_effect = Exception("Connection lost")
        result = await engine.assess_strengths_weaknesses("any-id")
        assert result == {"strengths": [], "weaknesses": []}

    @pytest.mark.asyncio
    async def test_assess_db_fetch_positions_exception(self, engine, mock_db):
        """DB exception on positions fetch still returns assessment."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "Test",
            "role": "Role",
            "organization": "Org",
            "background": "",
            "strengths": "[]",
            "weaknesses": "[]",
        }
        mock_db.fetch_all.side_effect = Exception("Position query failed")

        llm_resp = MagicMock()
        llm_resp.text = '{"strengths": ["resilient"], "weaknesses": ["incomplete data"]}'
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.assess_strengths_weaknesses(profile_id)
        assert "strengths" in result
        assert "weaknesses" in result

    @pytest.mark.asyncio
    async def test_assess_llm_failure_falls_back(self, engine, mock_db):
        """LLM exception during assessment triggers rule-based fallback."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "Test",
            "role": "Role",
            "organization": "Org",
            "background": "",
            "strengths": '["existing strength"]',
            "weaknesses": "[]",
        }
        mock_db.fetch_all.return_value = []
        engine._llm_service.generate.side_effect = Exception("LLM down")

        result = await engine.assess_strengths_weaknesses(profile_id)
        assert "strengths" in result
        assert "weaknesses" in result
        # Rule-based should include existing strengths
        assert "existing strength" in result["strengths"]

    @pytest.mark.asyncio
    async def test_assess_rules_divergent_positions(self, engine_no_llm, mock_db):
        """Rule-based assessment flags weakness for many different positions."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "Test",
            "role": "Role",
            "organization": "Org",
            "background": "",
            "strengths": "[]",
            "weaknesses": "[]",
        }
        # All positions are unique themes
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "position": "Dismissed for redundancy",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "document_id": "d1",
                "context": "",
            },
            {
                "id": "p2",
                "position": "Performance was the issue",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "document_id": "d2",
                "context": "",
            },
            {
                "id": "p3",
                "position": "Role no longer existed",
                "date": datetime(2024, 3, 1, tzinfo=timezone.utc),
                "document_id": "d3",
                "context": "",
            },
        ]

        result = await engine_no_llm.assess_strengths_weaknesses(profile_id)
        # Divergent positions should trigger weakness
        assert any("different positions" in w.lower() for w in result["weaknesses"])

    @pytest.mark.asyncio
    async def test_assess_rules_consistent_positions(self, engine_no_llm, mock_db):
        """Rule-based assessment flags strength for consistent positions."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "Test",
            "role": "Role",
            "organization": "Org",
            "background": "",
            "strengths": "[]",
            "weaknesses": "[]",
        }
        # All positions are same theme
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "position": "redundancy",
                "date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "document_id": "d1",
                "context": "",
            },
            {
                "id": "p2",
                "position": "redundancy",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "document_id": "d2",
                "context": "",
            },
            {
                "id": "p3",
                "position": "redundancy",
                "date": datetime(2024, 3, 1, tzinfo=timezone.utc),
                "document_id": "d3",
                "context": "",
            },
        ]

        result = await engine_no_llm.assess_strengths_weaknesses(profile_id)
        assert any("consistent" in s.lower() for s in result["strengths"])

    @pytest.mark.asyncio
    async def test_assess_rules_no_positions_insufficient(self, engine_no_llm, mock_db):
        """Rule-based assessment with no data returns insufficient data weakness."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "Test",
            "role": "Role",
            "organization": "Org",
            "background": "",
            "strengths": "[]",
            "weaknesses": "[]",
        }
        mock_db.fetch_all.return_value = []

        result = await engine_no_llm.assess_strengths_weaknesses(profile_id)
        assert any("insufficient" in w.lower() for w in result["weaknesses"])


# ---------------------------------------------------------------------------
# Event handler edge cases
# ---------------------------------------------------------------------------


class TestEventHandlerEdgeCases:
    """Edge cases for handle_entities_extracted and handle_document_processed."""

    @pytest.mark.asyncio
    async def test_entities_extracted_no_case_id(self, engine):
        """Missing case_id in event data is a no-op."""
        await engine.handle_entities_extracted({"entities": [{"text": "Name"}]})
        # Should not raise, no emit expected
        engine._event_bus.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_entities_extracted_no_entities(self, engine):
        """Missing entities in event data is a no-op."""
        await engine.handle_entities_extracted({"case_id": "c1"})
        engine._event_bus.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_entities_extracted_empty_entities(self, engine):
        """Empty entities list is a no-op."""
        await engine.handle_entities_extracted({"case_id": "c1", "entities": []})
        engine._event_bus.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_entities_extracted_emits_for_each(self, engine, mock_event_bus):
        """Each entity triggers a profile update event."""
        await engine.handle_entities_extracted(
            {
                "case_id": "c1",
                "entities": [{"text": "Alice"}, {"text": "Bob"}],
            }
        )
        assert mock_event_bus.emit.call_count == 2

    @pytest.mark.asyncio
    async def test_entities_extracted_empty_text_skipped(self, engine, mock_event_bus):
        """Entity with empty text is skipped."""
        await engine.handle_entities_extracted(
            {
                "case_id": "c1",
                "entities": [{"text": ""}, {"text": "Valid"}],
            }
        )
        # Only "Valid" should emit
        assert mock_event_bus.emit.call_count == 1

    @pytest.mark.asyncio
    async def test_entities_extracted_event_bus_failure(self, engine, mock_event_bus):
        """Event bus failure during entity processing does not raise."""
        mock_event_bus.emit.side_effect = Exception("Bus error")

        # Should not raise
        await engine.handle_entities_extracted(
            {
                "case_id": "c1",
                "entities": [{"text": "Someone"}],
            }
        )

    @pytest.mark.asyncio
    async def test_entities_extracted_no_event_bus(self, engine_bare):
        """No event bus is handled gracefully."""
        # Should not raise
        await engine_bare.handle_entities_extracted(
            {
                "case_id": "c1",
                "entities": [{"text": "Someone"}],
            }
        )

    @pytest.mark.asyncio
    async def test_document_processed_no_document_id(self, engine):
        """Missing document_id is handled gracefully."""
        # Should not raise
        await engine.handle_document_processed({})

    @pytest.mark.asyncio
    async def test_document_processed_with_document_id(self, engine):
        """Valid document_id is handled without error."""
        await engine.handle_document_processed({"document_id": "doc-123"})
        # Currently a no-op beyond logging, should not raise


# ---------------------------------------------------------------------------
# LLM prompt construction tests
# ---------------------------------------------------------------------------


class TestLLMPrompts:
    """Verify LLM prompt construction edge cases."""

    def test_build_profile_prompt_no_mentions(self):
        from arkham_shard_respondent_intel.llm import build_profile_prompt

        prompt = build_profile_prompt("Nobody", [])
        assert "Nobody" in prompt
        assert "No mentions found" in prompt

    def test_build_profile_prompt_with_mentions(self):
        from arkham_shard_respondent_intel.llm import build_profile_prompt

        mentions = [
            {"document_id": "d1", "context": "Was the manager", "document_date": "2024-01-01"},
        ]
        prompt = build_profile_prompt("Smith", mentions)
        assert "Smith" in prompt
        assert "Was the manager" in prompt
        assert "d1" in prompt

    def test_detect_inconsistencies_prompt_structure(self):
        from arkham_shard_respondent_intel.llm import detect_inconsistencies_prompt

        positions = [
            {"id": "p1", "position": "Pos A", "date": "2024-01-01", "document_id": "d1", "context": "ctx"},
            {"id": "p2", "position": "Pos B", "date": "2024-02-01", "document_id": "d2", "context": "ctx"},
        ]
        prompt = detect_inconsistencies_prompt(positions)
        assert "Pos A" in prompt
        assert "Pos B" in prompt
        assert "p1" in prompt
        assert "p2" in prompt

    def test_assess_prompt_with_empty_positions(self):
        from arkham_shard_respondent_intel.llm import assess_strengths_weaknesses_prompt

        profile = {"name": "Test", "role": "Role", "organization": "Org", "background": "bg"}
        prompt = assess_strengths_weaknesses_prompt(profile, [])
        assert "Test" in prompt
        assert "No positions tracked" in prompt

    def test_assess_prompt_with_positions(self):
        from arkham_shard_respondent_intel.llm import assess_strengths_weaknesses_prompt

        profile = {"name": "Test", "role": "Manager", "organization": "Corp", "background": "bg"}
        positions = [{"position": "Claim X", "date": "2024-01-01", "context": "statement"}]
        prompt = assess_strengths_weaknesses_prompt(profile, positions)
        assert "Claim X" in prompt
        assert "Manager" in prompt


# ---------------------------------------------------------------------------
# API domain endpoint 503 tests
# ---------------------------------------------------------------------------


class TestAPIDomainEndpoints503:
    """Test API domain endpoints return 503 when engine is None."""

    @pytest.fixture(autouse=True)
    def reset_api_globals(self):
        import arkham_shard_respondent_intel.api as api_mod

        api_mod._db = None
        api_mod._event_bus = None
        api_mod._llm_service = None
        api_mod._shard = None
        api_mod._engine = None
        yield

    @pytest.mark.asyncio
    async def test_build_profile_no_engine_503(self):
        from arkham_shard_respondent_intel.api import BuildProfileRequest, build_profile
        from fastapi import HTTPException

        req = BuildProfileRequest(case_id=str(uuid.uuid4()), respondent_name="Test")
        with pytest.raises(HTTPException) as exc:
            await build_profile(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_positions_no_engine_503(self):
        from arkham_shard_respondent_intel.api import get_positions
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_positions("any-id")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_detect_inconsistencies_no_engine_503(self):
        from arkham_shard_respondent_intel.api import detect_inconsistencies
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await detect_inconsistencies("any-id")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_assess_no_engine_503(self):
        from arkham_shard_respondent_intel.api import assess_strengths_weaknesses
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await assess_strengths_weaknesses("any-id")
        assert exc.value.status_code == 503
