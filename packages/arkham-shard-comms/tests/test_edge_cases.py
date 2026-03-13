"""
Comms Shard - Edge Case Tests

Covers boundary conditions, error paths, and corner cases
for reconstructor, LLM, event handlers, and helpers.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_comms.llm import CommsLLM, MessageIntent, PatternAnalysis
from arkham_shard_comms.reconstructor import ThreadReconstructor
from arkham_shard_comms.shard import CommsShard

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
def mock_event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def reconstructor(mock_db, mock_event_bus):
    return ThreadReconstructor(db=mock_db, event_bus=mock_event_bus)


@pytest.fixture
def reconstructor_no_db():
    return ThreadReconstructor(db=None, event_bus=None)


# ---------------------------------------------------------------------------
# Reconstructor Edge Cases
# ---------------------------------------------------------------------------


class TestParseEmailHeadersEdgeCases:
    """Edge cases for header parsing."""

    def test_empty_text(self, reconstructor):
        result = reconstructor.parse_email_headers("")
        assert result["message_id"] is None
        assert result["from_addr"] is None
        assert result["to_addrs"] == []
        assert result["cc_addrs"] == []
        assert result["references"] == []
        assert result["date"] is None

    def test_from_with_display_name(self, reconstructor):
        text = "From: Alice Smith <alice@example.com>\nTo: bob@example.com"
        result = reconstructor.parse_email_headers(text)
        assert result["from_addr"] == "alice@example.com"

    def test_multiple_cc_addresses(self, reconstructor):
        text = "From: a@b.com\nTo: b@b.com\nCC: c@b.com, d@b.com, e@b.com"
        result = reconstructor.parse_email_headers(text)
        assert len(result["cc_addrs"]) == 3
        assert "c@b.com" in result["cc_addrs"]
        assert "e@b.com" in result["cc_addrs"]

    def test_case_insensitive_headers(self, reconstructor):
        text = "from: alice@example.com\nto: bob@example.com\ncc: carol@example.com"
        result = reconstructor.parse_email_headers(text)
        assert result["from_addr"] == "alice@example.com"
        assert "bob@example.com" in result["to_addrs"]
        assert "carol@example.com" in result["cc_addrs"]

    def test_iso_date_format(self, reconstructor):
        text = "Date: 2024-01-15T10:30:00+0000"
        result = reconstructor.parse_email_headers(text)
        assert result["date"] is not None

    def test_simple_date_format(self, reconstructor):
        text = "Date: 2024-01-15 10:30:00"
        result = reconstructor.parse_email_headers(text)
        assert result["date"] is not None

    def test_unparseable_date_returns_raw(self, reconstructor):
        text = "Date: not-a-real-date-format"
        result = reconstructor.parse_email_headers(text)
        # Should return the raw string as fallback
        assert result["date"] == "not-a-real-date-format"

    def test_single_reference(self, reconstructor):
        text = "References: <single@ref.com>"
        result = reconstructor.parse_email_headers(text)
        assert result["references"] == ["<single@ref.com>"]

    def test_to_with_display_names(self, reconstructor):
        text = "To: Bob Smith <bob@example.com>, Carol <carol@example.com>"
        result = reconstructor.parse_email_headers(text)
        assert "bob@example.com" in result["to_addrs"]
        assert "carol@example.com" in result["to_addrs"]

    def test_body_not_treated_as_header(self, reconstructor):
        text = "From: alice@example.com\n\nFrom: this is body text mentioning From:"
        result = reconstructor.parse_email_headers(text)
        # Should pick up the header, not the body text
        assert result["from_addr"] == "alice@example.com"


class TestReconstructThreadEdgeCases:
    """Edge cases for thread reconstruction."""

    @pytest.mark.asyncio
    async def test_empty_message_list(self, reconstructor):
        result = await reconstructor.reconstruct_thread([])
        assert result["message_count"] == 0
        assert result["root_message_id"] is None
        assert result["tree"] == []

    @pytest.mark.asyncio
    async def test_single_message(self, reconstructor):
        messages = [
            {
                "message_id": "<only@ex.com>",
                "in_reply_to": None,
                "references": [],
                "from_addr": "alice@ex.com",
                "date": datetime(2024, 1, 1),
            }
        ]
        result = await reconstructor.reconstruct_thread(messages)
        assert result["message_count"] == 1
        assert result["root_message_id"] == "<only@ex.com>"
        assert len(result["tree"]) == 1
        assert result["tree"][0]["children"] == []

    @pytest.mark.asyncio
    async def test_messages_with_missing_message_id(self, reconstructor):
        """Messages without message_id should be skipped in tree building."""
        messages = [
            {"message_id": "<msg1@ex.com>", "in_reply_to": None, "date": datetime(2024, 1, 1)},
            {"message_id": None, "in_reply_to": "<msg1@ex.com>", "date": datetime(2024, 1, 2)},
        ]
        result = await reconstructor.reconstruct_thread(messages)
        # Only msg1 has a valid message_id
        assert len(result["tree"]) == 1
        assert result["tree"][0]["message_id"] == "<msg1@ex.com>"
        assert result["tree"][0]["children"] == []

    @pytest.mark.asyncio
    async def test_orphan_reply(self, reconstructor):
        """Reply to non-existent parent becomes a root."""
        messages = [
            {
                "message_id": "<orphan@ex.com>",
                "in_reply_to": "<nonexistent@ex.com>",
                "references": [],
                "from_addr": "alice@ex.com",
                "date": datetime(2024, 1, 1),
            }
        ]
        result = await reconstructor.reconstruct_thread(messages)
        assert result["message_count"] == 1
        # The orphan becomes a root since parent doesn't exist
        assert len(result["tree"]) == 1
        assert result["tree"][0]["message_id"] == "<orphan@ex.com>"

    @pytest.mark.asyncio
    async def test_multiple_roots(self, reconstructor):
        """Two unrelated messages produce two roots."""
        messages = [
            {"message_id": "<a@ex.com>", "in_reply_to": None, "date": datetime(2024, 1, 1)},
            {"message_id": "<b@ex.com>", "in_reply_to": None, "date": datetime(2024, 1, 2)},
        ]
        result = await reconstructor.reconstruct_thread(messages)
        assert len(result["tree"]) == 2

    @pytest.mark.asyncio
    async def test_reconstruct_emits_event(self, reconstructor, mock_event_bus):
        messages = [
            {"message_id": "<a@ex.com>", "in_reply_to": None, "date": datetime(2024, 1, 1)},
        ]
        await reconstructor.reconstruct_thread(messages)
        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args
        assert call_args[0][0] == "comms.thread.reconstructed"

    @pytest.mark.asyncio
    async def test_reconstruct_no_event_bus(self, mock_db):
        """No crash when event_bus is None."""
        recon = ThreadReconstructor(db=mock_db, event_bus=None)
        messages = [
            {"message_id": "<a@ex.com>", "in_reply_to": None, "date": datetime(2024, 1, 1)},
        ]
        result = await recon.reconstruct_thread(messages)
        assert result["message_count"] == 1

    @pytest.mark.asyncio
    async def test_messages_without_dates_sorted_to_front(self, reconstructor):
        """Messages with no date sort before dated messages."""
        messages = [
            {"message_id": "<dated@ex.com>", "in_reply_to": None, "date": datetime(2024, 6, 1)},
            {"message_id": "<undated@ex.com>", "in_reply_to": None, "date": None},
        ]
        result = await reconstructor.reconstruct_thread(messages)
        assert len(result["tree"]) == 2
        # Undated should sort first (datetime.min)
        assert result["tree"][0]["message_id"] == "<undated@ex.com>"


class TestDetectGapsEdgeCases:
    """Edge cases for gap detection."""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, reconstructor_no_db):
        gaps = await reconstructor_no_db.detect_gaps("thread-1")
        assert gaps == []

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self, reconstructor, mock_db):
        mock_db.fetch_all.return_value = []
        gaps = await reconstructor.detect_gaps("thread-1")
        assert gaps == []

    @pytest.mark.asyncio
    async def test_message_without_header_skipped(self, reconstructor, mock_db):
        """Messages missing message_id_header are not checked for gaps."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": None,
                "from_address": "alice@ex.com",
                "sent_at": datetime.utcnow() - timedelta(hours=72),
                "in_reply_to": None,
            }
        ]
        gaps = await reconstructor.detect_gaps("thread-1")
        assert gaps == []

    @pytest.mark.asyncio
    async def test_message_without_sent_at_skipped(self, reconstructor, mock_db):
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": None,
                "in_reply_to": None,
            }
        ]
        gaps = await reconstructor.detect_gaps("thread-1")
        assert gaps == []

    @pytest.mark.asyncio
    async def test_custom_threshold(self, reconstructor, mock_db):
        """Custom threshold of 1 hour flags a 2-hour gap."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime.utcnow() - timedelta(hours=2),
                "in_reply_to": None,
            }
        ]
        gaps = await reconstructor.detect_gaps("thread-1", threshold_hours=1.0)
        assert len(gaps) == 1

    @pytest.mark.asyncio
    async def test_gap_emits_event(self, reconstructor, mock_db, mock_event_bus):
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime.utcnow() - timedelta(hours=100),
                "in_reply_to": None,
            }
        ]
        await reconstructor.detect_gaps("thread-1")
        mock_event_bus.emit.assert_called_once()
        assert mock_event_bus.emit.call_args[0][0] == "comms.gap.detected"

    @pytest.mark.asyncio
    async def test_sent_at_as_iso_string(self, reconstructor, mock_db):
        """sent_at stored as ISO string is correctly parsed."""
        dt = datetime.utcnow() - timedelta(hours=100)
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": dt.isoformat(),
                "in_reply_to": None,
            }
        ]
        gaps = await reconstructor.detect_gaps("thread-1")
        assert len(gaps) == 1


class TestDetectBccPatternsEdgeCases:
    """Edge cases for BCC detection."""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, reconstructor_no_db):
        patterns = await reconstructor_no_db.detect_bcc_patterns("thread-1")
        assert patterns == []

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self, reconstructor, mock_db):
        mock_db.fetch_all.return_value = []
        patterns = await reconstructor.detect_bcc_patterns("thread-1")
        assert patterns == []

    @pytest.mark.asyncio
    async def test_single_message_no_bcc(self, reconstructor, mock_db):
        """Single message cannot have a BCC pattern."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": '["bob@ex.com"]',
                "cc_addresses": "[]",
                "sent_at": datetime(2024, 1, 1),
            }
        ]
        patterns = await reconstructor.detect_bcc_patterns("thread-1")
        assert patterns == []

    @pytest.mark.asyncio
    async def test_known_participant_not_flagged(self, reconstructor, mock_db):
        """Participant already in To of earlier message is not flagged."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": '["bob@ex.com", "carol@ex.com"]',
                "cc_addresses": "[]",
                "sent_at": datetime(2024, 1, 1, 10, 0),
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "carol@ex.com",
                "to_addresses": '["alice@ex.com"]',
                "cc_addresses": "[]",
                "sent_at": datetime(2024, 1, 1, 11, 0),
            },
        ]
        patterns = await reconstructor.detect_bcc_patterns("thread-1")
        # carol was already visible in m1's To list, so not flagged
        flagged = [p["participant"] for p in patterns]
        assert "carol@ex.com" not in flagged

    @pytest.mark.asyncio
    async def test_addresses_stored_as_list(self, reconstructor, mock_db):
        """Handle to_addresses already deserialized as Python list."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "to_addresses": ["bob@ex.com"],
                "cc_addresses": [],
                "sent_at": datetime(2024, 1, 1, 10, 0),
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "dave@ex.com",
                "to_addresses": ["alice@ex.com"],
                "cc_addresses": [],
                "sent_at": datetime(2024, 1, 1, 11, 0),
            },
        ]
        patterns = await reconstructor.detect_bcc_patterns("thread-1")
        assert len(patterns) >= 1
        flagged = [p["participant"] for p in patterns]
        assert "dave@ex.com" in flagged


