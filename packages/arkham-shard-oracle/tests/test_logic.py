"""
Oracle Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_oracle.api import ResearchRequest, get_authority, get_session, list_authorities, start_research
from arkham_shard_oracle.models import AuthorityChain, CaseSummary, LegalAuthority, ResearchSession
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


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and defaults."""

    def test_legal_authority_defaults(self):
        a = LegalAuthority(
            id="a1",
            title="Donoghue v Stevenson",
            citation="[1932] AC 562",
            type="case_law",
            jurisdiction="UK",
            binding_status="binding",
            summary="Ginger beer snail",
        )
        assert a.id == "a1"
        assert a.title == "Donoghue v Stevenson"
        assert a.citation == "[1932] AC 562"
        assert a.type == "case_law"
        assert a.jurisdiction == "UK"
        assert a.binding_status == "binding"
        assert a.summary == "Ginger beer snail"
        assert a.ratio_decidendi is None
        assert a.metadata == {}
        assert isinstance(a.created_at, datetime)

    def test_research_session_defaults(self):
        s = ResearchSession(id="s1", project_id="proj1", query="duty of care")
        assert s.id == "s1"
        assert s.project_id == "proj1"
        assert s.query == "duty of care"
        assert s.findings == []
        assert s.authority_ids == []
        assert isinstance(s.created_at, datetime)

    def test_case_summary_defaults(self):
        s = CaseSummary(id="s1", authority_id="auth1", facts="facts", decision="decision")
        assert s.id == "s1"
        assert s.authority_id == "auth1"
        assert s.facts == "facts"
        assert s.decision == "decision"
        assert s.legal_principles == []

    def test_authority_chain_defaults(self):
        c = AuthorityChain(
            id="c1", source_authority_id="auth1", cited_authority_id="auth2", relationship_type="follows"
        )
        assert c.id == "c1"
        assert c.source_authority_id == "auth1"
        assert c.cited_authority_id == "auth2"
        assert c.relationship_type == "follows"


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_oracle" in executed_sql
        assert "arkham_oracle.authorities" in executed_sql
        assert "arkham_oracle.research_sessions" in executed_sql
        assert "arkham_oracle.case_summaries" in executed_sql
        assert "arkham_oracle.authority_chains" in executed_sql

    @pytest.mark.asyncio
    async def test_authorities_table_columns(self, mock_frame, mock_db):
        shard = OracleShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        auth_ddl = next((s for s in ddl_calls if "authorities" in s and "CREATE TABLE" in s), None)
        assert auth_ddl is not None
        assert "tenant_id" in auth_ddl
        assert "title" in auth_ddl
        assert "citation" in auth_ddl
        assert "type" in auth_ddl
        assert "jurisdiction" in auth_ddl
        assert "binding_status" in auth_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = OracleShard()
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
        import arkham_shard_oracle.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_start_research_no_db(self):
        self.api._db = None
        req = ResearchRequest(project_id="p1", query="query")
        with pytest.raises(HTTPException) as exc:
            await start_research(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_start_research_success(self, mock_db, mock_events):
        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = ResearchRequest(project_id="p1", query="What is duty of care?")
        result = await start_research(req)

        assert "id" in result
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once_with("oracle.research.started", {"session_id": result["id"]})

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_session("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_session_success(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = {"id": "s1", "project_id": "proj1", "query": "q"}

        result = await get_session("s1")
        assert result["id"] == "s1"

    @pytest.mark.asyncio
    async def test_get_authority_not_found(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_authority("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_authority_success(self, mock_db):
        self.api._db = mock_db

        async def mock_fetch_one(query, params):
            if "authorities" in query:
                return {"id": "auth1", "title": "Title"}
            if "case_summaries" in query:
                return {"id": "sum1", "authority_id": "auth1", "facts": "Facts"}
            return None

        mock_db.fetch_one = mock_fetch_one

        result = await get_authority("auth1")
        assert result["id"] == "auth1"
        assert "summary_details" in result
        assert result["summary_details"]["id"] == "sum1"

    @pytest.mark.asyncio
    async def test_list_authorities(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "a1", "title": "Title"}]

        result = await list_authorities("proj1")
        assert len(result) == 1
        assert result[0]["id"] == "a1"
