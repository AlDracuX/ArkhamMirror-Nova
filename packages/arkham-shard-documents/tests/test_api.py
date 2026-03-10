"""
Tests for Documents Shard API endpoints.

Tests all API routes using FastAPI TestClient.

Run with:
    cd packages/arkham-shard-documents
    pytest tests/test_api.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_documents.api import router
from arkham_shard_documents.models import DocumentRecord, DocumentStatus
from fastapi import FastAPI
from fastapi.testclient import TestClient

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_shard():
    """Create a mock documents shard with all async methods."""
    shard = AsyncMock()

    # Configure return values for common methods
    shard.get_document_count = AsyncMock(return_value=0)
    shard.get_document_stats = AsyncMock(
        return_value={
            "total_documents": 0,
            "processed_documents": 0,
            "processing_documents": 0,
            "failed_documents": 0,
            "total_size_bytes": 0,
            "total_pages": 0,
            "total_chunks": 0,
        }
    )
    shard.list_documents = AsyncMock(return_value=[])
    shard.get_document = AsyncMock(return_value=None)
    shard.update_document = AsyncMock(return_value=None)
    shard.delete_document = AsyncMock(return_value=False)
    shard.get_document_content = AsyncMock(return_value=None)
    shard.get_document_chunks = AsyncMock(
        return_value={
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 50,
        }
    )
    shard.get_document_entities = AsyncMock(
        return_value={
            "items": [],
            "total": 0,
        }
    )
    shard.get_recently_viewed = AsyncMock(return_value=[])
    shard.mark_document_viewed = AsyncMock()
    shard.batch_update_tags = AsyncMock(
        return_value={
            "processed": 0,
            "failed": 0,
            "details": [],
        }
    )
    shard.batch_delete_documents = AsyncMock(
        return_value={
            "processed": 0,
            "failed": 0,
            "details": [],
        }
    )
    shard.deduplication = None

    return shard


@pytest.fixture
def app(mock_shard):
    """Create a FastAPI app with the documents router and mock shard."""
    app = FastAPI()
    app.include_router(router)
    # Set up app state so get_shard(request) works
    app.state.documents_shard = mock_shard
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# =============================================================================
# Health Check Tests
# =============================================================================


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_endpoint_exists(self, client):
        """Test health endpoint is accessible."""
        response = client.get("/api/documents/health")
        assert response.status_code == 200

    def test_health_returns_correct_data(self, client):
        """Test health endpoint returns correct structure."""
        response = client.get("/api/documents/health")
        data = response.json()

        assert "status" in data
        assert "shard" in data
        assert data["status"] == "healthy"
        assert data["shard"] == "documents"


# =============================================================================
# Document List Tests
# =============================================================================


class TestListDocuments:
    """Test document listing endpoint."""

    def test_list_documents_default_params(self, client):
        """Test listing documents with default parameters."""
        response = client.get("/api/documents/items")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

        assert isinstance(data["items"], list)
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_documents_with_pagination(self, client):
        """Test listing documents with custom pagination."""
        response = client.get("/api/documents/items?page=2&page_size=50")
        assert response.status_code == 200

        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 50

    def test_list_documents_with_sorting(self, client):
        """Test listing documents with sorting."""
        response = client.get("/api/documents/items?sort=title&order=asc")
        assert response.status_code == 200

        response.json()
        assert response.status_code == 200

    def test_list_documents_with_status_filter(self, client):
        """Test filtering documents by status."""
        response = client.get("/api/documents/items?status=processed")
        assert response.status_code == 200

    def test_list_documents_with_file_type_filter(self, client):
        """Test filtering documents by file type."""
        response = client.get("/api/documents/items?file_type=pdf")
        assert response.status_code == 200

    def test_list_documents_with_project_filter(self, client):
        """Test filtering documents by project."""
        response = client.get("/api/documents/items?project_id=proj-123")
        assert response.status_code == 200

    def test_list_documents_with_search_query(self, client):
        """Test searching documents."""
        response = client.get("/api/documents/items?q=contract")
        assert response.status_code == 200

    def test_list_documents_with_all_filters(self, client):
        """Test listing with multiple filters combined."""
        response = client.get(
            "/api/documents/items?"
            "page=1&page_size=10&"
            "sort=created_at&order=desc&"
            "status=processed&"
            "file_type=pdf&"
            "project_id=proj-1&"
            "q=test"
        )
        assert response.status_code == 200

    def test_list_documents_invalid_page(self, client):
        """Test listing with invalid page number."""
        response = client.get("/api/documents/items?page=0")
        # Should either return error or clamp to minimum
        assert response.status_code in [200, 422]

    def test_list_documents_page_size_limit(self, client):
        """Test page size is clamped to maximum."""
        response = client.get("/api/documents/items?page_size=1000")
        # Should either return error or clamp to 100
        assert response.status_code in [200, 422]


# =============================================================================
# Get Document Tests
# =============================================================================


class TestGetDocument:
    """Test get single document endpoint."""

    def test_get_document_by_id(self, client):
        """Test getting a single document."""
        response = client.get("/api/documents/items/doc-123")
        # Currently returns 404 (stub implementation)
        assert response.status_code == 404

    def test_get_document_not_found(self, client):
        """Test getting non-existent document."""
        response = client.get("/api/documents/items/nonexistent")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()


# =============================================================================
# Update Document Tests
# =============================================================================


class TestUpdateDocument:
    """Test update document metadata endpoint."""

    def test_update_document_title(self, client):
        """Test updating document title."""
        payload = {"title": "New Title"}
        response = client.patch("/api/documents/items/doc-123", json=payload)
        # Currently returns 404 (stub implementation)
        assert response.status_code == 404

    def test_update_document_tags(self, client):
        """Test updating document tags."""
        payload = {"tags": ["important", "legal"]}
        response = client.patch("/api/documents/items/doc-123", json=payload)
        assert response.status_code == 404

    def test_update_document_custom_metadata(self, client):
        """Test updating custom metadata."""
        payload = {"custom_metadata": {"department": "legal", "priority": "high"}}
        response = client.patch("/api/documents/items/doc-123", json=payload)
        assert response.status_code == 404

    def test_update_document_all_fields(self, client):
        """Test updating all allowed fields."""
        payload = {"title": "Updated Title", "tags": ["tag1", "tag2"], "custom_metadata": {"key": "value"}}
        response = client.patch("/api/documents/items/doc-123", json=payload)
        assert response.status_code == 404

    def test_update_document_empty_payload(self, client):
        """Test updating with empty payload."""
        payload = {}
        response = client.patch("/api/documents/items/doc-123", json=payload)
        # Should handle empty update gracefully
        assert response.status_code in [200, 404, 422]

    def test_update_document_not_found(self, client):
        """Test updating non-existent document."""
        payload = {"title": "New Title"}
        response = client.patch("/api/documents/items/nonexistent", json=payload)
        assert response.status_code == 404


# =============================================================================
# Delete Document Tests
# =============================================================================


class TestDeleteDocument:
    """Test delete document endpoint."""

    def test_delete_document(self, client):
        """Test deleting a document."""
        response = client.delete("/api/documents/items/doc-123")
        # Currently returns 404 (stub implementation)
        assert response.status_code == 404

    def test_delete_document_not_found(self, client):
        """Test deleting non-existent document."""
        response = client.delete("/api/documents/items/nonexistent")
        assert response.status_code == 404


# =============================================================================
# Document Content Tests
# =============================================================================


class TestDocumentContent:
    """Test document content retrieval endpoints."""

    def test_get_document_content(self, client):
        """Test getting document content."""
        response = client.get("/api/documents/doc-123/content")
        # Currently returns 404 (stub implementation)
        assert response.status_code == 404

    def test_get_document_content_with_page(self, client):
        """Test getting specific page content."""
        response = client.get("/api/documents/doc-123/content?page=2")
        assert response.status_code == 404

    def test_get_document_page(self, client):
        """Test getting specific page via dedicated endpoint."""
        response = client.get("/api/documents/doc-123/pages/1")
        assert response.status_code == 404

    def test_get_document_page_invalid_number(self, client):
        """Test getting page with invalid page number."""
        response = client.get("/api/documents/doc-123/pages/0")
        assert response.status_code == 404


# =============================================================================
# Document Chunks Tests
# =============================================================================


class TestDocumentChunks:
    """Test document chunks endpoint."""

    def test_get_document_chunks_default(self, client, mock_shard):
        """Test getting document chunks with defaults."""
        # Must have a document to get its chunks
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_chunks = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 50,
            }
        )

        response = client.get("/api/documents/doc-123/chunks")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_get_document_chunks_with_pagination(self, client, mock_shard):
        """Test getting chunks with custom pagination."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_chunks = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "page": 2,
                "page_size": 100,
            }
        )

        response = client.get("/api/documents/doc-123/chunks?page=2&page_size=100")
        assert response.status_code == 200

        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 100

    def test_get_document_chunks_page_size_limit(self, client, mock_shard):
        """Test chunks page size is clamped."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        response = client.get("/api/documents/doc-123/chunks?page_size=500")
        # Should either accept or clamp to 200
        assert response.status_code in [200, 422]


# =============================================================================
# Document Entities Tests
# =============================================================================


class TestDocumentEntities:
    """Test document entities endpoint."""

    def test_get_document_entities(self, client, mock_shard):
        """Test getting document entities."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_entities = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
            }
        )

        response = client.get("/api/documents/doc-123/entities")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_get_document_entities_with_type_filter(self, client, mock_shard):
        """Test filtering entities by type."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_entities = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
            }
        )

        response = client.get("/api/documents/doc-123/entities?entity_type=PERSON")
        assert response.status_code == 200

    def test_get_document_entities_various_types(self, client, mock_shard):
        """Test filtering by various entity types."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_entities = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
            }
        )

        entity_types = ["PERSON", "ORG", "GPE", "DATE", "EVENT"]

        for entity_type in entity_types:
            response = client.get(f"/api/documents/doc-123/entities?entity_type={entity_type}")
            assert response.status_code == 200


