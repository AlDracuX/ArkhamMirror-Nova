"""
Skeleton Shard - Logic Tests

Tests for models and API handler logic.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_skeleton.api import (
    ArgumentTreeCreate,
    AuthorityCreate,
    SubmissionCreate,
)
from arkham_shard_skeleton.models import (
    ArgumentTree,
    Authority,
    AuthorityType,
    Submission,
    SubmissionStatus,
)
from arkham_shard_skeleton.shard import SkeletonShard
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
    """Verify dataclass construction and enum values."""

    def test_argument_tree_defaults(self):
        at = ArgumentTree(id="at1")
        assert at.id == "at1"
        assert at.evidence_refs == []
        assert at.authority_ids == []

    def test_authority_defaults(self):
        a = Authority(id="a1")
        assert a.id == "a1"
        assert a.authority_type == AuthorityType.CASE_LAW
        assert a.is_binding is True

    def test_submission_defaults(self):
        s = Submission(id="s1")
        assert s.id == "s1"
        assert s.status == SubmissionStatus.DRAFT
        assert s.submission_type == "skeleton_argument"

    def test_enums(self):
        assert SubmissionStatus.DRAFT == "draft"
        assert AuthorityType.CASE_LAW == "case_law"


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = SkeletonShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_skeleton" in executed_sql
        assert "arkham_skeleton.argument_trees" in executed_sql
        assert "arkham_skeleton.authorities" in executed_sql
        assert "arkham_skeleton.submissions" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = SkeletonShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 5


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_skeleton.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_argument_trees_no_db(self):
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_argument_trees()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_argument_trees(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "at1", "title": "Test Tree"}]
        result = await self.api.list_argument_trees(project_id="p1")
        assert len(result) == 1
        assert "project_id = :project_id" in mock_db.fetch_all.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_argument_tree(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = ArgumentTreeCreate(title="New Tree", project_id="p1")
        result = await self.api.create_argument_tree(req)
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_authorities(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "a1", "citation": "123"}]
        result = await self.api.list_authorities()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create_authority(self, mock_db):
        self.api._db = mock_db
        self.api._shard = None
        req = AuthorityCreate(citation="[2024] UKSC 1", title="Case 1")
        result = await self.api.create_authority(req)
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()
        args = mock_db.execute.call_args[0][1]
        assert args["citation"] == "[2024] UKSC 1"

    @pytest.mark.asyncio
    async def test_list_submissions(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "s1", "title": "Test Sub"}]
        result = await self.api.list_submissions(project_id="p1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create_submission(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = SubmissionCreate(title="New Sub", project_id="p1")
        result = await self.api.create_submission(req)
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()
