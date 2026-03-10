"""
Comms Shard - Thread Reconstructor Tests

Tests for ThreadReconstructor domain logic.
All external dependencies are mocked.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from arkham_shard_comms.reconstructor import ThreadReconstructor

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
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def reconstructor(mock_db, mock_event_bus):
    """Create a ThreadReconstructor with mocked dependencies."""
    return ThreadReconstructor(db=mock_db, event_bus=mock_event_bus)


@pytest.fixture
def reconstructor_no_bus(mock_db):
    """Create a ThreadReconstructor without event bus."""
    return ThreadReconstructor(db=mock_db)


# ---------------------------------------------------------------------------
# 1. test_parse_email_headers_full
# ---------------------------------------------------------------------------


class TestParseEmailHeadersFull:
    """All headers extracted from a complete email text."""

    def test_parse_email_headers_full(self, reconstructor):
        parsed_text = (
            "Message-ID: <abc123@example.com>\n"
            "In-Reply-To: <parent456@example.com>\n"
            "References: <root789@example.com> <parent456@example.com>\n"
            "From: alice@example.com\n"
            "To: bob@example.com, carol@example.com\n"
            "CC: dave@example.com\n"
            "Date: Mon, 15 Jan 2024 10:30:00 +0000\n"
            "\n"
            "Body text here."
        )

        result = reconstructor.parse_email_headers(parsed_text)

        assert result["message_id"] == "<abc123@example.com>"
        assert result["in_reply_to"] == "<parent456@example.com>"
        assert result["references"] == ["<root789@example.com>", "<parent456@example.com>"]
        assert result["from_addr"] == "alice@example.com"
        assert "bob@example.com" in result["to_addrs"]
        assert "carol@example.com" in result["to_addrs"]
        assert "dave@example.com" in result["cc_addrs"]
        assert result["date"] is not None


# ---------------------------------------------------------------------------
# 2. test_parse_email_headers_partial
# ---------------------------------------------------------------------------


class TestParseEmailHeadersPartial:
    """Missing optional fields return safe defaults."""

    def test_parse_email_headers_partial(self, reconstructor):
        parsed_text = "From: alice@example.com\nTo: bob@example.com\n\nBody text only with From and To."

        result = reconstructor.parse_email_headers(parsed_text)

        assert result["message_id"] is None
        assert result["in_reply_to"] is None
        assert result["references"] == []
        assert result["from_addr"] == "alice@example.com"
        assert "bob@example.com" in result["to_addrs"]
        assert result["cc_addrs"] == []
        assert result["date"] is None


# ---------------------------------------------------------------------------
# 3. test_reconstruct_thread_linear
# ---------------------------------------------------------------------------


class TestReconstructThreadLinear:
    """A->B->C chain produces correct tree structure."""

    @pytest.mark.asyncio
    async def test_reconstruct_thread_linear(self, reconstructor):
        messages = [
            {
                "message_id": "<msg-a@ex.com>",
                "in_reply_to": None,
                "references": [],
                "from_addr": "alice@ex.com",
                "date": datetime(2024, 1, 1, 10, 0),
            },
            {
                "message_id": "<msg-b@ex.com>",
                "in_reply_to": "<msg-a@ex.com>",
                "references": ["<msg-a@ex.com>"],
                "from_addr": "bob@ex.com",
                "date": datetime(2024, 1, 1, 11, 0),
            },
            {
                "message_id": "<msg-c@ex.com>",
                "in_reply_to": "<msg-b@ex.com>",
                "references": ["<msg-a@ex.com>", "<msg-b@ex.com>"],
                "from_addr": "carol@ex.com",
                "date": datetime(2024, 1, 1, 12, 0),
            },
        ]

        result = await reconstructor.reconstruct_thread(messages)

        assert result["root_message_id"] == "<msg-a@ex.com>"
        assert result["message_count"] == 3
        assert result["thread_id"] is not None

        # Tree should be A -> B -> C
        tree = result["tree"]
        assert len(tree) == 1  # Single root
        root = tree[0]
        assert root["message_id"] == "<msg-a@ex.com>"
        assert len(root["children"]) == 1
        child_b = root["children"][0]
        assert child_b["message_id"] == "<msg-b@ex.com>"
        assert len(child_b["children"]) == 1
        child_c = child_b["children"][0]
        assert child_c["message_id"] == "<msg-c@ex.com>"
        assert child_c["children"] == []


# ---------------------------------------------------------------------------
# 4. test_reconstruct_thread_branching
# ---------------------------------------------------------------------------


class TestReconstructThreadBranching:
    """A->B and A->C fork produces correct tree structure."""

    @pytest.mark.asyncio
    async def test_reconstruct_thread_branching(self, reconstructor):
        messages = [
            {
                "message_id": "<msg-a@ex.com>",
                "in_reply_to": None,
                "references": [],
                "from_addr": "alice@ex.com",
                "date": datetime(2024, 1, 1, 10, 0),
            },
            {
                "message_id": "<msg-b@ex.com>",
                "in_reply_to": "<msg-a@ex.com>",
                "references": ["<msg-a@ex.com>"],
                "from_addr": "bob@ex.com",
                "date": datetime(2024, 1, 1, 11, 0),
            },
            {
                "message_id": "<msg-c@ex.com>",
                "in_reply_to": "<msg-a@ex.com>",
                "references": ["<msg-a@ex.com>"],
                "from_addr": "carol@ex.com",
                "date": datetime(2024, 1, 1, 11, 30),
            },
        ]

        result = await reconstructor.reconstruct_thread(messages)

        assert result["root_message_id"] == "<msg-a@ex.com>"
        assert result["message_count"] == 3

        tree = result["tree"]
        assert len(tree) == 1  # Single root
        root = tree[0]
        assert root["message_id"] == "<msg-a@ex.com>"
        assert len(root["children"]) == 2  # Two branches

        child_ids = {c["message_id"] for c in root["children"]}
        assert "<msg-b@ex.com>" in child_ids
        assert "<msg-c@ex.com>" in child_ids


# ---------------------------------------------------------------------------
# 5. test_detect_gaps_missing_reply
# ---------------------------------------------------------------------------


class TestDetectGapsMissingReply:
    """72h with no response flagged as gap."""

    @pytest.mark.asyncio
    async def test_detect_gaps_missing_reply(self, reconstructor, mock_db):
        thread_id = "thread-1"
        now = datetime(2024, 1, 5, 10, 0)

        # Message sent 72h ago with no reply
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": '["bob@ex.com"]',
                "sent_at": now - timedelta(hours=72),
                "in_reply_to": None,
                "thread_id": thread_id,
            },
        ]

        gaps = await reconstructor.detect_gaps(thread_id)

        assert len(gaps) >= 1
        gap = gaps[0]
        assert gap["message_id"] == "<msg1@ex.com>"
        assert gap["gap_duration_hours"] >= 48


# ---------------------------------------------------------------------------
# 6. test_detect_gaps_timely_reply
# ---------------------------------------------------------------------------


class TestDetectGapsTimelyReply:
    """Reply within 24h is not flagged."""

    @pytest.mark.asyncio
    async def test_detect_gaps_timely_reply(self, reconstructor, mock_db):
        thread_id = "thread-1"
        now = datetime(2024, 1, 2, 10, 0)

        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": '["bob@ex.com"]',
                "sent_at": now - timedelta(hours=24),
                "in_reply_to": None,
                "thread_id": thread_id,
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "to_addresses": '["alice@ex.com"]',
                "sent_at": now - timedelta(hours=12),
                "in_reply_to": "<msg1@ex.com>",
                "thread_id": thread_id,
            },
        ]

        gaps = await reconstructor.detect_gaps(thread_id)

        # No gaps should be detected -- msg1 got a timely reply
        flagged_ids = [g["message_id"] for g in gaps]
        assert "<msg1@ex.com>" not in flagged_ids


# ---------------------------------------------------------------------------
# 7. test_bcc_pattern_detected
# ---------------------------------------------------------------------------


class TestBccPatternDetected:
    """Participant appears late in thread, flagged as potential BCC."""

    @pytest.mark.asyncio
    async def test_bcc_pattern_detected(self, reconstructor, mock_db):
        thread_id = "thread-1"

        # dave@ex.com sends m3 replying to the thread, but was NEVER
        # in To or CC of any prior message -- suspected BCC recipient.
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": '["bob@ex.com"]',
                "cc_addresses": "[]",
                "sent_at": datetime(2024, 1, 1, 10, 0),
                "thread_id": thread_id,
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "to_addresses": '["alice@ex.com"]',
                "cc_addresses": "[]",
                "sent_at": datetime(2024, 1, 1, 11, 0),
                "thread_id": thread_id,
            },
            {
                "id": "m3",
                "message_id_header": "<msg3@ex.com>",
                "from_address": "dave@ex.com",
                "to_addresses": '["bob@ex.com", "alice@ex.com"]',
                "cc_addresses": "[]",
                "sent_at": datetime(2024, 1, 1, 11, 5),
                "thread_id": thread_id,
            },
        ]

        patterns = await reconstructor.detect_bcc_patterns(thread_id)

        # dave@ex.com appears as sender in m3 but was never visible
        # (To/CC) in any earlier message -- suspected BCC recipient
        assert len(patterns) >= 1
        flagged_participants = [p["participant"] for p in patterns]
        assert "dave@ex.com" in flagged_participants


# ---------------------------------------------------------------------------
# 8. test_coordination_simultaneous_sends
# ---------------------------------------------------------------------------


class TestCoordinationSimultaneousSends:
    """Two sends within 3min from different senders flagged."""

    @pytest.mark.asyncio
    async def test_coordination_simultaneous_sends(self, reconstructor, mock_db):
        thread_id = "thread-1"

        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": '["bob@ex.com"]',
                "sent_at": datetime(2024, 1, 1, 10, 0, 0),
                "thread_id": thread_id,
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "carol@ex.com",
                "to_addresses": '["bob@ex.com"]',
                "sent_at": datetime(2024, 1, 1, 10, 3, 0),
                "thread_id": thread_id,
            },
        ]

        coordination = await reconstructor.detect_coordination(thread_id)

        assert len(coordination) >= 1
        pattern = coordination[0]
        assert pattern["pattern_type"] == "simultaneous_send"
        assert len(pattern["messages_involved"]) == 2
