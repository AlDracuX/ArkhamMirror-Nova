"""Tests for witnesses shard API endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_witnesses.api import init_api, router
from arkham_shard_witnesses.models import (
    CredibilityLevel,
    CrossExamNote,
    Party,
    Witness,
    WitnessRole,
    WitnessStatement,
    WitnessStats,
    WitnessStatus,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock WitnessesShard."""
    shard = MagicMock()
    shard.create_witness = AsyncMock()
    shard.get_witness = AsyncMock()
    shard.list_witnesses = AsyncMock()
    shard.count_witnesses = AsyncMock()
    shard.update_witness = AsyncMock()
    shard.delete_witness = AsyncMock()
    shard.add_statement = AsyncMock()
    shard.list_statements = AsyncMock()
    shard.update_statement = AsyncMock()
    shard.add_cross_exam_note = AsyncMock()
    shard.list_cross_exam_notes = AsyncMock()
    shard.get_witness_summary = AsyncMock()
    shard.link_entity = AsyncMock()
    shard.get_stats = AsyncMock()
    return shard


@pytest.fixture
def sample_witness():
    """Create a sample Witness."""
    return Witness(
        id="w-123",
        name="John Smith",
        role=WitnessRole.CLAIMANT,
        status=WitnessStatus.IDENTIFIED,
        party=Party.CLAIMANT,
        organization="Bylor Ltd",
        position="Engineer",
        credibility_level=CredibilityLevel.MEDIUM,
    )


@pytest.fixture
def sample_statement():
    """Create a sample WitnessStatement."""
    return WitnessStatement(
        id="stmt-123",
        witness_id="w-123",
        version=1,
        title="Statement v1",
        content="I, John Smith, state...",
        status="draft",
        key_points=["Point 1", "Point 2"],
    )


@pytest.fixture
def sample_note():
    """Create a sample CrossExamNote."""
    return CrossExamNote(
        id="n-123",
        witness_id="w-123",
        topic="Employment dates",
        question="When did you start?",
        expected_answer="March 2020",
    )


@pytest.fixture
def client(mock_shard):
    """Create test client with mocked shard."""
    init_api(shard=mock_shard, event_bus=MagicMock())
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    init_api(shard=None, event_bus=None)


def test_list_witnesses(client, mock_shard, sample_witness):
    """Test GET /api/witnesses/."""
    mock_shard.list_witnesses.return_value = [sample_witness]

    response = client.get("/api/witnesses/")
    assert response.status_code == 200
    data = response.json()
    assert len(data["witnesses"]) == 1
    assert data["witnesses"][0]["name"] == "John Smith"


def test_list_witnesses_with_filters(client, mock_shard):
    """Test GET /api/witnesses/ with filters."""
    mock_shard.list_witnesses.return_value = []

    response = client.get("/api/witnesses/?role=claimant&party=claimant&search=smith")
    assert response.status_code == 200
    assert response.json()["witnesses"] == []


def test_count_witnesses(client, mock_shard):
    """Test GET /api/witnesses/count."""
    mock_shard.count_witnesses.return_value = 12

    response = client.get("/api/witnesses/count")
    assert response.status_code == 200
    assert response.json()["count"] == 12


