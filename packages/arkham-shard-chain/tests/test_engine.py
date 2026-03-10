"""
Chain Shard - Engine Tests

Tests for ChainEngine: hash verification, tampering detection,
provenance reporting, and integrity scoring.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_chain.engine import ChainEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Create a mock events service."""
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


@pytest.fixture
def engine(mock_db, mock_events):
    """Create a ChainEngine with mocked dependencies."""
    return ChainEngine(db=mock_db, event_bus=mock_events)


@pytest.fixture
def engine_no_events(mock_db):
    """Create a ChainEngine without event bus."""
    return ChainEngine(db=mock_db, event_bus=None)


# ---------------------------------------------------------------------------
# verify_hash tests
# ---------------------------------------------------------------------------


class TestVerifyHash:
    """Tests for hash verification against stored records."""

    @pytest.mark.asyncio
    async def test_verify_hash_matches(self, engine, mock_db):
        """Stored hash == current hash => verified: True."""
        the_hash = "abc123def456"  # pragma: allowlist secret
        mock_db.fetch_one.return_value = {"sha256_hash": the_hash}

        result = await engine.verify_hash("doc-1", the_hash)

        assert result["verified"] is True
        assert result["document_id"] == "doc-1"
        assert result["stored_hash"] == the_hash
        assert result["current_hash"] == the_hash

    @pytest.mark.asyncio
    async def test_verify_hash_mismatch(self, engine, mock_db):
        """Stored hash != current hash => verified: False."""
        stored = "aaa111"
        current = "bbb222"
        mock_db.fetch_one.return_value = {"sha256_hash": stored}

        result = await engine.verify_hash("doc-1", current)

        assert result["verified"] is False
        assert result["stored_hash"] == stored
        assert result["current_hash"] == current

    @pytest.mark.asyncio
    async def test_verify_hash_no_stored_hash(self, engine, mock_db):
        """No stored hash found => verified: False with stored_hash None."""
        mock_db.fetch_one.return_value = None

        result = await engine.verify_hash("doc-1", "anything")

        assert result["verified"] is False
        assert result["stored_hash"] is None


# ---------------------------------------------------------------------------
# detect_tampering tests
# ---------------------------------------------------------------------------


