"""
Redline Shard - Logic Tests

Tests for models and API handler logic for document comparison, version chains, and changes.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_redline.models import (
    DocumentChange,
    DocumentComparison,
    VersionChain,
)
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


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify pydantic model construction."""

    def test_document_comparison(self):
        dc = DocumentComparison(
            id="dc1",
            project_id="p1",
            base_document_id="doc1",
            target_document_id="doc2",
            diff_summary="Changes found",
            change_count=5,
        )
        assert dc.id == "dc1"
        assert dc.change_count == 5

    def test_version_chain(self):
        vc = VersionChain(
            id="vc1", project_id="p1", document_ids=["doc1", "doc2", "doc3"], description="Contract versions"
        )
        assert vc.id == "vc1"
        assert len(vc.document_ids) == 3

    def test_document_change(self):
        dc = DocumentChange(
            id="dc1",
            comparison_id="comp1",
            type="semantic",
            location="Paragraph 1",
            before="Hello",
            after="Hi",
            significance=0.2,
        )
        assert dc.id == "dc1"
        assert dc.type == "semantic"


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = RedlineShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_redline" in executed_sql
        assert "arkham_redline.comparisons" in executed_sql
        assert "arkham_redline.version_chains" in executed_sql
        assert "arkham_redline.changes" in executed_sql

    @pytest.mark.asyncio
    async def test_comparisons_columns(self, mock_frame, mock_db):
        shard = RedlineShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        comp_ddl = next((s for s in ddl_calls if "comparisons" in s and "CREATE TABLE" in s), None)
        assert comp_ddl is not None
        assert "base_document_id" in comp_ddl
        assert "target_document_id" in comp_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = RedlineShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 2


# ---------------------------------------------------------------------------
# API Logic Tests (unit-level, no HTTP layer)
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        """Reset module-level _db before each test."""
        import arkham_shard_redline.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_comparison_no_db(self):
        self.api._db = None
        from arkham_shard_redline.api import CreateComparisonRequest

        req = CreateComparisonRequest(project_id="p1", base_document_id="b1", target_document_id="t1")
        with pytest.raises(HTTPException) as exc:
            await self.api.create_comparison(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_comparison(self, mock_db, mock_events):
        from arkham_shard_redline.api import CreateComparisonRequest, create_comparison

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateComparisonRequest(project_id="p1", base_document_id="b1", target_document_id="t1")
        result = await create_comparison(req)
        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "redline.comparison.created"

    @pytest.mark.asyncio
    async def test_get_comparison(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {
            "id": "c1",
            "project_id": "p1",
            "base_document_id": "b1",
            "target_document_id": "t1",
            "diff_summary": "S1",
        }
        mock_db.fetch_all.return_value = [
            {"id": "ch1", "comparison_id": "c1", "type": "T1", "location": "L1", "significance": 0.5}
        ]

        result = await self.api.get_comparison("c1")
        assert result["id"] == "c1"
        assert len(result["changes"]) == 1

    @pytest.mark.asyncio
    async def test_get_comparison_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_comparison("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_chains(self, mock_db):
        self.api._db = mock_db
        await self.api.list_chains(project_id="p1")
        mock_db.fetch_all.assert_called_once()
