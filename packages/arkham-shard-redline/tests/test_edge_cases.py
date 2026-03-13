"""
Redline Shard - Edge Case Tests

Tests for boundary conditions, error handling, and uncommon inputs
across engine, shard, LLM parsing, and API layers.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_redline.engine import RedlineEngine
from arkham_shard_redline.llm import (
    SemanticChange,
    build_semantic_diff_prompt,
    parse_semantic_diff_response,
)
from arkham_shard_redline.models import Comparison, ComparisonStatus, DocumentChange
from arkham_shard_redline.shard import RedlineShard, _parse_json_field

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
def mock_frame(mock_events, mock_db):
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


@pytest.fixture
def engine():
    return RedlineEngine()


@pytest.fixture
def engine_with_db(mock_db, mock_events):
    return RedlineEngine(db=mock_db, event_bus=mock_events)


async def _make_shard(frame):
    shard = RedlineShard()
    await shard.initialize(frame)
    return shard


# ---------------------------------------------------------------------------
# _parse_json_field edge cases
# ---------------------------------------------------------------------------


class TestParseJsonField:
    """Edge cases for the JSON field parser."""

    def test_none_returns_empty_list(self):
        assert _parse_json_field(None) == []

    def test_none_with_custom_default(self):
        assert _parse_json_field(None, {"fallback": True}) == {"fallback": True}

    def test_already_parsed_list(self):
        data = [1, 2, 3]
        assert _parse_json_field(data) is data

    def test_already_parsed_dict(self):
        data = {"key": "value"}
        assert _parse_json_field(data) is data

    def test_valid_json_string(self):
        assert _parse_json_field("[1, 2]") == [1, 2]

    def test_invalid_json_string_returns_default(self):
        assert _parse_json_field("not json") == []

    def test_invalid_json_string_with_custom_default(self):
        assert _parse_json_field("bad", []) == []

    def test_numeric_value_returns_default(self):
        assert _parse_json_field(42) == []

    def test_numeric_value_with_custom_default(self):
        assert _parse_json_field(42, {}) == {}

    def test_empty_string_returns_default(self):
        assert _parse_json_field("") == []


# ---------------------------------------------------------------------------
# compute_diff edge cases
# ---------------------------------------------------------------------------


class TestComputeDiffEdgeCases:
    """Boundary conditions for diff computation."""

    def test_both_empty_strings(self, engine):
        diffs = engine.compute_diff("", "")
        assert diffs == []

    def test_empty_to_content(self, engine):
        diffs = engine.compute_diff("", "hello\nworld")
        add_diffs = [d for d in diffs if d["type"] == "add"]
        assert len(add_diffs) == 2

    def test_content_to_empty(self, engine):
        diffs = engine.compute_diff("hello\nworld", "")
        del_diffs = [d for d in diffs if d["type"] == "delete"]
        assert len(del_diffs) == 2

    def test_single_character_change(self, engine):
        diffs = engine.compute_diff("a", "b")
        assert len(diffs) >= 1

    def test_unicode_content(self, engine):
        text_a = "The amount is \u00a350,000"
        text_b = "The amount is \u00a375,000"
        diffs = engine.compute_diff(text_a, text_b)
        assert len(diffs) >= 1

    def test_multiline_addition_in_middle(self, engine):
        text_a = "line 1\nline 3"
        text_b = "line 1\nline 2\nline 3"
        diffs = engine.compute_diff(text_a, text_b)
        add_diffs = [d for d in diffs if d["type"] == "add"]
        assert len(add_diffs) >= 1
        assert any("line 2" in d["content"] for d in add_diffs)

    def test_reordered_lines(self, engine):
        text_a = "alpha\nbeta\ngamma"
        text_b = "gamma\nbeta\nalpha"
        diffs = engine.compute_diff(text_a, text_b)
        assert len(diffs) >= 1

    def test_trailing_newline_difference(self, engine):
        text_a = "line one\nline two"
        text_b = "line one\nline two\n"
        diffs = engine.compute_diff(text_a, text_b)
        # The trailing newline creates an empty line addition
        assert isinstance(diffs, list)

    def test_whitespace_only_lines(self, engine):
        text_a = "text"
        text_b = "text\n   \n  "
        diffs = engine.compute_diff(text_a, text_b)
        assert len(diffs) >= 1


# ---------------------------------------------------------------------------
# classify_changes edge cases
# ---------------------------------------------------------------------------


class TestClassifyEdgeCases:
    """Edge cases for change classification."""

    def test_empty_diffs_list(self, engine):
        classified = engine.classify_changes([])
        assert classified == []

    def test_none_content_field(self, engine):
        diffs = [{"type": "add", "line_number": 1}]
        classified = engine.classify_changes(diffs)
        assert len(classified) == 1
        assert classified[0]["category"] == "formatting"
        assert classified[0]["significance"] <= 0.1

    def test_very_short_content(self, engine):
        diffs = [{"type": "add", "line_number": 1, "content": "ab"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "formatting"

    def test_pound_symbol_amount(self, engine):
        diffs = [{"type": "modify", "line_number": 1, "content": "\u00a3100,000.00 awarded"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "amount"
        assert classified[0]["significance"] >= 0.7

    def test_iso_date_format(self, engine):
        diffs = [{"type": "modify", "line_number": 1, "content": "Changed to 2026-03-13"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "date"

    def test_slash_date_format(self, engine):
        diffs = [{"type": "modify", "line_number": 1, "content": "Date 13/03/2026 is final"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "date"

    def test_judge_reference(self, engine):
        diffs = [{"type": "modify", "line_number": 1, "content": "Judge Smith presiding"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "entity"

    def test_obligation_keyword_unless(self, engine):
        diffs = [{"type": "add", "line_number": 1, "content": "The claim is struck out unless compliance"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "obligation"

    def test_witness_statement_reference(self, engine):
        diffs = [{"type": "add", "line_number": 1, "content": "witness statement to be filed by Monday"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "obligation"

    def test_multiple_patterns_highest_wins(self, engine):
        """Amount pattern should win over date when both present."""
        diffs = [{"type": "modify", "line_number": 1, "content": "GBP 50,000 by 5 January 2026"}]
        classified = engine.classify_changes(diffs)
        # Amount has highest significance (0.85) so should be picked
        assert classified[0]["category"] == "amount"

    def test_plain_text_default_category(self, engine):
        diffs = [{"type": "add", "line_number": 1, "content": "This is a general paragraph of text"}]
        classified = engine.classify_changes(diffs)
        assert classified[0]["category"] == "text"
        assert classified[0]["significance"] == 0.40


# ---------------------------------------------------------------------------
# compare_documents edge cases
# ---------------------------------------------------------------------------


class TestCompareDocumentsEdgeCases:
    """Edge cases for full document comparison."""

    @pytest.mark.asyncio
    async def test_compare_no_db_returns_empty_counts(self):
        engine = RedlineEngine()
        result = await engine.compare_documents("doc-a", "doc-b")
        assert result["total_changes"] == 0
        assert result["additions"] == 0
        assert result["deletions"] == 0

    @pytest.mark.asyncio
    async def test_compare_missing_doc_uses_empty_string(self, engine_with_db, mock_db):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": "some text"},
            None,  # doc-b not found
        ]
        result = await engine_with_db.compare_documents("doc-a", "doc-b")
        # Should treat missing doc as empty and show deletions
        assert result["total_changes"] >= 1

    @pytest.mark.asyncio
    async def test_compare_both_empty_docs(self, engine_with_db, mock_db):
        mock_db.fetch_one.side_effect = [
            {"id": "doc-a", "content": ""},
            {"id": "doc-b", "content": ""},
        ]
        result = await engine_with_db.compare_documents("doc-a", "doc-b")
        assert result["total_changes"] == 0


# ---------------------------------------------------------------------------
# semantic_diff edge cases
# ---------------------------------------------------------------------------


class TestSemanticDiffEdgeCases:
    """Edge cases for semantic diff."""

    @pytest.mark.asyncio
    async def test_fallback_with_no_changes(self):
        engine = RedlineEngine()
        result = await engine.semantic_diff("doc-a", "doc-b")
        # No DB, empty texts, should return empty
        assert result == []

    @pytest.mark.asyncio
    async def test_fallback_classifies_formatting(self):
        """Fallback semantic diff labels low-significance as formatting."""
        engine = RedlineEngine()
        # Monkey-patch to provide texts directly
        engine._fetch_document_text = AsyncMock(side_effect=["text", "text\n   "])
        result = await engine.semantic_diff("a", "b")
        if result:
            assert result[0]["change_type"] in ("formatting", "clarification")

    @pytest.mark.asyncio
    async def test_llm_returns_non_list_json(self, mock_db):
        """LLM returns a single object instead of array."""
        from dataclasses import dataclass

        @dataclass
        class FakeLLMResponse:
            text: str

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=FakeLLMResponse(
                text=json.dumps({"change_type": "substantive", "description": "single item", "significance": 0.8})
            )
        )

        engine = RedlineEngine(db=mock_db, llm_service=mock_llm)
        mock_db.fetch_one.side_effect = [
            {"id": "a", "content": "old"},
            {"id": "b", "content": "new"},
        ]
        result = await engine.semantic_diff("a", "b")
        assert len(result) == 1
        assert result[0]["change_type"] == "substantive"

    @pytest.mark.asyncio
    async def test_llm_returns_empty_string(self, mock_db):
        """LLM returns empty response."""
        from dataclasses import dataclass

        @dataclass
        class FakeLLMResponse:
            text: str

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=FakeLLMResponse(text=""))

        engine = RedlineEngine(db=mock_db, llm_service=mock_llm)
        mock_db.fetch_one.side_effect = [
            {"id": "a", "content": "old"},
            {"id": "b", "content": "new"},
        ]
        result = await engine.semantic_diff("a", "b")
        # Should fallback gracefully
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# LLM module edge cases
# ---------------------------------------------------------------------------


class TestBuildSemanticDiffPrompt:
    """Edge cases for prompt building."""

    def test_truncates_long_text(self):
        long_text = "x" * 10000
        prompt = build_semantic_diff_prompt(long_text, "short")
        assert "[truncated]" in prompt

    def test_both_texts_truncated(self):
        long_a = "a" * 10000
        long_b = "b" * 10000
        prompt = build_semantic_diff_prompt(long_a, long_b)
        assert prompt.count("[truncated]") == 2

    def test_short_texts_not_truncated(self):
        prompt = build_semantic_diff_prompt("hello", "world")
        assert "[truncated]" not in prompt

    def test_prompt_contains_both_documents(self):
        prompt = build_semantic_diff_prompt("original text", "revised text")
        assert "original text" in prompt
        assert "revised text" in prompt


class TestParseSemanticDiffResponse:
    """Edge cases for LLM response parsing."""

    def test_empty_response(self):
        assert parse_semantic_diff_response("") == []

    def test_none_response(self):
        assert parse_semantic_diff_response(None) == []

    def test_valid_json_array(self):
        data = json.dumps([{"change_type": "substantive", "description": "test", "significance": 0.9}])
        result = parse_semantic_diff_response(data)
        assert len(result) == 1
        assert result[0]["change_type"] == "substantive"
        assert result[0]["significance"] == 0.9

    def test_json_wrapped_in_code_block(self):
        data = '```json\n[{"change_type": "formatting", "description": "indent", "significance": 0.1}]\n```'
        result = parse_semantic_diff_response(data)
        assert len(result) == 1
        assert result[0]["change_type"] == "formatting"

    def test_invalid_change_type_normalized(self):
        data = json.dumps([{"change_type": "unknown_type", "description": "x", "significance": 0.5}])
        result = parse_semantic_diff_response(data)
        assert result[0]["change_type"] == "substantive"  # default fallback

    def test_significance_clamped_to_range(self):
        data = json.dumps([{"change_type": "substantive", "description": "x", "significance": 5.0}])
        result = parse_semantic_diff_response(data)
        assert result[0]["significance"] == 1.0

    def test_negative_significance_clamped(self):
        data = json.dumps([{"change_type": "substantive", "description": "x", "significance": -1.0}])
        result = parse_semantic_diff_response(data)
        assert result[0]["significance"] == 0.0

    def test_non_numeric_significance_defaults(self):
        data = json.dumps([{"change_type": "substantive", "description": "x", "significance": "high"}])
        result = parse_semantic_diff_response(data)
        assert result[0]["significance"] == 0.5

    def test_invalid_json_returns_empty(self):
        assert parse_semantic_diff_response("not valid json at all") == []

    def test_single_object_wrapped_in_array(self):
        data = json.dumps({"change_type": "clarification", "description": "minor", "significance": 0.3})
        result = parse_semantic_diff_response(data)
        assert len(result) == 1

    def test_missing_fields_get_defaults(self):
        data = json.dumps([{}])
        result = parse_semantic_diff_response(data)
        assert result[0]["change_type"] == "substantive"
        assert result[0]["description"] == ""
        assert result[0]["significance"] == 0.5


class TestSemanticChangeDataclass:
    """Test the SemanticChange dataclass."""

    def test_defaults(self):
        sc = SemanticChange()
        assert sc.change_type == "substantive"
        assert sc.description == ""
        assert sc.significance == 0.5

    def test_custom_values(self):
        sc = SemanticChange(change_type="formatting", description="indent change", significance=0.1)
        assert sc.change_type == "formatting"
        assert sc.description == "indent change"
        assert sc.significance == 0.1


# ---------------------------------------------------------------------------
# Shard CRUD edge cases
# ---------------------------------------------------------------------------


class TestShardCrudEdgeCases:
    """Edge cases for shard CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_comparison_without_db(self, mock_frame, mock_events):
        """Create comparison when DB is None."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(
            side_effect=lambda name: {
                "events": mock_events,
                "llm": None,
                "vectors": None,
            }.get(name)
        )
        shard = RedlineShard()
        await shard.initialize(frame)

        result = await shard.create_comparison(doc_a_id="a", doc_b_id="b")
        assert result["status"] == "pending"
        assert "id" in result

    @pytest.mark.asyncio
    async def test_get_comparison_without_db(self, mock_frame):
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)
        shard = RedlineShard()
        await shard.initialize(frame)

        result = await shard.get_comparison("any-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_comparisons_without_db(self, mock_frame):
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)
        shard = RedlineShard()
        await shard.initialize(frame)

        result = await shard.list_comparisons()
        assert result == []

    @pytest.mark.asyncio
    async def test_update_comparison_without_db(self, mock_frame):
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)
        shard = RedlineShard()
        await shard.initialize(frame)

        result = await shard.update_comparison("any-id", {"title": "new"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_comparison_without_db(self, mock_frame):
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)
        shard = RedlineShard()
        await shard.initialize(frame)

        result = await shard.delete_comparison("any-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_with_no_allowed_fields(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        mock_db.execute.reset_mock()

        mock_db.fetch_one.return_value = {
            "id": "c1",
            "case_id": None,
            "doc_a_id": "a",
            "doc_b_id": "b",
            "title": "T",
            "status": "pending",
            "diff_count": 0,
            "additions": 0,
            "deletions": 0,
            "modifications": 0,
            "diffs": "[]",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        # Pass only unknown fields
        result = await shard.update_comparison("c1", {"unknown_field": "value"})
        # Should return current comparison without executing an UPDATE
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_diffs_serializes_list(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        mock_db.execute.reset_mock()
        mock_db.fetch_one.return_value = {
            "id": "c1",
            "case_id": None,
            "doc_a_id": "a",
            "doc_b_id": "b",
            "title": "T",
            "status": "pending",
            "diff_count": 0,
            "additions": 0,
            "deletions": 0,
            "modifications": 0,
            "diffs": '[{"type": "add"}]',
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        await shard.update_comparison("c1", {"diffs": [{"type": "add", "content": "new"}]})
        # The execute call should have JSON-serialized the diffs
        call_params = mock_db.execute.call_args[0][1]
        assert isinstance(call_params["diffs"], str)
        assert json.loads(call_params["diffs"]) == [{"type": "add", "content": "new"}]


# ---------------------------------------------------------------------------
# Event Handler edge cases
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Test event handler methods."""

    @pytest.mark.asyncio
    async def test_handle_document_processed_with_doc_id(self, mock_frame):
        shard = await _make_shard(mock_frame)
        # Should not raise
        await shard.handle_document_processed({"payload": {"document_id": "doc-123"}})

    @pytest.mark.asyncio
    async def test_handle_document_processed_without_doc_id(self, mock_frame):
        shard = await _make_shard(mock_frame)
        # Should not raise even with missing doc_id
        await shard.handle_document_processed({"payload": {}})

    @pytest.mark.asyncio
    async def test_handle_document_processed_empty_event(self, mock_frame):
        shard = await _make_shard(mock_frame)
        await shard.handle_document_processed({})

    @pytest.mark.asyncio
    async def test_handle_parse_completed_with_doc_id(self, mock_frame):
        shard = await _make_shard(mock_frame)
        await shard.handle_parse_completed({"payload": {"document_id": "doc-456"}})

    @pytest.mark.asyncio
    async def test_handle_parse_completed_without_doc_id(self, mock_frame):
        shard = await _make_shard(mock_frame)
        await shard.handle_parse_completed({"payload": {}})

    @pytest.mark.asyncio
    async def test_event_subscriptions_registered(self, mock_frame, mock_events):
        shard = await _make_shard(mock_frame)
        subscribe_calls = [c.args[0] for c in mock_events.subscribe.call_args_list]
        assert "documents.processed" in subscribe_calls
        assert "parse.completed" in subscribe_calls

    @pytest.mark.asyncio
    async def test_shutdown_unsubscribes(self, mock_frame, mock_events):
        shard = await _make_shard(mock_frame)
        await shard.shutdown()
        unsub_calls = [c.args[0] for c in mock_events.unsubscribe.call_args_list]
        assert "documents.processed" in unsub_calls
        assert "parse.completed" in unsub_calls


