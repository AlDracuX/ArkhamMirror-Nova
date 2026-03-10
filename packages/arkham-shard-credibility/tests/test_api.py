"""
Tests for credibility shard API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_credibility.api import router
from arkham_shard_credibility.models import (
    AssessmentMethod,
    CredibilityAssessment,
    CredibilityFactor,
    CredibilityStatistics,
    SourceCredibility,
    SourceType,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock CredibilityShard instance."""
    shard = MagicMock()

    # Mock async methods
    shard.create_assessment = AsyncMock()
    shard.get_assessment = AsyncMock()
    shard.list_assessments = AsyncMock()
    shard.update_assessment = AsyncMock()
    shard.delete_assessment = AsyncMock()
    shard.get_source_credibility = AsyncMock()
    shard.get_source_history = AsyncMock()
    shard.calculate_credibility = AsyncMock()
    shard.get_statistics = AsyncMock()
    shard.get_count = AsyncMock()
    shard.get_standard_factors = MagicMock()

    return shard


@pytest.fixture
def sample_assessment():
    """Create a sample CredibilityAssessment for testing."""
    return CredibilityAssessment(
        id="test-123",
        source_type=SourceType.DOCUMENT,
        source_id="doc-123",
        score=75,
        confidence=0.9,
        factors=[
            CredibilityFactor(
                factor_type="source_reliability",
                weight=0.25,
                score=80,
            )
        ],
        assessed_by=AssessmentMethod.MANUAL,
        assessor_id="analyst-1",
        notes="Test assessment",
    )


@pytest.fixture
def client(mock_shard):
    """Create test client with mocked shard."""
    with patch("arkham_shard_credibility.api._get_shard", return_value=mock_shard):
        app = FastAPI()
        app.include_router(router)
        yield TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/api/credibility/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["shard"] == "credibility"


def test_create_assessment(client, mock_shard, sample_assessment):
    """Test POST /api/credibility/ endpoint."""
    mock_shard.create_assessment.return_value = sample_assessment

    response = client.post(
        "/api/credibility/",
        json={
            "source_type": "document",
            "source_id": "doc-123",
            "score": 75,
            "confidence": 0.9,
            "assessed_by": "manual",
            "assessor_id": "analyst-1",
            "notes": "Test assessment",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "test-123"
    assert data["score"] == 75
    assert data["level"] == "high"


def test_get_assessment(client, mock_shard, sample_assessment):
    """Test GET /api/credibility/{id} endpoint."""
    mock_shard.get_assessment.return_value = sample_assessment

    response = client.get("/api/credibility/test-123")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-123"
    assert data["score"] == 75


def test_get_assessment_not_found(client, mock_shard):
    """Test GET /api/credibility/{id} with non-existent ID."""
    mock_shard.get_assessment.return_value = None

    response = client.get("/api/credibility/nonexistent")

    assert response.status_code == 404


def test_list_assessments(client, mock_shard, sample_assessment):
    """Test GET /api/credibility/ endpoint."""
    mock_shard.list_assessments.return_value = [sample_assessment]
    mock_shard.get_count.return_value = 1

    response = client.get("/api/credibility/")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_update_assessment(client, mock_shard, sample_assessment):
    """Test PUT /api/credibility/{id} endpoint."""
    updated_assessment = sample_assessment
    updated_assessment.score = 85

    mock_shard.update_assessment.return_value = updated_assessment

    response = client.put("/api/credibility/test-123", json={"score": 85})

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 85


def test_delete_assessment(client, mock_shard):
    """Test DELETE /api/credibility/{id} endpoint."""
    mock_shard.delete_assessment.return_value = True

    response = client.delete("/api/credibility/test-123")

    assert response.status_code == 204


def test_get_count(client, mock_shard):
    """Test GET /api/credibility/count endpoint."""
    mock_shard.get_count.return_value = 42

    response = client.get("/api/credibility/count")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 42


def test_get_statistics(client, mock_shard):
    """Test GET /api/credibility/stats endpoint."""
    stats = CredibilityStatistics(
        total_assessments=100,
        by_source_type={"document": 60, "entity": 40},
        by_level={"high": 50, "medium": 30, "low": 20},
        by_method={"manual": 70, "automated": 30},
        avg_score=65.5,
        avg_confidence=0.85,
        unreliable_count=5,
        low_count=15,
        medium_count=30,
        high_count=40,
        verified_count=10,
        sources_assessed=50,
        avg_assessments_per_source=2.0,
    )

    mock_shard.get_statistics.return_value = stats

    response = client.get("/api/credibility/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["total_assessments"] == 100
    assert data["avg_score"] == 65.5


def test_get_standard_factors(client, mock_shard):
    """Test GET /api/credibility/factors endpoint."""
    mock_shard.get_standard_factors.return_value = [
        {
            "factor_type": "source_reliability",
            "default_weight": 0.25,
            "description": "Track record of accuracy",
            "scoring_guidance": "100: Flawless, 0: Unreliable",
        }
    ]

    response = client.get("/api/credibility/factors")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["factor_type"] == "source_reliability"
