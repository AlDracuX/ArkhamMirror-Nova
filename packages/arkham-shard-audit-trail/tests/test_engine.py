"""
AuditTrail Shard - Engine Tests

Tests for AuditEngine domain logic with mocked database.
TDD: RED phase - these tests define the contract for AuditEngine.
"""

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_audit_trail.engine import AuditEngine

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
    return events


@pytest.fixture
def engine(mock_db, mock_events):
    return AuditEngine(db=mock_db, event_bus=mock_events)


@pytest.fixture
def engine_no_db():
    return AuditEngine(db=None, event_bus=None)


# ---------------------------------------------------------------------------
# Helper: build fake action rows
# ---------------------------------------------------------------------------


def _make_action(
    shard="ingest",
    user_id="u1",
    entity_id="doc-1",
    action_type="document.ingest",
    session_id=None,
    timestamp=None,
):
    ts = timestamp or datetime.now(timezone.utc)
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": None,
        "user_id": user_id,
        "action_type": action_type,
        "shard": shard,
        "entity_id": entity_id,
        "session_id": session_id,
        "description": f"Action from {shard}",
        "payload": "{}",
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# 1. test_search_by_shard
# ---------------------------------------------------------------------------


class TestSearchByShard:
    """Filter audit actions by shard name."""

    @pytest.mark.asyncio
    async def test_search_by_shard(self, engine, mock_db):
        rows = [_make_action(shard="ingest"), _make_action(shard="ingest")]
        mock_db.fetch_all.return_value = rows

        results = await engine.search_actions(shard="ingest")

        assert len(results) == 2
        # Verify the SQL contained the shard filter
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("values", {})
        assert "shard = :shard" in sql

    @pytest.mark.asyncio
    async def test_search_by_shard_no_results(self, engine, mock_db):
        mock_db.fetch_all.return_value = []
        results = await engine.search_actions(shard="nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# 2. test_search_by_date_range
# ---------------------------------------------------------------------------


class TestSearchByDateRange:
    """Filter audit actions by date range."""

    @pytest.mark.asyncio
    async def test_search_by_date_range(self, engine, mock_db):
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        rows = [_make_action(timestamp=now)]
        mock_db.fetch_all.return_value = rows

        results = await engine.search_actions(date_from=yesterday, date_to=now)

        assert len(results) == 1
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        assert "timestamp >=" in sql
        assert "timestamp <=" in sql

    @pytest.mark.asyncio
    async def test_search_by_date_from_only(self, engine, mock_db):
        now = datetime.now(timezone.utc)
        mock_db.fetch_all.return_value = [_make_action()]

        results = await engine.search_actions(date_from=now)

        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        assert "timestamp >=" in sql
        assert "timestamp <=" not in sql


# ---------------------------------------------------------------------------
# 3. test_search_by_user_and_entity
# ---------------------------------------------------------------------------


class TestSearchByUserAndEntity:
    """Combined filter by user_id and entity_id."""

    @pytest.mark.asyncio
    async def test_search_by_user_and_entity(self, engine, mock_db):
        rows = [_make_action(user_id="u1", entity_id="doc-42")]
        mock_db.fetch_all.return_value = rows

        results = await engine.search_actions(user_id="u1", entity_id="doc-42")

        assert len(results) == 1
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        assert "user_id = :user_id" in sql
        assert "entity_id = :entity_id" in sql


# ---------------------------------------------------------------------------
# 4. test_session_actions_ordered
# ---------------------------------------------------------------------------


class TestSessionActionsOrdered:
    """Get all actions for a session, ordered chronologically."""

    @pytest.mark.asyncio
    async def test_session_actions_ordered(self, engine, mock_db):
        t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 10, 5, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 1, 10, 10, 0, tzinfo=timezone.utc)
        # DB returns in chronological order (engine requests ORDER BY timestamp ASC)
        rows = [
            _make_action(session_id="sess-1", timestamp=t1),
            _make_action(session_id="sess-1", timestamp=t2),
            _make_action(session_id="sess-1", timestamp=t3),
        ]
        mock_db.fetch_all.return_value = rows

        results = await engine.get_session_actions("sess-1")

        assert len(results) == 3
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        assert "session_id = :session_id" in sql
        assert "ORDER BY" in sql

    @pytest.mark.asyncio
    async def test_session_actions_empty(self, engine, mock_db):
        mock_db.fetch_all.return_value = []
        results = await engine.get_session_actions("nonexistent-session")
        assert results == []


