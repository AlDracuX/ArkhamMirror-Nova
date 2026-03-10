"""
Disclosure Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_disclosure.models import (
    EvasionCategory,
    EvasionScore,
    Gap,
    GapStatus,
    Request,
    RequestStatus,
    Response,
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
        assert RequestStatus.PARTIAL == "partial"
        assert RequestStatus.FULFILLED == "fulfilled"
        assert RequestStatus.OVERDUE == "overdue"
        assert RequestStatus.REFUSED == "refused"

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

    def test_request_defaults(self):
        req = Request(id="req-1")
        assert req.id == "req-1"
        assert req.respondent_id == ""
        assert req.status == RequestStatus.PENDING

    def test_response_defaults(self):
        res = Response(id="res-1")
        assert res.id == "res-1"
        assert res.request_id == ""
        assert res.document_ids == []

    def test_gap_defaults(self):
        gap = Gap(id="gap-1")
        assert gap.id == "gap-1"
        assert gap.request_id == ""
        assert gap.status == GapStatus.OPEN

    def test_evasion_score_defaults(self):
        score = EvasionScore(id="score-1")
        assert score.id == "score-1"
        assert score.score == 0.0


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_disclosure" in executed_sql
        assert "arkham_disclosure.requests" in executed_sql
        assert "arkham_disclosure.responses" in executed_sql
        assert "arkham_disclosure.gaps" in executed_sql
        assert "arkham_disclosure.evasion_scores" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = DisclosureShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0


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
    async def test_create_request_no_db(self):
        from arkham_shard_disclosure.api import CreateRequestRequest
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.create_disclosure_request(CreateRequestRequest(respondent_id="r1", request_text="t"))
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_responses_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_disclosure_responses()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_response_no_db(self):
        from arkham_shard_disclosure.api import CreateResponseRequest
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.create_disclosure_response(CreateResponseRequest(request_id="req-1", response_text="t"))
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_gaps_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_disclosure_gaps()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_gap_no_db(self):
        from arkham_shard_disclosure.api import CreateGapRequest
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.create_disclosure_gap(CreateGapRequest(request_id="req-1", missing_items_description="d"))
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_evasion_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_evasion_scores()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_evasion_no_db(self):
        from arkham_shard_disclosure.api import CreateEvasionScoreRequest
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.create_evasion_score(CreateEvasionScoreRequest(respondent_id="r1", score=0.5))
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_compliance_dashboard_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_compliance_dashboard()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_request(self, mock_db):
        from arkham_shard_disclosure.api import CreateRequestRequest, create_disclosure_request

        self.api._db = mock_db
        self.api._shard = None
        req = CreateRequestRequest(respondent_id="resp-1", request_text="Please provide docs")
        result = await create_disclosure_request(req)
        assert "request_id" in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_response(self, mock_db, mock_events):
        from arkham_shard_disclosure.api import CreateResponseRequest, create_disclosure_response

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = CreateResponseRequest(request_id="req-1", response_text="Here are the docs", document_ids=["doc-1"])
        result = await create_disclosure_response(req)
        assert "response_id" in result
        # One for insert, one for update status
        assert mock_db.execute.call_count == 2
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_gap(self, mock_db, mock_events):
        from arkham_shard_disclosure.api import CreateGapRequest, create_disclosure_gap

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = CreateGapRequest(request_id="req-1", missing_items_description="Missing contract")
        result = await create_disclosure_gap(req)
        assert "gap_id" in result
        assert mock_db.execute.call_count == 2
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_evasion_score(self, mock_db, mock_events):
        from arkham_shard_disclosure.api import CreateEvasionScoreRequest, create_evasion_score

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None
        req = CreateEvasionScoreRequest(respondent_id="resp-1", score=0.8, reason="Delayed response")
        result = await create_evasion_score(req)
        assert "score_id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_requests(self, mock_db):
        from arkham_shard_disclosure.api import list_disclosure_requests

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "r1", "respondent_id": "resp-1"}]
        result = await list_disclosure_requests(respondent_id="resp-1")
        assert result["count"] == 1
        assert result["requests"][0]["id"] == "r1"
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_compliance_dashboard(self, mock_db):
        from arkham_shard_disclosure.api import get_compliance_dashboard

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"respondent_id": "resp-1", "total_requests": 5}]
        result = await get_compliance_dashboard()
        assert len(result["respondents"]) == 1
        assert result["respondents"][0]["total_requests"] == 5
