"""
Digest Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_digest.api import (
    GenerateBriefingRequest,
    generate_briefing,
    get_briefing,
    get_changelog,
    list_briefings,
)
from arkham_shard_digest.models import CaseBriefing, ChangeLogEntry, DigestSubscription
from arkham_shard_digest.shard import DigestShard
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
    """Verify dataclass construction and defaults."""

    def test_case_briefing_defaults(self):
        b = CaseBriefing(id="b1", project_id="proj1", type="daily", content="Content")
        assert b.id == "b1"
        assert b.project_id == "proj1"
        assert b.type == "daily"
        assert b.content == "Content"
        assert b.priority_items == []
        assert b.action_items == []
        assert b.metadata == {}
        assert isinstance(b.created_at, datetime)

    def test_changelog_entry_defaults(self):
        e = ChangeLogEntry(
            id="e1",
            project_id="proj1",
            shard="shard1",
            entity_type="type1",
            entity_id="id1",
            action="action",
            description="desc",
        )
        assert e.id == "e1"
        assert e.project_id == "proj1"
        assert e.shard == "shard1"
        assert e.entity_type == "type1"
        assert e.entity_id == "id1"
        assert e.action == "action"
        assert e.description == "desc"
        assert isinstance(e.timestamp, datetime)

    def test_digest_subscription_defaults(self):
        s = DigestSubscription(id="s1", project_id="proj1", user_id="user1", frequency="daily", format="markdown")
        assert s.id == "s1"
        assert s.project_id == "proj1"
        assert s.user_id == "user1"
        assert s.frequency == "daily"
        assert s.format == "markdown"
        assert s.last_sent is None


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = DigestShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_digest" in executed_sql
        assert "arkham_digest.briefings" in executed_sql
        assert "arkham_digest.change_log" in executed_sql
        assert "arkham_digest.subscriptions" in executed_sql

    @pytest.mark.asyncio
    async def test_briefings_table_columns(self, mock_frame, mock_db):
        shard = DigestShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        brief_ddl = next((s for s in ddl_calls if "briefings" in s and "CREATE TABLE" in s), None)
        assert brief_ddl is not None
        assert "tenant_id" in brief_ddl
        assert "project_id" in brief_ddl
        assert "type" in brief_ddl
        assert "content" in brief_ddl
        assert "priority_items" in brief_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = DigestShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 2


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        """Reset module-level state before each test."""
        import arkham_shard_digest.api as api_mod

        self.api = api_mod
        self.api._engine = None

    @pytest.mark.asyncio
    async def test_generate_briefing_no_db(self):
        self.api._db = None
        req = GenerateBriefingRequest(project_id="p1")
        with pytest.raises(HTTPException) as exc:
            await generate_briefing(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_generate_briefing_success(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = GenerateBriefingRequest(project_id="p1", type="daily")
        result = await generate_briefing(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once_with("digest.briefing.generated", {"briefing_id": result["id"]})

    @pytest.mark.asyncio
    async def test_get_briefing_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_briefing("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_briefing_success(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "b1", "project_id": "proj1", "type": "daily"}

        result = await get_briefing("b1")
        assert result["id"] == "b1"

    @pytest.mark.asyncio
    async def test_list_briefings(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "b1", "project_id": "proj1"}]

        result = await list_briefings("proj1")
        assert len(result) == 1
        assert result[0]["id"] == "b1"

    @pytest.mark.asyncio
    async def test_get_changelog(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "e1", "project_id": "proj1"}]

        result = await get_changelog("proj1")
        assert len(result) == 1
        assert result[0]["id"] == "e1"
