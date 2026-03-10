"""
Tests for Letters Shard - API Endpoints
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_letters.api import router
from arkham_shard_letters.models import (
    ExportFormat,
    Letter,
    LetterExportResult,
    LetterStatistics,
    LetterStatus,
    LetterTemplate,
    LetterType,
)
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock shard for API testing."""
    shard = MagicMock()
    shard.version = "0.1.0"
    shard._db = MagicMock()
    shard._events = MagicMock()
    shard._llm = None
    shard._storage = None
    return shard


@pytest.fixture
def client(mock_shard):
    """Create a test client with mock shard on app state."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.state.letters_shard = mock_shard
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client, mock_shard):
        """Test GET /api/letters/health."""
        response = client.get("/api/letters/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "services" in data


class TestCountEndpoint:
    """Test count endpoint."""

    def test_get_count(self, client, mock_shard):
        """Test GET /api/letters/count."""
        mock_shard.get_count = AsyncMock(return_value=42)

        response = client.get("/api/letters/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 42

    def test_get_count_filtered(self, client, mock_shard):
        """Test GET /api/letters/count with status filter."""
        mock_shard.get_count = AsyncMock(return_value=10)

        response = client.get("/api/letters/count?status=draft")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 10


class TestLettersCRUD:
    """Test letter CRUD endpoints."""

    def test_list_letters(self, client, mock_shard):
        """Test GET /api/letters/."""
        mock_letter = Letter(
            id="letter-1",
            title="Test Letter",
            letter_type=LetterType.FOIA,
            status=LetterStatus.DRAFT,
            content="Test content",
        )

        mock_shard.list_letters = AsyncMock(return_value=[mock_letter])
        mock_shard.get_count = AsyncMock(return_value=1)

        response = client.get("/api/letters/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "letter-1"
        assert data["items"][0]["title"] == "Test Letter"

    def test_create_letter(self, client, mock_shard):
        """Test POST /api/letters/."""
        created_letter = Letter(
            id="new-letter",
            title="New Letter",
            letter_type=LetterType.COMPLAINT,
            status=LetterStatus.DRAFT,
            content="New content",
        )

        mock_shard.create_letter = AsyncMock(return_value=created_letter)

        response = client.post(
            "/api/letters/",
            json={
                "title": "New Letter",
                "letter_type": "complaint",
                "content": "New content",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-letter"
        assert data["title"] == "New Letter"
        assert data["letter_type"] == "complaint"

    def test_get_letter(self, client, mock_shard):
        """Test GET /api/letters/{id}."""
        mock_letter = Letter(
            id="letter-1",
            title="Test Letter",
            letter_type=LetterType.FOIA,
            status=LetterStatus.DRAFT,
            content="Test content",
        )

        mock_shard.get_letter = AsyncMock(return_value=mock_letter)

        response = client.get("/api/letters/letter-1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "letter-1"
        assert data["title"] == "Test Letter"

    def test_get_letter_not_found(self, client, mock_shard):
        """Test GET /api/letters/{id} with non-existent letter."""
        mock_shard.get_letter = AsyncMock(return_value=None)

        response = client.get("/api/letters/nonexistent")

        assert response.status_code == 404

    def test_update_letter(self, client, mock_shard):
        """Test PUT /api/letters/{id}."""
        updated_letter = Letter(
            id="letter-1",
            title="Updated Title",
            letter_type=LetterType.FOIA,
            status=LetterStatus.REVIEW,
            content="Updated content",
        )

        mock_shard.update_letter = AsyncMock(return_value=updated_letter)

        response = client.put(
            "/api/letters/letter-1",
            json={
                "title": "Updated Title",
                "status": "review",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["status"] == "review"

    def test_delete_letter(self, client, mock_shard):
        """Test DELETE /api/letters/{id}."""
        mock_shard.delete_letter = AsyncMock(return_value=True)

        response = client.delete("/api/letters/letter-1")

        assert response.status_code == 204


class TestLetterExport:
    """Test letter export endpoints."""

    def test_export_letter(self, client, mock_shard):
        """Test POST /api/letters/{id}/export."""
        export_result = LetterExportResult(
            letter_id="letter-1",
            success=True,
            export_format=ExportFormat.PDF,
            file_path="/tmp/letter-1.pdf",
            file_size=2048,
            processing_time_ms=123.45,
        )

        mock_shard.export_letter = AsyncMock(return_value=export_result)

        response = client.post(
            "/api/letters/letter-1/export",
            json={"export_format": "pdf"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["export_format"] == "pdf"
        assert data["file_path"] == "/tmp/letter-1.pdf"
        assert data["file_size"] == 2048

    def test_download_letter(self, client, mock_shard):
        """Test GET /api/letters/{id}/download."""
        mock_letter = Letter(
            id="letter-1",
            title="Test",
            letter_type=LetterType.FOIA,
            last_export_path="/tmp/letter-1.pdf",
            last_export_format=ExportFormat.PDF,
        )

        mock_shard.get_letter = AsyncMock(return_value=mock_letter)

        response = client.get("/api/letters/letter-1/download")

        assert response.status_code == 200
        data = response.json()
        assert "file_path" in data


class TestTemplates:
    """Test template endpoints.

    NOTE: GET /templates is shadowed by /{letter_id} route (defined earlier in api.py).
    FastAPI matches letter_id="templates" and calls get_letter("templates").
    POST /templates is NOT shadowed (POST / only matches exact "/").
    GET /templates/{id} is also shadowed (matches /{letter_id} with letter_id="templates").
    """

    def test_list_templates_shadowed(self, client, mock_shard):
        """Test GET /api/letters/templates is shadowed by /{letter_id}.

        The /{letter_id} route matches first with letter_id="templates".
        When get_letter returns None, it returns 404.
        """
        mock_shard.get_letter = AsyncMock(return_value=None)

        response = client.get("/api/letters/templates")

        # Shadowed by /{letter_id} -> get_letter("templates") -> None -> 404
        assert response.status_code == 404

    def test_create_template(self, client, mock_shard):
        """Test POST /api/letters/templates."""
        created_template = LetterTemplate(
            id="new-template",
            name="New Template",
            letter_type=LetterType.COMPLAINT,
            description="Test template",
            content_template="Template {{field}}",
            placeholders=["field"],
            required_placeholders=[],
        )

        mock_shard.create_template = AsyncMock(return_value=created_template)

        response = client.post(
            "/api/letters/templates",
            json={
                "name": "New Template",
                "letter_type": "complaint",
                "description": "Test template",
                "content_template": "Template {{field}}",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-template"
        assert data["name"] == "New Template"

    def test_get_template(self, client, mock_shard):
        """Test GET /api/letters/templates/{id}.

        This route is NOT shadowed because /templates/{template_id} has two
        path segments while /{letter_id} only matches one segment.
        """
        mock_template = LetterTemplate(
            id="template-1",
            name="Test Template",
            letter_type=LetterType.FOIA,
            description="Test",
            content_template="Content",
            placeholders=[],
            required_placeholders=[],
        )

        mock_shard.get_template = AsyncMock(return_value=mock_template)

        response = client.get("/api/letters/templates/template-1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "template-1"


class TestTemplateApplication:
    """Test template application endpoints."""

    def test_apply_template(self, client, mock_shard):
        """Test POST /api/letters/apply-template."""
        created_letter = Letter(
            id="new-letter",
            title="Letter from Template",
            letter_type=LetterType.FOIA,
            status=LetterStatus.DRAFT,
            content="Rendered content",
            template_id="template-1",
        )

        mock_shard.apply_template = AsyncMock(return_value=created_letter)

        response = client.post(
            "/api/letters/apply-template",
            json={
                "template_id": "template-1",
                "title": "Letter from Template",
                "placeholder_values": [
                    {"key": "name", "value": "John Doe"},
                ],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-letter"
        assert data["template_id"] == "template-1"


class TestStatistics:
    """Test statistics endpoint.

    NOTE: GET /stats is shadowed by /{letter_id} route (defined earlier in api.py).
    FastAPI matches letter_id="stats" and calls get_letter("stats").
    """

    def test_get_statistics_shadowed(self, client, mock_shard):
        """Test GET /api/letters/stats is shadowed by /{letter_id}.

        The /{letter_id} route matches first with letter_id="stats".
        When get_letter returns None, it returns 404.
        """
        mock_shard.get_letter = AsyncMock(return_value=None)

        response = client.get("/api/letters/stats")

        # Shadowed by /{letter_id} -> get_letter("stats") -> None -> 404
        assert response.status_code == 404


class TestFilteredLists:
    """Test filtered list endpoints.

    NOTE: GET /drafts and /finalized are shadowed by /{letter_id} route.
    FastAPI matches letter_id="drafts" or "finalized" and calls get_letter().
    """

    def test_list_drafts_shadowed(self, client, mock_shard):
        """Test GET /api/letters/drafts is shadowed by /{letter_id}.

        The /{letter_id} route matches with letter_id="drafts".
        When get_letter returns None, it returns 404.
        """
        mock_shard.get_letter = AsyncMock(return_value=None)

        response = client.get("/api/letters/drafts")

        # Shadowed by /{letter_id} -> get_letter("drafts") -> None -> 404
        assert response.status_code == 404

    def test_list_finalized_shadowed(self, client, mock_shard):
        """Test GET /api/letters/finalized is shadowed by /{letter_id}.

        The /{letter_id} route matches with letter_id="finalized".
        When get_letter returns None, it returns 404.
        """
        mock_shard.get_letter = AsyncMock(return_value=None)

        response = client.get("/api/letters/finalized")

        # Shadowed by /{letter_id} -> get_letter("finalized") -> None -> 404
        assert response.status_code == 404