# ---------------------------------------------------------------------------
# Model edge cases
# ---------------------------------------------------------------------------


class TestModelEdgeCases:
    """Edge cases for Pydantic models."""

    def test_comparison_with_all_fields(self):
        comp = Comparison(
            id="test-id",
            case_id="case-1",
            doc_a_id="a",
            doc_b_id="b",
            title="Full comparison",
            status=ComparisonStatus.COMPLETE,
            diff_count=10,
            additions=5,
            deletions=3,
            modifications=2,
            diffs=[{"type": "add", "content": "test"}],
        )
        assert comp.id == "test-id"
        assert comp.diffs == [{"type": "add", "content": "test"}]

    def test_document_change_model(self):
        dc = DocumentChange(
            id="dc-1",
            comparison_id="c-1",
            type="semantic",
            location="paragraph 3",
            before="old text",
            after="new text",
            significance=0.8,
            is_silent=True,
        )
        assert dc.is_silent is True
        assert dc.significance == 0.8

    def test_comparison_status_all_set(self):
        assert ComparisonStatus.PENDING in ComparisonStatus.ALL
        assert ComparisonStatus.PROCESSING in ComparisonStatus.ALL
        assert ComparisonStatus.COMPLETE in ComparisonStatus.ALL
        assert ComparisonStatus.FAILED in ComparisonStatus.ALL
        assert "nonexistent" not in ComparisonStatus.ALL


