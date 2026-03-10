"""
Redline Shard - Logic Tests

Tests for comparison CRUD, status transitions, diff counting,
filtering by case_id, and the compare endpoint.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_redline.models import Comparison, ComparisonStatus
from arkham_shard_redline.shard import RedlineShard
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


async def _make_shard(mock_frame):
    """Helper: create and initialize a RedlineShard."""
    shard = RedlineShard()
    await shard.initialize(mock_frame)
    return shard


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestComparisonModel:
    """Test the Comparison pydantic model."""

    def test_defaults(self):
        comp = Comparison(doc_a_id="a1", doc_b_id="b1")
        assert comp.status == "pending"
        assert comp.diff_count == 0
        assert comp.additions == 0
        assert comp.deletions == 0
        assert comp.modifications == 0
        assert comp.diffs == []
        assert comp.id  # auto-generated UUID

    def test_status_values(self):
        assert ComparisonStatus.PENDING == "pending"
        assert ComparisonStatus.PROCESSING == "processing"
        assert ComparisonStatus.COMPLETE == "complete"
        assert ComparisonStatus.FAILED == "failed"
        assert len(ComparisonStatus.ALL) == 4


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify the comparisons table DDL matches requirements."""

    @pytest.mark.asyncio
    async def test_comparisons_table_created(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_redline" in executed_sql
        assert "arkham_redline.comparisons" in executed_sql

    @pytest.mark.asyncio
    async def test_comparisons_columns(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        comp_ddl = next((s for s in ddl_calls if "comparisons" in s and "CREATE TABLE" in s), None)
        assert comp_ddl is not None

        for col in [
            "id",
            "case_id",
            "doc_a_id",
            "doc_b_id",
            "title",
            "status",
            "diff_count",
            "additions",
            "deletions",
            "modifications",
            "diffs",
            "created_at",
            "updated_at",
        ]:
            assert col in comp_ddl, f"Column {col} missing from DDL"

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 2


# ---------------------------------------------------------------------------
# Comparison Creation Tests
# ---------------------------------------------------------------------------


class TestComparisonCreation:
    """Test creating comparison records via the shard."""

    @pytest.mark.asyncio
    async def test_create_comparison_returns_record(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        result = await shard.create_comparison(
            doc_a_id="doc-a",
            doc_b_id="doc-b",
            title="Test comparison",
            case_id="case-1",
        )

        assert result["doc_a_id"] == "doc-a"
        assert result["doc_b_id"] == "doc-b"
        assert result["title"] == "Test comparison"
        assert result["case_id"] == "case-1"
        assert result["status"] == "pending"
        assert result["diff_count"] == 0
        assert "id" in result

    @pytest.mark.asyncio
    async def test_create_comparison_calls_db(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        mock_db.execute.reset_mock()

        await shard.create_comparison(doc_a_id="a", doc_b_id="b", title="T")
        mock_db.execute.assert_called_once()

        call_sql = str(mock_db.execute.call_args[0][0])
        assert "INSERT INTO arkham_redline.comparisons" in call_sql

    @pytest.mark.asyncio
    async def test_create_comparison_emits_event(self, mock_frame, mock_db, mock_events):
        shard = await _make_shard(mock_frame)
        mock_events.emit.reset_mock()

        result = await shard.create_comparison(doc_a_id="a", doc_b_id="b")
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "redline.comparison.created"
        payload = mock_events.emit.call_args[0][1]
        assert payload["comparison_id"] == result["id"]

    @pytest.mark.asyncio
    async def test_create_comparison_default_status_pending(self, mock_frame):
        shard = await _make_shard(mock_frame)
        result = await shard.create_comparison(doc_a_id="a", doc_b_id="b")
        assert result["status"] == "pending"


# ---------------------------------------------------------------------------
# Status Transition Tests
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    """Test status transitions: pending -> processing -> complete."""

    @pytest.mark.asyncio
    async def test_transition_pending_to_processing(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        mock_db.fetch_one.return_value = {
            "id": "c1",
            "case_id": None,
            "doc_a_id": "a",
            "doc_b_id": "b",
            "title": "T",
            "status": "processing",
            "diff_count": 0,
            "additions": 0,
            "deletions": 0,
            "modifications": 0,
            "diffs": "[]",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = await shard.update_comparison("c1", {"status": "processing"})
        assert result is not None
        assert result["status"] == "processing"

    @pytest.mark.asyncio
    async def test_transition_processing_to_complete(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        mock_db.fetch_one.return_value = {
            "id": "c1",
            "case_id": None,
            "doc_a_id": "a",
            "doc_b_id": "b",
            "title": "T",
            "status": "complete",
            "diff_count": 5,
            "additions": 2,
            "deletions": 1,
            "modifications": 2,
            "diffs": "[]",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = await shard.update_comparison(
            "c1",
            {
                "status": "complete",
                "diff_count": 5,
                "additions": 2,
                "deletions": 1,
                "modifications": 2,
            },
        )
        assert result is not None
        assert result["status"] == "complete"
        assert result["diff_count"] == 5

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        result = await shard.update_comparison("c1", {"status": "invalid_status"})
        assert result is None


# ---------------------------------------------------------------------------
# Diff Count Calculation Tests
# ---------------------------------------------------------------------------


class TestDiffCountCalculation:
    """Test that diff counts are stored correctly."""

    @pytest.mark.asyncio
    async def test_update_with_diff_counts(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        mock_db.fetch_one.return_value = {
            "id": "c1",
            "case_id": None,
            "doc_a_id": "a",
            "doc_b_id": "b",
            "title": "T",
            "status": "complete",
            "diff_count": 10,
            "additions": 4,
            "deletions": 3,
            "modifications": 3,
            "diffs": '[{"type": "add", "text": "new"}]',
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = await shard.update_comparison(
            "c1",
            {
                "diff_count": 10,
                "additions": 4,
                "deletions": 3,
                "modifications": 3,
                "diffs": [{"type": "add", "text": "new"}],
            },
        )

        assert result is not None
        assert result["diff_count"] == 10
        assert result["additions"] == 4
        assert result["deletions"] == 3
        assert result["modifications"] == 3

    def test_comparison_model_diff_counts(self):
        comp = Comparison(
            doc_a_id="a",
            doc_b_id="b",
            diff_count=7,
            additions=3,
            deletions=2,
            modifications=2,
        )
        assert comp.diff_count == 7
        assert comp.additions + comp.deletions + comp.modifications == 7


# ---------------------------------------------------------------------------
# Filtering Tests
# ---------------------------------------------------------------------------


class TestFilteringByCaseId:
    """Test listing comparisons filtered by case_id."""

    @pytest.mark.asyncio
    async def test_filter_by_case_id(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)

        mock_db.fetch_all.return_value = [
            {
                "id": "c1",
                "case_id": "case-1",
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
        ]

        results = await shard.list_comparisons(case_id="case-1")
        assert len(results) == 1

        call_sql = str(mock_db.fetch_all.call_args[0][0])
        assert "case_id" in call_sql

    @pytest.mark.asyncio
    async def test_filter_by_status(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        mock_db.fetch_all.return_value = []

        await shard.list_comparisons(status="complete")
        call_sql = str(mock_db.fetch_all.call_args[0][0])
        assert "status" in call_sql

    @pytest.mark.asyncio
    async def test_no_filter_returns_all(self, mock_frame, mock_db):
        shard = await _make_shard(mock_frame)
        mock_db.fetch_all.return_value = []

        await shard.list_comparisons()
        call_sql = str(mock_db.fetch_all.call_args[0][0])
        # The WHERE 1=1 is always there, but case_id filter should NOT be
        assert "AND case_id" not in call_sql


# ---------------------------------------------------------------------------
# Compare Endpoint Tests
# ---------------------------------------------------------------------------


class TestCompareEndpoint:
    """Test the POST /compare endpoint logic."""

    @pytest.mark.asyncio
    async def test_compare_creates_pending_record(self, mock_frame, mock_events):
        shard = await _make_shard(mock_frame)
        mock_events.emit.reset_mock()

        result = await shard.create_comparison(
            doc_a_id="doc-x",
            doc_b_id="doc-y",
            title="Compare test",
        )

        assert result["status"] == "pending"
        assert result["doc_a_id"] == "doc-x"
        assert result["doc_b_id"] == "doc-y"
        assert result["title"] == "Compare test"
        assert result["diff_count"] == 0

    @pytest.mark.asyncio
    async def test_compare_emits_event(self, mock_frame, mock_events):
        shard = await _make_shard(mock_frame)
        mock_events.emit.reset_mock()

        await shard.create_comparison(doc_a_id="x", doc_b_id="y")
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "redline.comparison.created"


# ---------------------------------------------------------------------------
# API Endpoint Tests (module-level)
# ---------------------------------------------------------------------------


class TestAPIEndpoints:
    """Test the API module-level handler functions."""

    def setup_method(self):
        import arkham_shard_redline.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_no_shard_503(self):
        self.api._shard = None
        req = self.api.CreateComparisonRequest(doc_a_id="a", doc_b_id="b")
        with pytest.raises(HTTPException) as exc:
            await self.api.create_comparison(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_not_found_404(self, mock_db, mock_events):
        shard = RedlineShard()
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {"events": mock_events, "llm": None, "vectors": None}.get(name)
        )
        await shard.initialize(frame)

        self.api._shard = shard
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_comparison("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found_404(self, mock_db, mock_events):
        shard = RedlineShard()
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {"events": mock_events, "llm": None, "vectors": None}.get(name)
        )
        await shard.initialize(frame)

        self.api._shard = shard
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.delete_comparison("nonexistent")
        assert exc.value.status_code == 404
