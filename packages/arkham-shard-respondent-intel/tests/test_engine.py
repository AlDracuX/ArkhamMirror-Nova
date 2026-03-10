"""
RespondentIntel Shard - Engine Tests

Tests for RespondentIntelEngine: profile building, position tracking,
inconsistency detection, and strengths/weaknesses assessment.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_respondent_intel.engine import RespondentIntelEngine

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
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_event_bus, mock_llm):
    return RespondentIntelEngine(db=mock_db, event_bus=mock_event_bus, llm_service=mock_llm)


@pytest.fixture
def engine_no_llm(mock_db, mock_event_bus):
    return RespondentIntelEngine(db=mock_db, event_bus=mock_event_bus, llm_service=None)


# ---------------------------------------------------------------------------
# build_profile tests
# ---------------------------------------------------------------------------


class TestBuildProfile:
    """Tests for RespondentIntelEngine.build_profile."""

    @pytest.mark.asyncio
    async def test_build_profile_aggregates_mentions(self, engine, mock_db):
        """Profile built from entity mentions includes name, positions, and documents."""
        case_id = str(uuid.uuid4())
        doc_id_1 = str(uuid.uuid4())
        doc_id_2 = str(uuid.uuid4())

        # Entity mentions for this respondent
        mock_db.fetch_all.side_effect = [
            # First call: entity mentions
            [
                {
                    "document_id": doc_id_1,
                    "entity_text": "John Smith",
                    "context": "John Smith was the line manager responsible for the decision.",
                    "document_date": datetime(2024, 1, 15, tzinfo=timezone.utc),
                },
                {
                    "document_id": doc_id_2,
                    "entity_text": "John Smith",
                    "context": "John Smith stated the claimant was underperforming.",
                    "document_date": datetime(2024, 3, 10, tzinfo=timezone.utc),
                },
            ],
            # Second call: existing positions
            [],
        ]

        # LLM synthesises profile
        llm_resp = MagicMock()
        llm_resp.text = (
            '{"background": "Line manager at Bylor Ltd", "role": "Line Manager",'
            ' "positions": [{"position": "Claimant was underperforming", "date": "2024-03-10",'
            ' "document_id": "' + doc_id_2 + '", "context": "Performance review"}]}'
        )
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.build_profile(case_id=case_id, respondent_name="John Smith")

        assert result["respondent_name"] == "John Smith"
        assert result["profile_id"] is not None
        assert result["background"] == "Line manager at Bylor Ltd"
        assert len(result["positions"]) >= 1
        assert len(result["documents"]) == 2
        assert doc_id_1 in result["documents"]
        assert doc_id_2 in result["documents"]

    @pytest.mark.asyncio
    async def test_build_profile_no_mentions(self, engine, mock_db):
        """Empty profile returned when respondent has no entity mentions."""
        case_id = str(uuid.uuid4())
        mock_db.fetch_all.return_value = []

        result = await engine.build_profile(case_id=case_id, respondent_name="Unknown Person")

        assert result["respondent_name"] == "Unknown Person"
        assert result["profile_id"] is not None
        assert result["positions"] == []
        assert result["documents"] == []
        assert result["background"] == ""

    @pytest.mark.asyncio
    async def test_build_profile_no_llm_fallback(self, engine_no_llm, mock_db):
        """Profile built without LLM uses rule-based extraction."""
        case_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())

        mock_db.fetch_all.side_effect = [
            [
                {
                    "document_id": doc_id,
                    "entity_text": "Jane Doe",
                    "context": "Jane Doe denied knowledge of the grievance procedure.",
                    "document_date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                },
            ],
            [],
        ]

        result = await engine_no_llm.build_profile(case_id=case_id, respondent_name="Jane Doe")

        assert result["respondent_name"] == "Jane Doe"
        assert result["profile_id"] is not None
        assert len(result["documents"]) == 1


# ---------------------------------------------------------------------------
# track_positions tests
# ---------------------------------------------------------------------------


class TestTrackPositions:
    """Tests for RespondentIntelEngine.track_positions."""

    @pytest.mark.asyncio
    async def test_track_positions_returns_chronological(self, engine, mock_db):
        """Positions are returned ordered by date ascending."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "document_id": "doc-a",
                "position": "Claimant was dismissed for redundancy",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "context": "ET3 response",
            },
            {
                "document_id": "doc-b",
                "position": "Claimant was offered redeployment",
                "date": datetime(2024, 3, 5, tzinfo=timezone.utc),
                "context": "Witness statement",
            },
            {
                "document_id": "doc-c",
                "position": "Decision made following consultation",
                "date": datetime(2024, 2, 20, tzinfo=timezone.utc),
                "context": "Respondent letter",
            },
        ]

        result = await engine.track_positions(profile_id)

        assert len(result) == 3
        # Verify chronological order
        dates = [r["date"] for r in result]
        assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_track_positions_empty(self, engine, mock_db):
        """Empty list returned when profile has no positions."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_all.return_value = []

        result = await engine.track_positions(profile_id)

        assert result == []


# ---------------------------------------------------------------------------
# detect_inconsistencies tests
# ---------------------------------------------------------------------------


class TestDetectInconsistencies:
    """Tests for RespondentIntelEngine.detect_inconsistencies."""

    @pytest.mark.asyncio
    async def test_detect_inconsistencies_finds_contradictions(self, engine, mock_db):
        """Conflicting positions are detected as inconsistencies."""
        profile_id = str(uuid.uuid4())

        # Positions that contradict each other
        mock_db.fetch_all.return_value = [
            {
                "id": "pos-1",
                "document_id": "doc-a",
                "position": "The claimant was dismissed due to redundancy",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "context": "ET3 response",
            },
            {
                "id": "pos-2",
                "document_id": "doc-b",
                "position": "The claimant was dismissed due to poor performance",
                "date": datetime(2024, 3, 5, tzinfo=timezone.utc),
                "context": "Witness statement",
            },
        ]

        # LLM identifies the contradiction
        llm_resp = MagicMock()
        llm_resp.text = (
            '[{"position_a": "pos-1", "position_b": "pos-2",'
            ' "inconsistency": "Contradictory reasons given for dismissal:'
            ' redundancy vs poor performance"}]'
        )
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.detect_inconsistencies(profile_id)

        assert len(result) >= 1
        assert "inconsistency" in result[0]
        assert "position_a" in result[0]
        assert "position_b" in result[0]

    @pytest.mark.asyncio
    async def test_detect_inconsistencies_no_contradictions(self, engine, mock_db):
        """No inconsistencies returned for consistent positions."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "pos-1",
                "document_id": "doc-a",
                "position": "The claimant was dismissed due to redundancy",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "context": "ET3 response",
            },
            {
                "id": "pos-2",
                "document_id": "doc-b",
                "position": "The redundancy process followed company policy",
                "date": datetime(2024, 2, 20, tzinfo=timezone.utc),
                "context": "Witness statement",
            },
        ]

        # LLM finds no contradictions
        llm_resp = MagicMock()
        llm_resp.text = "[]"
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.detect_inconsistencies(profile_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_detect_inconsistencies_no_llm_fallback(self, engine_no_llm, mock_db):
        """Without LLM, keyword-based detection is used."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "pos-1",
                "document_id": "doc-a",
                "position": "The claimant was not given a warning",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "context": "ET3",
            },
            {
                "id": "pos-2",
                "document_id": "doc-b",
                "position": "The claimant was given a formal warning",
                "date": datetime(2024, 3, 5, tzinfo=timezone.utc),
                "context": "Witness statement",
            },
        ]

        result = await engine_no_llm.detect_inconsistencies(profile_id)

        # Heuristic should detect the negation contradiction
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_detect_inconsistencies_single_position(self, engine, mock_db):
        """No inconsistencies when only one position exists."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_all.return_value = [
            {
                "id": "pos-1",
                "document_id": "doc-a",
                "position": "The claimant was dismissed due to redundancy",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "context": "ET3",
            },
        ]

        result = await engine.detect_inconsistencies(profile_id)

        assert result == []