# =============================================================================
# Document Metadata Tests
# =============================================================================


class TestDocumentMetadata:
    """Test full metadata endpoint."""

    def test_get_full_metadata(self, client):
        """Test getting full document metadata."""
        response = client.get("/api/documents/doc-123/metadata")
        # Currently returns 404 (stub implementation)
        assert response.status_code == 404

    def test_get_full_metadata_not_found(self, client):
        """Test getting metadata for non-existent document."""
        response = client.get("/api/documents/nonexistent/metadata")
        assert response.status_code == 404


# =============================================================================
# Statistics Tests
# =============================================================================


class TestDocumentStatistics:
    """Test document statistics endpoints."""

    def test_get_document_count(self, client):
        """Test getting document count."""
        response = client.get("/api/documents/count")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)
        assert data["count"] >= 0

    def test_get_document_count_with_status(self, client):
        """Test getting count filtered by status."""
        response = client.get("/api/documents/count?status=processed")
        assert response.status_code == 200

        data = response.json()
        assert "count" in data

    def test_get_document_stats(self, client):
        """Test getting document statistics."""
        response = client.get("/api/documents/stats")
        assert response.status_code == 200

        data = response.json()
        assert "total_documents" in data
        assert "processed_documents" in data
        assert "processing_documents" in data
        assert "failed_documents" in data
        assert "total_size_bytes" in data
        assert "total_pages" in data
        assert "total_chunks" in data

        # All should be integers
        assert isinstance(data["total_documents"], int)
        assert isinstance(data["processed_documents"], int)
        assert isinstance(data["total_size_bytes"], int)


