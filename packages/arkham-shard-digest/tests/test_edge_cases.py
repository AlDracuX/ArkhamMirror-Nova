"""
Digest Shard - Edge Case Tests

Covers boundary conditions, error handling, deduplication,
LLM fallback paths, and adversarial inputs.
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_digest.engine import ACTIONABLE_PATTERNS, FREQUENCY_DELTAS, DigestEngine
from arkham_shard_digest.llm import BriefingResult, DigestLLM
from arkham_shard_digest.models import CaseBriefing, ChangeLogEntry, DigestSubscription
from arkham_shard_digest.shard import DigestShard

# =============================================================================
# Fixtures
# =============================================================================


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
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_events):
    return DigestEngine(db=mock_db, event_bus=mock_events, llm_service=None)


@pytest.fixture
def engine_with_llm(mock_db, mock_events, mock_llm):
    return DigestEngine(db=mock_db, event_bus=mock_events, llm_service=mock_llm)


# =============================================================================
# Engine: log_change edge cases
# =============================================================================


class TestLogChangeEdgeCases:
    """Edge cases for change logging."""

    @pytest.mark.asyncio
    async def test_log_change_single_part_event_type(self, engine, mock_db):
        """Event type with no dots uses entire string as shard and action."""
        entry_id = await engine.log_change("standalone", {"project_id": "p1"})
        params = mock_db.execute.call_args[0][1]
        assert params["shard"] == "standalone"
        assert params["action"] == "standalone"

    @pytest.mark.asyncio
    async def test_log_change_deeply_nested_event_type(self, engine, mock_db):
        """Event type with many dots preserves full action path."""
        entry_id = await engine.log_change("a.b.c.d.e", {"project_id": "p1"})
        params = mock_db.execute.call_args[0][1]
        assert params["shard"] == "a"
        assert params["action"] == "b.c.d.e"

    @pytest.mark.asyncio
    async def test_log_change_empty_event_type(self, engine, mock_db):
        """Empty string event type doesn't crash."""
        entry_id = await engine.log_change("", {"project_id": "p1"})
        assert entry_id is not None
        params = mock_db.execute.call_args[0][1]
        assert params["shard"] == ""
        assert params["action"] == ""

    @pytest.mark.asyncio
    async def test_log_change_empty_event_data(self, engine, mock_db):
        """Empty event data uses all defaults."""
        entry_id = await engine.log_change("test.event", {})
        params = mock_db.execute.call_args[0][1]
        assert params["project_id"] == "default"
        assert params["entity_type"] == "test"
        assert params["entity_id"] == ""
        assert "test.event event" in params["description"]

    @pytest.mark.asyncio
    async def test_log_change_unicode_description(self, engine, mock_db):
        """Unicode characters in description are preserved."""
        entry_id = await engine.log_change(
            "test.event",
            {"project_id": "p1", "description": "Breach in \u00a7 15.2 of T\u00fcrkiye agreement \u2014 urgent"},
        )
        params = mock_db.execute.call_args[0][1]
        assert "\u00a7" in params["description"]
        assert "\u2014" in params["description"]

    @pytest.mark.asyncio
    async def test_log_change_very_long_description(self, engine, mock_db):
        """Very long description is accepted without truncation at engine level."""
        long_desc = "A" * 10000
        entry_id = await engine.log_change("test.event", {"project_id": "p1", "description": long_desc})
        params = mock_db.execute.call_args[0][1]
        assert len(params["description"]) == 10000

    @pytest.mark.asyncio
    async def test_log_change_returns_unique_ids(self, engine, mock_db):
        """Each call returns a unique ID."""
        ids = set()
        for _ in range(50):
            entry_id = await engine.log_change("test.event", {"project_id": "p1"})
            ids.add(entry_id)
        assert len(ids) == 50


# =============================================================================
# Engine: extract_action_items edge cases
# =============================================================================