class TestDetectTampering:
    """Tests for tampering detection across custody events."""

    @pytest.mark.asyncio
    async def test_detect_tampering_found(self, engine, mock_db):
        """Hash mismatch in chain => tampered: True with mismatches listed."""
        # Two custody events with hashes; second hash differs from first
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "hash_a",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "event_id": "e2",
                "sha256_hash": "hash_b",  # different — tampering
                "action": "accessed",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]

        result = await engine.detect_tampering("doc-1")

        assert result["tampered"] is True
        assert result["document_id"] == "doc-1"
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["event_id"] == "e2"
        assert result["mismatches"][0]["expected_hash"] == "hash_a"
        assert result["mismatches"][0]["actual_hash"] == "hash_b"

    @pytest.mark.asyncio
    async def test_detect_tampering_clean(self, engine, mock_db):
        """All hashes match => tampered: False, no mismatches."""
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "same_hash",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "event_id": "e2",
                "sha256_hash": "same_hash",
                "action": "stored",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "event_id": "e3",
                "sha256_hash": "same_hash",
                "action": "accessed",
                "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
        ]

        result = await engine.detect_tampering("doc-1")

        assert result["tampered"] is False
        assert len(result["mismatches"]) == 0

    @pytest.mark.asyncio
    async def test_detect_tampering_empty_chain(self, engine, mock_db):
        """No events => tampered: False, empty mismatches."""
        mock_db.fetch_all.return_value = []

        result = await engine.detect_tampering("doc-1")

        assert result["tampered"] is False
        assert len(result["mismatches"]) == 0

    @pytest.mark.asyncio
    async def test_detect_tampering_single_event(self, engine, mock_db):
        """Single event => tampered: False (nothing to compare)."""
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "only_hash",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]

        result = await engine.detect_tampering("doc-1")

        assert result["tampered"] is False
        assert len(result["mismatches"]) == 0

    @pytest.mark.asyncio
    async def test_detect_tampering_emits_event(self, engine, mock_db, mock_events):
        """When tampering detected, chain.tampering.detected event is emitted."""
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

        await engine.detect_tampering("doc-1")

        mock_events.emit.assert_called_once()
        call_args = mock_events.emit.call_args
        assert call_args[0][0] == "chain.tampering.detected"

    @pytest.mark.asyncio
    async def test_detect_tampering_clean_no_event(self, engine, mock_db, mock_events):
        """When no tampering, no event emitted."""
        mock_db.fetch_all.return_value = [
            {
                "event_id": "e1",
                "sha256_hash": "h",
                "action": "received",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "event_id": "e2",
                "sha256_hash": "h",
                "action": "stored",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]

        await engine.detect_tampering("doc-1")

        mock_events.emit.assert_not_called()


# ---------------------------------------------------------------------------
# generate_provenance_report tests
# ---------------------------------------------------------------------------


class TestProvenanceReport:
    """Tests for provenance report generation."""

    @pytest.mark.asyncio
    async def test_provenance_report_timeline(self, engine, mock_db):
        """Events returned in chronological order."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "action": "received",
                "actor": "scanner",
                "sha256_hash": "h1",
                "timestamp": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            },
            {
                "id": "e2",
                "action": "stored",
                "actor": "system",
                "sha256_hash": "h1",
                "timestamp": datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            },
            {
                "id": "e3",
                "action": "accessed",
                "actor": "analyst",
                "sha256_hash": "h1",
                "timestamp": datetime(2024, 1, 2, 9, 0, 0, tzinfo=timezone.utc),
            },
        ]

        result = await engine.generate_provenance_report("doc-1")

        assert result["document_id"] == "doc-1"
        assert "report_id" in result
        assert len(result["events"]) == 3
        # Check chronological order
        assert result["events"][0]["action"] == "received"
        assert result["events"][1]["action"] == "stored"
        assert result["events"][2]["action"] == "accessed"
        # Integrity score included
        assert "integrity_score" in result

    @pytest.mark.asyncio
    async def test_provenance_report_includes_hashes(self, engine, mock_db):
        """Each event in report includes its hash."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "action": "received",
                "actor": "scanner",
                "sha256_hash": "abc123",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]

        result = await engine.generate_provenance_report("doc-1")

        assert result["events"][0]["hash"] == "abc123"

    @pytest.mark.asyncio
    async def test_provenance_report_empty(self, engine, mock_db):
        """No events => report with empty events list."""
        mock_db.fetch_all.return_value = []

        result = await engine.generate_provenance_report("doc-1")

        assert result["document_id"] == "doc-1"
        assert len(result["events"]) == 0
        assert result["integrity_score"] == 1.0  # No events = perfect by default

    @pytest.mark.asyncio
    async def test_provenance_report_stored_in_db(self, engine, mock_db):
        """Report is persisted to the provenance_reports table."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "action": "received",
                "actor": "scanner",
                "sha256_hash": "h1",
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]

        await engine.generate_provenance_report("doc-1")

        # Should have one INSERT call for the report
        insert_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "INSERT" in str(c.args[0]) and "provenance_reports" in str(c.args[0])
        ]
        assert len(insert_calls) == 1


# ---------------------------------------------------------------------------
# score_integrity tests
# ---------------------------------------------------------------------------


class TestScoreIntegrity:
    """Tests for integrity scoring."""

    @pytest.mark.asyncio
    async def test_integrity_score_perfect(self, engine, mock_db):
        """No gaps, no mismatches = 1.0."""
        # All events have same hash, linked sequentially via previous_event_id
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
                "previous_event_id": "e2",
                "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_integrity_score_with_gap(self, engine, mock_db):
        """Gap in custody chain penalizes score by 0.2 per gap."""
        # e2 doesn't point to e1 (previous_event_id is None => gap)
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
                "previous_event_id": None,  # Gap! Should reference e1
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        assert score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_integrity_score_with_mismatch(self, engine, mock_db):
        """Hash mismatch penalizes score by 0.3 per mismatch."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h1",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "id": "e2",
                "sha256_hash": "h2",  # Mismatch!
                "previous_event_id": "e1",
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        assert score == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_integrity_score_gap_and_mismatch(self, engine, mock_db):
        """Gap + mismatch combined penalties."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h1",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "id": "e2",
                "sha256_hash": "h2",  # Mismatch: -0.3
                "previous_event_id": None,  # Gap: -0.2
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        assert score == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_integrity_score_floors_at_zero(self, engine, mock_db):
        """Score never goes below 0.0 even with many penalties."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h1",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "id": "e2",
                "sha256_hash": "h2",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "id": "e3",
                "sha256_hash": "h3",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
            {
                "id": "e4",
                "sha256_hash": "h4",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 4, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        assert score == 0.0

    @pytest.mark.asyncio
    async def test_integrity_score_empty(self, engine, mock_db):
        """No events => 1.0 (vacuously perfect)."""
        mock_db.fetch_all.return_value = []

        score = await engine.score_integrity("doc-1")

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_integrity_score_single_event(self, engine, mock_db):
        """Single event with no gap/mismatch => 1.0."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]

        score = await engine.score_integrity("doc-1")

        assert score == 1.0

    @pytest.mark.asyncio
    async def test_integrity_score_emits_verified_event(self, engine, mock_db, mock_events):
        """Integrity check emits chain.integrity.verified event."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "sha256_hash": "h",
                "previous_event_id": None,
                "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]

        await engine.score_integrity("doc-1")

        mock_events.emit.assert_called_once()
        call_args = mock_events.emit.call_args
        assert call_args[0][0] == "chain.integrity.verified"
