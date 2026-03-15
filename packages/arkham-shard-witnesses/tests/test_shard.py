"""Tests for witnesses shard implementation."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_witnesses.models import (
    CredibilityLevel,
    CrossExamNote,
    Party,
    StatementStatus,
    Witness,
    WitnessFilter,
    WitnessRole,
    WitnessStatement,
    WitnessStats,
    WitnessStatus,
)
from arkham_shard_witnesses.shard import WitnessesShard, _parse_json_field


@pytest.fixture
def mock_frame():
    """Create a mock ArkhamFrame instance."""
    frame = MagicMock()
    frame.database = MagicMock()
    frame.get_service = MagicMock(return_value=MagicMock())

    frame.database.execute = AsyncMock()
    frame.database.fetch_one = AsyncMock()
    frame.database.fetch_all = AsyncMock()

    events = frame.get_service.return_value
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    events.emit = AsyncMock()

    return frame


@pytest.fixture
async def shard(mock_frame):
    """Create an initialized WitnessesShard instance."""
    s = WitnessesShard()
    await s.initialize(mock_frame)
    return s


def _witness_row(id="w-1", name="John Smith", role="claimant", status="identified", party="claimant", **kwargs):
    """Helper to create a witness row dict."""
    now = datetime.utcnow()
    base = {
        "id": id,
        "name": name,
        "role": role,
        "status": status,
        "party": party,
        "organization": kwargs.get("organization"),
        "position": kwargs.get("position"),
        "contact_info": kwargs.get("contact_info", "{}"),
        "notes": kwargs.get("notes", ""),
        "credibility_level": kwargs.get("credibility_level", "unknown"),
        "credibility_notes": kwargs.get("credibility_notes", ""),
        "linked_entity_id": kwargs.get("linked_entity_id"),
        "linked_document_ids": kwargs.get("linked_document_ids", "[]"),
        "created_at": now,
        "updated_at": now,
        "metadata": kwargs.get("metadata", "{}"),
    }
    return base


def _statement_row(id="stmt-1", witness_id="w-1", version=1, **kwargs):
    """Helper to create a statement row dict."""
    now = datetime.utcnow()
    return {
        "id": id,
        "witness_id": witness_id,
        "version": version,
        "title": kwargs.get("title", "Statement v1"),
        "content": kwargs.get("content", "I, John Smith, state that..."),
        "status": kwargs.get("status", "draft"),
        "key_points": kwargs.get("key_points", "[]"),
        "contradictions_found": kwargs.get("contradictions_found", "[]"),
        "filed_date": kwargs.get("filed_date"),
        "created_at": now,
        "updated_at": now,
    }


# === Initialization Tests ===


@pytest.mark.asyncio
async def test_shard_initialization(mock_frame):
    """Test shard initializes correctly."""
    s = WitnessesShard()
    assert s.name == "witnesses"
    assert s.version == "0.1.0"
    await s.initialize(mock_frame)
    assert s._db is mock_frame.database
    assert s._event_bus is not None
    mock_frame.database.execute.assert_called()


@pytest.mark.asyncio
async def test_shard_shutdown(shard, mock_frame):
    """Test shard shutdown clears references."""
    await shard.shutdown()
    assert shard._db is None
    assert shard._event_bus is None


@pytest.mark.asyncio
async def test_get_routes(shard):
    """Test get_routes returns the router."""
    routes = shard.get_routes()
    assert routes is not None


@pytest.mark.asyncio
async def test_event_subscriptions(mock_frame):
    """Test event bus subscriptions happen during init."""
    s = WitnessesShard()
    await s.initialize(mock_frame)
    events = mock_frame.get_service.return_value
    assert events.subscribe.call_count == 3


# === Witness CRUD Tests ===


@pytest.mark.asyncio
async def test_create_witness(shard, mock_frame):
    """Test creating a witness."""
    mock_frame.database.fetch_one.return_value = _witness_row()

    witness = await shard.create_witness(
        {
            "name": "John Smith",
            "role": "claimant",
            "party": "claimant",
        }
    )

    assert witness.name == "John Smith"
    assert witness.role == "claimant"
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_create_witness_with_details(shard, mock_frame):
    """Test creating a witness with full details."""
    mock_frame.database.fetch_one.return_value = _witness_row(
        organization="Bylor Ltd",
        position="Manager",
        credibility_level="high",
        credibility_notes="Reliable",
    )

    witness = await shard.create_witness(
        {
            "name": "John Smith",
            "organization": "Bylor Ltd",
            "position": "Manager",
            "credibility_level": "high",
            "credibility_notes": "Reliable",
            "contact_info": {"email": "john@example.com"},
        }
    )

    assert witness.organization == "Bylor Ltd"
    assert witness.credibility_level == "high"


@pytest.mark.asyncio
async def test_get_witness(shard, mock_frame):
    """Test retrieving a witness by ID."""
    mock_frame.database.fetch_one.return_value = _witness_row()

    witness = await shard.get_witness("w-1")
    assert witness is not None
    assert witness.id == "w-1"
    assert witness.name == "John Smith"


@pytest.mark.asyncio
async def test_get_witness_not_found(shard, mock_frame):
    """Test retrieving non-existent witness."""
    mock_frame.database.fetch_one.return_value = None
    witness = await shard.get_witness("nonexistent")
    assert witness is None


@pytest.mark.asyncio
async def test_list_witnesses(shard, mock_frame):
    """Test listing witnesses."""
    mock_frame.database.fetch_all.return_value = [
        _witness_row(id="w-1", name="Witness A"),
        _witness_row(id="w-2", name="Witness B", party="respondent"),
    ]

    witnesses = await shard.list_witnesses()
    assert len(witnesses) == 2
    assert witnesses[0].name == "Witness A"
    assert witnesses[1].party == "respondent"


@pytest.mark.asyncio
async def test_list_witnesses_with_filter(shard, mock_frame):
    """Test listing witnesses with filters."""
    mock_frame.database.fetch_all.return_value = []

    filters = WitnessFilter(
        role=WitnessRole.CLAIMANT,
        status=WitnessStatus.IDENTIFIED,
        party=Party.CLAIMANT,
        credibility_level=CredibilityLevel.HIGH,
        search_text="smith",
    )
    witnesses = await shard.list_witnesses(filters=filters)
    assert witnesses == []
    mock_frame.database.fetch_all.assert_called()


@pytest.mark.asyncio
async def test_count_witnesses(shard, mock_frame):
    """Test counting witnesses."""
    mock_frame.database.fetch_one.return_value = {"cnt": 8}
    count = await shard.count_witnesses()
    assert count == 8


@pytest.mark.asyncio
async def test_count_witnesses_empty(shard, mock_frame):
    """Test counting witnesses when none exist."""
    mock_frame.database.fetch_one.return_value = None
    count = await shard.count_witnesses()
    assert count == 0


@pytest.mark.asyncio
async def test_update_witness(shard, mock_frame):
    """Test updating a witness."""
    mock_frame.database.fetch_one.return_value = _witness_row(
        name="Jane Smith",
        credibility_level="high",
    )

    witness = await shard.update_witness(
        "w-1",
        {
            "name": "Jane Smith",
            "credibility_level": "high",
        },
    )
    assert witness.name == "Jane Smith"
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_delete_witness(shard, mock_frame):
    """Test deleting a witness."""
    result = await shard.delete_witness("w-1")
    assert result is True
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


# === Statement Tests ===


@pytest.mark.asyncio
async def test_add_statement(shard, mock_frame):
    """Test adding a witness statement."""
    mock_frame.database.fetch_one.side_effect = [
        {"next_ver": 1},  # version auto-increment
        _statement_row(),  # get_statement
    ]

    stmt = await shard.add_statement(
        "w-1",
        {
            "title": "Statement v1",
            "content": "I, John Smith, state that...",
            "status": "draft",
        },
    )

    assert stmt.title == "Statement v1"
    assert stmt.witness_id == "w-1"
    mock_frame.database.execute.assert_called()
    mock_frame.get_service.return_value.emit.assert_called()


@pytest.mark.asyncio
async def test_get_statement(shard, mock_frame):
    """Test retrieving a statement."""
    mock_frame.database.fetch_one.return_value = _statement_row()
    stmt = await shard.get_statement("stmt-1")
    assert stmt is not None
    assert stmt.id == "stmt-1"


@pytest.mark.asyncio
async def test_get_statement_not_found(shard, mock_frame):
    """Test retrieving non-existent statement."""
    mock_frame.database.fetch_one.return_value = None
    stmt = await shard.get_statement("nonexistent")
    assert stmt is None


@pytest.mark.asyncio
async def test_list_statements(shard, mock_frame):
    """Test listing statements for a witness."""
    mock_frame.database.fetch_all.return_value = [
        _statement_row(id="s-1", version=2),
        _statement_row(id="s-2", version=1),
    ]

    stmts = await shard.list_statements("w-1")
    assert len(stmts) == 2


@pytest.mark.asyncio
async def test_update_statement(shard, mock_frame):
    """Test updating a statement."""
    mock_frame.database.fetch_one.return_value = _statement_row(
        status="reviewed",
        content="Updated content",
    )

    stmt = await shard.update_statement(
        "stmt-1",
        {
            "status": "reviewed",
            "content": "Updated content",
        },
    )
    assert stmt is not None
    mock_frame.database.execute.assert_called()


# === Cross Examination Notes ===


@pytest.mark.asyncio
async def test_add_cross_exam_note(shard, mock_frame):
    """Test adding a cross-examination note."""
    note = await shard.add_cross_exam_note(
        "w-1",
        {
            "topic": "Employment dates",
            "question": "When did you start?",
            "expected_answer": "March 2020",
            "actual_answer": "",
            "effectiveness": "",
        },
    )

    assert note.witness_id == "w-1"
    assert note.topic == "Employment dates"
    assert note.question == "When did you start?"
    mock_frame.database.execute.assert_called()


@pytest.mark.asyncio
async def test_list_cross_exam_notes(shard, mock_frame):
    """Test listing cross-exam notes for a witness."""
    now = datetime.utcnow()
    mock_frame.database.fetch_all.return_value = [
        {
            "id": "n-1",
            "witness_id": "w-1",
            "statement_id": None,
            "topic": "Dates",
            "question": "When?",
            "expected_answer": "March",
            "actual_answer": "",
            "effectiveness": "",
            "notes": "",
            "created_at": now,
        },
    ]

    notes = await shard.list_cross_exam_notes("w-1")
    assert len(notes) == 1
    assert notes[0].topic == "Dates"


# === Entity Linking ===


@pytest.mark.asyncio
async def test_link_entity(shard, mock_frame):
    """Test linking a witness to an entity."""
    mock_frame.database.fetch_one.return_value = _witness_row(
        linked_entity_id="ent-1",
    )

    witness = await shard.link_entity("w-1", "ent-1")
    assert witness is not None
    mock_frame.database.execute.assert_called()


# === Summary ===


@pytest.mark.asyncio
async def test_get_witness_summary(shard, mock_frame):
    """Test getting witness summary."""
    mock_frame.database.fetch_one.side_effect = [
        _witness_row(),  # get_witness
        {"cnt": 2},  # statement count
        {"cnt": 3},  # cross-exam count
    ]

    summary = await shard.get_witness_summary("w-1")
    assert summary["name"] == "John Smith"
    assert summary["statement_count"] == 2
    assert summary["cross_exam_note_count"] == 3


@pytest.mark.asyncio
async def test_get_witness_summary_not_found(shard, mock_frame):
    """Test witness summary when witness not found."""
    mock_frame.database.fetch_one.return_value = None
    summary = await shard.get_witness_summary("nonexistent")
    assert summary == {}


# === Stats ===


@pytest.mark.asyncio
async def test_get_stats(shard, mock_frame):
    """Test getting witness statistics."""
    mock_frame.database.fetch_all.return_value = [
        {"role": "claimant", "status": "identified", "party": "claimant", "cnt": 3},
        {"role": "respondent_witness", "status": "confirmed", "party": "respondent", "cnt": 2},
    ]
    mock_frame.database.fetch_one.side_effect = [
        {"cnt": 5},  # total statements
        {"cnt": 8},  # total cross-exam notes
    ]

    stats = await shard.get_stats()
    assert stats.total_witnesses == 5
    assert stats.by_role["claimant"] == 3
    assert stats.by_party["respondent"] == 2
    assert stats.total_statements == 5
    assert stats.total_cross_exam_notes == 8


# === Helper Tests ===


def test_parse_json_field_none():
    """Test _parse_json_field with None."""
    assert _parse_json_field(None) == []
    assert _parse_json_field(None, {}) == {}


def test_parse_json_field_valid_json():
    """Test _parse_json_field with valid JSON."""
    assert _parse_json_field('["a","b"]') == ["a", "b"]
    assert _parse_json_field('{"k": "v"}') == {"k": "v"}


def test_parse_json_field_invalid():
    """Test _parse_json_field with invalid JSON."""
    assert _parse_json_field("not json") == []


def test_parse_json_field_passthrough():
    """Test _parse_json_field passes through lists and dicts."""
    assert _parse_json_field([1, 2]) == [1, 2]
    assert _parse_json_field({"a": 1}) == {"a": 1}


# === Model Tests ===


def test_witness_defaults():
    """Test Witness dataclass defaults."""
    w = Witness(id="w-1", name="Test", role=WitnessRole.CLAIMANT)
    assert w.status == WitnessStatus.IDENTIFIED
    assert w.party == Party.CLAIMANT
    assert w.credibility_level == CredibilityLevel.UNKNOWN
    assert w.linked_document_ids == []
    assert w.metadata == {}


def test_witness_statement_defaults():
    """Test WitnessStatement defaults."""
    s = WitnessStatement(id="s-1", witness_id="w-1")
    assert s.version == 1
    assert s.status == StatementStatus.DRAFT
    assert s.key_points == []
    assert s.contradictions_found == []


def test_cross_exam_note_defaults():
    """Test CrossExamNote defaults."""
    n = CrossExamNote(id="n-1", witness_id="w-1")
    assert n.topic == ""
    assert n.question == ""
    assert n.statement_id is None


def test_witness_filter_defaults():
    """Test WitnessFilter defaults."""
    f = WitnessFilter()
    assert f.role is None
    assert f.search_text is None


def test_witness_stats_defaults():
    """Test WitnessStats defaults."""
    s = WitnessStats()
    assert s.total_witnesses == 0
    assert s.by_role == {}
    assert s.total_statements == 0


def test_witness_role_enum():
    """Test WitnessRole enum values."""
    assert WitnessRole.CLAIMANT.value == "claimant"
    assert WitnessRole.RESPONDENT_WITNESS.value == "respondent_witness"
    assert WitnessRole.EXPERT.value == "expert"
    assert WitnessRole.INDEPENDENT.value == "independent"


def test_party_enum():
    """Test Party enum values."""
    assert Party.CLAIMANT.value == "claimant"
    assert Party.RESPONDENT.value == "respondent"
    assert Party.THIRD_PARTY.value == "third_party"


def test_credibility_enum():
    """Test CredibilityLevel enum values."""
    assert CredibilityLevel.HIGH.value == "high"
    assert CredibilityLevel.LOW.value == "low"
    assert CredibilityLevel.UNKNOWN.value == "unknown"
