"""
Disclosure Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