# ---------------------------------------------------------------------------
# 5. test_export_json_format
# ---------------------------------------------------------------------------


class TestExportJsonFormat:
    """JSON export includes records and metadata."""

    @pytest.mark.asyncio
    async def test_export_json_format(self, engine, mock_db, mock_events):
        rows = [_make_action(), _make_action()]
        mock_db.fetch_all.return_value = rows

        result = await engine.export_audit_log(filters={"shard": "ingest"}, format="json")

        assert "export_id" in result
        assert result["format"] == "json"
        assert result["record_count"] == 2
        assert isinstance(result["content"], list)
        # Should store export record in DB
        mock_db.execute.assert_called()
        # Should emit event
        mock_events.emit.assert_called_once()
        emit_args = mock_events.emit.call_args
        assert emit_args[0][0] == "audit.export.created"


# ---------------------------------------------------------------------------
# 6. test_export_csv_format
# ---------------------------------------------------------------------------


class TestExportCsvFormat:
    """CSV export returns a string with proper CSV structure."""

    @pytest.mark.asyncio
    async def test_export_csv_format(self, engine, mock_db, mock_events):
        rows = [
            _make_action(shard="ingest", user_id="u1"),
            _make_action(shard="ach", user_id="u2"),
        ]
        mock_db.fetch_all.return_value = rows

        result = await engine.export_audit_log(filters={}, format="csv")

        assert result["format"] == "csv"
        assert result["record_count"] == 2
        content = result["content"]
        assert isinstance(content, str)
        # Verify CSV parses correctly
        reader = csv.reader(io.StringIO(content))
        csv_rows = list(reader)
        assert len(csv_rows) >= 3  # header + 2 data rows


# ---------------------------------------------------------------------------
# 7. test_retention_deletes_old_records
# ---------------------------------------------------------------------------


class TestRetentionDeletesOld:
    """Retention policy removes records older than threshold."""

    @pytest.mark.asyncio
    async def test_retention_deletes_old_records(self, engine, mock_db):
        # Simulate 5 records deleted
        mock_db.fetch_one.return_value = {"count": 5}

        deleted_count = await engine.manage_retention(retention_days=365)

        assert deleted_count == 5
        call_args = mock_db.execute.call_args
        sql = call_args[0][0]
        assert "DELETE" in sql
        assert "arkham_audit_trail.actions" in sql


# ---------------------------------------------------------------------------
# 8. test_retention_keeps_recent_records
# ---------------------------------------------------------------------------


