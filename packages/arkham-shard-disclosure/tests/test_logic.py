"""
Disclosure Shard - Logic Tests

Tests for models, API handler logic, schema creation, and engine domain logic.
All external dependencies are mocked.
"""

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_disclosure.engine import DisclosureEngine
from arkham_shard_disclosure.models import (
    VALID_STATUSES,
    DisclosureRequest,
    EvasionCategory,
    GapStatus,
    RequestStatus,
    detect_overdue,
    generate_timeline,
    validate_status,
)
from arkham_shard_disclosure.shard import DisclosureShard

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

    def test_request_status_enum(self):
        assert RequestStatus.PENDING == "pending"
        assert RequestStatus.REQUESTED == "requested"
        assert RequestStatus.RECEIVED == "received"
        assert RequestStatus.PARTIAL == "partial"
        assert RequestStatus.REFUSED == "refused"
        assert RequestStatus.OVERDUE == "overdue"

    def test_gap_status_enum(self):
        assert GapStatus.OPEN == "open"
        assert GapStatus.CHASED == "chased"
        assert GapStatus.ESCALATED == "escalated"
        assert GapStatus.RESOLVED == "resolved"

    def test_evasion_category_enum(self):
        assert EvasionCategory.PARTIAL_RESPONSE == "partial_response"
        assert EvasionCategory.REDACTION == "redaction"
        assert EvasionCategory.DELAY == "delay"
        assert EvasionCategory.REFUSAL == "refusal"
        assert EvasionCategory.IRRELEVANT_DOCUMENTS == "irrelevant_documents"
        assert EvasionCategory.NONE == "none"

    def test_disclosure_request_defaults(self):
        req = DisclosureRequest(id="req-1")
        assert req.id == "req-1"
        assert req.status == "pending"
        assert req.document_ids == []
        assert req.deadline is None
        assert req.response_text is None


# ---------------------------------------------------------------------------
# Status Validation Tests
# ---------------------------------------------------------------------------


class TestStatusValidation:
    """Test request creation with valid and invalid statuses."""

    def test_valid_statuses_accepted(self):
        """Test request creation with each valid status."""
        for status in VALID_STATUSES:
            req = DisclosureRequest(id=f"req-{status}", status=status)
            assert req.status == status
            assert validate_status(status) is True

    def test_invalid_status_rejected(self):
        """Test that invalid status values are rejected by validation."""
        invalid_statuses = ["completed", "in_progress", "cancelled", "unknown", "", "PENDING"]
        for status in invalid_statuses:
            assert validate_status(status) is False, f"Status '{status}' should be invalid"

    def test_valid_status_set_includes_all_required(self):
        """Verify all six required statuses are in VALID_STATUSES."""
        required = {"pending", "requested", "received", "partial", "refused", "overdue"}
        assert required == VALID_STATUSES


# ---------------------------------------------------------------------------
# Schedule / Timeline Generation Tests
# ---------------------------------------------------------------------------


class TestScheduleGeneration:
    """Test disclosure timeline ordering by deadline."""

    def test_schedule_ordered_by_deadline(self):
        """Test that timeline entries are ordered by deadline ascending."""
        requests = [
            DisclosureRequest(id="r3", category="financial", deadline=date(2026, 5, 1), status="pending"),
            DisclosureRequest(id="r1", category="employment", deadline=date(2026, 3, 1), status="pending"),
            DisclosureRequest(id="r2", category="contracts", deadline=date(2026, 4, 1), status="requested"),
        ]
        timeline = generate_timeline(requests)

        assert len(timeline) == 3
        assert timeline[0]["request_id"] == "r1"
        assert timeline[1]["request_id"] == "r2"
        assert timeline[2]["request_id"] == "r3"

    def test_schedule_null_deadlines_last(self):
        """Test that requests without deadlines appear at end of timeline."""
        requests = [
            DisclosureRequest(id="r-none", category="other", deadline=None, status="pending"),
            DisclosureRequest(id="r-dated", category="financial", deadline=date(2026, 3, 15), status="requested"),
        ]
        timeline = generate_timeline(requests)

        assert len(timeline) == 2
        assert timeline[0]["request_id"] == "r-dated"
        assert timeline[1]["request_id"] == "r-none"
        assert timeline[1]["deadline"] is None

    def test_schedule_empty_case(self):
        """Test timeline generation with no requests."""
        timeline = generate_timeline([])
        assert timeline == []

    def test_schedule_response_format(self):
        """Test that timeline entries have the correct response keys."""
        requests = [
            DisclosureRequest(id="r1", category="docs", deadline=date(2026, 6, 1), status="received"),
        ]
        timeline = generate_timeline(requests)
        entry = timeline[0]
        assert set(entry.keys()) == {"request_id", "category", "deadline", "status"}
        assert entry["deadline"] == "2026-06-01"