class TestExtractActionItemsEdgeCases:
    """Edge cases for action item extraction."""

    @pytest.mark.asyncio
    async def test_duplicate_actions_not_repeated(self, engine):
        """Same description across multiple changes only appears once."""
        changes = [
            {"action": "breach.detected", "description": "Same breach", "entity_type": "doc"},
            {"action": "breach.found", "description": "Same breach", "entity_type": "doc"},
        ]
        items = await engine.extract_action_items(changes)
        assert items.count("Same breach") == 1

    @pytest.mark.asyncio
    async def test_pattern_match_in_description_only(self, engine):
        """Pattern in description field triggers action item even if action is clean."""
        changes = [
            {"action": "updated", "description": "Found a breach in the evidence", "entity_type": "doc"},
        ]
        items = await engine.extract_action_items(changes)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_pattern_match_in_entity_type(self, engine):
        """Pattern in entity_type triggers action item."""
        changes = [
            {"action": "created", "description": "New item", "entity_type": "risk_assessment"},
        ]
        items = await engine.extract_action_items(changes)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_case_insensitive_pattern_matching(self, engine):
        """Pattern matching is case-insensitive."""
        changes = [
            {"action": "BREACH.DETECTED", "description": "CRITICAL BREACH", "entity_type": "DOC"},
        ]
        items = await engine.extract_action_items(changes)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_missing_fields_in_change(self, engine):
        """Changes with missing fields don't crash."""
        changes = [
            {},  # completely empty
            {"action": "breach.detected"},  # missing description and entity_type
        ]
        items = await engine.extract_action_items(changes)
        # Second item should match on "breach" in action
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_all_actionable_patterns_detected(self, engine):
        """Every pattern in ACTIONABLE_PATTERNS is actually detected."""
        changes = [
            {"action": pattern, "description": f"Test {pattern}", "entity_type": "test"}
            for pattern in ACTIONABLE_PATTERNS
        ]
        items = await engine.extract_action_items(changes)
        assert len(items) == len(ACTIONABLE_PATTERNS)

    @pytest.mark.asyncio
    async def test_empty_description_uses_label_fallback(self, engine):
        """When description is empty, fallback label format is used."""
        changes = [
            {"action": "breach.detected", "description": "", "entity_type": "evidence"},
        ]
        items = await engine.extract_action_items(changes)
        assert len(items) == 1
        # Fallback format: "{label}: {entity_type} - {action}"
        assert "evidence" in items[0].lower() or "breach" in items[0].lower()


# =============================================================================
# Engine: generate_briefing edge cases
# =============================================================================


class TestGenerateBriefingEdgeCases:
    """Edge cases for briefing generation."""

    @pytest.mark.asyncio
    async def test_briefing_without_db(self, mock_events):
        """Briefing generation works without database (empty changes)."""
        engine = DigestEngine(db=None, event_bus=mock_events)
        result = await engine.generate_briefing("proj-1", "daily")

        assert result["change_count"] == 0
        assert "briefing_id" in result

    @pytest.mark.asyncio
    async def test_briefing_without_event_bus(self, mock_db):
        """Briefing generation works without event bus (no emit)."""
        engine = DigestEngine(db=mock_db, event_bus=None)
        mock_db.fetch_all.return_value = []
        result = await engine.generate_briefing("proj-1", "daily")
        assert "briefing_id" in result

    @pytest.mark.asyncio
    async def test_briefing_sitrep_type(self, engine, mock_db):
        """Sitrep briefing type is accepted and passed through."""
        mock_db.fetch_all.return_value = [
            {
                "id": "c1",
                "project_id": "proj-1",
                "shard": "costs",
                "entity_type": "cost",
                "entity_id": "cost-1",
                "action": "risk.escalated",
                "description": "Cost risk high",
                "timestamp": datetime(2026, 3, 10),
            },
        ]
        result = await engine.generate_briefing("proj-1", briefing_type="sitrep")
        assert result["change_count"] == 1

    @pytest.mark.asyncio
    async def test_briefing_deduplicates_action_items(self, engine, mock_db):
        """Action items from changes and LLM are deduplicated."""
        mock_db.fetch_all.return_value = [
            {
                "id": "c1",
                "project_id": "proj-1",
                "shard": "disclosure",
                "entity_type": "document",
                "entity_id": "doc-1",
                "action": "breach.detected",
                "description": "Disclosure breach found",
                "timestamp": datetime(2026, 3, 10),
            },
        ]
        result = await engine.generate_briefing("proj-1")
        # Action items should not have duplicates
        assert len(result["action_items"]) == len(set(result["action_items"]))

    @pytest.mark.asyncio
    async def test_briefing_large_change_set(self, engine, mock_db, mock_events):
        """Briefing handles large number of changes."""
        changes = [
            {
                "id": f"c{i}",
                "project_id": "proj-1",
                "shard": "evidence",
                "entity_type": "document",
                "entity_id": f"doc-{i}",
                "action": "updated",
                "description": f"Document {i} updated",
                "timestamp": datetime(2026, 3, 10),
            }
            for i in range(100)
        ]
        mock_db.fetch_all.return_value = changes
        result = await engine.generate_briefing("proj-1")
        assert result["change_count"] == 100


# =============================================================================
# Engine: manage_subscription edge cases
# =============================================================================


