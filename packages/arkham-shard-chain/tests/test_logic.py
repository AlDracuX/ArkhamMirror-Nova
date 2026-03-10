"""
Chain Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_chain.models import (
    CustodyAction,
    CustodyEvent,
    EvidenceHash,
    ProvenanceReport,
)
from arkham_shard_chain.shard import ChainShard

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
def mock_storage():
    storage = AsyncMock()
    storage.retrieve = AsyncMock(return_value=(b"file content", {}))
    storage.store = AsyncMock()
    return storage


@pytest.fixture
def mock_frame(mock_events, mock_db, mock_storage):
    frame = MagicMock()
    frame.database = mock_db
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "events": mock_events,
            "llm": None,
            "database": mock_db,
            "vectors": None,
            "documents": None,
            "storage": mock_storage,
        }.get(name)
    )
    return frame


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and enum values."""

    def test_custody_action_enum(self):
        assert CustodyAction.RECEIVED == "received"
        assert CustodyAction.STORED == "stored"
        assert CustodyAction.ACCESSED == "accessed"
        assert CustodyAction.TRANSFORMED == "transformed"
        assert CustodyAction.EXPORTED == "exported"
        assert CustodyAction.VERIFIED == "verified"

    def test_evidence_hash_defaults(self):
        h = EvidenceHash(id="h1", tenant_id=None, document_id="d1", sha256_hash="abc")
        assert h.id == "h1"
        assert h.document_id == "d1"
        assert h.sha256_hash == "abc"

    def test_custody_event_defaults(self):
        from datetime import datetime

        now = datetime.utcnow()
        e = CustodyEvent(
            id="e1",
            tenant_id=None,
            document_id="d1",
            action=CustodyAction.RECEIVED,
            actor="sys",
            location="loc",
            timestamp=now,
            previous_event_id=None,
            hash_verified=True,
        )
        assert e.id == "e1"
        assert e.action == CustodyAction.RECEIVED
        assert e.hash_verified is True

    def test_provenance_report_defaults(self):
        r = ProvenanceReport(id="r1", tenant_id=None, document_id="d1", report_json={})
        assert r.id == "r1"
        assert r.document_id == "d1"
        assert r.report_json == {}


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = ChainShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_chain" in executed_sql
        assert "arkham_chain.hashes" in executed_sql
        assert "arkham_chain.custody_events" in executed_sql
        assert "arkham_chain.provenance_reports" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = ChainShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_chain.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_log_custody_event_no_db(self):
        from arkham_shard_chain.api import LogEventRequest
        from fastapi import HTTPException

        self.api._db = None
        req = LogEventRequest(document_id="d1", action="received", actor="a", location="l")
        with pytest.raises(HTTPException) as exc:
            await self.api.log_custody_event(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_history_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_document_history("d1")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_verify_integrity_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.verify_document_integrity("d1")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_generate_report_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.generate_provenance_report("d1")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_log_event(self, mock_db, mock_storage, mock_events):
        from arkham_shard_chain.api import LogEventRequest, log_custody_event

        self.api._db = mock_db
        self.api._storage_service = mock_storage
        self.api._event_bus = mock_events
        self.api._shard = None

        req = LogEventRequest(document_id="d1", action="received", actor="user", location="office")
        result = await log_custody_event(req)

        assert result["status"] == "logged"
        assert "event_id" in result
        # One for hashes, one for custody_events
        assert mock_db.execute.call_count == 2
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_history(self, mock_db):
        from arkham_shard_chain.api import get_document_history

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "e1", "action": "received"}]
        result = await get_document_history("d1")
        assert result["document_id"] == "d1"
        assert len(result["history"]) == 1
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_integrity(self, mock_db, mock_storage):
        from arkham_shard_chain.api import verify_document_integrity

        self.api._db = mock_db
        self.api._storage_service = mock_storage
        self.api._shard = None

        content = b"hello"
        h = hashlib.sha256(content).hexdigest()
        mock_db.fetch_one.return_value = {"sha256_hash": h}
        mock_storage.retrieve.return_value = (content, {})

        result = await verify_document_integrity("d1")
        assert result["valid"] is True
        assert result["current_hash"] == h

    @pytest.mark.asyncio
    async def test_generate_report(self, mock_db):
        from arkham_shard_chain.api import generate_provenance_report

        self.api._db = mock_db
        self.api._shard = None
        mock_db.fetch_all.return_value = [
            {"id": "e1", "action": "received", "timestamp": MagicMock(isoformat=lambda: "2024-01-01")}
        ]

        result = await generate_provenance_report("d1")
        assert "report_id" in result
        assert result["report"]["document_id"] == "d1"
        # fetch_all for history, execute for insert
        assert mock_db.fetch_all.call_count == 1
        assert mock_db.execute.call_count == 1