def test_create_witness(client, mock_shard, sample_witness):
    """Test POST /api/witnesses/."""
    mock_shard.create_witness.return_value = sample_witness

    response = client.post(
        "/api/witnesses/",
        json={
            "name": "John Smith",
            "role": "claimant",
            "party": "claimant",
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "John Smith"


def test_get_stats(client, mock_shard):
    """Test GET /api/witnesses/stats."""
    mock_shard.get_stats.return_value = WitnessStats(
        total_witnesses=10,
        by_role={"claimant": 5, "respondent_witness": 5},
        by_status={"identified": 3, "confirmed": 7},
        by_party={"claimant": 5, "respondent": 5},
        total_statements=8,
        total_cross_exam_notes=15,
    )

    response = client.get("/api/witnesses/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_witnesses"] == 10
    assert data["total_statements"] == 8


def test_get_witness(client, mock_shard, sample_witness):
    """Test GET /api/witnesses/{witness_id}."""
    mock_shard.get_witness.return_value = sample_witness
    mock_shard.list_statements.return_value = []
    mock_shard.list_cross_exam_notes.return_value = []

    response = client.get("/api/witnesses/w-123")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "w-123"
    assert data["statements"] == []
    assert data["cross_exam_notes"] == []


def test_get_witness_not_found(client, mock_shard):
    """Test GET /api/witnesses/{witness_id} not found."""
    mock_shard.get_witness.return_value = None

    response = client.get("/api/witnesses/nonexistent")
    assert response.status_code == 404


def test_update_witness(client, mock_shard, sample_witness):
    """Test PUT /api/witnesses/{witness_id}."""
    sample_witness.name = "Jane Smith"
    mock_shard.update_witness.return_value = sample_witness

    response = client.put("/api/witnesses/w-123", json={"name": "Jane Smith"})
    assert response.status_code == 200
    assert response.json()["name"] == "Jane Smith"


def test_update_witness_not_found(client, mock_shard):
    """Test PUT /api/witnesses/{witness_id} not found."""
    mock_shard.update_witness.return_value = None

    response = client.put("/api/witnesses/nonexistent", json={"name": "X"})
    assert response.status_code == 404


def test_delete_witness(client, mock_shard):
    """Test DELETE /api/witnesses/{witness_id}."""
    response = client.delete("/api/witnesses/w-123")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_add_statement(client, mock_shard, sample_statement):
    """Test POST /api/witnesses/{witness_id}/statements."""
    mock_shard.add_statement.return_value = sample_statement

    response = client.post(
        "/api/witnesses/w-123/statements",
        json={
            "title": "Statement v1",
            "content": "I, John Smith, state...",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Statement v1"
    assert data["version"] == 1


def test_list_statements(client, mock_shard, sample_statement):
    """Test GET /api/witnesses/{witness_id}/statements."""
    mock_shard.list_statements.return_value = [sample_statement]

    response = client.get("/api/witnesses/w-123/statements")
    assert response.status_code == 200
    assert len(response.json()["statements"]) == 1


def test_update_statement(client, mock_shard, sample_statement):
    """Test PUT /api/witnesses/{witness_id}/statements/{statement_id}."""
    sample_statement.status = "reviewed"
    mock_shard.update_statement.return_value = sample_statement

    response = client.put("/api/witnesses/w-123/statements/stmt-123", json={"status": "reviewed"})
    assert response.status_code == 200


def test_update_statement_not_found(client, mock_shard):
    """Test PUT statement not found."""
    mock_shard.update_statement.return_value = None

    response = client.put("/api/witnesses/w-123/statements/nonexistent", json={"status": "reviewed"})
    assert response.status_code == 404


def test_add_cross_exam(client, mock_shard, sample_note):
    """Test POST /api/witnesses/{witness_id}/cross-exam."""
    mock_shard.add_cross_exam_note.return_value = sample_note

    response = client.post(
        "/api/witnesses/w-123/cross-exam",
        json={
            "topic": "Employment dates",
            "question": "When did you start?",
            "expected_answer": "March 2020",
        },
    )
    assert response.status_code == 200
    assert response.json()["topic"] == "Employment dates"


def test_list_cross_exam(client, mock_shard, sample_note):
    """Test GET /api/witnesses/{witness_id}/cross-exam."""
    mock_shard.list_cross_exam_notes.return_value = [sample_note]

    response = client.get("/api/witnesses/w-123/cross-exam")
    assert response.status_code == 200
    assert len(response.json()["notes"]) == 1


def test_get_summary(client, mock_shard):
    """Test GET /api/witnesses/{witness_id}/summary."""
    mock_shard.get_witness_summary.return_value = {
        "witness_id": "w-123",
        "name": "John Smith",
        "role": "claimant",
        "party": "claimant",
        "credibility_level": "medium",
        "statement_count": 2,
        "cross_exam_note_count": 5,
    }

    response = client.get("/api/witnesses/w-123/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["statement_count"] == 2
    assert data["cross_exam_note_count"] == 5


def test_link_entity(client, mock_shard, sample_witness):
    """Test POST /api/witnesses/{witness_id}/link-entity."""
    sample_witness.linked_entity_id = "ent-1"
    mock_shard.link_entity.return_value = sample_witness

    response = client.post("/api/witnesses/w-123/link-entity", json={"entity_id": "ent-1"})
    assert response.status_code == 200
    assert response.json()["linked_entity_id"] == "ent-1"


def test_link_entity_not_found(client, mock_shard):
    """Test POST link-entity when witness not found."""
    mock_shard.link_entity.return_value = None

    response = client.post("/api/witnesses/nonexistent/link-entity", json={"entity_id": "ent-1"})
    assert response.status_code == 404
