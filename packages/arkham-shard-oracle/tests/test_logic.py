"""
Oracle Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_oracle.models import (
    AuthorityChain,
    AuthorityCreate,
    AuthoritySearchRequest,
    AuthorityType,
    AuthorityUpdate,
    CaseSummary,
    LegalAuthority,
    ResearchSession,
)
from arkham_shard_oracle.shard import OracleShard
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
def api_module():
    """Return the api module and reset its globals."""
    import arkham_shard_oracle.api as api_mod

    return api_mod


@pytest.fixture
def setup_api(api_module, mock_db, mock_events):
    """Initialize api module globals for testing."""
    api_module._db = mock_db
    api_module._event_bus = mock_events
    api_module._shard = None
    return api_module


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and defaults."""

    def test_legal_authority_defaults(self):
        a = LegalAuthority(
            id=uuid.uuid4(),
            title="Donoghue v Stevenson",
            citation="[1932] AC 562",
            jurisdiction="UK",
            court="House of Lords",
            summary="Neighbour principle and duty of care",
        )
        assert a.title == "Donoghue v Stevenson"
        assert a.citation == "[1932] AC 562"
        assert a.jurisdiction == "UK"
        assert a.authority_type == AuthorityType.case_law
        assert a.relevance_tags == []
        assert a.claim_types == []
        assert a.full_text is None
        assert isinstance(a.created_at, datetime)
        assert isinstance(a.updated_at, datetime)

    def test_authority_type_enum_values(self):
        assert AuthorityType.case_law.value == "case_law"
        assert AuthorityType.statute.value == "statute"
        assert AuthorityType.regulation.value == "regulation"
        assert AuthorityType.guidance.value == "guidance"
        assert AuthorityType.commentary.value == "commentary"

    def test_authority_create_model(self):
        ac = AuthorityCreate(
            citation="[2021] UKSC 5",
            jurisdiction="UK",
            title="Test Case",
            authority_type=AuthorityType.statute,
            claim_types=["unfair_dismissal"],
        )
        assert ac.citation == "[2021] UKSC 5"
        assert ac.authority_type == AuthorityType.statute
        assert ac.claim_types == ["unfair_dismissal"]

    def test_authority_update_partial(self):
        au = AuthorityUpdate(title="Updated Title")
        assert au.title == "Updated Title"
        assert au.citation is None
        assert au.jurisdiction is None

    def test_authority_search_request(self):
        sr = AuthoritySearchRequest(
            query="duty of care",
            jurisdiction="UK",
            claim_types=["negligence"],
        )
        assert sr.query == "duty of care"
        assert sr.jurisdiction == "UK"
        assert sr.claim_types == ["negligence"]

    def test_research_session_defaults(self):
        s = ResearchSession(id="s1", project_id="proj1", query="duty of care")
        assert s.findings == []
        assert s.authority_ids == []

    def test_case_summary_defaults(self):
        s = CaseSummary(id="s1", authority_id="auth1", facts="facts", decision="decision")
        assert s.legal_principles == []

    def test_authority_chain_defaults(self):
        c = AuthorityChain(
            id="c1", source_authority_id="auth1", cited_authority_id="auth2", relationship_type="follows"
        )
        assert c.relationship_type == "follows"


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify legal_authorities table is created during initialize()."""

    @pytest.mark.asyncio
    async def test_legal_authorities_table_created(self, mock_frame, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_oracle" in executed_sql
        assert "arkham_oracle.legal_authorities" in executed_sql

    @pytest.mark.asyncio
    async def test_legal_authorities_columns(self, mock_frame, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        auth_ddl = next((s for s in ddl_calls if "legal_authorities" in s and "CREATE TABLE" in s), None)
        assert auth_ddl is not None
        assert "id UUID" in auth_ddl or "id uuid" in auth_ddl.lower()
        assert "citation TEXT UNIQUE" in auth_ddl
        assert "jurisdiction TEXT" in auth_ddl
        assert "court TEXT" in auth_ddl
        assert "title TEXT" in auth_ddl
        assert "year INT" in auth_ddl
        assert "summary TEXT" in auth_ddl
        assert "full_text TEXT" in auth_ddl
        assert "relevance_tags TEXT[]" in auth_ddl
        assert "claim_types TEXT[]" in auth_ddl
        assert "authority_type TEXT" in auth_ddl
        assert "created_at TIMESTAMPTZ" in auth_ddl
        assert "updated_at TIMESTAMPTZ" in auth_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 1


# ---------------------------------------------------------------------------
# API CRUD Tests
# ---------------------------------------------------------------------------


class TestAuthorityCreation:
    """Test authority creation with citation uniqueness."""

    @pytest.mark.asyncio
    async def test_create_authority_success(self, setup_api, mock_db):
        from arkham_shard_oracle.api import create_authority

        mock_db.fetch_one.return_value = None  # No existing citation

        body = AuthorityCreate(
            citation="[1932] AC 562",
            jurisdiction="UK",
            court="House of Lords",
            title="Donoghue v Stevenson",
            year=1932,
            summary="Neighbour principle",
            authority_type=AuthorityType.case_law,
        )
        result = await create_authority(body)

        assert "id" in result
        assert result["citation"] == "[1932] AC 562"
        assert result["title"] == "Donoghue v Stevenson"
        assert result["authority_type"] == "case_law"
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_create_authority_duplicate_citation(self, setup_api, mock_db):
        from arkham_shard_oracle.api import create_authority

        # Simulate existing citation
        mock_db.fetch_one.return_value = {"id": "existing-id", "citation": "[1932] AC 562"}

        body = AuthorityCreate(
            citation="[1932] AC 562",
            jurisdiction="UK",
            title="Donoghue v Stevenson",
        )
        with pytest.raises(HTTPException) as exc:
            await create_authority(body)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_authority_invalid_type(self):
        """Authority type must be one of the valid enum values."""
        with pytest.raises(ValueError):
            AuthorityCreate(
                citation="[2020] UKSC 1",
                jurisdiction="UK",
                title="Test",
                authority_type="invalid_type",
            )


class TestAuthoritySearch:
    """Test search by query text."""

    @pytest.mark.asyncio
    async def test_search_by_query_text(self, setup_api, mock_db):
        from arkham_shard_oracle.api import search_authorities

        mock_db.fetch_all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "citation": "[1932] AC 562",
                "jurisdiction": "UK",
                "court": "House of Lords",
                "title": "Donoghue v Stevenson",
                "year": 1932,
                "summary": "Neighbour principle and duty of care",
                "full_text": None,
                "relevance_tags": [],
                "claim_types": [],
                "authority_type": "case_law",
                "created_at": datetime.now(tz=timezone.utc),
                "updated_at": datetime.now(tz=timezone.utc),
            }
        ]

        body = AuthoritySearchRequest(query="duty of care")
        result = await search_authorities(body)

        assert len(result) == 1
        assert result[0]["title"] == "Donoghue v Stevenson"

    @pytest.mark.asyncio
    async def test_search_no_results(self, setup_api, mock_db):
        from arkham_shard_oracle.api import search_authorities

        mock_db.fetch_all.return_value = []

        body = AuthoritySearchRequest(query="nonexistent topic")
        result = await search_authorities(body)

        assert result == []


class TestJurisdictionFiltering:
    """Test jurisdiction filtering on list endpoint."""

    @pytest.mark.asyncio
    async def test_list_filter_by_jurisdiction(self, setup_api, mock_db):
        from arkham_shard_oracle.api import list_authorities

        mock_db.fetch_all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "citation": "[1932] AC 562",
                "jurisdiction": "UK",
                "court": "House of Lords",
                "title": "Donoghue v Stevenson",
                "year": 1932,
                "summary": "Test",
                "full_text": None,
                "relevance_tags": [],
                "claim_types": [],
                "authority_type": "case_law",
                "created_at": datetime.now(tz=timezone.utc),
                "updated_at": datetime.now(tz=timezone.utc),
            }
        ]

        result = await list_authorities(jurisdiction="UK")

        assert len(result) == 1
        # Verify the SQL included a jurisdiction filter
        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "jurisdiction" in sql

    @pytest.mark.asyncio
    async def test_list_filter_by_authority_type(self, setup_api, mock_db):
        from arkham_shard_oracle.api import list_authorities

        mock_db.fetch_all.return_value = []

        _result = await list_authorities(authority_type="statute")

        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "authority_type" in sql

    @pytest.mark.asyncio
    async def test_list_filter_by_year_range(self, setup_api, mock_db):
        from arkham_shard_oracle.api import list_authorities

        mock_db.fetch_all.return_value = []

        _result = await list_authorities(year_from=1900, year_to=2000)

        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "year" in sql


class TestAuthorityTypeValidation:
    """Test authority_type validation."""

    def test_valid_authority_types(self):
        for at in ["case_law", "statute", "regulation", "guidance", "commentary"]:
            ac = AuthorityCreate(
                citation=f"test-{at}",
                jurisdiction="UK",
                title="Test",
                authority_type=at,
            )
            assert ac.authority_type == AuthorityType(at)

    def test_invalid_authority_type_rejected(self):
        with pytest.raises(ValueError):
            AuthorityCreate(
                citation="test",
                jurisdiction="UK",
                title="Test",
                authority_type="opinion",
            )


class TestClaimTypesFiltering:
    """Test claim_types array filtering."""

    @pytest.mark.asyncio
    async def test_search_with_claim_types_filter(self, setup_api, mock_db):
        from arkham_shard_oracle.api import search_authorities

        mock_db.fetch_all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "citation": "[2021] UKEAT 1",
                "jurisdiction": "UK",
                "court": "EAT",
                "title": "Employment Rights Case",
                "year": 2021,
                "summary": "Unfair dismissal claim",
                "full_text": None,
                "relevance_tags": [],
                "claim_types": ["unfair_dismissal"],
                "authority_type": "case_law",
                "created_at": datetime.now(tz=timezone.utc),
                "updated_at": datetime.now(tz=timezone.utc),
            }
        ]

        body = AuthoritySearchRequest(
            query="dismissal",
            claim_types=["unfair_dismissal"],
        )
        result = await search_authorities(body)

        assert len(result) == 1
        # Verify SQL contained claim_types filter
        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "claim_types" in sql

    @pytest.mark.asyncio
    async def test_search_with_jurisdiction_filter(self, setup_api, mock_db):
        from arkham_shard_oracle.api import search_authorities

        mock_db.fetch_all.return_value = []

        body = AuthoritySearchRequest(
            query="test",
            jurisdiction="US",
        )
        _result = await search_authorities(body)

        call_args = mock_db.fetch_all.call_args
        sql = str(call_args.args[0])
        assert "jurisdiction" in sql


class TestCRUDOperations:
    """Test get, update, delete operations."""

    @pytest.mark.asyncio
    async def test_get_authority_success(self, setup_api, mock_db):
        from arkham_shard_oracle.api import get_authority

        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "citation": "[1932] AC 562",
            "jurisdiction": "UK",
            "court": "House of Lords",
            "title": "Donoghue v Stevenson",
            "year": 1932,
            "summary": "Test",
            "full_text": None,
            "relevance_tags": [],
            "claim_types": [],
            "authority_type": "case_law",
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        }

        result = await get_authority(auth_id)
        assert result["id"] == auth_id

    @pytest.mark.asyncio
    async def test_get_authority_not_found(self, setup_api, mock_db):
        from arkham_shard_oracle.api import get_authority

        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_authority(str(uuid.uuid4()))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_authority(self, setup_api, mock_db):
        from arkham_shard_oracle.api import update_authority

        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": auth_id,
            "citation": "[1932] AC 562",
            "jurisdiction": "UK",
            "court": "House of Lords",
            "title": "Original Title",
            "year": 1932,
            "summary": "Test",
            "full_text": None,
            "relevance_tags": [],
            "claim_types": [],
            "authority_type": "case_law",
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
        }

        body = AuthorityUpdate(title="Updated Title")
        result = await update_authority(auth_id, body)

        assert result["title"] == "Updated Title"
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_delete_authority(self, setup_api, mock_db):
        from arkham_shard_oracle.api import delete_authority

        auth_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": auth_id}

        result = await delete_authority(auth_id)
        assert result["deleted"] is True
        mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_delete_authority_not_found(self, setup_api, mock_db):
        from arkham_shard_oracle.api import delete_authority

        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await delete_authority(str(uuid.uuid4()))
        assert exc.value.status_code == 404
