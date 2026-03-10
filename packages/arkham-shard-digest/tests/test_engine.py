"""
Digest Shard - Engine Tests

Tests for DigestEngine domain logic: change logging, briefing generation,
action item extraction, and subscription management.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_digest.engine import DigestEngine

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_events():
    """Create a mock event bus."""
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    """Create a mock LLM service."""
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_events):
    """Create a DigestEngine with mocked services (no LLM)."""
    return DigestEngine(db=mock_db, event_bus=mock_events, llm_service=None)


@pytest.fixture
def engine_with_llm(mock_db, mock_events, mock_llm):
    """Create a DigestEngine with all services including LLM."""
    return DigestEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)


# =============================================================================
# Change Log Tests
# =============================================================================


class TestLogChange:
    """Tests for engine.log_change."""

    @pytest.mark.asyncio
    async def test_log_change_persists(self, engine, mock_db):
        """Verify log_change inserts into DB and returns an entry ID."""
        entry_id = await engine.log_change(
            event_type="disclosure.breach.detected",
            event_data={
                "project_id": "proj-1",
                "entity_type": "document",
                "entity_id": "doc-42",
                "description": "Disclosure breach in witness statement",
            },
        )

        # Returns a valid UUID string
        assert entry_id is not None
        uuid.UUID(entry_id)  # Validates UUID format

        # DB execute was called with INSERT
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "INSERT INTO arkham_digest.change_log" in sql
        assert params["id"] == entry_id
        assert params["project_id"] == "proj-1"
        assert params["shard"] == "disclosure"
        assert params["action"] == "breach.detected"
        assert params["entity_type"] == "document"
        assert params["entity_id"] == "doc-42"
        assert params["description"] == "Disclosure breach in witness statement"

    @pytest.mark.asyncio
    async def test_log_change_no_db(self):
        """Verify log_change works without DB (returns ID, no error)."""
        engine = DigestEngine(db=None, event_bus=None)
        entry_id = await engine.log_change("test.event", {"project_id": "p1"})

        assert entry_id is not None
        uuid.UUID(entry_id)

    @pytest.mark.asyncio
    async def test_log_change_defaults(self, engine, mock_db):
        """Verify log_change uses sensible defaults for missing fields."""
        entry_id = await engine.log_change("simple.event", {})

        params = mock_db.execute.call_args[0][1]
        assert params["project_id"] == "default"
        assert params["shard"] == "simple"
        assert params["action"] == "event"


# =============================================================================
# Briefing Generation Tests
# =============================================================================


class TestGenerateBriefing:
    """Tests for engine.generate_briefing."""

    @pytest.mark.asyncio
    async def test_generate_briefing_daily(self, engine, mock_db, mock_events):
        """Daily briefing with changes produces correct structure."""
        # Simulate changes in DB
        mock_db.fetch_all.return_value = [
            {
                "id": "c1",
                "project_id": "proj-1",
                "shard": "disclosure",
                "entity_type": "document",
                "entity_id": "doc-1",
                "action": "breach.detected",
                "description": "Disclosure breach in witness statement",
                "timestamp": datetime(2026, 3, 10, 9, 0),
            },
            {
                "id": "c2",
                "project_id": "proj-1",
                "shard": "deadlines",
                "entity_type": "deadline",
                "entity_id": "dl-1",
                "action": "deadline.approaching",
                "description": "Filing deadline in 3 days",
                "timestamp": datetime(2026, 3, 10, 8, 0),
            },
        ]

        result = await engine.generate_briefing("proj-1", briefing_type="daily")

        # Verify structure
        assert "briefing_id" in result
        assert "summary" in result
        assert "action_items" in result
        assert "change_count" in result
        assert "priority_items" in result

        # Verify change count matches
        assert result["change_count"] == 2

        # Verify briefing was persisted
        insert_calls = [c for c in mock_db.execute.call_args_list if "INSERT INTO arkham_digest.briefings" in str(c)]
        assert len(insert_calls) == 1

        # Verify event was emitted
        mock_events.emit.assert_called_once()
        emit_args = mock_events.emit.call_args
        assert emit_args[0][0] == "digest.briefing.generated"

    @pytest.mark.asyncio
    async def test_generate_briefing_no_changes(self, engine, mock_db):
        """Empty briefing when no changes exist."""
        mock_db.fetch_all.return_value = []

        result = await engine.generate_briefing("proj-1", briefing_type="daily")

        assert result["change_count"] == 0
        assert result["action_items"] == []
        assert "briefing_id" in result
        assert "No changes" in result["summary"] or result["summary"] != ""

    @pytest.mark.asyncio
    async def test_generate_briefing_action_items_from_breach(self, engine, mock_db):
        """Breach events should produce action items in briefing."""
        mock_db.fetch_all.return_value = [
            {
                "id": "c1",
                "project_id": "proj-1",
                "shard": "disclosure",
                "entity_type": "document",
                "entity_id": "doc-1",
                "action": "breach.detected",
                "description": "Critical disclosure breach found",
                "timestamp": datetime(2026, 3, 10, 9, 0),
            },
        ]

        result = await engine.generate_briefing("proj-1")

        # Breach should generate an action item
        assert len(result["action_items"]) > 0


# =============================================================================
# Action Item Extraction Tests
# =============================================================================


class TestExtractActionItems:
    """Tests for engine.extract_action_items."""

    @pytest.mark.asyncio
    async def test_extract_action_items_breach(self, engine):
        """Breach event produces an action item."""
        changes = [
            {
                "action": "breach.detected",
                "description": "Disclosure breach in expert report",
                "entity_type": "document",
            },
        ]

        items = await engine.extract_action_items(changes)

        assert len(items) == 1
        assert "breach" in items[0].lower() or "Disclosure" in items[0]

    @pytest.mark.asyncio
    async def test_extract_action_items_deadline(self, engine):
        """Deadline event produces an action item."""
        changes = [
            {
                "action": "deadline.approaching",
                "description": "Filing deadline in 3 days",
                "entity_type": "deadline",
            },
        ]

        items = await engine.extract_action_items(changes)

        assert len(items) == 1
        assert "deadline" in items[0].lower() or "Filing" in items[0]

    @pytest.mark.asyncio
    async def test_extract_action_items_no_actions(self, engine):
        """Non-actionable events produce no action items."""
        changes = [
            {
                "action": "created",
                "description": "New note added to case file",
                "entity_type": "note",
            },
            {
                "action": "updated",
                "description": "Case metadata refreshed",
                "entity_type": "metadata",
            },
        ]

        items = await engine.extract_action_items(changes)

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_extract_action_items_multiple_patterns(self, engine):
        """Multiple actionable patterns detected across changes."""
        changes = [
            {"action": "breach.detected", "description": "Disclosure breach", "entity_type": "doc"},
            {"action": "gap.identified", "description": "Evidence gap found", "entity_type": "evidence"},
            {"action": "evasion.pattern", "description": "Evasion pattern detected", "entity_type": "witness"},
            {"action": "updated", "description": "Note updated", "entity_type": "note"},
        ]

        items = await engine.extract_action_items(changes)

        assert len(items) == 3  # breach, gap, evasion -- not the note update

    @pytest.mark.asyncio
    async def test_extract_action_items_empty_list(self, engine):
        """Empty change list returns empty action items."""
        items = await engine.extract_action_items([])
        assert items == []


# =============================================================================
# Subscription Management Tests
# =============================================================================


class TestManageSubscription:
    """Tests for engine.manage_subscription."""

    @pytest.mark.asyncio
    async def test_manage_subscription_create(self, engine, mock_db):
        """New subscription is created with correct fields."""
        mock_db.fetch_one.return_value = None  # No existing subscription

        result = await engine.manage_subscription(
            user_id="user-1",
            project_id="proj-1",
            frequency="daily",
        )

        assert "subscription_id" in result
        assert result["user_id"] == "user-1"
        assert result["project_id"] == "proj-1"
        assert result["frequency"] == "daily"
        assert "next_briefing" in result

        # Verify INSERT was called (after the SELECT check)
        insert_calls = [
            c for c in mock_db.execute.call_args_list if "INSERT INTO arkham_digest.subscriptions" in str(c)
        ]
        assert len(insert_calls) == 1

    @pytest.mark.asyncio
    async def test_manage_subscription_update(self, engine, mock_db):
        """Existing subscription frequency is updated."""
        existing_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": existing_id}

        result = await engine.manage_subscription(
            user_id="user-1",
            project_id="proj-1",
            frequency="weekly",
        )

        assert result["subscription_id"] == existing_id
        assert result["frequency"] == "weekly"

        # Verify UPDATE was called, not INSERT
        update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE arkham_digest.subscriptions" in str(c)]
        insert_calls = [
            c for c in mock_db.execute.call_args_list if "INSERT INTO arkham_digest.subscriptions" in str(c)
        ]
        assert len(update_calls) == 1
        assert len(insert_calls) == 0

    @pytest.mark.asyncio
    async def test_manage_subscription_next_briefing(self, engine, mock_db):
        """Next briefing time is calculated from frequency."""
        mock_db.fetch_one.return_value = None

        result = await engine.manage_subscription("user-1", "proj-1", frequency="weekly")

        # next_briefing should be an ISO timestamp string
        assert result["next_briefing"] is not None
        # Parse it to verify it's valid
        datetime.fromisoformat(result["next_briefing"])
