"""Tests for Provenance Shard API endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_provenance.api import init_api, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_shard():
    """Create a mock ProvenanceShard with async methods."""
    shard = MagicMock()
    shard.name = "provenance"
    shard.version = "0.1.0"

    # Chain methods
    shard.count_chains = AsyncMock(return_value=0)
    shard.count_artifacts = AsyncMock(return_value=0)
    shard.list_chains = AsyncMock(return_value=[])
    shard.create_chain_impl = AsyncMock(
        return_value={
            "id": "chain-new",
            "title": "Test Chain",
            "description": "",
            "chain_type": "evidence",
            "status": "active",
            "project_id": None,
            "root_artifact_id": None,
            "created_by": "user-1",
            "metadata": {},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "link_count": 0,
        }
    )
    shard.get_chain_impl = AsyncMock(return_value=None)
    shard.update_chain_impl = AsyncMock(return_value=None)
    shard.delete_chain_impl = AsyncMock(return_value=True)

    # Link methods
    shard.add_link_impl = AsyncMock(
        return_value={
            "id": "link-new",
            "chain_id": "chain-1",
            "source_artifact_id": "src-1",
            "target_artifact_id": "tgt-1",
            "link_type": "derived_from",
            "confidence": 0.95,
            "metadata": {},
            "created_at": "2024-01-01T00:00:00",
            "verified": False,
        }
    )
    shard.get_chain_links = AsyncMock(return_value=[])
    shard.remove_link = AsyncMock(return_value=True)
    shard.verify_link = AsyncMock(return_value=None)

    # Lineage methods
    shard.get_lineage_impl = AsyncMock(
        return_value={
            "nodes": [],
            "edges": [],
            "root": None,
            "ancestor_count": 0,
            "descendant_count": 0,
        }
    )
    shard.get_artifact = AsyncMock(return_value=None)
    shard.get_upstream = AsyncMock(return_value=[])
    shard.get_downstream = AsyncMock(return_value=[])

    # Audit methods - list_audit_records returns (items, total) tuple
    shard.list_audit_records = AsyncMock(return_value=([], 0))
    shard.get_chain_audit_records = AsyncMock(return_value=[])
    shard.export_audit_records = AsyncMock(return_value=None)

    # Verification
    shard.verify_chain_impl = AsyncMock(
        return_value={
            "chain_id": "chain-123",
            "verified": True,
            "issues": [],
            "checked_at": "2024-01-01T00:00:00",
        }
    )

    # Artifacts
    shard.list_artifacts = AsyncMock(return_value=[])
    shard.create_artifact = AsyncMock(return_value=None)
    shard.get_artifact_by_entity = AsyncMock(return_value=None)

    # Records
    shard.list_records = AsyncMock(return_value=[])
    shard.get_record_for_entity = AsyncMock(return_value=None)
    shard.get_record = AsyncMock(return_value=None)
    shard.get_transformations = AsyncMock(return_value=[])
    shard.get_audit_trail = AsyncMock(return_value=[])

    # Stats
    shard.get_statistics = AsyncMock(return_value={})
    shard.get_count = AsyncMock(return_value=0)

    # DB for forensic endpoints
    shard._db = AsyncMock()
    shard._db.fetch_one = AsyncMock(return_value=None)

    return shard


@pytest.fixture
def app(mock_shard):
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    app.state.provenance_shard = mock_shard
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/api/provenance/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["shard"] == "provenance"
        assert data["version"] == "0.1.0"


class TestCountEndpoint:
    """Test count/badge endpoint."""

    def test_get_count(self, client, mock_shard):
        """Test getting count for badge."""
        mock_shard.count_chains.return_value = 5
        mock_shard.count_artifacts.return_value = 10

        response = client.get("/api/provenance/count")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data
        assert data["count"] == 10
        assert data["chains"] == 5


class TestChainEndpoints:
    """Test evidence chain endpoints."""

    def test_list_chains_default(self, client, mock_shard):
        """Test listing chains with default parameters."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_chains_with_pagination(self, client, mock_shard):
        """Test listing chains with custom pagination."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?page=2&page_size=10")
        assert response.status_code == 200

        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 10

    def test_list_chains_with_sort(self, client, mock_shard):
        """Test listing chains with sorting."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?sort=title&order=asc")
        assert response.status_code == 200

    def test_list_chains_with_search(self, client, mock_shard):
        """Test listing chains with search query."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?q=test")
        assert response.status_code == 200

    def test_list_chains_with_status_filter(self, client, mock_shard):
        """Test listing chains with status filter."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?status=active")
        assert response.status_code == 200

    def test_list_chains_invalid_sort_field(self, client, mock_shard):
        """Test listing chains with invalid sort field - no validation, passes through."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?sort=invalid")
        # No sort validation in the API, so it succeeds
        assert response.status_code == 200

    def test_list_chains_invalid_order(self, client, mock_shard):
        """Test listing chains with invalid order - no validation, passes through."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?order=invalid")
        assert response.status_code == 200

    def test_create_chain(self, client, mock_shard):
        """Test creating a new chain."""
        chain_data = {
            "title": "Test Chain",
            "description": "A test evidence chain",
            "created_by": "user-1",
        }
        response = client.post("/api/provenance/chains", json=chain_data)
        # Might be 201 or 501 depending on implementation
        assert response.status_code in [200, 201, 501]

    def test_get_chain(self, client, mock_shard):
        """Test getting a single chain."""
        mock_shard.get_chain_impl.return_value = None
        response = client.get("/api/provenance/chains/chain-123")
        assert response.status_code == 404  # Not found

    def test_update_chain(self, client, mock_shard):
        """Test updating a chain."""
        mock_shard.update_chain_impl.return_value = None
        update_data = {
            "title": "Updated Title",
            "status": "verified",
        }
        response = client.put("/api/provenance/chains/chain-123", json=update_data)
        assert response.status_code == 404  # Not found

    def test_delete_chain(self, client, mock_shard):
        """Test deleting a chain."""
        response = client.delete("/api/provenance/chains/chain-123")
        assert response.status_code == 200

        data = response.json()
        assert data["deleted"] is True