# ---------------------------------------------------------------------------
# API edge cases
# ---------------------------------------------------------------------------


class TestAPIEdgeCases:
    """Edge cases for API endpoints."""

    def setup_method(self):
        import arkham_shard_redline.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_engine_unavailable_503(self):
        self.api._engine = None
        req = self.api.DiffRequest(text_a="a", text_b="b")
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self.api.raw_diff(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_classify_no_engine_503(self):
        self.api._engine = None
        req = self.api.ClassifyRequest(diffs=[])
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self.api.classify_changes(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_semantic_no_engine_503(self):
        self.api._engine = None
        req = self.api.SemanticDiffRequest(doc_a_id="a", doc_b_id="b")
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self.api.semantic_diff(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_compare_no_engine_503(self):
        self.api._engine = None
        req = self.api.CompareRequest(doc_a_id="a", doc_b_id="b")
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self.api.compare_documents(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_update_empty_body_returns_existing(self, mock_db, mock_events):
        shard = RedlineShard()
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {"events": mock_events, "llm": None, "vectors": None}.get(name)
        )
        await shard.initialize(frame)
        self.api._shard = shard

        existing = {
            "id": "c1",
            "case_id": None,
            "doc_a_id": "a",
            "doc_b_id": "b",
            "title": "T",
            "status": "pending",
            "diff_count": 0,
            "additions": 0,
            "deletions": 0,
            "modifications": 0,
            "diffs": "[]",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.fetch_one.return_value = existing

        req = self.api.UpdateComparisonRequest()  # all None
        result = await self.api.update_comparison("c1", req)
        # Should return existing without error
        assert result is not None

    @pytest.mark.asyncio
    async def test_count_items_no_db_503(self):
        self.api._db = None
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self.api.count_items()
        assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# Schema creation edge cases
# ---------------------------------------------------------------------------


class TestSchemaEdgeCases:
    """Edge cases for database schema creation."""

    @pytest.mark.asyncio
    async def test_schema_creation_db_error_handled(self):
        """Schema creation failure should be caught, not crash."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("Connection refused"))

        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)

        shard = RedlineShard()
        # Should not raise - error is logged
        await shard.initialize(frame)

    @pytest.mark.asyncio
    async def test_schema_creation_no_db_warns(self):
        """Schema creation with no DB should warn, not crash."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)

        shard = RedlineShard()
        await shard.initialize(frame)
        # Should complete without error

    @pytest.mark.asyncio
    async def test_shutdown_without_events(self):
        """Shutdown without event bus should not raise."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)

        shard = RedlineShard()
        await shard.initialize(frame)
        await shard.shutdown()
        assert shard.engine is None