class TestDetectCoordinationEdgeCases:
    """Edge cases for coordination detection."""

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, reconstructor_no_db):
        result = await reconstructor_no_db.detect_coordination("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty(self, reconstructor, mock_db):
        mock_db.fetch_all.return_value = []
        result = await reconstructor.detect_coordination("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_same_sender_not_flagged(self, reconstructor, mock_db):
        """Two messages from the same sender within window are NOT coordination."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 0, 0),
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 2, 0),
            },
        ]
        result = await reconstructor.detect_coordination("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_outside_window_not_flagged(self, reconstructor, mock_db):
        """Messages 10 minutes apart (beyond 5-min window) are not flagged."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 0, 0),
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 10, 0),
            },
        ]
        result = await reconstructor.detect_coordination("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_custom_window(self, reconstructor, mock_db):
        """Custom window of 15 minutes catches wider spread."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 0, 0),
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 12, 0),
            },
        ]
        result = await reconstructor.detect_coordination("thread-1", window_minutes=15)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_coordination_emits_event(self, reconstructor, mock_db, mock_event_bus):
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 0, 0),
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 1, 0),
            },
        ]
        await reconstructor.detect_coordination("thread-1")
        mock_event_bus.emit.assert_called_once()
        assert mock_event_bus.emit.call_args[0][0] == "comms.coordination.flagged"

    @pytest.mark.asyncio
    async def test_missing_sent_at_skipped(self, reconstructor, mock_db):
        """Messages without sent_at are skipped in coordination check."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": None,
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "sent_at": datetime(2024, 1, 1, 10, 1, 0),
            },
        ]
        result = await reconstructor.detect_coordination("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_sent_at_as_string(self, reconstructor, mock_db):
        """sent_at stored as ISO string is correctly parsed."""
        mock_db.fetch_all.return_value = [
            {
                "id": "m1",
                "message_id_header": "<msg1@ex.com>",
                "from_address": "alice@ex.com",
                "sent_at": "2024-01-01T10:00:00",
            },
            {
                "id": "m2",
                "message_id_header": "<msg2@ex.com>",
                "from_address": "bob@ex.com",
                "sent_at": "2024-01-01T10:02:00",
            },
        ]
        result = await reconstructor.detect_coordination("thread-1")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Helper Method Edge Cases
# ---------------------------------------------------------------------------


class TestHelperMethods:
    """Edge cases for private helper methods."""

    def test_extract_email_bare(self, reconstructor):
        assert reconstructor._extract_email("alice@example.com") == "alice@example.com"

    def test_extract_email_with_name(self, reconstructor):
        assert reconstructor._extract_email("Alice <alice@example.com>") == "alice@example.com"

    def test_extract_email_no_at(self, reconstructor):
        result = reconstructor._extract_email("not-an-email")
        assert result == "not-an-email"

    def test_extract_email_list_empty(self, reconstructor):
        result = reconstructor._extract_email_list("")
        assert result == []

    def test_parse_json_list_string(self, reconstructor):
        assert reconstructor._parse_json_list('["a@b.com"]') == ["a@b.com"]

    def test_parse_json_list_already_list(self, reconstructor):
        assert reconstructor._parse_json_list(["a@b.com"]) == ["a@b.com"]

    def test_parse_json_list_invalid_json(self, reconstructor):
        assert reconstructor._parse_json_list("not-json") == []

    def test_parse_json_list_non_list_json(self, reconstructor):
        assert reconstructor._parse_json_list('{"key": "value"}') == []

    def test_parse_json_list_none(self, reconstructor):
        assert reconstructor._parse_json_list(None) == []

    def test_parse_json_list_int(self, reconstructor):
        assert reconstructor._parse_json_list(42) == []


# ---------------------------------------------------------------------------
# LLM Edge Cases
# ---------------------------------------------------------------------------


class TestCommsLLMEdgeCases:
    """Edge cases for CommsLLM."""

    def test_unavailable_when_no_service(self):
        llm = CommsLLM(llm_service=None)
        assert llm.available is False

    def test_available_when_service_provided(self):
        llm = CommsLLM(llm_service=MagicMock())
        assert llm.available is True

    @pytest.mark.asyncio
    async def test_analyze_patterns_no_llm(self):
        llm = CommsLLM(llm_service=None)
        result = await llm.analyze_patterns([{"id": "m1"}])
        assert isinstance(result, PatternAnalysis)
        assert result.patterns_detected == []
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_classify_intents_no_llm(self):
        llm = CommsLLM(llm_service=None)
        result = await llm.classify_intents([{"id": "m1"}])
        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_patterns_success(self):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "patterns": [{"type": "coordination", "description": "test", "confidence": 0.8}],
                "overall_assessment": "Suspicious",
                "confidence": 0.7,
            }
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm = CommsLLM(llm_service=mock_llm)
        result = await llm.analyze_patterns(
            [{"id": "m1", "from_address": "a@b.com", "body_summary": "test", "sent_at": "2024-01-01"}]
        )
        assert len(result.patterns_detected) == 1
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_analyze_patterns_llm_error(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM down"))

        llm = CommsLLM(llm_service=mock_llm)
        result = await llm.analyze_patterns([{"id": "m1"}])
        assert isinstance(result, PatternAnalysis)
        assert result.patterns_detected == []

    @pytest.mark.asyncio
    async def test_analyze_patterns_bad_json(self):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm = CommsLLM(llm_service=mock_llm)
        result = await llm.analyze_patterns([{"id": "m1"}])
        # Should gracefully return empty on parse failure
        assert isinstance(result, PatternAnalysis)

    @pytest.mark.asyncio
    async def test_classify_intents_success(self):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            [{"message_id": "m1", "intent": "evasive", "confidence": 0.9, "reasoning": "Deflecting"}]
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm = CommsLLM(llm_service=mock_llm)
        result = await llm.classify_intents([{"id": "m1", "body_summary": "test"}])
        assert len(result) == 1
        assert result[0].intent == "evasive"
        assert result[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_classify_intents_llm_error(self):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM down"))

        llm = CommsLLM(llm_service=mock_llm)
        result = await llm.classify_intents([{"id": "m1"}])
        assert result == []

    @pytest.mark.asyncio
    async def test_classify_intents_response_without_text_attr(self):
        """Response object without .text attribute falls back to str()."""
        mock_llm = AsyncMock()
        # Return a string directly (no .text attribute)
        mock_llm.generate = AsyncMock(
            return_value=json.dumps([{"message_id": "m1", "intent": "directive", "confidence": 0.5, "reasoning": ""}])
        )

        llm = CommsLLM(llm_service=mock_llm)
        result = await llm.classify_intents([{"id": "m1"}])
        assert len(result) == 1
        assert result[0].intent == "directive"


# ---------------------------------------------------------------------------
# Event Handler Edge Cases
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Test shard event handler methods."""

    @pytest.fixture
    def mock_frame(self, mock_db, mock_event_bus):
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {
                "events": mock_event_bus,
                "llm": None,
                "vectors": None,
            }.get(name)
        )
        return frame

    @pytest.mark.asyncio
    async def test_on_document_processed_non_email_ignored(self, mock_frame):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        # Non-email document should be silently ignored
        await shard._on_document_processed({"document_id": "d1", "document_type": "pdf"})
        # No error raised

    @pytest.mark.asyncio
    async def test_on_document_processed_email_with_text(self, mock_frame):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        event = {
            "document_id": "d1",
            "document_type": "email",
            "parsed_text": "From: alice@example.com\nTo: bob@example.com\n\nHello",
        }
        await shard._on_document_processed(event)
        # Should not raise; reconstructor.parse_email_headers called

    @pytest.mark.asyncio
    async def test_on_document_processed_email_no_text(self, mock_frame):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        event = {"document_id": "d1", "document_type": "email", "parsed_text": ""}
        await shard._on_document_processed(event)
        # Empty text -- should not raise

    @pytest.mark.asyncio
    async def test_on_document_processed_missing_type(self, mock_frame):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        event = {"document_id": "d1"}
        await shard._on_document_processed(event)
        # Missing type != "email", silently ignored

    @pytest.mark.asyncio
    async def test_on_entities_extracted(self, mock_frame):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        await shard._on_entities_extracted({"document_id": "d1", "entities": []})
        # Should not raise

    @pytest.mark.asyncio
    async def test_event_subscriptions_registered(self, mock_frame, mock_event_bus):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        # Check that subscribe was called for both events
        subscribe_calls = [str(c) for c in mock_event_bus.subscribe.call_args_list]
        assert any("ingest.document.processed" in c for c in subscribe_calls)
        assert any("entities.extracted" in c for c in subscribe_calls)

    @pytest.mark.asyncio
    async def test_shutdown_clears_services(self, mock_frame):
        shard = CommsShard()
        await shard.initialize(mock_frame)
        assert shard.reconstructor is not None
        assert shard.comms_llm is not None
        await shard.shutdown()
        assert shard.reconstructor is None
        assert shard.comms_llm is None

    @pytest.mark.asyncio
    async def test_initialize_no_event_bus(self, mock_db):
        """Initialization without event bus should not crash."""
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)
        shard = CommsShard()
        await shard.initialize(frame)
        # No subscriptions made, no crash
        assert shard.reconstructor is not None

    @pytest.mark.asyncio
    async def test_create_schema_no_db(self):
        """Schema creation with no db should log warning, not crash."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)
        shard = CommsShard()
        await shard.initialize(frame)
        # Should not raise
