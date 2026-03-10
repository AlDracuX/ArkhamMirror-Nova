"""
Comparator Shard - LLM Integration Tests

Tests for ComparatorLLM: identify comparators and assess treatment.
LLM service is mocked.
"""

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_comparator.llm import ComparatorLLM, ComparatorSuggestion, TreatmentAssessment

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeLLMResponse:
    text: str


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def comp_llm(mock_llm):
    return ComparatorLLM(llm_service=mock_llm)


@pytest.fixture
def comp_llm_no_service():
    return ComparatorLLM(llm_service=None)


# ---------------------------------------------------------------------------
# Availability Tests
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_available_with_service(self, comp_llm):
        assert comp_llm.available is True

    def test_unavailable_without_service(self, comp_llm_no_service):
        assert comp_llm_no_service.available is False


# ---------------------------------------------------------------------------
# Identify Comparators Tests
# ---------------------------------------------------------------------------


class TestIdentifyComparators:
    @pytest.mark.asyncio
    async def test_identify_returns_suggestions(self, comp_llm, mock_llm):
        """LLM returns valid comparator suggestions."""
        response_data = [
            {
                "name": "John Doe",
                "role": "Senior Engineer",
                "reasoning": "Same team, same grade, different race",
                "comparator_type": "actual",
            },
            {
                "name": "Hypothetical comparator",
                "role": "Senior Engineer",
                "reasoning": "How a white employee would have been treated",
                "comparator_type": "hypothetical",
            },
        ]
        mock_llm.generate = AsyncMock(return_value=FakeLLMResponse(text=json.dumps(response_data)))

        results = await comp_llm.identify_comparators(
            context="Claimant was denied promotion despite strong performance reviews",
            characteristic="race",
            claimant_role="Senior Engineer",
        )

        assert len(results) == 2
        assert results[0].name == "John Doe"
        assert results[0].comparator_type == "actual"
        assert results[1].comparator_type == "hypothetical"

    @pytest.mark.asyncio
    async def test_identify_no_llm_returns_empty(self, comp_llm_no_service):
        """Without LLM service, returns empty list."""
        results = await comp_llm_no_service.identify_comparators(
            context="test",
            characteristic="race",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_identify_llm_error_returns_empty(self, comp_llm, mock_llm):
        """LLM error returns empty list gracefully."""
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM timeout"))

        results = await comp_llm.identify_comparators(
            context="test",
            characteristic="race",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_identify_malformed_json(self, comp_llm, mock_llm):
        """Malformed JSON from LLM returns empty list."""
        mock_llm.generate = AsyncMock(return_value=FakeLLMResponse(text="not json at all"))

        results = await comp_llm.identify_comparators(
            context="test",
            characteristic="race",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_identify_json_embedded_in_text(self, comp_llm, mock_llm):
        """JSON array embedded in surrounding text is extracted."""
        response_data = [{"name": "Jane", "role": "Manager", "reasoning": "Same dept", "comparator_type": "actual"}]
        text = f"Here are the comparators:\n{json.dumps(response_data)}\n\nHope this helps!"
        mock_llm.generate = AsyncMock(return_value=FakeLLMResponse(text=text))

        results = await comp_llm.identify_comparators(
            context="test",
            characteristic="sex",
        )
        assert len(results) == 1
        assert results[0].name == "Jane"


# ---------------------------------------------------------------------------
# Assess Treatment Tests
# ---------------------------------------------------------------------------


class TestAssessTreatment:
    @pytest.mark.asyncio
    async def test_assess_less_favourable(self, comp_llm, mock_llm):
        """LLM identifies less favourable treatment."""
        response_data = {
            "is_less_favourable": True,
            "reasoning": "Claimant was disciplined while comparator was not for same conduct",
            "confidence": 0.85,
            "relevant_factors": ["same conduct", "different outcome"],
            "legal_references": ["Shamoon v Chief Constable [2003]"],
        }
        mock_llm.generate = AsyncMock(return_value=FakeLLMResponse(text=json.dumps(response_data)))

        result = await comp_llm.assess_treatment(
            claimant_treatment="Formal written warning",
            comparator_treatment="Verbal discussion only",
            context="Both involved in same policy violation",
            characteristic="race",
        )

        assert result.is_less_favourable is True
        assert result.confidence == 0.85
        assert len(result.relevant_factors) == 2
        assert len(result.legal_references) == 1

    @pytest.mark.asyncio
    async def test_assess_not_less_favourable(self, comp_llm, mock_llm):
        """LLM finds treatment is not less favourable."""
        response_data = {
            "is_less_favourable": False,
            "reasoning": "Both received same disciplinary outcome",
            "confidence": 0.9,
            "relevant_factors": [],
            "legal_references": [],
        }
        mock_llm.generate = AsyncMock(return_value=FakeLLMResponse(text=json.dumps(response_data)))

        result = await comp_llm.assess_treatment(
            claimant_treatment="Verbal warning",
            comparator_treatment="Verbal warning",
        )

        assert result.is_less_favourable is False
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_assess_no_llm_returns_default(self, comp_llm_no_service):
        """Without LLM, returns default neutral assessment."""
        result = await comp_llm_no_service.assess_treatment(
            claimant_treatment="test",
            comparator_treatment="test",
        )

        assert result.is_less_favourable is False
        assert result.confidence == 0.0
        assert result.reasoning == ""

    @pytest.mark.asyncio
    async def test_assess_llm_error_returns_default(self, comp_llm, mock_llm):
        """LLM error returns default assessment."""
        mock_llm.generate = AsyncMock(side_effect=Exception("timeout"))

        result = await comp_llm.assess_treatment(
            claimant_treatment="test",
            comparator_treatment="test",
        )

        assert result.is_less_favourable is False
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# JSON Parsing Tests
# ---------------------------------------------------------------------------


class TestJSONParsing:
    """Test the static JSON parsing helpers."""

    def test_parse_array_direct(self):
        assert ComparatorLLM._parse_json_array('[{"a": 1}]') == [{"a": 1}]

    def test_parse_array_embedded(self):
        result = ComparatorLLM._parse_json_array('Some text [{"a": 1}] more text')
        assert result == [{"a": 1}]

    def test_parse_array_empty_string(self):
        assert ComparatorLLM._parse_json_array("") == []

    def test_parse_array_invalid(self):
        assert ComparatorLLM._parse_json_array("not json") == []

    def test_parse_object_direct(self):
        assert ComparatorLLM._parse_json_object('{"a": 1}') == {"a": 1}

    def test_parse_object_embedded(self):
        result = ComparatorLLM._parse_json_object('Here: {"a": 1} end')
        assert result == {"a": 1}

    def test_parse_object_empty(self):
        assert ComparatorLLM._parse_json_object("") == {}

    def test_parse_object_invalid(self):
        assert ComparatorLLM._parse_json_object("not json") == {}
