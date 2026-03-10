"""
Redline Shard - Engine Tests

Tests for RedlineEngine: diff computation, change classification,
document comparison, and semantic diff.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_redline.engine import RedlineEngine

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
def engine(mock_db, mock_events):
    """Engine with DB and events but no LLM."""
    return RedlineEngine(db=mock_db, event_bus=mock_events)


@pytest.fixture
def engine_with_llm(mock_db, mock_events, mock_llm):
    """Engine with all services including LLM."""
    return RedlineEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)


# ---------------------------------------------------------------------------
# compute_diff Tests
# ---------------------------------------------------------------------------


class TestComputeDiffAdditions:
    """test_compute_diff_additions -- new lines detected."""

    def test_added_lines_detected(self, engine):
        text_a = "line one\nline two"
        text_b = "line one\nline two\nline three"

        diffs = engine.compute_diff(text_a, text_b)

        add_diffs = [d for d in diffs if d["type"] == "add"]
        assert len(add_diffs) >= 1
        assert any("line three" in d["content"] for d in add_diffs)

    def test_multiple_additions(self, engine):
        text_a = "first"
        text_b = "first\nsecond\nthird"

        diffs = engine.compute_diff(text_a, text_b)

        add_diffs = [d for d in diffs if d["type"] == "add"]
        assert len(add_diffs) >= 2

    def test_addition_has_line_number(self, engine):
        text_a = "line one"
        text_b = "line one\nline two"

        diffs = engine.compute_diff(text_a, text_b)

        add_diffs = [d for d in diffs if d["type"] == "add"]
        assert len(add_diffs) >= 1
        assert "line_number" in add_diffs[0]
        assert isinstance(add_diffs[0]["line_number"], int)


class TestComputeDiffDeletions:
    """test_compute_diff_deletions -- removed lines detected."""

    def test_deleted_lines_detected(self, engine):
        text_a = "line one\nline two\nline three"
        text_b = "line one\nline three"

        diffs = engine.compute_diff(text_a, text_b)

        del_diffs = [d for d in diffs if d["type"] == "delete"]
        assert len(del_diffs) >= 1
        assert any("line two" in d["content"] for d in del_diffs)

    def test_all_lines_deleted(self, engine):
        text_a = "alpha\nbeta\ngamma"
        text_b = ""

        diffs = engine.compute_diff(text_a, text_b)

        del_diffs = [d for d in diffs if d["type"] == "delete"]
        assert len(del_diffs) >= 3


class TestComputeDiffModifications:
    """test_compute_diff_modifications -- changed lines detected."""

    def test_modified_line_detected(self, engine):
        text_a = "The meeting was on 5 January 2024."
        text_b = "The meeting was on 12 January 2024."

        diffs = engine.compute_diff(text_a, text_b)

        # A modification shows as a delete + add pair; engine should
        # consolidate adjacent delete/add into a 'modify' entry.
        assert len(diffs) >= 1
        types = {d["type"] for d in diffs}
        assert "modify" in types or ("delete" in types and "add" in types)

    def test_modification_preserves_content(self, engine):
        text_a = "salary: 50000"
        text_b = "salary: 65000"

        diffs = engine.compute_diff(text_a, text_b)

        assert len(diffs) >= 1
        # At least one diff should mention the changed content
        all_content = " ".join(d["content"] for d in diffs)
        assert "50000" in all_content or "65000" in all_content


# ---------------------------------------------------------------------------
# classify_changes Tests
# ---------------------------------------------------------------------------


class TestClassifyChangesLegalSignificance:
    """test_classify_changes_legal_significance -- dates/amounts score high."""

    def test_date_change_high_significance(self, engine):
        diffs = [
            {"type": "modify", "line_number": 1, "content": "Date changed from 5 January to 12 January"},
        ]

        classified = engine.classify_changes(diffs)

        assert len(classified) == 1
        assert classified[0]["significance"] >= 0.6
        assert classified[0]["category"] == "date"

    def test_monetary_amount_high_significance(self, engine):
        diffs = [
            {"type": "modify", "line_number": 3, "content": "Compensation: GBP 50,000 changed to GBP 65,000"},
        ]

        classified = engine.classify_changes(diffs)

        assert len(classified) == 1
        assert classified[0]["significance"] >= 0.7
        assert classified[0]["category"] == "amount"

    def test_name_change_high_significance(self, engine):
        diffs = [
            {"type": "modify", "line_number": 5, "content": "Respondent: Smith Ltd replaced with Jones Ltd"},
        ]

        classified = engine.classify_changes(diffs)

        assert len(classified) == 1
        assert classified[0]["significance"] >= 0.6

    def test_obligation_change_high_significance(self, engine):
        diffs = [
            {"type": "add", "line_number": 10, "content": "The claimant shall provide disclosure by 1 March 2026"},
        ]

        classified = engine.classify_changes(diffs)

        assert len(classified) == 1
        assert classified[0]["significance"] >= 0.6


class TestClassifyChangesFormatting:
    """test_classify_changes_formatting -- whitespace changes score low."""

    def test_whitespace_only_change_low_significance(self, engine):
        diffs = [
            {"type": "modify", "line_number": 1, "content": "   extra spaces added   "},
        ]

        classified = engine.classify_changes(diffs)

        assert len(classified) == 1
        assert classified[0]["significance"] <= 0.2
        assert classified[0]["category"] == "formatting"

    def test_empty_line_change_low_significance(self, engine):
        diffs = [
            {"type": "add", "line_number": 5, "content": ""},
        ]

        classified = engine.classify_changes(diffs)

        assert len(classified) == 1
        assert classified[0]["significance"] <= 0.1


# ---------------------------------------------------------------------------
# compare_documents Tests
# ---------------------------------------------------------------------------


class TestCompareDocumentsStoresResult:
    """test_compare_documents_stores_result -- DB persistence verified."""

    @pytest.mark.asyncio
    async def test_compare_stores_in_db(self, engine, mock_db):
        # Set up DB to return document texts
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "The hearing is on 5 January.\nSalary is 50000."},
            {"id": "doc-b", "content": "The hearing is on 12 January.\nSalary is 50000."},
        ]

        result = await engine.compare_documents("doc-a", "doc-b")

        assert "comparison_id" in result
        assert isinstance(result["total_changes"], int)
        assert result["total_changes"] >= 1
        # DB execute should have been called to persist
        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_compare_returns_counts(self, engine, mock_db):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "line one\nline two"},
            {"id": "doc-b", "content": "line one\nline two\nline three"},
        ]

        result = await engine.compare_documents("doc-a", "doc-b")

        assert "additions" in result
        assert "deletions" in result
        assert "modifications" in result
        assert result["additions"] >= 1

    @pytest.mark.asyncio
    async def test_compare_emits_event(self, engine, mock_db, mock_events):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "old text"},
            {"id": "doc-b", "content": "new text"},
        ]

        await engine.compare_documents("doc-a", "doc-b")

        mock_events.emit.assert_called()
        event_names = [c.args[0] for c in mock_events.emit.call_args_list]
        assert "redline.comparison.completed" in event_names

    @pytest.mark.asyncio
    async def test_compare_significant_change_emits_event(self, engine, mock_db, mock_events):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "Compensation: GBP 50,000"},
            {"id": "doc-b", "content": "Compensation: GBP 100,000"},
        ]

        await engine.compare_documents("doc-a", "doc-b")

        event_names = [c.args[0] for c in mock_events.emit.call_args_list]
        assert "redline.significant_change.detected" in event_names


# ---------------------------------------------------------------------------
# Identical Documents Tests
# ---------------------------------------------------------------------------


class TestIdenticalDocumentsNoChanges:
    """test_identical_documents_no_changes -- no diffs for same text."""

    @pytest.mark.asyncio
    async def test_identical_texts_zero_diffs(self, engine, mock_db):
        same_text = "This is exactly the same.\nLine two is also the same."
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": same_text},
            {"id": "doc-b", "content": same_text},
        ]

        result = await engine.compare_documents("doc-a", "doc-b")

        assert result["total_changes"] == 0
        assert result["additions"] == 0
        assert result["deletions"] == 0
        assert result["modifications"] == 0

    def test_identical_texts_compute_diff_empty(self, engine):
        text = "Identical line one.\nIdentical line two."
        diffs = engine.compute_diff(text, text)
        assert diffs == []


# ---------------------------------------------------------------------------
# Semantic Diff Tests
# ---------------------------------------------------------------------------


class TestSemanticDiff:
    """Test LLM-powered semantic diff."""

    @pytest.mark.asyncio
    async def test_semantic_diff_calls_llm(self, engine_with_llm, mock_db, mock_llm):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "The notice period is 4 weeks."},
            {"id": "doc-b", "content": "The notice period is 12 weeks."},
        ]

        # LLM returns semantic analysis
        from dataclasses import dataclass

        @dataclass
        class FakeLLMResponse:
            text: str

        mock_llm.generate.return_value = FakeLLMResponse(
            text=json.dumps(
                [
                    {
                        "change_type": "substantive",
                        "description": "Notice period increased from 4 to 12 weeks",
                        "significance": 0.9,
                    }
                ]
            )
        )

        result = await engine_with_llm.semantic_diff("doc-a", "doc-b")

        assert len(result) >= 1
        assert result[0]["change_type"] == "substantive"
        mock_llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_semantic_diff_without_llm_falls_back(self, engine, mock_db):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "Original text."},
            {"id": "doc-b", "content": "Changed text."},
        ]

        result = await engine.semantic_diff("doc-a", "doc-b")

        # Should return basic diff results without LLM
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_semantic_diff_handles_llm_error(self, engine_with_llm, mock_db, mock_llm):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "Text A."},
            {"id": "doc-b", "content": "Text B."},
        ]
        mock_llm.generate.side_effect = Exception("LLM unavailable")

        result = await engine_with_llm.semantic_diff("doc-a", "doc-b")

        # Should gracefully fall back
        assert isinstance(result, list)