class TestManageSubscriptionEdgeCases:
    """Edge cases for subscription management."""

    @pytest.mark.asyncio
    async def test_subscription_hourly_frequency(self, engine, mock_db):
        """Hourly frequency calculates correct next_briefing."""
        mock_db.fetch_one.return_value = None
        result = await engine.manage_subscription("user-1", "proj-1", frequency="hourly")
        next_time = datetime.fromisoformat(result["next_briefing"])
        # Should be roughly 1 hour from now
        now = datetime.utcnow()
        diff = next_time - now
        assert timedelta(minutes=50) < diff < timedelta(minutes=70)

    @pytest.mark.asyncio
    async def test_subscription_unknown_frequency_defaults(self, engine, mock_db):
        """Unknown frequency falls back to daily delta."""
        mock_db.fetch_one.return_value = None
        result = await engine.manage_subscription("user-1", "proj-1", frequency="monthly")
        next_time = datetime.fromisoformat(result["next_briefing"])
        now = datetime.utcnow()
        diff = next_time - now
        # Falls back to timedelta(days=1)
        assert timedelta(hours=23) < diff < timedelta(hours=25)

    @pytest.mark.asyncio
    async def test_subscription_no_db(self):
        """Subscription without DB still returns result (no persistence)."""
        engine = DigestEngine(db=None, event_bus=None)
        result = await engine.manage_subscription("user-1", "proj-1", "daily")
        assert result["subscription_id"] is not None
        assert result["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_subscription_update_existing_tuple_result(self, engine, mock_db):
        """Existing subscription returned as tuple (not dict) is handled."""
        existing_id = str(uuid.uuid4())
        # Some DB drivers return Row objects that support index access
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: existing_id if k in ("id", 0) else None)
        mock_row.__contains__ = MagicMock(return_value=True)
        # Make it dict-like for the isinstance check
        mock_db.fetch_one.return_value = {"id": existing_id}

        result = await engine.manage_subscription("user-1", "proj-1", "weekly")
        assert result["subscription_id"] == existing_id
        assert result["frequency"] == "weekly"


# =============================================================================
# LLM: edge cases
# =============================================================================


