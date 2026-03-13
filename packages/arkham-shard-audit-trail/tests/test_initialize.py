"""
AuditTrail Shard - Initialization Tests

Tests for AuditTrailShard with mocked Frame services.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_audit_trail.shard import AuditTrailShard

# === Fixtures ===


@pytest.fixture
def mock_events():
    """Create a mock events service."""
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_db():
    """Create a mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_frame(mock_events, mock_db):
    """Create a mock Frame with all services."""
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


# === Tests ===


class TestShardInitialization:
    """Tests for shard initialization and shutdown."""

    def test_shard_class_attributes(self):
        """Verify shard has required class-level attributes."""
        shard = AuditTrailShard()
        assert shard.name == "audit-trail"
        assert shard.version == "0.1.0"
        assert shard.description != ""

    @pytest.mark.asyncio
    async def test_initialize(self, mock_frame):
        """Test shard initialization with Frame."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        assert shard._frame is mock_frame
        assert shard._db is not None
        assert shard._event_bus is not None

    @pytest.mark.asyncio
    async def test_schema_creation(self, mock_frame, mock_db):
        """Test database schema is created on init."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        # Verify CREATE SCHEMA was called
        calls = [str(c) for c in mock_db.execute.call_args_list]
        schema_calls = [c for c in calls if "CREATE SCHEMA" in c]
        assert len(schema_calls) > 0, "CREATE SCHEMA not called"

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_frame):
        """Test shard shutdown."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        await shard.shutdown()
        # Should not raise

    def test_get_routes(self):
        """Test that get_routes returns the router."""
        shard = AuditTrailShard()
        routes = shard.get_routes()
        assert routes is not None

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, mock_frame, mock_events):
        """Verify shard subscribes to wildcard '*' events."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        mock_events.subscribe.assert_called_once_with("*", shard._on_event)

    @pytest.mark.asyncio
    async def test_shutdown_unsubscribes(self, mock_frame, mock_events):
        """Verify shard unsubscribes from wildcard on shutdown."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        await shard.shutdown()

        mock_events.unsubscribe.assert_called_once_with("*", shard._on_event)

    @pytest.mark.asyncio
    async def test_engine_created(self, mock_frame):
        """Verify AuditEngine is created during initialize."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        assert shard.engine is not None
        from arkham_shard_audit_trail.engine import AuditEngine

        assert isinstance(shard.engine, AuditEngine)

    @pytest.mark.asyncio
    async def test_initialize_no_event_bus(self, mock_db):
        """Shard initializes gracefully without event bus."""
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)

        shard = AuditTrailShard()
        await shard.initialize(frame)

        assert shard.engine is not None
        assert shard._event_bus is None

    @pytest.mark.asyncio
    async def test_shutdown_no_event_bus(self, mock_db):
        """Shard shuts down gracefully without event bus."""
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)

        shard = AuditTrailShard()
        await shard.initialize(frame)
        await shard.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# Event Handler Tests
# ---------------------------------------------------------------------------


class TestEventHandler:
    """Tests for the wildcard event handler _on_event."""

    @pytest.mark.asyncio
    async def test_on_event_logs_action(self, mock_frame, mock_db):
        """Event handler inserts action into database."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)

        # Reset execute call count from schema creation
        mock_db.execute.reset_mock()

        event_data = {
            "event_type": "document.processed",
            "payload": {"id": "doc-1", "title": "Test"},
            "source": "ingest-shard",
        }
        await shard._on_event(event_data)

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO arkham_audit_trail.actions" in sql

    @pytest.mark.asyncio
    async def test_on_event_skips_audit_events(self, mock_frame, mock_db):
        """Event handler skips events prefixed with 'audit.' to prevent loops."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        event_data = {
            "event_type": "audit.export.created",
            "payload": {"export_id": "e1"},
            "source": "audit-trail-shard",
        }
        await shard._on_event(event_data)

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_event_no_db(self, mock_frame):
        """Event handler does nothing if db is None."""
        shard = AuditTrailShard()
        shard._db = None

        event_data = {"event_type": "test.event", "payload": {}, "source": "test"}
        await shard._on_event(event_data)  # Should not raise

    @pytest.mark.asyncio
    async def test_on_event_missing_fields(self, mock_frame, mock_db):
        """Event handler handles events with missing optional fields."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        # Minimal event data -- no payload, no source
        event_data = {}
        await shard._on_event(event_data)

        # Should still insert (with defaults)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_event_db_error_logged(self, mock_frame, mock_db):
        """Event handler catches database errors gracefully."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()
        mock_db.execute.side_effect = Exception("DB connection lost")

        event_data = {"event_type": "test.event", "payload": {}, "source": "test"}
        # Should not raise -- error is caught and logged
        await shard._on_event(event_data)

    @pytest.mark.asyncio
    async def test_on_event_extracts_entity_id_from_document_id(self, mock_frame, mock_db):
        """Event handler extracts entity_id from payload.document_id fallback."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        event_data = {
            "event_type": "document.processed",
            "payload": {"document_id": "doc-42"},
            "source": "ingest",
        }
        await shard._on_event(event_data)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["entity"] == "doc-42"

    @pytest.mark.asyncio
    async def test_on_event_extracts_entity_id_from_item_id(self, mock_frame, mock_db):
        """Event handler extracts entity_id from payload.item_id fallback."""
        shard = AuditTrailShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        event_data = {
            "event_type": "item.updated",
            "payload": {"item_id": "item-99"},
            "source": "claims",
        }
        await shard._on_event(event_data)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["entity"] == "item-99"