# ---------------------------------------------------------------------------
# Overdue Detection Tests
# ---------------------------------------------------------------------------


class TestOverdueDetection:
    """Test detection of overdue disclosure requests."""

    def test_overdue_pending_past_deadline(self):
        """Requests past deadline and still pending are flagged overdue."""
        yesterday = date.today() - timedelta(days=1)
        requests = [
            DisclosureRequest(id="r1", status="pending", deadline=yesterday),
            DisclosureRequest(id="r2", status="received", deadline=yesterday),
            DisclosureRequest(id="r3", status="requested", deadline=yesterday),
        ]
        overdue = detect_overdue(requests)

        overdue_ids = {r.id for r in overdue}
        assert "r1" in overdue_ids, "Pending request past deadline should be overdue"
        assert "r3" in overdue_ids, "Requested request past deadline should be overdue"
        assert "r2" not in overdue_ids, "Received request should not be overdue"

    def test_not_overdue_if_future_deadline(self):
        """Requests with future deadlines are not overdue."""
        tomorrow = date.today() + timedelta(days=1)
        requests = [
            DisclosureRequest(id="r1", status="pending", deadline=tomorrow),
        ]
        overdue = detect_overdue(requests)
        assert len(overdue) == 0

    def test_not_overdue_if_no_deadline(self):
        """Requests without deadlines are not overdue."""
        requests = [
            DisclosureRequest(id="r1", status="pending", deadline=None),
        ]
        overdue = detect_overdue(requests)
        assert len(overdue) == 0

    def test_overdue_with_specific_date(self):
        """Test overdue detection with a specific as_of date."""
        requests = [
            DisclosureRequest(id="r1", status="pending", deadline=date(2026, 3, 1)),
        ]
        # Check as of March 10 - should be overdue
        overdue = detect_overdue(requests, as_of=date(2026, 3, 10))
        assert len(overdue) == 1

        # Check as of Feb 28 - should not be overdue
        overdue = detect_overdue(requests, as_of=date(2026, 2, 28))
        assert len(overdue) == 0


# ---------------------------------------------------------------------------
# Document IDs Array Handling Tests
# ---------------------------------------------------------------------------


