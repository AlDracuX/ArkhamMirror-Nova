"""
Tests for Templates Shard API Routes
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_templates import TemplatesShard
from arkham_shard_templates.api import router, set_shard
from arkham_shard_templates.models import (
    OutputFormat,
    Template,
    TemplateCreate,
    TemplatePlaceholder,
    TemplateRenderRequest,
    TemplateType,
)
from fastapi.testclient import TestClient


class MockDatabase:
    """In-memory mock database that simulates execute/fetch_one/fetch_all."""

    def __init__(self):
        self.templates = {}  # id -> row dict
        self.versions = {}  # id -> row dict

    async def execute(self, sql, params=None):
        """Handle INSERT, UPDATE, DELETE, CREATE TABLE, etc."""
        if params is None:
            params = {}

        sql_stripped = sql.strip().upper()

        # Schema creation / index creation / DO blocks - just ignore
        if sql_stripped.startswith("CREATE") or sql_stripped.startswith("DO"):
            return

        # INSERT INTO arkham_templates
        if "INSERT INTO ARKHAM_TEMPLATES" in sql_stripped:
            row = dict(params)
            self.templates[row["id"]] = row
            return

        # INSERT INTO arkham_template_versions
        if "INSERT INTO ARKHAM_TEMPLATE_VERSIONS" in sql_stripped:
            row = dict(params)
            self.versions[row["id"]] = row
            return

        # UPDATE arkham_templates
        if "UPDATE ARKHAM_TEMPLATES" in sql_stripped:
            tid = params.get("id")
            if tid and tid in self.templates:
                for k, v in params.items():
                    if k != "id":
                        self.templates[tid][k] = v
            return

        # DELETE FROM arkham_templates
        if "DELETE FROM ARKHAM_TEMPLATES" in sql_stripped:
            tid = params.get("id")
            if tid and tid in self.templates:
                del self.templates[tid]
                # Also delete associated versions
                to_delete = [vid for vid, v in self.versions.items() if v.get("template_id") == tid]
                for vid in to_delete:
                    del self.versions[vid]
            return

    async def fetch_one(self, sql, params=None):
        """Handle SELECT queries returning a single row."""
        if params is None:
            params = {}

        sql_upper = sql.strip().upper()

        # COUNT queries
        if "COUNT(*)" in sql_upper:
            if "ARKHAM_TEMPLATE_VERSIONS" in sql_upper:
                rows = list(self.versions.values())
                if "TEMPLATE_ID" in sql_upper:
                    tid = params.get("template_id")
                    rows = [r for r in rows if r.get("template_id") == tid]
                return {"count": len(rows)}

            if "ARKHAM_TEMPLATES" in sql_upper:
                rows = list(self.templates.values())
                if "IS_ACTIVE = TRUE" in sql_upper:
                    rows = [r for r in rows if r.get("is_active") is True]
                if "IS_ACTIVE = :IS_ACTIVE" in sql_upper:
                    rows = [r for r in rows if r.get("is_active") == params.get("is_active")]
                if "TEMPLATE_TYPE = :TEMPLATE_TYPE" in sql_upper:
                    rows = [r for r in rows if r.get("template_type") == params.get("template_type")]
                if "LOWER(NAME) LIKE :NAME_CONTAINS" in sql_upper:
                    pattern = params.get("name_contains", "")
                    rows = [r for r in rows if pattern.strip("%").lower() in r.get("name", "").lower()]
                return {"count": len(rows)}

        # SELECT id FROM arkham_templates WHERE id = :id (existence check in _save_template)
        if "SELECT ID FROM ARKHAM_TEMPLATES" in sql_upper:
            tid = params.get("id")
            if tid in self.templates:
                return {"id": tid}
            return None

        # SELECT * FROM arkham_templates WHERE id = :id
        if "ARKHAM_TEMPLATES" in sql_upper and "WHERE" in sql_upper:
            tid = params.get("id")
            if tid and tid in self.templates:
                return dict(self.templates[tid])
            return None

        # SELECT * FROM arkham_template_versions WHERE id = :id
        if "ARKHAM_TEMPLATE_VERSIONS" in sql_upper and "WHERE" in sql_upper:
            vid = params.get("id")
            if vid and vid in self.versions:
                return dict(self.versions[vid])
            return None

        return None

    async def fetch_all(self, sql, params=None):
        """Handle SELECT queries returning multiple rows."""
        if params is None:
            params = {}

        sql_upper = sql.strip().upper()

        # SELECT template_type, COUNT(*) ... GROUP BY template_type
        if "GROUP BY TEMPLATE_TYPE" in sql_upper:
            type_counts = {}
            for row in self.templates.values():
                t = row.get("template_type", "")
                type_counts[t] = type_counts.get(t, 0) + 1
            return [{"template_type": k, "count": v} for k, v in type_counts.items()]

        # SELECT * FROM arkham_template_versions WHERE template_id = :template_id
        if "ARKHAM_TEMPLATE_VERSIONS" in sql_upper:
            tid = params.get("template_id")
            rows = [dict(v) for v in self.versions.values() if v.get("template_id") == tid]
            if "ORDER BY VERSION_NUMBER DESC" in sql_upper:
                rows.sort(key=lambda r: r.get("version_number", 0), reverse=True)
            return rows

        # SELECT * FROM arkham_templates with filtering/pagination
        if "ARKHAM_TEMPLATES" in sql_upper:
            rows = list(self.templates.values())

            # Apply filters
            if "TEMPLATE_TYPE = :TEMPLATE_TYPE" in sql_upper:
                tt = params.get("template_type")
                rows = [r for r in rows if r.get("template_type") == tt]
            if "IS_ACTIVE = :IS_ACTIVE" in sql_upper:
                ia = params.get("is_active")
                rows = [r for r in rows if r.get("is_active") == ia]
            if "LOWER(NAME) LIKE :NAME_CONTAINS" in sql_upper:
                pattern = params.get("name_contains", "")
                rows = [r for r in rows if pattern.strip("%").lower() in r.get("name", "").lower()]

            # Sort
            if "ORDER BY" in sql_upper:
                desc = "DESC" in sql_upper
                rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=desc)

            # Pagination
            limit = params.get("limit")
            offset = params.get("offset", 0)
            if limit is not None:
                rows = rows[offset : offset + limit]

            return [dict(r) for r in rows]

        return []


@pytest.fixture
def mock_frame():
    """Create a mock ArkhamFrame."""
    mock_db = MockDatabase()

    frame = MagicMock()
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "database": mock_db,
            "events": AsyncMock(),
            "storage": None,
        }.get(name)
    )
    return frame


@pytest.fixture
async def shard(mock_frame):
    """Create and initialize a Templates shard."""
    shard = TemplatesShard()
    await shard.initialize(mock_frame)
    set_shard(shard)
    return shard


@pytest.fixture
def client(shard):
    """Create a test client."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestHealthEndpoints:
    """Test health and status endpoints."""

    def test_health(self, client):
        """Test health check endpoint."""
        response = client.get("/api/templates/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["shard"] == "templates"

    def test_count(self, client, shard):
        """Test count endpoint."""
        response = client.get("/api/templates/count")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] == 0

    def test_stats(self, client):
        """Test statistics endpoint."""
        response = client.get("/api/templates/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_templates" in data
        assert "active_templates" in data
        assert "by_type" in data


class TestTemplateCRUDEndpoints:
    """Test template CRUD endpoints."""

    def test_list_templates_empty(self, client):
        """Test listing templates when none exist."""
        response = client.get("/api/templates/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    def test_create_template(self, client):
        """Test creating a template."""
        template_data = {
            "name": "Test Template",
            "template_type": "LETTER",
            "description": "A test template",
            "content": "Dear {{ name }},\n\nHello!",
            "placeholders": [
                {"name": "name", "description": "Recipient name", "data_type": "string", "required": True}
            ],
            "is_active": True,
        }
        response = client.post("/api/templates/", json=template_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Template"
        assert data["template_type"] == "LETTER"
        assert "id" in data

    def test_create_template_invalid_syntax(self, client):
        """Test creating template with invalid syntax."""
        template_data = {
            "name": "Invalid Template",
            "template_type": "REPORT",
            "content": "Dear {{ name },\n\nMissing closing brace!",
        }
        response = client.post("/api/templates/", json=template_data)
        assert response.status_code == 400

    def test_get_template(self, client):
        """Test getting a template by ID."""
        # Create template
        template_data = {
            "name": "Get Test",
            "template_type": "REPORT",
            "content": "Test content",
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Get template
        response = client.get(f"/api/templates/{template_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == template_id
        assert data["name"] == "Get Test"

    def test_get_template_not_found(self, client):
        """Test getting non-existent template."""
        response = client.get("/api/templates/nonexistent_id")
        assert response.status_code == 404

    def test_update_template(self, client):
        """Test updating a template."""
        # Create template
        template_data = {
            "name": "Original Name",
            "template_type": "LETTER",
            "content": "Original content",
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Update template
        update_data = {
            "name": "Updated Name",
            "description": "Updated description",
        }
        response = client.put(f"/api/templates/{template_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"

    def test_update_template_not_found(self, client):
        """Test updating non-existent template."""
        update_data = {"name": "New Name"}
        response = client.put("/api/templates/nonexistent_id", json=update_data)
        assert response.status_code == 404

    def test_delete_template(self, client):
        """Test deleting a template."""
        # Create template
        template_data = {
            "name": "To Delete",
            "template_type": "REPORT",
            "content": "Content",
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Delete template
        response = client.delete(f"/api/templates/{template_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

        # Verify deleted
        get_response = client.get(f"/api/templates/{template_id}")
        assert get_response.status_code == 404

    def test_activate_template(self, client):
        """Test activating a template."""
        # Create inactive template
        template_data = {
            "name": "Inactive",
            "template_type": "LETTER",
            "content": "Content",
            "is_active": False,
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Activate
        response = client.post(f"/api/templates/{template_id}/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    def test_deactivate_template(self, client):
        """Test deactivating a template."""
        # Create active template
        template_data = {
            "name": "Active",
            "template_type": "LETTER",
            "content": "Content",
            "is_active": True,
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Deactivate
        response = client.post(f"/api/templates/{template_id}/deactivate")
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False


class TestVersioningEndpoints:
    """Test versioning endpoints."""

    def test_get_versions(self, client):
        """Test getting template versions."""
        # Create template
        template_data = {
            "name": "Version Test",
            "template_type": "REPORT",
            "content": "Initial content",
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Get versions
        response = client.get(f"/api/templates/{template_id}/versions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["version_number"] == 1

    def test_create_version(self, client):
        """Test creating a new version."""
        # Create template
        template_data = {
            "name": "Version Test",
            "template_type": "REPORT",
            "content": "Initial content",
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Create version
        version_data = {"changes": "Updated for testing"}
        response = client.post(f"/api/templates/{template_id}/versions", json=version_data)
        assert response.status_code == 201
        data = response.json()
        assert data["version_number"] == 2
        assert data["changes"] == "Updated for testing"

    def test_restore_version(self, client):
        """Test restoring a previous version."""
        # Create template
        template_data = {
            "name": "Restore Test",
            "template_type": "LETTER",
            "content": "Version 1 content",
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Get version 1 ID
        versions_response = client.get(f"/api/templates/{template_id}/versions")
        version1_id = versions_response.json()[0]["id"]

        # Update to version 2
        update_data = {"content": "Version 2 content"}
        client.put(f"/api/templates/{template_id}", json=update_data)

        # Restore version 1
        response = client.post(f"/api/templates/{template_id}/restore/{version1_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Version 1 content"


class TestRenderingEndpoints:
    """Test rendering endpoints."""

    def test_render_template(self, client):
        """Test rendering a template."""
        # Create template
        template_data = {
            "name": "Render Test",
            "template_type": "LETTER",
            "content": "Hello {{ name }}!",
            "placeholders": [{"name": "name", "required": True}],
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Render template
        render_data = {
            "data": {"name": "World"},
            "output_format": "text",
        }
        response = client.post(f"/api/templates/{template_id}/render", json=render_data)
        assert response.status_code == 200
        data = response.json()
        assert "Hello World!" in data["rendered_content"]
        assert "name" in data["placeholders_used"]

    def test_render_template_not_found(self, client):
        """Test rendering non-existent template."""
        render_data = {
            "data": {"name": "Test"},
            "output_format": "text",
        }
        response = client.post("/api/templates/nonexistent_id/render", json=render_data)
        assert response.status_code == 404

    def test_preview_template(self, client):
        """Test previewing a template."""
        # Create template
        template_data = {
            "name": "Preview Test",
            "template_type": "LETTER",
            "content": "Hello {{ name }}!",
            "placeholders": [{"name": "name", "example": "Example User"}],
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Preview template
        response = client.post(f"/api/templates/{template_id}/preview")
        assert response.status_code == 200
        data = response.json()
        assert "Example User" in data["rendered_content"]

    def test_validate_template_data(self, client):
        """Test validating placeholder data."""
        # Create template
        template_data = {
            "name": "Validate Test",
            "template_type": "LETTER",
            "content": "Hello {{ name }}!",
            "placeholders": [{"name": "name", "required": True}],
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Validate with missing required field
        validation_data = {}
        response = client.post(f"/api/templates/{template_id}/validate", json=validation_data)
        assert response.status_code == 200
        warnings = response.json()
        assert len(warnings) > 0
        assert any("required" in w["message"].lower() for w in warnings)


class TestMetadataEndpoints:
    """Test metadata endpoints."""

    def test_get_template_types(self, client):
        """Test getting template types."""
        response = client.get("/api/templates/types")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert any(t["type"] == "REPORT" for t in data)
        assert any(t["type"] == "LETTER" for t in data)

    def test_get_template_placeholders(self, client):
        """Test getting template placeholders."""
        # Create template
        template_data = {
            "name": "Placeholder Test",
            "template_type": "LETTER",
            "content": "Hello {{ name }}!",
            "placeholders": [
                {"name": "name", "description": "Recipient name", "data_type": "string", "required": True}
            ],
        }
        create_response = client.post("/api/templates/", json=template_data)
        template_id = create_response.json()["id"]

        # Get placeholders
        response = client.get(f"/api/templates/{template_id}/placeholders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "name"
        assert data[0]["required"] is True


class TestBulkActions:
    """Test bulk action endpoints."""

    def test_bulk_activate(self, client):
        """Test bulk activating templates."""
        # Create inactive templates
        template_ids = []
        for i in range(3):
            template_data = {
                "name": f"Template {i}",
                "template_type": "REPORT",
                "content": "Content",
                "is_active": False,
            }
            response = client.post("/api/templates/", json=template_data)
            template_ids.append(response.json()["id"])

        # Bulk activate
        bulk_data = {"template_ids": template_ids}
        response = client.post("/api/templates/batch/activate", json=bulk_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["processed"] == 3
        assert data["failed"] == 0

    def test_bulk_deactivate(self, client):
        """Test bulk deactivating templates."""
        # Create active templates
        template_ids = []
        for i in range(3):
            template_data = {
                "name": f"Template {i}",
                "template_type": "REPORT",
                "content": "Content",
                "is_active": True,
            }
            response = client.post("/api/templates/", json=template_data)
            template_ids.append(response.json()["id"])

        # Bulk deactivate
        bulk_data = {"template_ids": template_ids}
        response = client.post("/api/templates/batch/deactivate", json=bulk_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["processed"] == 3

    def test_bulk_delete(self, client):
        """Test bulk deleting templates."""
        # Create templates
        template_ids = []
        for i in range(3):
            template_data = {
                "name": f"Template {i}",
                "template_type": "REPORT",
                "content": "Content",
            }
            response = client.post("/api/templates/", json=template_data)
            template_ids.append(response.json()["id"])

        # Bulk delete
        bulk_data = {"template_ids": template_ids}
        response = client.post("/api/templates/batch/delete", json=bulk_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["processed"] == 3

        # Verify deleted
        for template_id in template_ids:
            get_response = client.get(f"/api/templates/{template_id}")
            assert get_response.status_code == 404


class TestPaginationAndFiltering:
    """Test pagination and filtering."""

    def test_pagination(self, client):
        """Test template pagination."""
        # Create 10 templates
        for i in range(10):
            template_data = {
                "name": f"Template {i}",
                "template_type": "REPORT",
                "content": f"Content {i}",
            }
            client.post("/api/templates/", json=template_data)

        # Get page 1
        response = client.get("/api/templates/?page=1&page_size=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 10
        assert data["page"] == 1

        # Get page 2
        response = client.get("/api/templates/?page=2&page_size=3")
        data = response.json()
        assert len(data["items"]) == 3
        assert data["page"] == 2

    def test_filter_by_type(self, client):
        """Test filtering by template type."""
        # Create templates of different types
        client.post(
            "/api/templates/",
            json={
                "name": "Report 1",
                "template_type": "REPORT",
                "content": "Content",
            },
        )
        client.post(
            "/api/templates/",
            json={
                "name": "Letter 1",
                "template_type": "LETTER",
                "content": "Content",
            },
        )

        # Filter by REPORT
        response = client.get("/api/templates/?template_type=REPORT")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["template_type"] == "REPORT"

    def test_filter_by_active_status(self, client):
        """Test filtering by active status."""
        # Create active and inactive templates
        client.post(
            "/api/templates/",
            json={
                "name": "Active",
                "template_type": "REPORT",
                "content": "Content",
                "is_active": True,
            },
        )
        client.post(
            "/api/templates/",
            json={
                "name": "Inactive",
                "template_type": "REPORT",
                "content": "Content",
                "is_active": False,
            },
        )

        # Filter by active
        response = client.get("/api/templates/?is_active=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["is_active"] is True

    def test_search_by_name(self, client):
        """Test searching by name."""
        # Create templates
        client.post(
            "/api/templates/",
            json={
                "name": "FOIA Request Letter",
                "template_type": "LETTER",
                "content": "Content",
            },
        )
        client.post(
            "/api/templates/",
            json={
                "name": "Report Template",
                "template_type": "REPORT",
                "content": "Content",
            },
        )

        # Search for "FOIA"
        response = client.get("/api/templates/?name_contains=FOIA")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert "FOIA" in data["items"][0]["name"]
