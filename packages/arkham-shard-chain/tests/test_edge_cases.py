"""
Chain Shard - Edge Case Tests

Covers: no-DB fallbacks, no-event-bus paths, multi-mismatch tampering,
event handler missing payloads, storage failures, hash helper edge paths,
and integrity score boundary conditions.
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_chain.engine import ChainEngine
from arkham_shard_chain.shard import ChainShard

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
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.retrieve = AsyncMock(return_value=(b"file content", {}))
    return storage


@pytest.fixture
def mock_frame(mock_events, mock_db, mock_storage):
    frame = MagicMock()
    frame.database = mock_db
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "events": mock_events,
            "storage": mock_storage,
        }.get(name)
    )
    return frame


@pytest.fixture
def engine_no_db():
    """Engine with no database — all DB-dependent paths return defaults."""
    return ChainEngine(db=None, event_bus=None)


@pytest.fixture
def engine_no_events(mock_db):
    """Engine with DB but no event bus."""
    return ChainEngine(db=mock_db, event_bus=None)


# ---------------------------------------------------------------------------
# ChainEngine: No-DB Fallback Paths
# ---------------------------------------------------------------------------


class TestEngineNoDbFallbacks:
    """When db=None, engine methods should return safe defaults, not crash."""

    @pytest.mark.asyncio
    async def test_verify_hash_no_db_returns_unverified(self, engine_no_db):
        result = await engine_no_db.verify_hash("doc-1", "abc123")
        assert result["verified"] is False
        assert result["stored_hash"] is None
        assert result["current_hash"] == "abc123"
        assert result["document_id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_detect_tampering_no_db_returns_clean(self, engine_no_db):
        result = await engine_no_db.detect_tampering("doc-1")
        assert result["tampered"] is False
        assert result["mismatches"] == []
        assert result["document_id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_score_integrity_no_db_returns_perfect(self, engine_no_db):
        score = await engine_no_db.score_integrity("doc-1")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_provenance_report_no_db_returns_empty_events(self, engine_no_db):
        result = await engine_no_db.generate_provenance_report("doc-1")
        assert result["document_id"] == "doc-1"
        assert result["events"] == []
        assert result["integrity_score"] == 1.0
        assert "report_id" in result
        assert "generated_at" in result


# ---------------------------------------------------------------------------
# ChainEngine: No-Event-Bus Paths
# ---------------------------------------------------------------------------


class TestEngineNoEventBus:
    """When event_bus=None, operations that emit events should not crash."""

    @pytest.mark.asyncio
    async def test_score_integrity_no_event_bus(self, engine_no_events, mock_db):
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]
        # Should not raise even though event_bus is None
        score = await engine_no_events.score_integrity("doc-1")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_detect_tampering_no_event_bus_with_mismatch(self, engine_no_events, mock_db):
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "h1",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "event_id": "e2",
                "sha256_hash": "h2",
                "action": "accessed",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]
        # Tampering detected but no event bus to emit to — should not raise
        result = await engine_no_events.detect_tampering("doc-1")
        assert result["tampered"] is True
        assert len(result["mismatches"]) == 1


# ---------------------------------------------------------------------------
# ChainEngine: Multi-Mismatch Tampering Detection
# ---------------------------------------------------------------------------


class TestMultiMismatchTampering:
    """Verify that rolling baseline correctly flags multiple mismatches."""

    @pytest.mark.asyncio
    async def test_three_sequential_hash_changes(self, mock_db, mock_events):
        """A->B->C should flag 2 mismatches (B vs A, C vs B)."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "hash_a",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "event_id": "e2",
                "sha256_hash": "hash_b",
                "action": "stored",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "event_id": "e3",
                "sha256_hash": "hash_c",
                "action": "accessed",
                "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
        ]

        result = await engine.detect_tampering("doc-1")

        assert result["tampered"] is True
        assert len(result["mismatches"]) == 2
        # First mismatch: e2 expected hash_a got hash_b
        assert result["mismatches"][0]["event_id"] == "e2"
        assert result["mismatches"][0]["expected_hash"] == "hash_a"
        assert result["mismatches"][0]["actual_hash"] == "hash_b"
        # Second mismatch: e3 expected hash_b got hash_c (rolling baseline)
        assert result["mismatches"][1]["event_id"] == "e3"
        assert result["mismatches"][1]["expected_hash"] == "hash_b"
        assert result["mismatches"][1]["actual_hash"] == "hash_c"

    @pytest.mark.asyncio
    async def test_mismatch_then_match_back(self, mock_db, mock_events):
        """A->B->A should flag 2 mismatches (B vs A, A vs B)."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "original",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "event_id": "e2",
                "sha256_hash": "tampered",
                "action": "stored",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "event_id": "e3",
                "sha256_hash": "original",
                "action": "verified",
                "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
        ]

        result = await engine.detect_tampering("doc-1")

        assert result["tampered"] is True
        assert len(result["mismatches"]) == 2


# ---------------------------------------------------------------------------
# ChainEngine: Integrity Score Edge Cases
# ---------------------------------------------------------------------------


class TestIntegrityScoreEdgeCases:
    """Additional boundary conditions for score_integrity."""

    @pytest.mark.asyncio
    async def test_wrong_previous_event_id(self, mock_db, mock_events):
        """previous_event_id points to wrong event (not None, not correct)."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "id": "e2",
                "sha256_hash": "h",
                "previous_event_id": "e999",  # Wrong!
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        # Should penalize as a gap (-0.2) since e999 != e1
        assert score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_all_penalties_applied_long_chain(self, mock_db, mock_events):
        """Long chain with every event having gap + mismatch."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "id": f"e{i}",
                "sha256_hash": f"h{i}",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, i + 1, tzinfo=timezone.utc),
            }
            for i in range(6)
        ]

        score = await engine.score_integrity("doc-1")

        # 5 events after first, each: -0.2 (gap) + -0.3 (mismatch) = -0.5 each
        # 1.0 - (5 * 0.5) = 1.0 - 2.5 = -1.5, floored to 0.0
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_mixed_gaps_no_hash_change(self, mock_db, mock_events):
        """Some events linked, some not, but all same hash."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "id": "e2",
                "sha256_hash": "h",
                "previous_event_id": "e1",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "id": "e3",
                "sha256_hash": "h",
                "previous_event_id": None,  # Gap
                "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
            {
                "id": "e4",
                "sha256_hash": "h",
                "previous_event_id": "e3",
                "timestamp": datetime(2024, 1, 4, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        # e2: linked to e1 (ok), same hash (ok) => no penalty
        # e3: gap (prev=None, expected e2) => -0.2
        # e4: linked to e3 (ok), same hash (ok) => no penalty
        assert score == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Event Handler Edge Cases
# ---------------------------------------------------------------------------


class TestEventHandlerEdgeCases:
    """Shard event handlers with missing/invalid payloads."""

    @pytest.mark.asyncio
    async def test_on_document_ingested_missing_document_id(self, mock_frame, mock_db):
        """Missing document_id in payload => handler returns silently."""
        shard = ChainShard()
        await shard.initialize(mock_frame)

        # Reset db.execute count after initialization
        mock_db.execute.reset_mock()

        await shard._on_document_ingested({"payload": {}})

        # No custody event should have been logged
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_document_ingested_empty_event_data(self, mock_frame, mock_db):
        """Empty event_data => handler returns silently."""
        shard = ChainShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        await shard._on_document_ingested({})

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_document_accessed_missing_document_id(self, mock_frame, mock_db):
        """Missing document_id in accessed payload => handler returns silently."""
        shard = ChainShard()
        await shard.initialize(mock_frame)
        mock_db.execute.reset_mock()

        await shard._on_document_accessed({"payload": {}})

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_document_ingested_exception_handled(self, mock_frame, mock_db, mock_storage):
        """If _log_hash_and_event raises, handler logs warning but does not crash."""
        shard = ChainShard()
        await shard.initialize(mock_frame)

        # Make DB throw on the next execute call
        mock_db.execute.side_effect = RuntimeError("DB connection lost")

        # Should not raise
        await shard._on_document_ingested({"payload": {"document_id": "doc-1", "source": "test"}})

    @pytest.mark.asyncio
    async def test_on_document_accessed_exception_handled(self, mock_frame, mock_db, mock_storage):
        """If _log_hash_and_event raises, handler logs warning but does not crash."""
        shard = ChainShard()
        await shard.initialize(mock_frame)

        mock_db.execute.side_effect = RuntimeError("DB connection lost")

        await shard._on_document_accessed({"payload": {"document_id": "doc-2", "actor": "user"}})


# ---------------------------------------------------------------------------
# _log_hash_and_event Edge Cases
# ---------------------------------------------------------------------------


class TestLogHashAndEventEdgeCases:
    """Edge cases for the internal helper that logs hashes and events."""

    @pytest.mark.asyncio
    async def test_storage_failure_falls_back_to_unknown_hash(self, mock_db, mock_events):
        """When storage.retrieve fails, hash should be 'unknown'."""
        from arkham_shard_chain.api import _log_hash_and_event

        failing_storage = AsyncMock()
        failing_storage.retrieve = AsyncMock(side_effect=IOError("Storage down"))

        event_id = await _log_hash_and_event(
            db=mock_db,
            storage_service=failing_storage,
            event_bus=mock_events,
            document_id="doc-1",
            action="received",
            actor="test",
            location="test",
        )

        assert event_id  # Should still return a valid event_id

        # Check the hash was stored as "unknown"
        hash_insert_call = mock_db.execute.call_args_list[0]
        params = (
            hash_insert_call.args[1] if len(hash_insert_call.args) > 1 else hash_insert_call.kwargs.get("values", {})
        )
        assert params["hash"] == "unknown"

    @pytest.mark.asyncio
    async def test_no_storage_service_uses_unknown_hash(self, mock_db, mock_events):
        """When storage_service is None, hash defaults to 'unknown'."""
        from arkham_shard_chain.api import _log_hash_and_event

        event_id = await _log_hash_and_event(
            db=mock_db,
            storage_service=None,
            event_bus=mock_events,
            document_id="doc-1",
            action="received",
            actor="test",
            location="test",
        )

        assert event_id
        hash_insert_call = mock_db.execute.call_args_list[0]
        params = (
            hash_insert_call.args[1] if len(hash_insert_call.args) > 1 else hash_insert_call.kwargs.get("values", {})
        )
        assert params["hash"] == "unknown"

    @pytest.mark.asyncio
    async def test_no_event_bus_skips_emit(self, mock_db, mock_storage):
        """When event_bus is None, no emit is called."""
        from arkham_shard_chain.api import _log_hash_and_event

        event_id = await _log_hash_and_event(
            db=mock_db,
            storage_service=mock_storage,
            event_bus=None,
            document_id="doc-1",
            action="received",
            actor="test",
            location="test",
        )

        assert event_id
        # DB calls should still happen (hash insert + event insert)
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_hash_verified_flag_set_correctly(self, mock_db, mock_storage, mock_events):
        """When storage retrieves successfully, hash_verified should be True."""
        from arkham_shard_chain.api import _log_hash_and_event

        mock_storage.retrieve.return_value = (b"test content", {})

        await _log_hash_and_event(
            db=mock_db,
            storage_service=mock_storage,
            event_bus=mock_events,
            document_id="doc-1",
            action="received",
            actor="test",
            location="test",
            hash_verified=False,  # explicit False, but storage works => should be True
        )

        # Event insert is second call
        event_insert_call = mock_db.execute.call_args_list[1]
        params = event_insert_call.args[1] if len(event_insert_call.args) > 1 else {}
        # hash_verified should be True since sha256_hash != "unknown"
        assert params["verified"] is True


# ---------------------------------------------------------------------------
# Shard Lifecycle Edge Cases
# ---------------------------------------------------------------------------


class TestShardLifecycleEdgeCases:
    """Edge cases around initialization and shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_without_event_bus(self, mock_db):
        """Shutdown when event bus was never set should not crash."""
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)  # No services available

        shard = ChainShard()
        await shard.initialize(frame)
        await shard.shutdown()

        # Engine should be cleared
        assert shard.engine is None

    @pytest.mark.asyncio
    async def test_schema_creation_without_db(self):
        """If database is None, schema creation should skip gracefully."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)

        shard = ChainShard()
        await shard.initialize(frame)
        # Should not raise, just log a warning

    @pytest.mark.asyncio
    async def test_schema_creation_db_error(self, mock_events):
        """If DB throws during schema creation, error is logged but init continues."""
        failing_db = AsyncMock()
        failing_db.execute = AsyncMock(side_effect=RuntimeError("Connection refused"))

        frame = MagicMock()
        frame.database = failing_db
        frame.get_service = MagicMock(side_effect=lambda name: {"events": mock_events, "storage": None}.get(name))

        shard = ChainShard()
        # Should not raise — error is caught and logged
        await shard.initialize(frame)
        assert shard.engine is not None

    @pytest.mark.asyncio
    async def test_event_subscriptions_registered(self, mock_frame, mock_events):
        """Both event subscriptions should be registered during init."""
        shard = ChainShard()
        await shard.initialize(mock_frame)

        subscribe_calls = [str(c) for c in mock_events.subscribe.call_args_list]
        assert any("ingest.document.processed" in c for c in subscribe_calls)
        assert any("documents.accessed" in c for c in subscribe_calls)

    @pytest.mark.asyncio
    async def test_event_subscriptions_unregistered_on_shutdown(self, mock_frame, mock_events):
        """Both event subscriptions should be unregistered during shutdown."""
        shard = ChainShard()
        await shard.initialize(mock_frame)
        await shard.shutdown()

        unsubscribe_calls = [str(c) for c in mock_events.unsubscribe.call_args_list]
        assert any("ingest.document.processed" in c for c in unsubscribe_calls)
        assert any("documents.accessed" in c for c in unsubscribe_calls)


# ---------------------------------------------------------------------------
# Provenance Report Edge Cases
# ---------------------------------------------------------------------------


class TestProvenanceReportEdgeCases:
    """Edge cases for generate_provenance_report."""

    @pytest.mark.asyncio
    async def test_report_timestamp_format(self, mock_db, mock_events):
        """Timestamps in events should be ISO formatted strings."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        ts = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        mock_db.fetch_all.return_value = [
            {"id": "e1", "action": "received", "actor": "scanner", "sha256_hash": "abc", "timestamp": ts},
        ]

        result = await engine.generate_provenance_report("doc-1")

        assert result["events"][0]["timestamp"] == ts.isoformat()

    @pytest.mark.asyncio
    async def test_report_timestamp_string_passthrough(self, mock_db, mock_events):
        """If timestamp is already a string, it should pass through."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "action": "received",
                "actor": "scanner",
                "sha256_hash": "abc",
                "timestamp": "2024-06-15T14:30:00",
            },
        ]

        result = await engine.generate_provenance_report("doc-1")

        assert result["events"][0]["timestamp"] == "2024-06-15T14:30:00"

    @pytest.mark.asyncio
    async def test_report_includes_generated_at(self, mock_db, mock_events):
        """Report should include a generated_at ISO timestamp."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = []

        result = await engine.generate_provenance_report("doc-1")

        assert "generated_at" in result
        # Should be parseable as ISO timestamp
        datetime.fromisoformat(result["generated_at"])

    @pytest.mark.asyncio
    async def test_report_with_missing_optional_fields(self, mock_db, mock_events):
        """Events with missing optional fields should use defaults."""
        engine = ChainEngine(db=mock_db, event_bus=mock_events)
        mock_db.fetch_all.return_value = [
            {"id": "e1", "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        ]

        result = await engine.generate_provenance_report("doc-1")

        event = result["events"][0]
        assert event["action"] == ""
        assert event["actor"] == ""
        assert event["hash"] == ""