class TestDocumentIdsHandling:
    """Test UUID[] document_ids array handling."""

    def test_empty_document_ids_default(self):
        """New request has empty document_ids by default."""
        req = DisclosureRequest(id="r1")
        assert req.document_ids == []
        assert isinstance(req.document_ids, list)

    def test_document_ids_with_values(self):
        """Request can hold multiple document UUIDs."""
        doc_ids = [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]
        req = DisclosureRequest(id="r1", document_ids=doc_ids)
        assert len(req.document_ids) == 3
        assert req.document_ids == doc_ids

    def test_document_ids_independent_between_instances(self):
        """Each request instance has its own document_ids list (no shared mutable default)."""
        r1 = DisclosureRequest(id="r1")
        r2 = DisclosureRequest(id="r2")
        r1.document_ids.append("doc-1")
        assert len(r2.document_ids) == 0, "Mutable default should not be shared"

    def test_document_ids_in_timeline_not_exposed(self):
        """Timeline entries do not leak document_ids (only id, category, deadline, status)."""
        req = DisclosureRequest(
            id="r1",
            category="evidence",
            deadline=date(2026, 4, 1),
            status="pending",
            document_ids=["doc-1", "doc-2"],
        )
        timeline = generate_timeline([req])
        assert "document_ids" not in timeline[0]


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_disclosure_requests_table_created(self, mock_frame, mock_db):
        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_disclosure" in executed_sql
        assert "arkham_disclosure.disclosure_requests" in executed_sql

    @pytest.mark.asyncio
    async def test_disclosure_requests_has_required_columns(self, mock_frame, mock_db):
        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        for col in [
            "id UUID",
            "case_id UUID",
            "category TEXT",
            "description TEXT",
            "requesting_party TEXT",
            "status TEXT",
            "deadline DATE",
            "document_ids UUID[]",
            "response_text TEXT",
            "created_at TIMESTAMPTZ",
            "updated_at TIMESTAMPTZ",
        ]:
            assert col in executed_sql, f"Column '{col}' not found in CREATE TABLE"

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0

    @pytest.mark.asyncio
    async def test_event_subscriptions(self, mock_frame, mock_events):
        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        subscribe_calls = [str(c) for c in mock_events.subscribe.call_args_list]
        assert any("document.processed" in c for c in subscribe_calls)
        assert any("case.updated" in c for c in subscribe_calls)


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_disclosure.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_requests_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_disclosure_requests()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_request_valid_status(self, mock_db):
        """Test creating a request with a valid status succeeds."""
        from arkham_shard_disclosure.api import CreateDisclosureRequest, create_disclosure_request

        self.api._db = mock_db
        self.api._event_bus = None
        self.api._shard = None

        req = CreateDisclosureRequest(
            case_id="case-1",
            category="financial",
            description="Provide bank statements",
            requesting_party="claimant",
            status="pending",
        )
        result = await create_disclosure_request(req)
        assert "request_id" in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_request_invalid_status(self, mock_db):
        """Test creating a request with an invalid status is rejected with 422."""
        from arkham_shard_disclosure.api import CreateDisclosureRequest, create_disclosure_request
        from fastapi import HTTPException

        self.api._db = mock_db
        self.api._event_bus = None
        self.api._shard = None

        req = CreateDisclosureRequest(
            case_id="case-1",
            category="financial",
            description="Provide bank statements",
            requesting_party="claimant",
            status="completed",
        )
        with pytest.raises(HTTPException) as exc:
            await create_disclosure_request(req)
        assert exc.value.status_code == 422
        assert "Invalid status" in exc.value.detail

    @pytest.mark.asyncio
    async def test_get_request_not_found(self, mock_db):
        """Test getting a non-existent request returns 404."""
        from arkham_shard_disclosure.api import get_disclosure_request
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_disclosure_request("nonexistent-id")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_request(self, mock_db, mock_events):
        """Test deleting an existing request succeeds."""
        from arkham_shard_disclosure.api import delete_disclosure_request

        self.api._db = mock_db
        self.api._event_bus = mock_events
        mock_db.fetch_one.return_value = {"id": "req-1"}

        result = await delete_disclosure_request("req-1")
        assert result["deleted"] is True
        assert result["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_delete_request_not_found(self, mock_db):
        """Test deleting a non-existent request returns 404."""
        from arkham_shard_disclosure.api import delete_disclosure_request
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await delete_disclosure_request("nonexistent-id")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_request_invalid_status(self, mock_db):
        """Test updating with an invalid status returns 422."""
        from arkham_shard_disclosure.api import UpdateDisclosureRequest, update_disclosure_request
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "req-1", "status": "pending"}

        req = UpdateDisclosureRequest(status="invalid_status")
        with pytest.raises(HTTPException) as exc:
            await update_disclosure_request("req-1", req)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_schedule_endpoint(self, mock_db):
        """Test schedule endpoint returns ordered timeline."""
        from arkham_shard_disclosure.api import ScheduleRequest, generate_disclosure_schedule

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [
            {"id": "r1", "category": "employment", "deadline": date(2026, 3, 1), "status": "pending"},
            {"id": "r2", "category": "financial", "deadline": date(2026, 4, 1), "status": "requested"},
        ]

        result = await generate_disclosure_schedule(ScheduleRequest(case_id="case-1"))
        assert "timeline" in result
        assert len(result["timeline"]) == 2
        assert result["timeline"][0]["request_id"] == "r1"
        assert result["timeline"][1]["request_id"] == "r2"

    @pytest.mark.asyncio
    async def test_list_requests_with_filters(self, mock_db):
        """Test listing requests with case_id and status filters."""
        from arkham_shard_disclosure.api import list_disclosure_requests

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "r1", "status": "pending"}]

        result = await list_disclosure_requests(case_id="case-1", status="pending", category="financial")
        assert result["count"] == 1

        # Verify the query had all filter params
        call_args = mock_db.fetch_all.call_args
        query = call_args[0][0]
        assert "case_id" in query
        assert "status" in query
        assert "category" in query


# ---------------------------------------------------------------------------
# Engine: Gap Detection Tests
# ---------------------------------------------------------------------------