# =============================================================================
# Batch Operation Tests
# =============================================================================


class TestBatchOperations:
    """Test batch operation endpoints."""

    def test_batch_update_tags(self, client, mock_shard):
        """Test batch updating tags."""
        mock_shard.batch_update_tags = AsyncMock(
            return_value={
                "processed": 3,
                "failed": 0,
                "details": [],
            }
        )
        payload = {"document_ids": ["doc-1", "doc-2", "doc-3"], "add_tags": ["important"], "remove_tags": ["obsolete"]}
        response = client.post("/api/documents/batch/update-tags", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "processed" in data
        assert "failed" in data
        assert "message" in data

    def test_batch_update_tags_add_only(self, client, mock_shard):
        """Test batch adding tags."""
        mock_shard.batch_update_tags = AsyncMock(
            return_value={
                "processed": 2,
                "failed": 0,
                "details": [],
            }
        )
        payload = {"document_ids": ["doc-1", "doc-2"], "add_tags": ["new-tag"]}
        response = client.post("/api/documents/batch/update-tags", json=payload)
        assert response.status_code == 200

    def test_batch_update_tags_remove_only(self, client, mock_shard):
        """Test batch removing tags."""
        mock_shard.batch_update_tags = AsyncMock(
            return_value={
                "processed": 2,
                "failed": 0,
                "details": [],
            }
        )
        payload = {"document_ids": ["doc-1", "doc-2"], "remove_tags": ["old-tag"]}
        response = client.post("/api/documents/batch/update-tags", json=payload)
        assert response.status_code == 200

    def test_batch_update_tags_empty_list(self, client, mock_shard):
        """Test batch update with empty document list."""
        payload = {"document_ids": [], "add_tags": ["tag"]}
        response = client.post("/api/documents/batch/update-tags", json=payload)
        # API now returns 400 for empty document list
        assert response.status_code == 400

    def test_batch_delete_documents(self, client, mock_shard):
        """Test batch deleting documents."""
        mock_shard.batch_delete_documents = AsyncMock(
            return_value={
                "processed": 3,
                "failed": 0,
                "details": [],
            }
        )
        payload = {"document_ids": ["doc-1", "doc-2", "doc-3"]}
        response = client.post("/api/documents/batch/delete", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "processed" in data
        assert "failed" in data
        assert "message" in data

    def test_batch_delete_empty_list(self, client, mock_shard):
        """Test batch delete with empty list."""
        payload = {"document_ids": []}
        response = client.post("/api/documents/batch/delete", json=payload)
        # API now returns 400 for empty list
        assert response.status_code == 400


# =============================================================================
# Request Validation Tests
# =============================================================================


class TestRequestValidation:
    """Test request validation and error handling."""

    def test_list_documents_invalid_sort_order(self, client):
        """Test invalid sort order."""
        response = client.get("/api/documents/items?order=invalid")
        # Should accept any string (validation at app level)
        assert response.status_code == 200

    def test_update_document_invalid_json(self, client):
        """Test update with invalid JSON."""
        response = client.patch(
            "/api/documents/items/doc-123", data="invalid json", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_batch_operation_missing_field(self, client):
        """Test batch operation with missing required field."""
        response = client.post("/api/documents/batch/delete", json={})
        # Should fail validation
        assert response.status_code == 422


# =============================================================================
# Response Schema Tests
# =============================================================================


class TestResponseSchemas:
    """Test API response schemas match Pydantic models."""

    def test_document_list_response_schema(self, client):
        """Test DocumentListResponse schema."""
        response = client.get("/api/documents/items")
        data = response.json()

        # Required fields
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

        # Types
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["page"], int)
        assert isinstance(data["page_size"], int)

    def test_chunk_list_response_schema(self, client, mock_shard):
        """Test ChunkListResponse schema."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_chunks = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 50,
            }
        )

        response = client.get("/api/documents/doc-123/chunks")
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_entity_list_response_schema(self, client, mock_shard):
        """Test EntityListResponse schema."""
        mock_shard.get_document = AsyncMock(return_value=MagicMock(id="doc-123"))
        mock_shard.get_document_entities = AsyncMock(
            return_value={
                "items": [],
                "total": 0,
            }
        )

        response = client.get("/api/documents/doc-123/entities")
        data = response.json()

        assert "items" in data
        assert "total" in data

    def test_document_stats_response_schema(self, client):
        """Test DocumentStats schema."""
        response = client.get("/api/documents/stats")
        data = response.json()

        required_fields = [
            "total_documents",
            "processed_documents",
            "processing_documents",
            "failed_documents",
            "total_size_bytes",
            "total_pages",
            "total_chunks",
        ]

        for field in required_fields:
            assert field in data
            assert isinstance(data[field], int)

    def test_batch_result_response_schema(self, client, mock_shard):
        """Test batch operation response schema."""
        mock_shard.batch_delete_documents = AsyncMock(
            return_value={
                "processed": 1,
                "failed": 0,
                "details": [],
            }
        )
        payload = {"document_ids": ["doc-1"]}
        response = client.post("/api/documents/batch/delete", json=payload)
        data = response.json()

        assert "success" in data
        assert "processed" in data
        assert "failed" in data
        assert "message" in data

        assert isinstance(data["success"], bool)
        assert isinstance(data["processed"], int)
        assert isinstance(data["failed"], int)
        assert isinstance(data["message"], str)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_document_id(self, client):
        """Test handling very long document ID."""
        long_id = "x" * 1000
        response = client.get(f"/api/documents/items/{long_id}")
        assert response.status_code in [404, 414]  # Not found or URI too long

    def test_special_characters_in_search(self, client):
        """Test search with special characters."""
        response = client.get("/api/documents/items?q=test%20%26%20special")
        assert response.status_code == 200

    def test_unicode_in_search(self, client):
        """Test search with unicode characters."""
        response = client.get("/api/documents/items?q=caf\u00e9")
        assert response.status_code == 200

    def test_negative_page_number(self, client):
        """Test negative page number."""
        response = client.get("/api/documents/items?page=-1")
        assert response.status_code in [200, 422]

    def test_zero_page_size(self, client):
        """Test zero page size."""
        response = client.get("/api/documents/items?page_size=0")
        assert response.status_code == 422