# ---------------------------------------------------------------------------
# assess_strengths_weaknesses tests
# ---------------------------------------------------------------------------


class TestAssessStrengthsWeaknesses:
    """Tests for RespondentIntelEngine.assess_strengths_weaknesses."""

    @pytest.mark.asyncio
    async def test_assess_strengths_weaknesses(self, engine, mock_db):
        """Assessment returns both strengths and weaknesses sections."""
        profile_id = str(uuid.uuid4())

        # Profile data
        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "John Smith",
            "role": "Manager",
            "organization": "Bylor Ltd",
            "background": "10 years as line manager",
            "known_positions": '["dismissed for redundancy", "followed procedure"]',
            "strengths": "[]",
            "weaknesses": "[]",
        }

        # Positions
        mock_db.fetch_all.return_value = [
            {
                "id": "pos-1",
                "position": "Dismissed for redundancy",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "document_id": "doc-a",
                "context": "ET3",
            },
        ]

        # LLM assessment
        llm_resp = MagicMock()
        llm_resp.text = (
            '{"strengths": ["Consistent account of events", "Documentary evidence supports timeline"],'
            ' "weaknesses": ["Changed reason for dismissal", "No contemporaneous notes"]}'
        )
        engine._llm_service.generate.return_value = llm_resp

        result = await engine.assess_strengths_weaknesses(profile_id)

        assert "strengths" in result
        assert "weaknesses" in result
        assert len(result["strengths"]) >= 1
        assert len(result["weaknesses"]) >= 1

    @pytest.mark.asyncio
    async def test_assess_no_profile(self, engine, mock_db):
        """Assessment returns empty when profile not found."""
        profile_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = None

        result = await engine.assess_strengths_weaknesses(profile_id)

        assert result["strengths"] == []
        assert result["weaknesses"] == []

    @pytest.mark.asyncio
    async def test_assess_no_llm_fallback(self, engine_no_llm, mock_db):
        """Without LLM, rule-based assessment is returned."""
        profile_id = str(uuid.uuid4())

        mock_db.fetch_one.return_value = {
            "id": profile_id,
            "name": "Jane Doe",
            "role": "HR Director",
            "organization": "Corp",
            "background": "HR professional",
            "known_positions": '["followed procedure", "consulted with employee"]',
            "strengths": '["experience"]',
            "weaknesses": '["delayed response"]',
        }

        mock_db.fetch_all.return_value = [
            {
                "id": "pos-1",
                "position": "Followed procedure",
                "date": datetime(2024, 1, 10, tzinfo=timezone.utc),
                "document_id": "doc-a",
                "context": "Statement",
            },
            {
                "id": "pos-2",
                "position": "Consulted with employee",
                "date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "document_id": "doc-b",
                "context": "Minutes",
            },
        ]

        result = await engine_no_llm.assess_strengths_weaknesses(profile_id)

        assert "strengths" in result
        assert "weaknesses" in result