class TestDetectGaps:
    """Tests for DisclosureEngine.detect_gaps."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_event_bus(self):
        bus = AsyncMock()
        bus.emit = AsyncMock()
        return bus

    @pytest.mark.asyncio
    async def test_detect_gaps_finds_unanswered_requests(self, mock_db, mock_event_bus):
        """3 requests, 1 has a response -- expect 2 gaps for the unanswered ones."""
        # DB returns 3 pending requests
        mock_db.fetch_all.return_value = [
            {"id": "req-1", "category": "financial", "description": "Bank statements", "status": "pending"},
            {"id": "req-2", "category": "employment", "description": "Contract of employment", "status": "requested"},
            {"id": "req-3", "category": "emails", "description": "Relevant emails", "status": "pending"},
        ]

        call_count = 0

        async def fetch_one_side_effect(query, params=None):
            nonlocal call_count
            # Response lookups (first call per request)
            if "responses" in query:
                req_id = params.get("request_id", "")
                if req_id == "req-1":
                    # req-1 has a response with text
                    return {"id": "resp-1", "response_text": "Here are the bank statements"}
                return None  # No response for req-2 and req-3
            # Gap existence check
            if "gaps" in query:
                return None  # No existing gaps

        mock_db.fetch_one = AsyncMock(side_effect=fetch_one_side_effect)

        engine = DisclosureEngine(db=mock_db, event_bus=mock_event_bus)
        gaps = await engine.detect_gaps("case-1")

        assert len(gaps) == 2
        gap_request_ids = {g["request_id"] for g in gaps}
        assert "req-2" in gap_request_ids
        assert "req-3" in gap_request_ids
        assert "req-1" not in gap_request_ids

        # Verify event was emitted
        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args
        assert call_args[0][0] == "disclosure.gap.detected"

    @pytest.mark.asyncio
    async def test_detect_gaps_partial_response_flagged(self, mock_db, mock_event_bus):
        """Request with status 'partial' is flagged as a gap even if a response exists."""
        mock_db.fetch_all.return_value = [
            {"id": "req-1", "category": "contracts", "description": "Supply agreements", "status": "partial"},
        ]

        async def fetch_one_side_effect(query, params=None):
            if "responses" in query:
                return {"id": "resp-1", "response_text": "Partial documents"}
            if "gaps" in query:
                return None

        mock_db.fetch_one = AsyncMock(side_effect=fetch_one_side_effect)

        engine = DisclosureEngine(db=mock_db, event_bus=mock_event_bus)
        gaps = await engine.detect_gaps("case-1")

        assert len(gaps) == 1
        assert gaps[0]["request_id"] == "req-1"
        assert (
            "partial" in gaps[0]["missing_items_description"].lower()
            or "Partial" in gaps[0]["missing_items_description"]
        )


# ---------------------------------------------------------------------------
# Engine: Evasion Scoring Tests
# ---------------------------------------------------------------------------


class TestEvasionScoring:
    """Tests for DisclosureEngine.score_evasion."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_event_bus(self):
        bus = AsyncMock()
        bus.emit = AsyncMock()
        return bus

    @pytest.mark.asyncio
    async def test_evasion_scoring_high_delay_pattern(self, mock_db, mock_event_bus):
        """5 delays out of 6 requests should produce a high-ish score."""
        yesterday = date.today() - timedelta(days=1)

        # 6 requests, 5 are overdue
        mock_db.fetch_all.side_effect = [
            # First call: requests
            [
                {"id": "r1", "status": "overdue", "deadline": yesterday, "created_at": datetime.now()},
                {"id": "r2", "status": "overdue", "deadline": yesterday, "created_at": datetime.now()},
                {"id": "r3", "status": "overdue", "deadline": yesterday, "created_at": datetime.now()},
                {"id": "r4", "status": "overdue", "deadline": yesterday, "created_at": datetime.now()},
                {"id": "r5", "status": "overdue", "deadline": yesterday, "created_at": datetime.now()},
                {"id": "r6", "status": "received", "deadline": None, "created_at": datetime.now()},
            ],
            # Second call: responses (no redactions)
            [],
        ]

        engine = DisclosureEngine(db=mock_db, event_bus=mock_event_bus)
        result = await engine.score_evasion("resp-1", "case-1")

        assert result["respondent_id"] == "resp-1"
        assert result["score"] > 0
        assert result["breakdown"]["delay"] == 5
        assert result["breakdown"]["total_requests"] == 6
        assert result["category"] != "none"

    @pytest.mark.asyncio
    async def test_evasion_scoring_no_evasion_returns_zero(self, mock_db, mock_event_bus):
        """All requests fully responded -- score should be zero."""
        mock_db.fetch_all.side_effect = [
            # First call: all received
            [
                {"id": "r1", "status": "received", "deadline": None, "created_at": datetime.now()},
                {"id": "r2", "status": "received", "deadline": None, "created_at": datetime.now()},
                {"id": "r3", "status": "received", "deadline": None, "created_at": datetime.now()},
            ],
            # Second call: responses (no redactions)
            [],
        ]

        engine = DisclosureEngine(db=mock_db, event_bus=mock_event_bus)
        result = await engine.score_evasion("resp-1", "case-1")

        assert result["respondent_id"] == "resp-1"
        assert result["score"] == 0.0
        assert result["category"] == "none"
        assert result["breakdown"]["delay"] == 0
        assert result["breakdown"]["partial"] == 0
        assert result["breakdown"]["refusal"] == 0


