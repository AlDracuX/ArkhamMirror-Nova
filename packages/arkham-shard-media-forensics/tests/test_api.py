"""Tests for media-forensics shard API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_media_forensics.api import init_api, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock MediaForensicsShard."""
    shard = MagicMock()
    shard.get_analysis_count = AsyncMock()
    shard.list_analyses = AsyncMock()
    shard.get_analysis = AsyncMock()
    shard.get_analysis_by_document = AsyncMock()
    shard.analyze_document = AsyncMock()
    shard.generate_ela = AsyncMock()
    shard.find_similar_images = AsyncMock()
    shard.get_stats = AsyncMock()
    return shard


@pytest.fixture
def client(mock_shard):
    """Create test client with mocked shard."""
    app = FastAPI()
    app.state.media_forensics_shard = mock_shard
    app.include_router(router)
    init_api(mock_shard)
    yield TestClient(app)
    init_api(None)


def test_get_analyses_count(client, mock_shard):
    """Test GET /api/media-forensics/analyses/count."""
    mock_shard.get_analysis_count.return_value = 42

    response = client.get("/api/media-forensics/analyses/count")
    assert response.status_code == 200
    assert response.json()["count"] == 42


def test_get_analyses_count_error(client, mock_shard):
    """Test count endpoint returns 0 on error."""
    mock_shard.get_analysis_count.side_effect = Exception("DB error")

    response = client.get("/api/media-forensics/analyses/count")
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_list_analyses(client, mock_shard):
    """Test GET /api/media-forensics/analyses."""
    mock_shard.list_analyses.return_value = [
        {"id": "a-1", "document_id": "doc-1", "integrity_status": "unverified"},
    ]
    mock_shard.get_analysis_count.return_value = 1

    response = client.get("/api/media-forensics/analyses")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_list_analyses_with_filters(client, mock_shard):
    """Test GET /api/media-forensics/analyses with filters."""
    mock_shard.list_analyses.return_value = []
    mock_shard.get_analysis_count.return_value = 0

    response = client.get("/api/media-forensics/analyses?integrity_status=verified&has_c2pa=true&limit=10&offset=0")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_list_analyses_pagination(client, mock_shard):
    """Test analyses list pagination metadata."""
    mock_shard.list_analyses.return_value = [{"id": f"a-{i}"} for i in range(10)]
    mock_shard.get_analysis_count.return_value = 25

    response = client.get("/api/media-forensics/analyses?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 25
    assert data["has_more"] is True


def test_get_analysis(client, mock_shard):
    """Test GET /api/media-forensics/analyses/{analysis_id}."""
    mock_shard.get_analysis.return_value = {
        "id": "a-1",
        "document_id": "doc-1",
        "integrity_status": "unverified",
        "exif_data": {"Make": "Canon"},
    }

    response = client.get("/api/media-forensics/analyses/a-1")
    assert response.status_code == 200
    assert response.json()["id"] == "a-1"


def test_get_analysis_not_found(client, mock_shard):
    """Test GET /api/media-forensics/analyses/{analysis_id} not found."""
    mock_shard.get_analysis.return_value = None

    response = client.get("/api/media-forensics/analyses/nonexistent")
    assert response.status_code == 404


def test_get_analysis_by_document(client, mock_shard):
    """Test GET /api/media-forensics/document/{document_id}."""
    mock_shard.get_analysis_by_document.return_value = {
        "id": "a-1",
        "document_id": "doc-1",
    }

    response = client.get("/api/media-forensics/document/doc-1")
    assert response.status_code == 200
    assert response.json()["document_id"] == "doc-1"


def test_get_analysis_by_document_not_found(client, mock_shard):
    """Test GET /api/media-forensics/document/{document_id} not found."""
    mock_shard.get_analysis_by_document.return_value = None

    response = client.get("/api/media-forensics/document/nonexistent")
    assert response.status_code == 404


def test_analyze_document(client, mock_shard):
    """Test POST /api/media-forensics/analyze."""
    mock_shard.analyze_document.return_value = {
        "analysis_id": "a-new",
        "document_id": "doc-1",
        "integrity_status": "unverified",
        "warnings": [],
        "exif": {},
        "hashes": {},
    }

    response = client.post("/api/media-forensics/analyze", json={"document_id": "doc-1"})
    assert response.status_code == 200
    assert response.json()["analysis_id"] == "a-new"


def test_analyze_document_not_found(client, mock_shard):
    """Test POST /api/media-forensics/analyze with non-existent document."""
    mock_shard.analyze_document.side_effect = FileNotFoundError("Document not found")

    response = client.post("/api/media-forensics/analyze", json={"document_id": "nonexistent"})
    assert response.status_code == 404


def test_analyze_document_bad_type(client, mock_shard):
    """Test POST /api/media-forensics/analyze with non-image document."""
    mock_shard.analyze_document.side_effect = ValueError("Not an image")

    response = client.post("/api/media-forensics/analyze", json={"document_id": "doc-pdf"})
    assert response.status_code == 400


def test_analyze_batch(client, mock_shard):
    """Test POST /api/media-forensics/analyze/batch."""
    mock_shard.analyze_document.side_effect = [
        {"analysis_id": "a-1", "document_id": "doc-1", "integrity_status": "unverified"},
        FileNotFoundError("Not found"),
    ]

    response = client.post(
        "/api/media-forensics/analyze/batch",
        json={
            "document_ids": ["doc-1", "doc-2"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["successful"] == 1
    assert data["failed"] == 1