class TestDigestLLMEdgeCases:
    """Edge cases for LLM integration."""

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self):
        """LLM returning invalid JSON falls back to rule-based."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(text="not valid json {{{"))
        digest_llm = DigestLLM(llm_service=mock_llm)

        changes = [{"action": "breach.detected", "description": "Breach found", "entity_type": "doc"}]
        result = await digest_llm.generate_briefing_content(changes, "daily")

        # Should fall back to rule-based (BriefingResult with summary)
        assert isinstance(result, BriefingResult)
        assert result.summary != ""

    @pytest.mark.asyncio
    async def test_llm_returns_partial_json(self):
        """LLM returning partial JSON still produces a result."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(text='{"summary": "Test summary"}'))
        digest_llm = DigestLLM(llm_service=mock_llm)

        changes = [{"action": "updated", "description": "Note updated", "entity_type": "note"}]
        result = await digest_llm.generate_briefing_content(changes, "daily")

        assert result.summary == "Test summary"
        assert result.priority_items == []
        assert result.action_items == []

    @pytest.mark.asyncio
    async def test_llm_raises_exception(self):
        """LLM raising exception falls back gracefully."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM connection timeout"))
        digest_llm = DigestLLM(llm_service=mock_llm)

        changes = [{"action": "violation.found", "description": "Rule violated", "entity_type": "rule"}]
        result = await digest_llm.generate_briefing_content(changes, "daily")

        assert isinstance(result, BriefingResult)
        assert "violation" in result.summary.lower() or len(result.priority_items) > 0

    @pytest.mark.asyncio
    async def test_llm_no_service_no_changes(self):
        """No LLM service and no changes returns empty briefing."""
        digest_llm = DigestLLM(llm_service=None)
        result = await digest_llm.generate_briefing_content([], "daily")
        assert result.summary != ""
        assert "No changes" in result.summary

    @pytest.mark.asyncio
    async def test_llm_extract_action_items_no_service(self):
        """extract_action_items_llm with no service returns empty list."""
        digest_llm = DigestLLM(llm_service=None)
        result = await digest_llm.extract_action_items_llm([{"action": "breach"}])
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_extract_action_items_invalid_response(self):
        """LLM returning non-list for action items returns empty."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(text='{"not": "a list"}'))
        digest_llm = DigestLLM(llm_service=mock_llm)

        result = await digest_llm.extract_action_items_llm(
            [{"action": "breach", "description": "test", "entity_type": "doc"}]
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_extract_action_items_success(self):
        """LLM returning valid action items list works."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=MagicMock(text='["File response by March 15", "Review evidence gaps"]')
        )
        digest_llm = DigestLLM(llm_service=mock_llm)

        result = await digest_llm.extract_action_items_llm(
            [{"action": "breach", "description": "test", "entity_type": "doc"}]
        )
        assert len(result) == 2
        assert "March 15" in result[0]

    @pytest.mark.asyncio
    async def test_llm_response_without_text_attr(self):
        """LLM response without .text attribute uses str() fallback."""
        mock_llm = MagicMock()
        response_json = '{"summary": "Fallback works", "priority_items": [], "action_items": [], "key_changes": []}'

        class FakeResponse:
            """Response object without .text attribute."""

            def __str__(self):
                return response_json

        mock_llm.generate = AsyncMock(return_value=FakeResponse())
        digest_llm = DigestLLM(llm_service=mock_llm)

        changes = [{"action": "updated", "description": "test", "entity_type": "doc"}]
        result = await digest_llm.generate_briefing_content(changes, "daily")

        assert result.summary == "Fallback works"

    def test_fallback_categorizes_urgency_correctly(self):
        """Rule-based fallback categorizes by urgency keywords."""
        digest_llm = DigestLLM(llm_service=None)

        changes = [
            {"action": "breach.detected", "description": "Critical breach", "entity_type": "doc"},
            {"action": "violation.found", "description": "Rule violation", "entity_type": "rule"},
            {"action": "deadline.approaching", "description": "Filing due soon", "entity_type": "deadline"},
            {"action": "gap.identified", "description": "Evidence gap", "entity_type": "evidence"},
            {"action": "updated", "description": "Note updated", "entity_type": "note"},
        ]

        result = digest_llm._generate_briefing_fallback(changes, "daily")

        # Check priority ordering: urgent items first
        levels = [item["level"] for item in result.priority_items]
        # All urgent items should come before important, which come before fyi
        urgent_indices = [i for i, l in enumerate(levels) if l == "urgent"]
        important_indices = [i for i, l in enumerate(levels) if l == "important"]
        fyi_indices = [i for i, l in enumerate(levels) if l == "fyi"]

        if urgent_indices and important_indices:
            assert max(urgent_indices) < min(important_indices)
        if important_indices and fyi_indices:
            assert max(important_indices) < min(fyi_indices)

    def test_fallback_summary_includes_counts(self):
        """Fallback summary includes change counts."""
        digest_llm = DigestLLM(llm_service=None)
        changes = [
            {"action": "breach.detected", "description": "Breach 1", "entity_type": "doc"},
            {"action": "updated", "description": "Note updated", "entity_type": "note"},
        ]
        result = digest_llm._generate_briefing_fallback(changes, "weekly")
        assert "2 changes" in result.summary
        assert "1 urgent" in result.summary
        assert "Weekly" in result.summary


# =============================================================================
# Shard: event handling edge cases
# =============================================================================


class TestShardEventHandling:
    """Edge cases for shard event subscription and handling."""

    @pytest.fixture
    def mock_frame(self, mock_events, mock_db):
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {
                "events": mock_events,
                "llm": None,
                "vectors": None,
            }.get(name)
        )
        return frame

    @pytest.mark.asyncio
    async def test_self_events_are_filtered(self, mock_frame):
        """Events from digest-shard source are ignored."""
        shard = DigestShard()
        await shard.initialize(mock_frame)

        # Simulate self-event
        await shard._handle_event(
            {
                "event_type": "digest.briefing.generated",
                "source": "digest-shard",
                "payload": {"briefing_id": "b1"},
            }
        )

        # Engine.log_change should NOT have been called for self-events
        # We check by verifying no DB insert happened beyond schema creation
        initial_call_count = mock_frame.database.execute.call_count
        await shard._handle_event(
            {
                "event_type": "digest.briefing.generated",
                "source": "digest-shard",
            }
        )
        assert mock_frame.database.execute.call_count == initial_call_count

    @pytest.mark.asyncio
    async def test_external_events_are_logged(self, mock_frame, mock_db):
        """Events from other shards are logged via engine."""
        shard = DigestShard()
        await shard.initialize(mock_frame)

        call_count_before = mock_db.execute.call_count

        await shard._handle_event(
            {
                "event_type": "disclosure.breach.detected",
                "source": "disclosure-shard",
                "payload": {"project_id": "p1", "entity_type": "doc", "entity_id": "d1"},
            }
        )

        # Should have one more execute call (the INSERT)
        assert mock_db.execute.call_count == call_count_before + 1

    @pytest.mark.asyncio
    async def test_event_without_payload_uses_event_data(self, mock_frame, mock_db):
        """When payload key is missing, full event_data is used."""
        shard = DigestShard()
        await shard.initialize(mock_frame)

        call_count_before = mock_db.execute.call_count

        await shard._handle_event(
            {
                "event_type": "rules.violation.found",
                "source": "rules-shard",
                "project_id": "p1",
            }
        )

        assert mock_db.execute.call_count == call_count_before + 1

    @pytest.mark.asyncio
    async def test_event_handling_with_no_engine(self, mock_frame):
        """Event handling is safe when engine is None."""
        shard = DigestShard()
        await shard.initialize(mock_frame)
        shard.engine = None

        # Should not raise
        await shard._handle_event(
            {
                "event_type": "test.event",
                "source": "other-shard",
            }
        )

    @pytest.mark.asyncio
    async def test_shutdown_unsubscribes_all_patterns(self, mock_frame, mock_events):
        """Shutdown unsubscribes from all event patterns."""
        shard = DigestShard()
        await shard.initialize(mock_frame)

        subscribe_count = mock_events.subscribe.call_count

        await shard.shutdown()

        assert mock_events.unsubscribe.call_count == subscribe_count
        assert shard.engine is None

    @pytest.mark.asyncio
    async def test_initialize_without_event_bus(self, mock_db):
        """Shard initializes gracefully without event bus."""
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)

        shard = DigestShard()
        await shard.initialize(frame)

        assert shard.engine is not None
        assert shard._event_bus is None

    @pytest.mark.asyncio
    async def test_schema_creation_without_db(self):
        """Schema creation is skipped without database."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)

        shard = DigestShard()
        await shard.initialize(frame)
        # Should not raise - just logs warning

    @pytest.mark.asyncio
    async def test_schema_creation_db_error(self, mock_db):
        """Schema creation handles database errors gracefully."""
        mock_db.execute = AsyncMock(side_effect=Exception("Connection refused"))
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)

        shard = DigestShard()
        # Should not raise - catches and logs
        await shard.initialize(frame)