# ---------------------------------------------------------------------------
# Engine: Deadline Calculation Tests
# ---------------------------------------------------------------------------


class TestDeadlineCalculation:
    """Tests for DisclosureEngine.calculate_deadline."""

    @pytest.mark.asyncio
    async def test_deadline_calculation_calendar_days(self):
        """order_date + 14 calendar days should be exactly 14 days later."""
        engine = DisclosureEngine(db=None)
        order = date(2026, 3, 1)  # Sunday
        result = await engine.calculate_deadline(order, deadline_days=14, deadline_type="calendar_days")
        assert result == date(2026, 3, 15)

    @pytest.mark.asyncio
    async def test_deadline_calculation_working_days(self):
        """Working days calculation skips weekends."""
        engine = DisclosureEngine(db=None)
        # Monday 2 March 2026
        order = date(2026, 3, 2)
        result = await engine.calculate_deadline(order, deadline_days=10, deadline_type="working_days")
        # 10 working days from Monday March 2:
        # Week 1: Mar 3,4,5,6 (Tu-Fr) = 4
        # Mar 9,10,11,12,13 (Mo-Fr) = 5 -> 9 total
        # Mar 16 (Mo) = 10 total
        assert result == date(2026, 3, 16)
        # Verify it's a Monday (weekday 0)
        assert result.weekday() == 0


# ---------------------------------------------------------------------------
# Engine: Document Matching Tests
# ---------------------------------------------------------------------------


class TestDocumentMatching:
    """Tests for DisclosureEngine.match_document_to_request."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.mark.asyncio
    async def test_document_match_keyword_fallback(self, mock_db):
        """When LLM is unavailable, falls back to keyword matching on category."""
        mock_db.fetch_all.return_value = [
            {"id": "req-1", "category": "financial bank statements", "description": "Monthly bank statements"},
            {"id": "req-2", "category": "employment contract", "description": "Written terms of employment"},
            {"id": "req-3", "category": "email correspondence", "description": "All relevant emails"},
        ]

        # No LLM helper -- keyword fallback
        engine = DisclosureEngine(db=mock_db, llm_helper=None)
        matches = await engine.match_document_to_request(
            document_id="doc-1",
            document_metadata={
                "category": "financial",
                "title": "Bank Statement March 2026",
                "text": "HSBC bank account statement showing transactions",
            },
        )

        assert "req-1" in matches
        # req-2 and req-3 should not match financial/bank document
        assert "req-2" not in matches


# ---------------------------------------------------------------------------
# Event Handler Tests
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Tests for shard event handlers."""

    @pytest.fixture
    def mock_events(self):
        events = AsyncMock()
        events.emit = AsyncMock()
        events.subscribe = AsyncMock()
        events.unsubscribe = AsyncMock()
        return events

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_frame(self, mock_events, mock_db):
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

    @pytest.mark.asyncio
    async def test_event_handler_auto_matches_document(self, mock_frame, mock_db, mock_events):
        """document.processed event triggers match_document_to_request on the engine."""
        # Setup: one pending request that matches the document
        mock_db.fetch_all.return_value = [
            {"id": "req-1", "category": "financial statements", "description": "Bank records"},
        ]

        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        # Simulate document.processed event
        event = {
            "document_id": "doc-abc",
            "metadata": {
                "category": "financial",
                "title": "Bank Statement",
                "text": "Monthly financial statements from HSBC",
            },
        }

        await shard._handle_document_processed(event)

        # The engine should have been called and emitted a match event
        # Since we have a matching document, the event bus should have disclosure.document.matched
        emit_calls = mock_events.emit.call_args_list
        # Filter for our specific event (not the subscribe calls etc)
        match_events = [c for c in emit_calls if len(c[0]) > 0 and c[0][0] == "disclosure.document.matched"]
        assert len(match_events) == 1
        assert "doc-abc" in str(match_events[0])
