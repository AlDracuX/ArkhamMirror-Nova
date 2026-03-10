"""
Comms Shard - Logic Tests

Tests for models and API handler logic.
All external dependencies are mocked.
"""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_comms.api import (
    MessageCreate,
    ThreadCreate,
)
from arkham_shard_comms.models import (
    CoordinationFlag,
    CoordinationFlagRecord,
    Gap,
    GapType,
    Message,
    Participant,
    ParticipantRole,
    Thread,
    ThreadStatus,
)
from arkham_shard_comms.shard import CommsShard
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

    def test_thread_defaults(self):
        t = Thread(id="t1")
        assert t.id == "t1"
        assert t.status == ThreadStatus.ACTIVE
        assert t.message_count == 0

    def test_message_defaults(self):
        m = Message(id="m1", thread_id="t1")
        assert m.id == "m1"
        assert m.thread_id == "t1"
        assert m.to_addresses == []

    def test_participant_defaults(self):
        p = Participant(id="p1", email_address="test@example.com")
        assert p.email_address == "test@example.com"
        assert p.bcc_appearances == 0

    def test_gap_defaults(self):
        g = Gap(id="g1", thread_id="t1")
        assert g.gap_type == GapType.MISSING_REPLY
        assert g.significance == "medium"

    def test_coordination_flag_record_defaults(self):
        cfr = CoordinationFlagRecord(id="cfr1", thread_id="t1")
        assert cfr.flag_type == CoordinationFlag.BCC_CHAIN
        assert cfr.confidence == 0.5

    def test_enums(self):
        assert ThreadStatus.ACTIVE == "active"
        assert ParticipantRole.BCC == "bcc"
        assert GapType.MISSING_REPLY == "missing_reply"
        assert CoordinationFlag.BCC_CHAIN == "bcc_chain"


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = CommsShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_comms" in executed_sql
        assert "arkham_comms.threads" in executed_sql
        assert "arkham_comms.messages" in executed_sql
        assert "arkham_comms.participants" in executed_sql
        assert "arkham_comms.gaps" in executed_sql
        assert "arkham_comms.coordination_flags" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = CommsShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 9


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_comms.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_threads_no_db(self):
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_threads()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_threads(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "t1", "subject": "Test Thread"}]
        result = await self.api.list_threads(project_id="p1")
        assert len(result) == 1
        assert "project_id = :project_id" in mock_db.fetch_all.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_thread(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = ThreadCreate(subject="New Thread", description="Desc")
        result = await self.api.create_thread(req)
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_messages(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "m1", "subject": "Test Message"}]
        result = await self.api.list_messages(thread_id="t1")
        assert len(result) == 1
        assert "thread_id = :thread_id" in mock_db.fetch_all.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_message(self, mock_db):
        self.api._db = mock_db
        self.api._shard = None
        req = MessageCreate(thread_id="t1", subject="Msg", from_address="a@b.com", to_addresses=["c@d.com"])
        result = await self.api.create_message(req)
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()
        # Verify JSON serialization of addresses
        args = mock_db.execute.call_args[0][1]
        assert json.loads(args["to_addresses"]) == ["c@d.com"]

    @pytest.mark.asyncio
    async def test_list_participants(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "p1", "email_address": "a@b.com"}]
        result = await self.api.list_participants()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_gaps(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "g1", "gap_type": "missing_reply"}]
        result = await self.api.list_gaps(thread_id="t1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_coordination_flags(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "f1", "flag_type": "bcc_chain"}]
        result = await self.api.list_coordination_flags(thread_id="t1")
        assert len(result) == 1
