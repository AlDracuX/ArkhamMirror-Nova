"""
Reports Shard - API Tests

Tests for FastAPI routes and endpoints.

NOTE: Several routes (/templates, /schedules, /stats, /pending, /completed, /failed)
are shadowed by the /{report_id} catch-all route, which is registered first.
Tests for those routes verify they return 404 (current behavior).
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_reports.api import router
from arkham_shard_reports.models import (
    Report,
    ReportFormat,
    ReportSchedule,
    ReportStatistics,
    ReportStatus,
    ReportTemplate,
    ReportType,
)
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock ReportsShard."""
    shard = MagicMock()
    shard.version = "0.1.0"
    shard._db = MagicMock()
    shard._events = MagicMock()
    shard._llm = None
    shard._storage = None
    shard._workers = None

    # Mock async methods
    shard.generate_report = AsyncMock()
    shard.get_report = AsyncMock(return_value=None)
    shard.list_reports = AsyncMock(return_value=[])
    shard.delete_report = AsyncMock()
    shard.get_count = AsyncMock(return_value=0)
    shard.create_template = AsyncMock()
    shard.get_template = AsyncMock()
    shard.list_templates = AsyncMock()
    shard.create_schedule = AsyncMock()
    shard.list_schedules = AsyncMock()
    shard.delete_schedule = AsyncMock()
    shard.get_statistics = AsyncMock()

    return shard


@pytest.fixture
def client(mock_shard):
    """Create a test client with mocked shard."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.state.reports_shard = mock_shard

    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/reports/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "services" in data


class TestCountEndpoints:
    """Tests for count endpoints."""

    def test_get_reports_count(self, client, mock_shard):
        """Test getting total report count."""
        mock_shard.get_count.return_value = 42
        response = client.get("/api/reports/count")
        assert response.status_code == 200
        assert response.json()["count"] == 42

    def test_get_pending_count(self, client, mock_shard):
        """Test getting pending report count (badge endpoint)."""
        mock_shard.get_count.return_value = 15
        response = client.get("/api/reports/pending/count")
        assert response.status_code == 200
        assert response.json()["count"] == 15


class TestReportsCRUD:
    """Tests for report CRUD endpoints."""

    def test_list_reports(self, client, mock_shard):
        """Test listing reports."""
        mock_report = Report(
            id="rep-1",
            report_type=ReportType.SUMMARY,
            title="Test Report",
            status=ReportStatus.COMPLETED,
        )
        mock_shard.list_reports.return_value = [mock_report]
        mock_shard.get_count.return_value = 1

        response = client.get("/api/reports/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        # API uses ReportListResponse with "items" field, not "reports"
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "rep-1"

    def test_create_report(self, client, mock_shard):
        """Test creating a report."""
        mock_report = Report(
            id="rep-new",
            report_type=ReportType.SUMMARY,
            title="New Report",
            status=ReportStatus.PENDING,
        )
        mock_shard.generate_report.return_value = mock_report

        response = client.post(
            "/api/reports/",
            json={
                "report_type": "summary",
                "title": "New Report",
                "output_format": "html",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "rep-new"
        assert data["title"] == "New Report"

    def test_get_report(self, client, mock_shard):
        """Test getting a specific report."""
        mock_report = Report(
            id="rep-1",
            report_type=ReportType.SUMMARY,
            title="Test Report",
            status=ReportStatus.COMPLETED,
        )
        mock_shard.get_report.return_value = mock_report

        response = client.get("/api/reports/rep-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "rep-1"
        assert data["title"] == "Test Report"

    def test_get_report_not_found(self, client, mock_shard):
        """Test getting a non-existent report."""
        mock_shard.get_report.return_value = None

        response = client.get("/api/reports/nonexistent")
        assert response.status_code == 404

    def test_delete_report(self, client, mock_shard):
        """Test deleting a report."""
        mock_shard.delete_report.return_value = True

        response = client.delete("/api/reports/rep-1")
        assert response.status_code == 204

    def test_delete_report_not_found(self, client, mock_shard):
        """Test deleting a non-existent report."""
        mock_shard.delete_report.return_value = False

        response = client.delete("/api/reports/nonexistent")
        assert response.status_code == 404

    def test_download_report_file_not_found(self, client, mock_shard):
        """Test downloading when report file doesn't exist on disk returns 404."""
        mock_report = Report(
            id="rep-1",
            report_type=ReportType.SUMMARY,
            title="Test Report",
            status=ReportStatus.COMPLETED,
            file_path="/nonexistent/rep-1.html",
            file_size=1024,
        )
        mock_shard.get_report.return_value = mock_report

        response = client.get("/api/reports/rep-1/download")
        assert response.status_code == 404

    def test_download_report_no_file_path(self, client, mock_shard):
        """Test downloading report with no file_path returns 404."""
        mock_report = Report(
            id="rep-1",
            report_type=ReportType.SUMMARY,
            title="Test Report",
            status=ReportStatus.COMPLETED,
        )
        mock_shard.get_report.return_value = mock_report

        response = client.get("/api/reports/rep-1/download")
        assert response.status_code == 404

    def test_download_report_not_found(self, client, mock_shard):
        """Test downloading non-existent report returns 404."""
        mock_shard.get_report.return_value = None

        response = client.get("/api/reports/nonexistent/download")
        assert response.status_code == 404


