"""Tests for Summary Shard API endpoints."""

import json
import re
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arkham_shard_summary import SummaryShard
from arkham_shard_summary.api import init_api, router
from arkham_shard_summary.models import (
    SourceType,
    Summary,
    SummaryLength,
    SummaryResult,
    SummaryStatus,
    SummaryType,
)
from fastapi.testclient import TestClient


class MockDatabase:
    """In-memory mock database for summary shard testing."""

    def __init__(self):
        self.summaries = {}  # id -> row dict
        self.documents = {}

    def _make_doc(self, doc_id):
        """Generate a document row for any doc_id."""
        return {
            "id": doc_id,
            "filename": f"{doc_id}.txt",
            "metadata": json.dumps(
                {"content": f"Document content for {doc_id}. This is test content with enough text to summarize."}
            ),
        }

    async def execute(self, sql, params=None):
        if params is None:
            params = {}
        sql_upper = sql.strip().upper()

        if sql_upper.startswith("CREATE") or sql_upper.startswith("DO"):
            return

        if "INSERT INTO ARKHAM_SUMMARIES" in sql_upper:
            row = dict(params)
            self.summaries[row["id"]] = row
            return

        if "DELETE FROM ARKHAM_SUMMARIES" in sql_upper:
            sid = params.get("id")
            if sid and sid in self.summaries:
                del self.summaries[sid]
            return

        if "UPDATE ARKHAM_SUMMARIES" in sql_upper:
            sid = params.get("id")
            if sid and sid in self.summaries:
                for k, v in params.items():
                    if k != "id":
                        self.summaries[sid][k] = v
            return

    async def fetch_one(self, sql, params=None):
        if params is None:
            params = {}
        sql_upper = sql.strip().upper()

        if "COUNT(*)" in sql_upper:
            if "ARKHAM_SUMMARIES" in sql_upper:
                return {"count": len(self.summaries)}
            return {"count": 0}

        if "ARKHAM_FRAME.DOCUMENTS" in sql_upper or "ARKHAM_DOCUMENTS" in sql_upper:
            doc_id = params.get("id")
            if doc_id:
                return self._make_doc(doc_id)
            return None

        if "ARKHAM_SUMMARIES" in sql_upper:
            sid = params.get("id")
            if sid and sid in self.summaries:
                return dict(self.summaries[sid])
            return None

        return None

    async def fetch_all(self, sql, params=None):
        if params is None:
            params = {}
        sql_upper = sql.strip().upper()

        if "GROUP BY" in sql_upper:
            if "SUMMARY_TYPE" in sql_upper:
                type_counts = {}
                for row in self.summaries.values():
                    t = row.get("summary_type", "")
                    type_counts[t] = type_counts.get(t, 0) + 1
                return [{"summary_type": k, "count": v} for k, v in type_counts.items()]
            if "SOURCE_TYPE" in sql_upper:
                src_counts = {}
                for row in self.summaries.values():
                    t = row.get("source_type", "")
                    src_counts[t] = src_counts.get(t, 0) + 1
                return [{"source_type": k, "count": v} for k, v in src_counts.items()]
            if "STATUS" in sql_upper:
                status_counts = {}
                for row in self.summaries.values():
                    t = row.get("status", "")
                    status_counts[t] = status_counts.get(t, 0) + 1
                return [{"status": k, "count": v} for k, v in status_counts.items()]

        if "ARKHAM_SUMMARIES" in sql_upper:
            rows = list(self.summaries.values())

            if "summary_type" in params:
                rows = [r for r in rows if r.get("summary_type") == params["summary_type"]]
            if "source_type" in params:
                rows = [r for r in rows if r.get("source_type") == params["source_type"]]

            rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)

            limit_match = re.search(r"LIMIT\s+(\d+)", sql_upper)
            offset_match = re.search(r"OFFSET\s+(\d+)", sql_upper)
            if limit_match:
                limit = int(limit_match.group(1))
                offset = int(offset_match.group(1)) if offset_match else 0
                rows = rows[offset : offset + limit]

            return [dict(r) for r in rows]

        return []


