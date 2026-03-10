"""
RespondentIntel Shard - Logic Tests

Tests for respondent_profiles CRUD, dossier generation, assessment logic,
organization filtering, and document_ids handling.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_respondent_intel.api import (
    CreateProfileRequest,
    UpdateProfileRequest,
    create_profile,
    delete_profile,
    get_dossier,
    get_profile,
    list_profiles,
    update_profile,
)
from arkham_shard_respondent_intel.models import RespondentProfile
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
        }.get(name)
    )
    return frame


@pytest.fixture(autouse=True)
def reset_api_globals():
    """Reset module-level globals before each test."""
    import arkham_shard_respondent_intel.api as api_mod

    api_mod._db = None
    api_mod._event_bus = None
    api_mod._llm_service = None
    api_mod._shard = None
    yield


@pytest.fixture
def wired_api(mock_db, mock_events):
    """Wire up the API module globals for endpoint testing."""
    import arkham_shard_respondent_intel.api as api_mod

    api_mod._db = mock_db
    api_mod._event_bus = mock_events
    api_mod._shard = None
    return api_mod


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestRespondentProfileModel:
    """Verify RespondentProfile pydantic model construction and defaults."""

    def test_profile_minimal_construction(self):
        p = RespondentProfile(
            id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            name="John Smith",
            role="Manager",
            organization="Bylor Ltd",
        )
        assert p.name == "John Smith"
        assert p.role == "Manager"
        assert p.organization == "Bylor Ltd"
        assert p.title is None
        assert p.background is None
        assert p.strengths == []
        assert p.weaknesses == []
        assert p.known_positions == []
        assert p.credibility_notes is None
        assert p.document_ids == []

    def test_profile_full_construction(self):
        doc_id = str(uuid.uuid4())
        p = RespondentProfile(
            id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            name="Jane Doe",
            role="Director",
            organization="TLT Solicitors",
            title="Senior Partner",
            background="20 years in employment law",
            strengths=["experience", "credibility"],
            weaknesses=["bias"],
            known_positions=["denies all claims"],
            credibility_notes="Contradicted own statement",
            document_ids=[doc_id],
        )
        assert p.title == "Senior Partner"
        assert len(p.strengths) == 2
        assert len(p.weaknesses) == 1
        assert len(p.document_ids) == 1


# ---------------------------------------------------------------------------
# API Logic Tests - Creation
# ---------------------------------------------------------------------------


class TestProfileCreation:
    """Test POST /api/respondent-intel/ endpoint logic."""

    @pytest.mark.asyncio
    async def test_create_profile_returns_id(self, wired_api, mock_db):
        req = CreateProfileRequest(
            case_id=str(uuid.uuid4()),
            name="Witness A",
            role="Witness",
            organization="Bylor Ltd",
        )
        result = await create_profile(req)
        assert "id" in result
        # Verify UUID format
        uuid.UUID(result["id"])
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_profile_no_db_returns_503(self):
        import arkham_shard_respondent_intel.api as api_mod

        api_mod._db = None
        req = CreateProfileRequest(
            case_id=str(uuid.uuid4()),
            name="Name",
            role="Role",
            organization="Org",
        )
        with pytest.raises(HTTPException) as exc:
            await create_profile(req)
        assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# Dossier & Assessment Logic Tests
# ---------------------------------------------------------------------------


class TestDossierAndAssessment:
    """Test GET /api/respondent-intel/dossier/{id} and assessment logic."""

    @pytest.mark.asyncio
    async def test_dossier_strong_assessment(self, wired_api, mock_db):
        """When strengths > weaknesses, assessment should be 'strong'."""
        profile_row = {
            "id": "p1",
            "case_id": str(uuid.uuid4()),
            "name": "Strong Witness",
            "role": "Expert",
            "organization": "Corp",
            "title": None,
            "background": None,
            "strengths": ["credible", "consistent", "detailed"],
            "weaknesses": ["nervous"],
            "known_positions": [],
            "credibility_notes": None,
            "document_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.fetch_one.return_value = profile_row

        result = await get_dossier("p1")
        assert result["assessment"] == "strong"
        assert result["strength_count"] == 3
        assert result["weakness_count"] == 1
        assert result["document_count"] == 2

    @pytest.mark.asyncio
    async def test_dossier_weak_assessment(self, wired_api, mock_db):
        """When weaknesses > strengths, assessment should be 'weak'."""
        profile_row = {
            "id": "p2",
            "case_id": str(uuid.uuid4()),
            "name": "Weak Witness",
            "role": "Manager",
            "organization": "Corp",
            "title": None,
            "background": None,
            "strengths": [],
            "weaknesses": ["inconsistent", "hostile", "evasive"],
            "known_positions": [],
            "credibility_notes": None,
            "document_ids": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.fetch_one.return_value = profile_row

        result = await get_dossier("p2")
        assert result["assessment"] == "weak"
        assert result["strength_count"] == 0
        assert result["weakness_count"] == 3
        assert result["document_count"] == 0

    @pytest.mark.asyncio
    async def test_dossier_moderate_assessment(self, wired_api, mock_db):
        """When strengths == weaknesses, assessment should be 'moderate'."""
        profile_row = {
            "id": "p3",
            "case_id": str(uuid.uuid4()),
            "name": "Balanced Witness",
            "role": "Employee",
            "organization": "Corp",
            "title": None,
            "background": None,
            "strengths": ["honest"],
            "weaknesses": ["vague"],
            "known_positions": [],
            "credibility_notes": None,
            "document_ids": [str(uuid.uuid4())],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.fetch_one.return_value = profile_row

        result = await get_dossier("p3")
        assert result["assessment"] == "moderate"

    @pytest.mark.asyncio
    async def test_dossier_not_found(self, wired_api, mock_db):
        mock_db.fetch_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            await get_dossier("nonexistent")
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Filtering Tests
# ---------------------------------------------------------------------------


class TestOrganizationFiltering:
    """Test GET /api/respondent-intel/ with organization and case_id filters."""

    @pytest.mark.asyncio
    async def test_filter_by_organization(self, wired_api, mock_db):
        mock_db.fetch_all.return_value = [
            {"id": "p1", "name": "A", "organization": "Bylor Ltd"},
        ]
        result = await list_profiles(case_id=None, organization="Bylor Ltd")
        assert len(result) == 1
        # Verify the query included organization filter
        call_args = mock_db.fetch_all.call_args
        query = call_args[0][0]
        assert "organization" in query

    @pytest.mark.asyncio
    async def test_filter_by_case_id(self, wired_api, mock_db):
        cid = str(uuid.uuid4())
        mock_db.fetch_all.return_value = [
            {"id": "p1", "name": "B", "case_id": cid},
        ]
        result = await list_profiles(case_id=cid, organization=None)
        assert len(result) == 1
        call_args = mock_db.fetch_all.call_args
        query = call_args[0][0]
        assert "case_id" in query


# ---------------------------------------------------------------------------
# Document IDs Handling
# ---------------------------------------------------------------------------


class TestDocumentIdsHandling:
    """Test that document_ids array field is handled correctly."""

    @pytest.mark.asyncio
    async def test_create_with_document_ids(self, wired_api, mock_db):
        doc1, doc2 = str(uuid.uuid4()), str(uuid.uuid4())
        req = CreateProfileRequest(
            case_id=str(uuid.uuid4()),
            name="Documented Person",
            role="Claimant",
            organization="Self",
            document_ids=[doc1, doc2],
        )
        result = await create_profile(req)
        assert "id" in result
        # Verify the execute call included document_ids
        call_args = mock_db.execute.call_args
        params = call_args[0][1]
        assert params["document_ids"] == [doc1, doc2]

    @pytest.mark.asyncio
    async def test_update_document_ids(self, wired_api, mock_db):
        mock_db.fetch_one.return_value = {"id": "p1", "name": "X", "organization": "Y"}
        new_doc = str(uuid.uuid4())
        req = UpdateProfileRequest(document_ids=[new_doc])
        result = await update_profile("p1", req)
        assert result["id"] == "p1"