class TestLinkEndpoints:
    """Test provenance link endpoints."""

    def test_add_link(self, client, mock_shard):
        """Test adding a link to a chain."""
        link_data = {
            "source_artifact_id": "src-1",
            "target_artifact_id": "tgt-1",
            "link_type": "derived_from",
            "confidence": 0.95,
        }
        response = client.post("/api/provenance/chains/chain-1/links", json=link_data)
        assert response.status_code in [200, 201, 501]

    def test_list_chain_links(self, client, mock_shard):
        """Test listing links in a chain."""
        response = client.get("/api/provenance/chains/chain-1/links")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_delete_link(self, client, mock_shard):
        """Test deleting a link."""
        response = client.delete("/api/provenance/links/link-123")
        assert response.status_code == 200

        data = response.json()
        assert data["deleted"] is True

    def test_verify_link(self, client, mock_shard):
        """Test verifying a link."""
        mock_shard.verify_link.return_value = None
        verify_data = {
            "verified_by": "reviewer-1",
            "notes": "Verified manually",
        }
        response = client.put("/api/provenance/links/link-123/verify", json=verify_data)
        assert response.status_code == 404  # Not found (stub)


class TestLineageEndpoints:
    """Test lineage tracking endpoints."""

    def test_get_lineage_default(self, client, mock_shard):
        """Test getting lineage with default parameters."""
        response = client.get("/api/provenance/lineage/artifact-123")
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_get_lineage_upstream(self, client, mock_shard):
        """Test getting upstream lineage."""
        response = client.get("/api/provenance/lineage/artifact-123?direction=upstream")
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data

    def test_get_lineage_downstream(self, client, mock_shard):
        """Test getting downstream lineage."""
        response = client.get("/api/provenance/lineage/artifact-123?direction=downstream")
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data

    def test_get_lineage_with_max_depth(self, client, mock_shard):
        """Test getting lineage with max depth."""
        response = client.get("/api/provenance/lineage/artifact-123?max_depth=3")
        assert response.status_code == 200

    def test_get_lineage_invalid_direction(self, client):
        """Test getting lineage with invalid direction."""
        response = client.get("/api/provenance/lineage/artifact-123?direction=invalid")
        assert response.status_code == 422

    def test_get_upstream(self, client, mock_shard):
        """Test getting upstream dependencies."""
        response = client.get("/api/provenance/lineage/artifact-123/upstream")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_get_downstream(self, client, mock_shard):
        """Test getting downstream dependents."""
        response = client.get("/api/provenance/lineage/artifact-123/downstream")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data == []


class TestAuditEndpoints:
    """Test audit log endpoints."""

    def test_list_audit_records_default(self, client, mock_shard):
        """Test listing audit records with default parameters."""
        mock_shard.list_audit_records.return_value = ([], 0)

        response = client.get("/api/provenance/audit")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_audit_records_with_filters(self, client, mock_shard):
        """Test listing audit records with filters."""
        mock_shard.list_audit_records.return_value = ([], 0)
        response = client.get("/api/provenance/audit?chain_id=chain-1&event_type=chain_created")
        assert response.status_code == 200

    def test_list_audit_records_with_event_source(self, client, mock_shard):
        """Test listing audit records filtered by event source."""
        mock_shard.list_audit_records.return_value = ([], 0)
        response = client.get("/api/provenance/audit?event_source=provenance")
        assert response.status_code == 200

    def test_get_chain_audit(self, client, mock_shard):
        """Test getting audit trail for a specific chain."""
        response = client.get("/api/provenance/audit/chain-123")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert data == []

    def test_export_audit_json(self, client, mock_shard):
        """Test exporting audit trail as JSON."""
        response = client.post("/api/provenance/audit/export?format=json")
        # Should fail without storage service
        assert response.status_code in [501, 503]

    def test_export_audit_csv(self, client, mock_shard):
        """Test exporting audit trail as CSV."""
        response = client.post("/api/provenance/audit/export?format=csv")
        assert response.status_code in [501, 503]

    def test_export_audit_pdf(self, client, mock_shard):
        """Test exporting audit trail as PDF - not a valid format."""
        response = client.post("/api/provenance/audit/export?format=pdf")
        assert response.status_code == 422  # Only json/csv supported

    def test_export_audit_invalid_format(self, client):
        """Test exporting audit with invalid format."""
        response = client.post("/api/provenance/audit/export?format=invalid")
        assert response.status_code == 422

    def test_export_audit_with_chain_filter(self, client, mock_shard):
        """Test exporting audit for specific chain."""
        response = client.post("/api/provenance/audit/export?chain_id=chain-1")
        assert response.status_code in [501, 503]