class MockFrame:
    """Mock ArkhamFrame for API testing."""

    def __init__(self):
        self.services = {}
        self.db = MockDatabase()

    def get_service(self, name: str):
        """Get a mock service."""
        if name == "database" or name == "db":
            return self.db

        if name == "events":
            mock_events = Mock()
            mock_events.subscribe = AsyncMock()
            mock_events.unsubscribe = AsyncMock()
            mock_events.emit = AsyncMock()
            return mock_events

        if name == "llm":
            mock_llm = Mock()
            mock_llm.generate = AsyncMock(return_value="Mock LLM summary.")
            mock_llm.model_name = "mock-llm"
            return mock_llm

        if name == "workers":
            return Mock()

        return None


@pytest.fixture
async def shard():
    """Create and initialize a shard for testing."""
    shard = SummaryShard()
    frame = MockFrame()
    await shard.initialize(frame)
    init_api(shard)
    return shard


@pytest.fixture
def client(shard):
    """Create test client."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health(self, client, shard):
        """Test health endpoint."""
        response = client.get("/api/summary/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["shard"] == "summary"
        assert "llm_available" in data


class TestCapabilitiesEndpoint:
    """Test capabilities endpoint."""

    def test_capabilities(self, client, shard):
        """Test capabilities endpoint."""
        response = client.get("/api/summary/capabilities")

        assert response.status_code == 200
        data = response.json()
        assert "llm_available" in data
        assert "workers_available" in data
        assert "summary_types" in data
        assert "source_types" in data
        assert "target_lengths" in data


class TestTypesEndpoint:
    """Test types endpoint."""

    def test_get_types(self, client, shard):
        """Test getting summary types."""
        response = client.get("/api/summary/types")

        assert response.status_code == 200
        data = response.json()
        assert "types" in data
        assert len(data["types"]) > 0

        # Check structure
        first_type = data["types"][0]
        assert "value" in first_type
        assert "label" in first_type
        assert "description" in first_type


class TestCountEndpoint:
    """Test count endpoint."""

    @pytest.mark.asyncio
    async def test_get_count_empty(self, client, shard):
        """Test getting count when no summaries exist."""
        response = client.get("/api/summary/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_count_with_summaries(self, client, shard):
        """Test getting count with summaries."""
        # Create a summary first
        from arkham_shard_summary.models import SummaryRequest

        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
        )
        await shard.generate_summary(request)

        response = client.get("/api/summary/count")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1


class TestListEndpoint:
    """Test list summaries endpoint."""

    def test_list_empty(self, client, shard):
        """Test listing when no summaries exist."""
        response = client.get("/api/summary/")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20

    @pytest.mark.asyncio
    async def test_list_with_summaries(self, client, shard):
        """Test listing summaries."""
        from arkham_shard_summary.models import SummaryRequest

        # Create a few summaries
        for i in range(3):
            request = SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=[f"doc-{i}"],
            )
            await shard.generate_summary(request)

        response = client.get("/api/summary/")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3

    def test_list_with_pagination(self, client, shard):
        """Test listing with pagination."""
        response = client.get("/api/summary/?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_list_with_filters(self, client, shard):
        """Test listing with filters."""
        response = client.get("/api/summary/?summary_type=detailed&source_type=document")

        assert response.status_code == 200

    def test_list_with_invalid_filter(self, client, shard):
        """Test listing with invalid filter."""
        response = client.get("/api/summary/?summary_type=invalid")

        assert response.status_code == 400


class TestCreateEndpoint:
    """Test create summary endpoint."""

    def test_create_summary(self, client, shard):
        """Test creating a summary."""
        request_data = {
            "source_type": "document",
            "source_ids": ["doc-123"],
            "summary_type": "detailed",
            "target_length": "medium",
            "include_key_points": True,
            "include_title": True,
        }

        response = client.post("/api/summary/", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "summary_id" in data
        assert data["status"] == "completed"
        assert "content" in data

    def test_create_summary_with_focus(self, client, shard):
        """Test creating summary with focus areas."""
        request_data = {
            "source_type": "document",
            "source_ids": ["doc-123"],
            "summary_type": "executive",
            "focus_areas": ["key findings"],
            "exclude_topics": ["acknowledgments"],
        }

        response = client.post("/api/summary/", json=request_data)

        assert response.status_code == 200

    def test_create_summary_invalid_type(self, client, shard):
        """Test creating summary with invalid type."""
        request_data = {
            "source_type": "invalid_type",
            "source_ids": ["doc-123"],
        }

        response = client.post("/api/summary/", json=request_data)

        assert response.status_code == 422  # Validation error

    def test_create_summary_no_sources(self, client, shard):
        """Test creating summary with no source IDs."""
        request_data = {
            "source_type": "document",
            "source_ids": [],
        }

        response = client.post("/api/summary/", json=request_data)

        assert response.status_code == 422  # Validation error


class TestGetEndpoint:
    """Test get summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_summary(self, client, shard):
        """Test getting a summary by ID."""
        from arkham_shard_summary.models import SummaryRequest

        # Create a summary first
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
        )
        result = await shard.generate_summary(request)
        summary_id = result.summary_id

        # Get it
        response = client.get(f"/api/summary/{summary_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == summary_id
        assert "content" in data

    def test_get_nonexistent_summary(self, client, shard):
        """Test getting a summary that doesn't exist."""
        response = client.get("/api/summary/nonexistent-id")

        assert response.status_code == 404


class TestDeleteEndpoint:
    """Test delete summary endpoint."""

    @pytest.mark.asyncio
    async def test_delete_summary(self, client, shard):
        """Test deleting a summary."""
        from arkham_shard_summary.models import SummaryRequest

        # Create a summary first
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
        )
        result = await shard.generate_summary(request)
        summary_id = result.summary_id

        # Delete it
        response = client.delete(f"/api/summary/{summary_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["summary_id"] == summary_id

    def test_delete_nonexistent_summary(self, client, shard):
        """Test deleting a summary that doesn't exist.

        Note: The shard always returns True for deletes (SQL DELETE on
        nonexistent row is a no-op), so the API returns 200.
        """
        response = client.delete("/api/summary/nonexistent-id")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True


class TestBatchEndpoint:
    """Test batch summary endpoint."""

    def test_batch_summaries(self, client, shard):
        """Test batch summary creation."""
        request_data = {
            "requests": [
                {
                    "source_type": "document",
                    "source_ids": ["doc-1"],
                    "summary_type": "brief",
                },
                {
                    "source_type": "document",
                    "source_ids": ["doc-2"],
                    "summary_type": "detailed",
                },
            ],
            "parallel": False,
            "stop_on_error": False,
        }

        response = client.post("/api/summary/batch", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["successful"] == 2
        assert data["failed"] == 0
        assert len(data["summaries"]) == 2


class TestDocumentEndpoint:
    """Test document summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_document_summary_new(self, client, shard):
        """Test getting summary for document (creates new)."""
        response = client.get("/api/summary/document/doc-123")

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "content" in data

    @pytest.mark.asyncio
    async def test_get_document_summary_existing(self, client, shard):
        """Test getting summary for document (returns existing)."""
        from arkham_shard_summary.models import SummaryRequest

        # Create a summary first
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-456"],
        )
        result = await shard.generate_summary(request)
        summary_id = result.summary_id

        # Get it via document endpoint
        response = client.get("/api/summary/document/doc-456")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == summary_id

    def test_get_document_summary_regenerate(self, client, shard):
        """Test forcing regeneration of document summary."""
        response = client.get("/api/summary/document/doc-789?regenerate=true")

        assert response.status_code == 200

    def test_get_document_summary_invalid_type(self, client, shard):
        """Test getting document summary with invalid type."""
        response = client.get("/api/summary/document/doc-123?summary_type=invalid")

        assert response.status_code == 400


class TestStatsEndpoint:
    """Test statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats(self, client, shard):
        """Test getting statistics."""
        from arkham_shard_summary.models import SummaryRequest

        # Create a few summaries
        await shard.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-1"],
                summary_type=SummaryType.BRIEF,
            )
        )
        await shard.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-2"],
                summary_type=SummaryType.DETAILED,
            )
        )

        response = client.get("/api/summary/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_summaries"] == 2
        assert "by_type" in data
        assert "by_source_type" in data
        assert "avg_confidence" in data
