"""
BurdenMap Shard - Logic Tests

Tests for CRUD API logic, matrix grouping, status validation,
evidence_ids handling, and claim filtering.
All external dependencies are mocked.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_burden_map.api import (
    CreateElementRequest,
    UpdateElementRequest,
    init_api,
)
from arkham_shard_burden_map.shard import VALID_STATUSES, BurdenMapShard
from fastapi import HTTPException

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


@pytest.fixture
def api_module(mock_db, mock_events):
    """Import and configure the api module with mock deps."""
    import arkham_shard_burden_map.api as api_mod

    api_mod._db = mock_db
    api_mod._event_bus = mock_events
    api_mod._shard = None
    api_mod._llm_service = None
    return api_mod


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify the table is created during initialize()."""

    @pytest.mark.asyncio
    async def test_burden_elements_table_created(self, mock_frame, mock_db):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_burden_map" in executed_sql
        assert "arkham_burden_map.burden_elements" in executed_sql
        assert "UUID PRIMARY KEY" in executed_sql
        assert "evidence_ids" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 3


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


class TestCreateElement:
    """Test element creation via the API module."""

    @pytest.mark.asyncio
    async def test_create_element_success(self, api_module, mock_db, mock_events):
        req = CreateElementRequest(
            case_id="c1",
            claim="unfair dismissal",
            element="notice period",
            legal_standard="ERA 1996 s.86",
            burden_party="claimant",
            evidence_ids=["e1", "e2"],
            status="unmet",
        )
        result = await api_module.create_element(req)

        assert "element_id" in result
        assert result["status"] == "created"
        mock_db.execute.assert_called_once()

        # Verify the SQL contains the right table
        sql = mock_db.execute.call_args[0][0]
        assert "arkham_burden_map.burden_elements" in sql

        # Verify event emitted
        mock_events.emit.assert_called_once()
        event_name = mock_events.emit.call_args[0][0]
        assert event_name == "burden-map.item.created"

    @pytest.mark.asyncio
    async def test_create_element_invalid_status(self, api_module, mock_db):
        req = CreateElementRequest(
            claim="unfair dismissal",
            element="notice period",
            status="invalid_status",
        )
        with pytest.raises(HTTPException) as exc:
            await api_module.create_element(req)
        assert exc.value.status_code == 422
        assert "Invalid status" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_element_defaults(self, api_module, mock_db, mock_events):
        req = CreateElementRequest(
            claim="discrimination",
            element="protected characteristic",
        )
        result = await api_module.create_element(req)
        assert result["status"] == "created"

        # Check params passed to DB
        params = mock_db.execute.call_args[0][1]
        assert params["burden_party"] == "claimant"
        assert params["status"] == "unmet"
        assert params["evidence_ids"] == []


# ---------------------------------------------------------------------------
# Matrix Grouping Tests
# ---------------------------------------------------------------------------


class TestMatrixGrouping:
    """Test the /matrix endpoint that groups elements by claim."""

    @pytest.mark.asyncio
    async def test_matrix_groups_by_claim(self, api_module, mock_db):
        mock_db.fetch_all.return_value = [
            {"claim": "unfair dismissal", "element": "notice", "status": "met", "id": "1"},
            {"claim": "unfair dismissal", "element": "procedure", "status": "unmet", "id": "2"},
            {"claim": "unfair dismissal", "element": "reason", "status": "met", "id": "3"},
            {"claim": "discrimination", "element": "protected char", "status": "met", "id": "4"},
            {"claim": "discrimination", "element": "less favourable", "status": "partial", "id": "5"},
        ]

        result = await api_module.get_matrix(case_id="c1")

        assert "claims" in result
        assert len(result["claims"]) == 2

        # Find unfair dismissal group
        ud = next(c for c in result["claims"] if c["claim"] == "unfair dismissal")
        assert ud["met_count"] == 2
        assert ud["total"] == 3

        # Find discrimination group
        disc = next(c for c in result["claims"] if c["claim"] == "discrimination")
        assert disc["met_count"] == 1
        assert disc["total"] == 2

    @pytest.mark.asyncio
    async def test_matrix_empty_case(self, api_module, mock_db):
        mock_db.fetch_all.return_value = []
        result = await api_module.get_matrix(case_id="nonexistent")
        assert result["claims"] == []


# ---------------------------------------------------------------------------
# Status Validation Tests
# ---------------------------------------------------------------------------