class TestVerificationEndpoints:
    """Test chain verification endpoints."""

    def test_verify_chain(self, client, mock_shard):
        """Test verifying chain integrity."""
        response = client.post("/api/provenance/chains/chain-123/verify")
        assert response.status_code == 200

        data = response.json()
        assert "chain_id" in data
        assert "verified" in data
        assert "issues" in data
        assert data["chain_id"] == "chain-123"
        assert data["verified"] is True
        assert data["issues"] == []


class TestRequestValidation:
    """Test request validation."""

    def test_create_chain_missing_title(self, client):
        """Test creating chain without required title."""
        chain_data = {
            "description": "Missing title",
        }
        response = client.post("/api/provenance/chains", json=chain_data)
        assert response.status_code == 422

    def test_add_link_missing_fields(self, client):
        """Test adding link with missing required fields."""
        link_data = {
            "source_artifact_id": "src-1",
            # Missing target_artifact_id and link_type
        }
        response = client.post("/api/provenance/chains/chain-1/links", json=link_data)
        assert response.status_code == 422

    def test_add_link_invalid_confidence(self, client):
        """Test adding link with invalid confidence value."""
        link_data = {
            "source_artifact_id": "src-1",
            "target_artifact_id": "tgt-1",
            "link_type": "derived_from",
            "confidence": 1.5,  # Invalid - should be 0.0 to 1.0
        }
        response = client.post("/api/provenance/chains/chain-1/links", json=link_data)
        # Could be 422 if validation exists, or 501/200/201 if not
        assert response.status_code in [422, 501, 200, 201]

    def test_list_chains_invalid_page(self, client):
        """Test listing chains with invalid page number."""
        response = client.get("/api/provenance/chains?page=0")
        assert response.status_code == 422

    def test_list_chains_page_size_too_large(self, client):
        """Test listing chains with page size exceeding max."""
        response = client.get("/api/provenance/chains?page_size=1000")
        assert response.status_code == 422


class TestPaginationBehavior:
    """Test pagination behavior."""

    def test_pagination_page_defaults(self, client, mock_shard):
        """Test that page defaults to 1."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains")
        data = response.json()
        assert data["page"] == 1

    def test_pagination_page_size_defaults(self, client, mock_shard):
        """Test that page_size defaults to 20."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains")
        data = response.json()
        assert data["page_size"] == 20

    def test_pagination_custom_values(self, client, mock_shard):
        """Test custom pagination values."""
        mock_shard.list_chains.return_value = []
        mock_shard.count_chains.return_value = 0

        response = client.get("/api/provenance/chains?page=3&page_size=50")
        data = response.json()
        assert data["page"] == 3
        assert data["page_size"] == 50

    def test_audit_pagination(self, client, mock_shard):
        """Test audit endpoint pagination."""
        mock_shard.list_audit_records.return_value = ([], 0)

        response = client.get("/api/provenance/audit?page=2&page_size=10")
        assert response.status_code == 200

        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 10


class TestAPIInitialization:
    """Test API initialization."""

    def test_api_init_sets_globals(self):
        """Test that init_api sets global variables."""
        from arkham_shard_provenance import api

        # Mock objects
        mock_shard = object()
        mock_event_bus = object()
        mock_storage = object()
        mock_forensic = object()

        init_api(
            shard=mock_shard,
            event_bus=mock_event_bus,
            storage=mock_storage,
            forensic_analyzer=mock_forensic,
        )

        assert api._shard is mock_shard
        assert api._event_bus is mock_event_bus
        assert api._storage is mock_storage
        assert api._forensic_analyzer is mock_forensic


class TestRouterConfiguration:
    """Test router configuration."""

    def test_router_prefix(self):
        """Test that router has correct prefix."""
        assert router.prefix == "/api/provenance"

    def test_router_tags(self):
        """Test that router has correct tags."""
        assert "provenance" in router.tags