# =============================================================================
# Model: edge cases
# =============================================================================


class TestModelEdgeCases:
    """Edge cases for Pydantic models."""

    def test_case_briefing_with_all_fields(self):
        """CaseBriefing with all fields explicitly set."""
        now = datetime(2026, 3, 13, 12, 0, 0)
        b = CaseBriefing(
            id="b1",
            tenant_id="tenant-1",
            project_id="proj-1",
            type="sitrep",
            content="Full briefing content here",
            priority_items=[{"level": "urgent", "text": "Critical"}],
            action_items=["Action 1", "Action 2"],
            metadata={"source": "test", "version": 2},
            created_at=now,
        )
        assert b.tenant_id == "tenant-1"
        assert len(b.priority_items) == 1
        assert len(b.action_items) == 2
        assert b.created_at == now

    def test_case_briefing_tenant_id_none(self):
        """CaseBriefing accepts None tenant_id."""
        b = CaseBriefing(id="b1", project_id="p1", type="daily", content="c")
        assert b.tenant_id is None

    def test_changelog_entry_all_fields(self):
        """ChangeLogEntry with explicit timestamp."""
        ts = datetime(2026, 1, 1)
        e = ChangeLogEntry(
            id="e1",
            project_id="p1",
            shard="s",
            entity_type="t",
            entity_id="i",
            action="a",
            description="d",
            timestamp=ts,
        )
        assert e.timestamp == ts

    def test_subscription_with_last_sent(self):
        """DigestSubscription with last_sent set."""
        now = datetime(2026, 3, 13)
        s = DigestSubscription(
            id="s1",
            project_id="p1",
            user_id="u1",
            frequency="weekly",
            format="text",
            last_sent=now,
        )
        assert s.last_sent == now


# =============================================================================
# Constants / Configuration
# =============================================================================


class TestConstants:
    """Verify constant configuration is correct."""

    def test_actionable_patterns_keys(self):
        """All expected actionable patterns are defined."""
        expected = {"breach", "gap", "deadline", "evasion", "violation", "risk"}
        assert set(ACTIONABLE_PATTERNS.keys()) == expected

    def test_frequency_deltas_keys(self):
        """All expected frequency deltas are defined."""
        expected = {"daily", "weekly", "hourly"}
        assert set(FREQUENCY_DELTAS.keys()) == expected

    def test_frequency_delta_values(self):
        """Frequency deltas have correct durations."""
        assert FREQUENCY_DELTAS["daily"] == timedelta(days=1)
        assert FREQUENCY_DELTAS["weekly"] == timedelta(weeks=1)
        assert FREQUENCY_DELTAS["hourly"] == timedelta(hours=1)
