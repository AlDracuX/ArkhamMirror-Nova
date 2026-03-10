"""
RespondentIntel Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_respondent_intel.api import CreateProfileRequest, create_profile, get_profile, list_profiles
from arkham_shard_respondent_intel.models import (
    PublicRecord,
    RespondentConnection,
    RespondentProfile,
    RespondentVulnerability,
)
from arkham_shard_respondent_intel.shard import RespondentIntelShard
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


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and defaults."""

    def test_respondent_profile_defaults(self):
        p = RespondentProfile(id="p1", name="Acme Corp", type="corporate")
        assert p.id == "p1"
        assert p.name == "Acme Corp"
        assert p.type == "corporate"
        assert p.corporate_structure == {}
        assert p.key_personnel == []
        assert p.metadata == {}
        assert isinstance(p.created_at, datetime)

    def test_respondent_connection_defaults(self):
        c = RespondentConnection(
            id="c1", source_respondent_id="p1", target_respondent_id="p2", relationship_type="subsidiary", strength=0.9
        )
        assert c.id == "c1"
        assert c.source_respondent_id == "p1"
        assert c.target_respondent_id == "p2"
        assert c.relationship_type == "subsidiary"
        assert c.strength == 0.9
        assert c.description is None

    def test_public_record_defaults(self):
        r = PublicRecord(
            id="r1",
            respondent_id="p1",
            record_type="news",
            title="News Article",
            summary="Summary",
            date=datetime.utcnow(),
        )
        assert r.id == "r1"
        assert r.respondent_id == "p1"
        assert r.record_type == "news"
        assert r.title == "News Article"
        assert r.summary == "Summary"
        assert isinstance(r.date, datetime)
        assert r.url is None

    def test_respondent_vulnerability_defaults(self):
        v = RespondentVulnerability(
            id="v1", respondent_id="p1", category="financial", description="Debt", severity="high"
        )
        assert v.id == "v1"
        assert v.respondent_id == "p1"
        assert v.category == "financial"
        assert v.description == "Debt"
        assert v.severity == "high"
        assert v.evidence_ids == []


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_respondent_intel" in executed_sql
        assert "arkham_respondent_intel.profiles" in executed_sql
        assert "arkham_respondent_intel.connections" in executed_sql
        assert "arkham_respondent_intel.public_records" in executed_sql
        assert "arkham_respondent_intel.vulnerabilities" in executed_sql

    @pytest.mark.asyncio
    async def test_profiles_table_columns(self, mock_frame, mock_db):
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        prof_ddl = next((s for s in ddl_calls if "profiles" in s and "CREATE TABLE" in s), None)
        assert prof_ddl is not None
        assert "tenant_id" in prof_ddl
        assert "name" in prof_ddl
        assert "type" in prof_ddl
        assert "corporate_structure" in prof_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = RespondentIntelShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 2


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        """Reset module-level _db before each test."""
        import arkham_shard_respondent_intel.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_profile_no_db(self):
        self.api._db = None
        req = CreateProfileRequest(name="Name", type="individual")
        with pytest.raises(HTTPException) as exc:
            await create_profile(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_profile_success(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateProfileRequest(name="Acme", type="corporate")
        result = await create_profile(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once_with("respondent.profile.updated", {"profile_id": result["id"]})

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_profile("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_profile_success(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "p1", "name": "Acme", "type": "corporate"}
        mock_db.fetch_all.return_value = []

        result = await get_profile("p1")
        assert result["id"] == "p1"
        assert "public_records" in result
        assert "vulnerabilities" in result

    @pytest.mark.asyncio
    async def test_list_profiles(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "p1", "name": "Acme"}]

        result = await list_profiles()
        assert len(result) == 1
        assert result[0]["id"] == "p1"
