"""Tests for casemap shard API endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_casemap.api import get_shard, init_api, router
from arkham_shard_casemap.models import (
    ClaimType,
    EvidenceLink,
    LegalElement,
    LegalTheory,
    StrengthAssessment,
    TheoryStatus,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock CasemapShard."""
    shard = MagicMock()
    shard.create_theory = AsyncMock()
    shard.get_theory = AsyncMock()
    shard.list_theories = AsyncMock()
    shard.count_theories = AsyncMock()
    shard.update_theory = AsyncMock()
    shard.delete_theory = AsyncMock()
    shard.create_element = AsyncMock()
    shard.list_elements = AsyncMock()
    shard.update_element = AsyncMock()
    shard.delete_element = AsyncMock()
    shard.link_evidence = AsyncMock()
    shard.list_evidence = AsyncMock()
    shard.delete_evidence = AsyncMock()
    shard.assess_strength = AsyncMock()
    shard.identify_gaps = AsyncMock()
    shard.get_evidence_matrix = AsyncMock()
    shard.get_theory_tree = AsyncMock()
    shard.seed_elements = AsyncMock()
    return shard


@pytest.fixture
def sample_theory():
    """Create a sample LegalTheory."""
    return LegalTheory(
        id="t-123",
        title="Unfair Dismissal",
        claim_type=ClaimType.UNFAIR_DISMISSAL,
        description="Test theory",
        statutory_basis="ERA 1996",
        status=TheoryStatus.ACTIVE,
        overall_strength=50,
    )


@pytest.fixture
def sample_element():
    """Create a sample LegalElement."""
    return LegalElement(
        id="e-123",
        theory_id="t-123",
        title="Employee with 2+ years service",
        burden="claimant",
        status="unproven",
        required=True,
        statutory_reference="ERA 1996 s.108",
        display_order=1,
    )


@pytest.fixture
def sample_evidence():
    """Create a sample EvidenceLink."""
    return EvidenceLink(
        id="ev-123",
        element_id="e-123",
        document_id="doc-1",
        description="Employment contract",
        strength="strong",
        supports_element=True,
    )


@pytest.fixture
def client(mock_shard):
    """Create test client with mocked shard."""
    init_api(shard=mock_shard, event_bus=MagicMock())
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    # Clean up
    init_api(shard=None, event_bus=None)


def test_list_theories(client, mock_shard, sample_theory):
    """Test GET /api/casemap/theories."""
    mock_shard.list_theories.return_value = [sample_theory]

    response = client.get("/api/casemap/theories")
    assert response.status_code == 200
    data = response.json()
    assert "theories" in data
    assert len(data["theories"]) == 1
    assert data["theories"][0]["title"] == "Unfair Dismissal"


def test_count_theories(client, mock_shard):
    """Test GET /api/casemap/theories/count."""
    mock_shard.count_theories.return_value = 5

    response = client.get("/api/casemap/theories/count")
    assert response.status_code == 200
    assert response.json()["count"] == 5