class TestStatusValidation:
    """Verify that only valid statuses are accepted."""

    @pytest.mark.asyncio
    async def test_valid_statuses_accepted(self, api_module, mock_db, mock_events):
        for valid_status in VALID_STATUSES:
            mock_db.execute.reset_mock()
            req = CreateElementRequest(
                claim="test",
                element="test element",
                status=valid_status,
            )
            result = await api_module.create_element(req)
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_invalid_status_rejected_on_create(self, api_module, mock_db):
        req = CreateElementRequest(
            claim="test",
            element="test element",
            status="approved",
        )
        with pytest.raises(HTTPException) as exc:
            await api_module.create_element(req)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_status_rejected_on_update(self, api_module, mock_db):
        mock_db.fetch_one.return_value = {"id": "e1", "claim": "test", "element": "test", "status": "unmet"}
        req = UpdateElementRequest(status="approved")
        with pytest.raises(HTTPException) as exc:
            await api_module.update_element("e1", req)
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Evidence IDs Handling Tests
# ---------------------------------------------------------------------------


class TestEvidenceIdsHandling:
    """Test that evidence_ids (UUID array) is handled correctly."""

    @pytest.mark.asyncio
    async def test_evidence_ids_stored_on_create(self, api_module, mock_db, mock_events):
        evidence = [str(uuid.uuid4()), str(uuid.uuid4())]
        req = CreateElementRequest(
            claim="test",
            element="test element",
            evidence_ids=evidence,
        )
        await api_module.create_element(req)

        params = mock_db.execute.call_args[0][1]
        assert params["evidence_ids"] == evidence

    @pytest.mark.asyncio
    async def test_evidence_ids_default_empty(self, api_module, mock_db, mock_events):
        req = CreateElementRequest(
            claim="test",
            element="test element",
        )
        await api_module.create_element(req)

        params = mock_db.execute.call_args[0][1]
        assert params["evidence_ids"] == []

    @pytest.mark.asyncio
    async def test_evidence_ids_updated(self, api_module, mock_db, mock_events):
        mock_db.fetch_one.side_effect = [
            {"id": "e1", "claim": "test", "element": "test", "status": "unmet"},
            {"id": "e1", "claim": "test", "element": "test", "status": "unmet", "evidence_ids": ["new1"]},
        ]
        req = UpdateElementRequest(evidence_ids=["new1"])
        result = await api_module.update_element("e1", req)
        assert result["evidence_ids"] == ["new1"]


# ---------------------------------------------------------------------------
# Filtering Tests
# ---------------------------------------------------------------------------


class TestFiltering:
    """Test list endpoint filtering by case_id, claim, and status."""

    @pytest.mark.asyncio
    async def test_filter_by_claim(self, api_module, mock_db):
        mock_db.fetch_all.return_value = [
            {"id": "e1", "claim": "discrimination", "element": "protected char"},
        ]
        result = await api_module.list_elements(claim="discrimination")
        assert result["count"] == 1

        sql = mock_db.fetch_all.call_args[0][0]
        assert "claim = :claim" in sql

    @pytest.mark.asyncio
    async def test_filter_by_status(self, api_module, mock_db):
        mock_db.fetch_all.return_value = []
        result = await api_module.list_elements(status="met")
        assert result["count"] == 0

        sql = mock_db.fetch_all.call_args[0][0]
        assert "status = :status" in sql

    @pytest.mark.asyncio
    async def test_filter_by_case_id(self, api_module, mock_db):
        mock_db.fetch_all.return_value = [
            {"id": "e1", "case_id": "c1", "claim": "test"},
        ]
        result = await api_module.list_elements(case_id="c1")
        assert result["count"] == 1

        sql = mock_db.fetch_all.call_args[0][0]
        assert "case_id = :case_id" in sql

    @pytest.mark.asyncio
    async def test_filter_invalid_status(self, api_module, mock_db):
        with pytest.raises(HTTPException) as exc:
            await api_module.list_elements(status="invalid")
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Get / Delete Tests
# ---------------------------------------------------------------------------


class TestGetAndDelete:
    """Test single-element get and delete."""

    @pytest.mark.asyncio
    async def test_get_element_found(self, api_module, mock_db):
        mock_db.fetch_one.return_value = {"id": "e1", "claim": "test", "element": "el"}
        result = await api_module.get_element("e1")
        assert result["id"] == "e1"

    @pytest.mark.asyncio
    async def test_get_element_not_found(self, api_module, mock_db):
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await api_module.get_element("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_element(self, api_module, mock_db, mock_events):
        mock_db.fetch_one.return_value = {"id": "e1", "claim": "test"}
        result = await api_module.delete_element("e1")
        assert result["status"] == "deleted"
        mock_events.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_element_not_found(self, api_module, mock_db):
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await api_module.delete_element("nonexistent")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Shard Lifecycle Tests
# ---------------------------------------------------------------------------


class TestShardLifecycle:
    """Test shard initialize and shutdown."""

    @pytest.mark.asyncio
    async def test_initialize_subscribes_events(self, mock_frame, mock_events):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)
        assert mock_events.subscribe.call_count == 3

    @pytest.mark.asyncio
    async def test_shutdown_unsubscribes(self, mock_frame, mock_events):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)
        await shard.shutdown()
        assert mock_events.unsubscribe.call_count == 3