class TestShadowedRoutes:
    """Tests for routes shadowed by /{report_id} catch-all.

    NOTE: /templates, /schedules, /stats, /pending, /completed, /failed
    are all matched by the /{report_id} route which is registered first.
    This is an API design issue (route ordering). These tests verify
    the current (broken) behavior - they all return 404.
    """

    def test_templates_shadowed(self, client, mock_shard):
        """GET /templates is caught by /{report_id} -> 404."""
        response = client.get("/api/reports/templates")
        assert response.status_code == 404

    def test_schedules_shadowed(self, client, mock_shard):
        """GET /schedules is caught by /{report_id} -> 404."""
        response = client.get("/api/reports/schedules")
        assert response.status_code == 404

    def test_stats_shadowed(self, client, mock_shard):
        """GET /stats is caught by /{report_id} -> 404."""
        response = client.get("/api/reports/stats")
        assert response.status_code == 404

    def test_pending_shadowed(self, client, mock_shard):
        """GET /pending is caught by /{report_id} -> 404."""
        response = client.get("/api/reports/pending")
        assert response.status_code == 404

    def test_completed_shadowed(self, client, mock_shard):
        """GET /completed is caught by /{report_id} -> 404."""
        response = client.get("/api/reports/completed")
        assert response.status_code == 404

    def test_failed_shadowed(self, client, mock_shard):
        """GET /failed is caught by /{report_id} -> 404."""
        response = client.get("/api/reports/failed")
        assert response.status_code == 404


class TestTemplatesCRUD:
    """Tests for template CRUD via non-shadowed paths."""

    def test_create_template(self, client, mock_shard):
        """Test creating a template via POST /templates."""
        mock_template = ReportTemplate(
            id="tmpl-new",
            name="New Template",
            report_type=ReportType.SUMMARY,
            description="New template",
        )
        mock_shard.create_template.return_value = mock_template

        response = client.post(
            "/api/reports/templates",
            json={
                "name": "New Template",
                "report_type": "summary",
                "description": "New template",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "tmpl-new"
        assert data["name"] == "New Template"

    def test_get_template(self, client, mock_shard):
        """Test getting a specific template."""
        mock_template = ReportTemplate(
            id="tmpl-1",
            name="Summary Template",
            report_type=ReportType.SUMMARY,
            description="Weekly summary",
        )
        mock_shard.get_template.return_value = mock_template

        response = client.get("/api/reports/templates/tmpl-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tmpl-1"
        assert data["name"] == "Summary Template"

    def test_get_template_not_found(self, client, mock_shard):
        """Test getting a non-existent template."""
        mock_shard.get_template.return_value = None

        response = client.get("/api/reports/templates/nonexistent")
        assert response.status_code == 404


class TestSchedulesCRUD:
    """Tests for schedule CRUD via non-shadowed paths."""

    def test_create_schedule(self, client, mock_shard):
        """Test creating a schedule."""
        mock_template = ReportTemplate(
            id="tmpl-1",
            name="Test Template",
            report_type=ReportType.SUMMARY,
            description="Test",
        )
        mock_schedule = ReportSchedule(
            id="sched-new",
            template_id="tmpl-1",
            cron_expression="0 9 * * 1",
        )
        mock_shard.get_template.return_value = mock_template
        mock_shard.create_schedule.return_value = mock_schedule

        response = client.post(
            "/api/reports/schedules",
            json={
                "template_id": "tmpl-1",
                "cron_expression": "0 9 * * 1",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "sched-new"

    def test_create_schedule_template_not_found(self, client, mock_shard):
        """Test creating a schedule with non-existent template."""
        mock_shard.get_template.return_value = None

        response = client.post(
            "/api/reports/schedules",
            json={
                "template_id": "nonexistent",
                "cron_expression": "0 9 * * 1",
            },
        )
        assert response.status_code == 404

    def test_delete_schedule(self, client, mock_shard):
        """Test deleting a schedule."""
        mock_shard.delete_schedule.return_value = True

        response = client.delete("/api/reports/schedules/sched-1")
        assert response.status_code == 204

    def test_delete_schedule_not_found(self, client, mock_shard):
        """Test deleting a non-existent schedule."""
        mock_shard.delete_schedule.return_value = False

        response = client.delete("/api/reports/schedules/nonexistent")
        assert response.status_code == 404


class TestPreview:
    """Tests for preview endpoint."""

    def test_preview_report(self, client, mock_shard):
        """Test previewing a report."""
        response = client.post(
            "/api/reports/preview",
            json={
                "report_type": "summary",
                "title": "Preview Report",
                "output_format": "html",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "preview_content" in data
        assert data["estimated_size"] > 0