def test_create_theory(client, mock_shard, sample_theory):
    """Test POST /api/casemap/theories."""
    mock_shard.create_theory.return_value = sample_theory

    response = client.post(
        "/api/casemap/theories",
        json={
            "title": "Unfair Dismissal",
            "claim_type": "unfair_dismissal",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Unfair Dismissal"


def test_create_theory_with_seed(client, mock_shard, sample_theory, sample_element):
    """Test POST /api/casemap/theories with seed_elements=True."""
    mock_shard.create_theory.return_value = sample_theory
    mock_shard.seed_elements.return_value = [sample_element]

    response = client.post(
        "/api/casemap/theories",
        json={
            "title": "Unfair Dismissal",
            "claim_type": "unfair_dismissal",
            "seed_elements": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "seeded_elements" in data
    assert len(data["seeded_elements"]) == 1


def test_get_theory(client, mock_shard, sample_theory):
    """Test GET /api/casemap/theories/{theory_id}."""
    mock_shard.get_theory.return_value = sample_theory
    mock_shard.list_elements.return_value = []

    response = client.get("/api/casemap/theories/t-123")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "t-123"
    assert data["elements"] == []


def test_get_theory_not_found(client, mock_shard):
    """Test GET /api/casemap/theories/{theory_id} with non-existent ID."""
    mock_shard.get_theory.return_value = None

    response = client.get("/api/casemap/theories/nonexistent")
    assert response.status_code == 404


def test_update_theory(client, mock_shard, sample_theory):
    """Test PUT /api/casemap/theories/{theory_id}."""
    sample_theory.title = "Updated Title"
    mock_shard.update_theory.return_value = sample_theory

    response = client.put("/api/casemap/theories/t-123", json={"title": "Updated Title"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


def test_update_theory_not_found(client, mock_shard):
    """Test PUT /api/casemap/theories/{theory_id} when not found."""
    mock_shard.update_theory.return_value = None

    response = client.put("/api/casemap/theories/nonexistent", json={"title": "X"})
    assert response.status_code == 404


def test_delete_theory(client, mock_shard):
    """Test DELETE /api/casemap/theories/{theory_id}."""
    response = client.delete("/api/casemap/theories/t-123")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_create_element(client, mock_shard, sample_element):
    """Test POST /api/casemap/theories/{theory_id}/elements."""
    mock_shard.create_element.return_value = sample_element

    response = client.post(
        "/api/casemap/theories/t-123/elements",
        json={
            "title": "Employee with 2+ years service",
            "burden": "claimant",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Employee with 2+ years service"


def test_list_elements(client, mock_shard, sample_element):
    """Test GET /api/casemap/theories/{theory_id}/elements."""
    mock_shard.list_elements.return_value = [sample_element]

    response = client.get("/api/casemap/theories/t-123/elements")
    assert response.status_code == 200
    data = response.json()
    assert len(data["elements"]) == 1


def test_update_element_not_found(client, mock_shard):
    """Test PUT /api/casemap/elements/{element_id} when not found."""
    mock_shard.update_element.return_value = None

    response = client.put("/api/casemap/elements/nonexistent", json={"title": "X"})
    assert response.status_code == 404


def test_link_evidence(client, mock_shard, sample_evidence):
    """Test POST /api/casemap/elements/{element_id}/evidence."""
    mock_shard.link_evidence.return_value = sample_evidence

    response = client.post(
        "/api/casemap/elements/e-123/evidence",
        json={
            "document_id": "doc-1",
            "description": "Employment contract",
            "strength": "strong",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "doc-1"


def test_list_evidence(client, mock_shard, sample_evidence):
    """Test GET /api/casemap/elements/{element_id}/evidence."""
    mock_shard.list_evidence.return_value = [sample_evidence]

    response = client.get("/api/casemap/elements/e-123/evidence")
    assert response.status_code == 200
    assert len(response.json()["evidence"]) == 1


def test_delete_evidence(client, mock_shard):
    """Test DELETE /api/casemap/evidence/{link_id}."""
    response = client.delete("/api/casemap/evidence/ev-123")
    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_assess_strength(client, mock_shard):
    """Test GET /api/casemap/theories/{theory_id}/strength."""
    mock_shard.assess_strength.return_value = StrengthAssessment(
        theory_id="t-123",
        total_elements=3,
        proven_count=2,
        contested_count=1,
        overall_score=75,
        gaps=["e-2"],
        weaknesses=[],
        strengths=["e-1"],
    )

    response = client.get("/api/casemap/theories/t-123/strength")
    assert response.status_code == 200
    data = response.json()
    assert data["overall_score"] == 75
    assert data["proven_count"] == 2


def test_identify_gaps(client, mock_shard):
    """Test GET /api/casemap/theories/{theory_id}/gaps."""
    mock_shard.identify_gaps.return_value = [
        {
            "element_id": "e-1",
            "title": "Missing evidence",
            "burden": "claimant",
            "statutory_reference": "",
            "status": "unproven",
        },
    ]

    response = client.get("/api/casemap/theories/t-123/gaps")
    assert response.status_code == 200
    data = response.json()
    assert data["gap_count"] == 1


def test_seed_elements(client, mock_shard, sample_element):
    """Test POST /api/casemap/theories/{theory_id}/seed."""
    mock_shard.seed_elements.return_value = [sample_element]

    response = client.post("/api/casemap/theories/t-123/seed", json={"claim_type": "unfair_dismissal"})
    assert response.status_code == 200
    data = response.json()
    assert data["seeded"] == 1


def test_list_templates(client):
    """Test GET /api/casemap/templates."""
    response = client.get("/api/casemap/templates")
    assert response.status_code == 200
    data = response.json()
    assert "templates" in data
    assert "unfair_dismissal" in data["templates"]


def test_get_matrix(client, mock_shard):
    """Test GET /api/casemap/theories/{theory_id}/matrix."""
    mock_shard.get_evidence_matrix.return_value = {"elements": [], "evidence_columns": []}

    response = client.get("/api/casemap/theories/t-123/matrix")
    assert response.status_code == 200
    assert "elements" in response.json()


def test_get_tree(client, mock_shard):
    """Test GET /api/casemap/theories/{theory_id}/tree."""
    mock_shard.get_theory_tree.return_value = {"theory": {}, "elements": []}

    response = client.get("/api/casemap/theories/t-123/tree")
    assert response.status_code == 200