class TestRetentionKeepsRecent:
    """Retention policy preserves records within the window."""

    @pytest.mark.asyncio
    async def test_retention_keeps_recent_records(self, engine, mock_db):
        # No records deleted (all recent)
        mock_db.fetch_one.return_value = {"count": 0}

        deleted_count = await engine.manage_retention(retention_days=365)

        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_retention_custom_days(self, engine, mock_db):
        mock_db.fetch_one.return_value = {"count": 10}

        deleted_count = await engine.manage_retention(retention_days=30)

        assert deleted_count == 10
        call_args = mock_db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else {}
        assert "cutoff" in params


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEngineEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_search_no_db(self, engine_no_db):
        results = await engine_no_db.search_actions(shard="test")
        assert results == []

    @pytest.mark.asyncio
    async def test_export_no_db(self, engine_no_db):
        result = await engine_no_db.export_audit_log(filters={}, format="json")
        assert result["record_count"] == 0
        assert result["content"] == []

    @pytest.mark.asyncio
    async def test_export_text_format(self, engine, mock_db, mock_events):
        rows = [_make_action()]
        mock_db.fetch_all.return_value = rows

        result = await engine.export_audit_log(filters={}, format="text")

        assert result["format"] == "text"
        assert isinstance(result["content"], str)

    @pytest.mark.asyncio
    async def test_session_no_db(self, engine_no_db):
        results = await engine_no_db.get_session_actions("sess-1")
        assert results == []

    @pytest.mark.asyncio
    async def test_retention_no_db(self, engine_no_db):
        deleted = await engine_no_db.manage_retention()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_search_all_filters(self, engine, mock_db):
        """All filters combined."""
        now = datetime.now(timezone.utc)
        mock_db.fetch_all.return_value = [_make_action()]

        results = await engine.search_actions(
            shard="ingest",
            user_id="u1",
            date_from=now - timedelta(days=1),
            date_to=now,
            entity_id="doc-1",
        )

        assert len(results) == 1
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        assert "shard = :shard" in sql
        assert "user_id = :user_id" in sql
        assert "entity_id = :entity_id" in sql
        assert "timestamp >=" in sql
        assert "timestamp <=" in sql

    @pytest.mark.asyncio
    async def test_search_no_filters(self, engine, mock_db):
        """Search with no filters returns all actions."""
        rows = [_make_action(), _make_action(), _make_action()]
        mock_db.fetch_all.return_value = rows

        results = await engine.search_actions()

        assert len(results) == 3
        call_args = mock_db.fetch_all.call_args
        sql = call_args[0][0]
        # Should have no filter clauses beyond WHERE 1=1
        assert "shard = :shard" not in sql
        assert "user_id = :user_id" not in sql

    @pytest.mark.asyncio
    async def test_export_no_event_bus(self, mock_db):
        """Export works when event_bus is None (no emit)."""
        engine = AuditEngine(db=mock_db, event_bus=None)
        mock_db.fetch_all.return_value = [_make_action()]

        result = await engine.export_audit_log(filters={}, format="json")

        assert result["record_count"] == 1
        assert "export_id" in result
        # DB insert should still happen
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_export_csv_empty_records(self, engine, mock_db, mock_events):
        """CSV export with empty results returns empty string."""
        mock_db.fetch_all.return_value = []

        result = await engine.export_audit_log(filters={}, format="csv")

        assert result["format"] == "csv"
        assert result["record_count"] == 0
        assert result["content"] == ""

    @pytest.mark.asyncio
    async def test_export_text_empty_records(self, engine, mock_db, mock_events):
        """Text export with empty results returns 'no records' message."""
        mock_db.fetch_all.return_value = []

        result = await engine.export_audit_log(filters={}, format="text")

        assert result["format"] == "text"
        assert result["record_count"] == 0
        assert "No audit records found" in result["content"]

    @pytest.mark.asyncio
    async def test_export_text_missing_fields(self, engine, mock_db, mock_events):
        """Text export handles records with missing optional fields."""
        row = {
            "id": "a1",
            "tenant_id": None,
            "user_id": None,
            "action_type": "test",
            "shard": None,
            "entity_id": None,
            "session_id": None,
            "description": None,
            "payload": "{}",
            "timestamp": None,
        }
        mock_db.fetch_all.return_value = [row]

        result = await engine.export_audit_log(filters={}, format="text")

        assert result["format"] == "text"
        assert result["record_count"] == 1
        assert isinstance(result["content"], str)

    @pytest.mark.asyncio
    async def test_export_csv_with_none_values(self, engine, mock_db, mock_events):
        """CSV export serializes None values as empty strings."""
        row = _make_action()
        row["user_id"] = None
        row["entity_id"] = None
        row["timestamp"] = None
        mock_db.fetch_all.return_value = [row]

        result = await engine.export_audit_log(filters={}, format="csv")

        content = result["content"]
        reader = csv.reader(io.StringIO(content))
        csv_rows = list(reader)
        assert len(csv_rows) == 2  # header + 1 data row
        # None fields should be empty strings
        data_row = csv_rows[1]
        assert "" in data_row  # At least one empty field


# ---------------------------------------------------------------------------
# Formatting helpers unit tests
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    """Direct tests for _serialize_value and formatting methods."""

    def test_serialize_none(self):
        assert AuditEngine._serialize_value(None) == ""

    def test_serialize_datetime(self):
        dt = datetime(2026, 3, 13, 12, 0, 0, tzinfo=timezone.utc)
        result = AuditEngine._serialize_value(dt)
        assert "2026-03-13" in result

    def test_serialize_string(self):
        assert AuditEngine._serialize_value("hello") == "hello"

    def test_serialize_integer(self):
        assert AuditEngine._serialize_value(42) == "42"

    def test_format_csv_empty(self):
        engine = AuditEngine()
        assert engine._format_csv([]) == ""

    def test_format_text_empty(self):
        engine = AuditEngine()
        assert engine._format_text([]) == "No audit records found."

    def test_format_csv_header_fields(self):
        """CSV header contains expected column names."""
        engine = AuditEngine()
        records = [_make_action()]
        csv_output = engine._format_csv(records)
        header = csv_output.split("\n")[0]
        assert "id" in header
        assert "action_type" in header
        assert "shard" in header
        assert "timestamp" in header

    def test_format_text_structure(self):
        """Text output has title line and separator."""
        engine = AuditEngine()
        records = [_make_action(), _make_action()]
        text_output = engine._format_text(records)
        lines = text_output.split("\n")
        assert "2 records" in lines[0]
        assert "=" * 60 in lines[1]
