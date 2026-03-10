"""
RespondentIntel Shard - Initialization Tests

Tests for RespondentIntelShard with mocked Frame services.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_respondent_intel.shard import RespondentIntelShard

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
        }.get(name)
    )
    return frame


# === Tests ===


class TestShardInitialization:
    """Tests for shard initialization and shutdown."""

    def test_shard_class_attributes(self):
        """Verify shard has required class-level attributes."""
        shard = RespondentIntelShard()
        assert shard.name == "respondent-intel"
        assert shard.version == "0.1.0"
        assert shard.description != ""

    @pytest.mark.asyncio
    async def test_initialize(self, mock_frame):
        """Test shard initialization with Frame."""
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        assert shard._frame is mock_frame
        assert shard._db is not None
        assert shard._event_bus is not None

    @pytest.mark.asyncio
    async def test_schema_creation(self, mock_frame, mock_db):
        """Test database schema is created on init."""
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        calls = [str(c) for c in mock_db.execute.call_args_list]
        schema_calls = [c for c in calls if "CREATE SCHEMA" in c]
        assert len(schema_calls) > 0, "CREATE SCHEMA not called"

    @pytest.mark.asyncio
    async def test_respondent_profiles_table_created(self, mock_frame, mock_db):
        """Test respondent_profiles table DDL is executed."""
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        profiles_ddl = next((s for s in ddl_calls if "respondent_profiles" in s and "CREATE TABLE" in s), None)
        assert profiles_ddl is not None, "respondent_profiles CREATE TABLE not found"
        # Verify key columns
        assert "case_id" in profiles_ddl
        assert "organization" in profiles_ddl
        assert "strengths" in profiles_ddl
        assert "weaknesses" in profiles_ddl
        assert "document_ids" in profiles_ddl
        assert "JSONB" in profiles_ddl
        assert "UUID" in profiles_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        """Test indexes are created on init."""
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 3, f"Expected at least 3 indexes, got {len(index_calls)}"

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_frame):
        """Test shard shutdown."""
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)
        await shard.shutdown()
        # Should not raise

    def test_get_routes(self):
        """Test that get_routes returns the router."""
        shard = RespondentIntelShard()
        routes = shard.get_routes()
        assert routes is not None
