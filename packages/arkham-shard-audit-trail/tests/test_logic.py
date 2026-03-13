"""
AuditTrail Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_audit_trail.models import (
    ActionType,
    AuditAction,
    AuditExport,
    AuditSession,
)
from arkham_shard_audit_trail.shard import AuditTrailShard

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

    def test_action_type_enum(self):
        assert ActionType.DOCUMENT_INGEST == "document.ingest"
        assert ActionType.SEARCH_QUERY == "search.query"
        assert ActionType.AUTH_LOGIN == "auth.login"

    def test_audit_action_to_dict(self):
        a = AuditAction(
            id="a1",
            tenant_id=None,
            user_id="u1",
            action_type="test",
            shard="shard",
            entity_id=None,
            description="desc",
            payload={"foo": "bar"},
        )
        d = a.to_dict()
        assert d["id"] == "a1"
        assert d["payload"]["foo"] == "bar"

    def test_audit_session_to_dict(self):
        from datetime import datetime

        now = datetime.utcnow()
        s = AuditSession(
            id="s1",
            tenant_id=None,
            user_id="u1",
            start_time=now,
            end_time=None,
            ip_address="127.0.0.1",
            user_agent="agent",
        )
        d = s.to_dict()
        assert d["id"] == "s1"
        assert d["ip_address"] == "127.0.0.1"

    def test_audit_export_to_dict(self):
        e = AuditExport(id="e1", tenant_id=None, user_id="u1", export_format="csv", filters_applied={}, row_count=10)
        d = e.to_dict()
        assert d["id"] == "e1"
        assert d["export_format"] == "csv"


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_audit_trail" in executed_sql
        assert "arkham_audit_trail.actions" in executed_sql
        assert "arkham_audit_trail.sessions" in executed_sql
        assert "arkham_audit_trail.exports" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_audit_trail.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_actions_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_actions()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_sessions_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_sessions()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_exports_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_exports()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_record_export_no_db(self):
        from arkham_shard_audit_trail.api import CreateExportRequest
        from fastapi import HTTPException

        self.api._db = None
        req = CreateExportRequest(export_format="csv")
        with pytest.raises(HTTPException) as exc:
            await self.api.record_export(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_actions(self, mock_db):
        from arkham_shard_audit_trail.api import list_actions

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "a1", "action_type": "test"}]
        result = await list_actions(user_id="u1")
        assert result["count"] == 1
        assert result["actions"][0]["id"] == "a1"
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_summary(self, mock_db):
        from arkham_shard_audit_trail.api import get_audit_summary

        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"cnt": 100}
        mock_db.fetch_all.return_value = [{"shard": "ingest", "cnt": 50}]
        result = await get_audit_summary()
        assert result["total_actions"] == 100
        assert result["shards"]["ingest"] == 50

    @pytest.mark.asyncio
    async def test_list_sessions(self, mock_db):
        from arkham_shard_audit_trail.api import list_sessions

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "s1"}]
        result = await list_sessions()
        assert result["count"] == 1
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_export(self, mock_db, mock_events):
        from arkham_shard_audit_trail.api import CreateExportRequest, record_export

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = CreateExportRequest(user_id="u1", export_format="json", filters_applied={"shard": "ach"}, row_count=10)
        result = await record_export(req)
        assert "export_id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_items_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.count_items()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_count_items(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"count": 42}
        result = await self.api.count_items()
        assert result["count"] == 42

    @pytest.mark.asyncio
    async def test_count_items_no_result(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None
        result = await self.api.count_items()
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_get_summary_no_db(self):
        self.api._db = None
        result = await self.api.get_audit_summary()
        assert result["total_actions"] == 0

    @pytest.mark.asyncio
    async def test_list_actions_with_all_filters(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "a1"}]

        result = await self.api.list_actions(
            user_id="u1", shard="ingest", action_type="document.ingest", entity_id="doc-1"
        )
        assert result["count"] == 1
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        assert "user_id = :user_id" in sql
        assert "shard = :shard" in sql
        assert "action_type = :action_type" in sql
        assert "entity_id = :entity_id" in sql


# ---------------------------------------------------------------------------
# _parse_datetime Tests
# ---------------------------------------------------------------------------


class TestParseDatetime:
    """Edge cases for the API datetime parser."""

    def test_parse_valid_iso(self):
        from arkham_shard_audit_trail.api import _parse_datetime

        result = _parse_datetime("2026-03-13T12:00:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 3

    def test_parse_none(self):
        from arkham_shard_audit_trail.api import _parse_datetime

        assert _parse_datetime(None) is None

    def test_parse_empty_string(self):
        from arkham_shard_audit_trail.api import _parse_datetime

        assert _parse_datetime("") is None

    def test_parse_invalid_string(self):
        from arkham_shard_audit_trail.api import _parse_datetime

        assert _parse_datetime("not-a-date") is None

    def test_parse_date_only(self):
        from arkham_shard_audit_trail.api import _parse_datetime

        result = _parse_datetime("2026-03-13")
        assert result is not None
        assert result.day == 13


# ---------------------------------------------------------------------------
# Engine-Powered API Endpoint Tests
# ---------------------------------------------------------------------------


class TestEngineEndpoints:
    """Tests for API endpoints that delegate to AuditEngine."""

    def setup_method(self):
        import arkham_shard_audit_trail.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_search_endpoint_no_engine(self):
        from arkham_shard_audit_trail.api import SearchRequest, search_actions
        from fastapi import HTTPException

        self.api._engine = None
        with pytest.raises(HTTPException) as exc:
            await search_actions(SearchRequest())
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_search_endpoint_delegates(self):
        from arkham_shard_audit_trail.api import SearchRequest, search_actions

        mock_engine = AsyncMock()
        mock_engine.search_actions = AsyncMock(return_value=[{"id": "a1"}])
        self.api._engine = mock_engine

        result = await search_actions(SearchRequest(shard="ingest"))

        assert result["count"] == 1
        mock_engine.search_actions.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_endpoint_no_engine(self):
        from arkham_shard_audit_trail.api import get_session_actions
        from fastapi import HTTPException

        self.api._engine = None
        with pytest.raises(HTTPException) as exc:
            await get_session_actions("sess-1")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_session_endpoint_delegates(self):
        from arkham_shard_audit_trail.api import get_session_actions

        mock_engine = AsyncMock()
        mock_engine.get_session_actions = AsyncMock(return_value=[{"id": "a1"}])
        self.api._engine = mock_engine

        result = await get_session_actions("sess-1")

        assert result["count"] == 1
        assert result["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_export_endpoint_no_engine(self):
        from arkham_shard_audit_trail.api import ExportRequest, export_audit_log
        from fastapi import HTTPException

        self.api._engine = None
        with pytest.raises(HTTPException) as exc:
            await export_audit_log(ExportRequest())
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_export_endpoint_delegates(self):
        from arkham_shard_audit_trail.api import ExportRequest, export_audit_log

        mock_engine = AsyncMock()
        mock_engine.export_audit_log = AsyncMock(
            return_value={"export_id": "e1", "format": "json", "record_count": 5, "content": []}
        )
        self.api._engine = mock_engine

        result = await export_audit_log(ExportRequest(shard="ach", format="csv"))

        assert result["export_id"] == "e1"
        mock_engine.export_audit_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_retention_endpoint_no_engine(self):
        from arkham_shard_audit_trail.api import RetentionRequest, manage_retention
        from fastapi import HTTPException

        self.api._engine = None
        with pytest.raises(HTTPException) as exc:
            await manage_retention(RetentionRequest())
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_retention_endpoint_delegates(self):
        from arkham_shard_audit_trail.api import RetentionRequest, manage_retention

        mock_engine = AsyncMock()
        mock_engine.manage_retention = AsyncMock(return_value=10)
        self.api._engine = mock_engine

        result = await manage_retention(RetentionRequest(retention_days=30))

        assert result["deleted_count"] == 10
        assert result["retention_days"] == 30
