"""Tests for Summary Shard implementation."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arkham_shard_summary import SummaryShard
from arkham_shard_summary.models import (
    BatchSummaryRequest,
    SourceType,
    Summary,
    SummaryFilter,
    SummaryLength,
    SummaryRequest,
    SummaryStatus,
    SummaryType,
)


class MockDatabase:
    """In-memory mock database for summary shard testing."""

    def __init__(self):
        self.summaries = {}  # id -> row dict
        # Pre-populate with fake document content
        self.documents = {
            "doc-123": {
                "id": "doc-123",
                "filename": "test.txt",
                "metadata": json.dumps(
                    {
                        "content": "This is a test document with important content for summarization. It contains multiple sentences and ideas that can be summarized effectively."
                    }
                ),
            },
        }

    def _make_doc(self, doc_id):
        """Generate a document row for any doc_id."""
        if doc_id in self.documents:
            return self.documents[doc_id]
        return {
            "id": doc_id,
            "filename": f"{doc_id}.txt",
            "metadata": json.dumps(
                {"content": f"Document content for {doc_id}. This is test content with enough text to summarize."}
            ),
        }

    async def execute(self, sql, params=None):
        """Handle INSERT, UPDATE, DELETE, CREATE TABLE."""
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
        """Handle SELECT returning one row."""
        if params is None:
            params = {}
        sql_upper = sql.strip().upper()

        # AVG/SUM aggregation queries (statistics)
        if "AVG(" in sql_upper or "SUM(" in sql_upper:
            completed = [s for s in self.summaries.values() if s.get("status") == "completed"]
            if not completed:
                return {
                    "avg_confidence": 0,
                    "avg_completeness": 0,
                    "avg_word_count": 0,
                    "avg_processing_time": 0,
                    "total_words": 0,
                    "total_tokens": 0,
                }
            return {
                "avg_confidence": sum(float(s.get("confidence", 0) or 0) for s in completed) / len(completed),
                "avg_completeness": sum(float(s.get("completeness", 0) or 0) for s in completed) / len(completed),
                "avg_word_count": sum(int(s.get("word_count", 0) or 0) for s in completed) / len(completed),
                "avg_processing_time": sum(float(s.get("processing_time_ms", 0) or 0) for s in completed)
                / len(completed),
                "total_words": sum(int(s.get("word_count", 0) or 0) for s in completed),
                "total_tokens": sum(int(s.get("token_count", 0) or 0) for s in completed),
            }

        # FILTER queries (recent activity stats)
        if "FILTER" in sql_upper:
            return {"generated": 0, "failed": 0}

        # Count queries
        if "COUNT(*)" in sql_upper:
            if "ARKHAM_SUMMARIES" in sql_upper:
                rows = list(self.summaries.values())
                return {"count": len(rows)}
            return {"count": 0}

        # Document content fetch
        if "ARKHAM_FRAME.DOCUMENTS" in sql_upper or "ARKHAM_DOCUMENTS" in sql_upper:
            doc_id = params.get("id")
            if doc_id:
                return self._make_doc(doc_id)
            return None

        # Summary by ID
        if "ARKHAM_SUMMARIES" in sql_upper:
            sid = params.get("id")
            if sid and sid in self.summaries:
                return dict(self.summaries[sid])
            return None

        return None

    async def fetch_all(self, sql, params=None):
        """Handle SELECT returning multiple rows."""
        if params is None:
            params = {}
        sql_upper = sql.strip().upper()

        # Group by queries for statistics
        if "GROUP BY" in sql_upper:
            if "MODEL_USED" in sql_upper:
                model_counts = {}
                for row in self.summaries.values():
                    m = row.get("model_used")
                    if m is not None:
                        model_counts[m] = model_counts.get(m, 0) + 1
                return [{"model_used": k, "count": v} for k, v in model_counts.items()]
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

        # List summaries
        if "ARKHAM_SUMMARIES" in sql_upper:
            rows = list(self.summaries.values())

            # Apply filters from params
            if "summary_type" in params:
                rows = [r for r in rows if r.get("summary_type") == params["summary_type"]]
            if "source_type" in params:
                rows = [r for r in rows if r.get("source_type") == params["source_type"]]
            if "status" in params:
                rows = [r for r in rows if r.get("status") == params["status"]]

            # Sort by created_at DESC
            rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)

            # Handle LIMIT/OFFSET from SQL
            import re

            limit_match = re.search(r"LIMIT\s+(\d+)", sql_upper)
            offset_match = re.search(r"OFFSET\s+(\d+)", sql_upper)
            if limit_match:
                limit = int(limit_match.group(1))
                offset = int(offset_match.group(1)) if offset_match else 0
                rows = rows[offset : offset + limit]

            return [dict(r) for r in rows]

        return []


class MockFrame:
    """Mock ArkhamFrame for testing."""

    def __init__(self, llm_available=True, workers_available=True):
        self.services = {}
        self.llm_available_flag = llm_available
        self.workers_available_flag = workers_available
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
            if not self.llm_available_flag:
                return None
            mock_llm = Mock()
            mock_llm.generate = AsyncMock(return_value="This is a mock summary from the LLM.")
            mock_llm.model_name = "mock-llm-model"
            return mock_llm

        if name == "workers":
            if not self.workers_available_flag:
                return None
            return Mock()

        return None


@pytest.fixture
async def shard_with_llm():
    """Create a shard instance with LLM available."""
    shard = SummaryShard()
    frame = MockFrame(llm_available=True, workers_available=True)
    await shard.initialize(frame)
    return shard


@pytest.fixture
async def shard_without_llm():
    """Create a shard instance without LLM."""
    shard = SummaryShard()
    frame = MockFrame(llm_available=False, workers_available=False)
    await shard.initialize(frame)
    return shard


class TestShardInitialization:
    """Test shard initialization."""

    @pytest.mark.asyncio
    async def test_initialize_with_llm(self):
        """Test initialization with LLM service available."""
        shard = SummaryShard()
        frame = MockFrame(llm_available=True)

        await shard.initialize(frame)

        assert shard._frame is not None
        assert shard._events is not None
        assert shard._llm is not None
        assert shard.llm_available is True

    @pytest.mark.asyncio
    async def test_initialize_without_llm(self):
        """Test initialization without LLM service."""
        shard = SummaryShard()
        frame = MockFrame(llm_available=False)

        await shard.initialize(frame)

        assert shard._frame is not None
        assert shard._events is not None
        assert shard._llm is None
        assert shard.llm_available is False

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shard shutdown."""
        shard = SummaryShard()
        frame = MockFrame()

        await shard.initialize(frame)
        await shard.shutdown()

        assert len(shard._summaries) == 0

    def test_get_routes(self):
        """Test getting API routes."""
        shard = SummaryShard()
        router = shard.get_routes()

        assert router is not None
        assert router.prefix == "/api/summary"


class TestSummarization:
    """Test summary generation."""

    @pytest.mark.asyncio
    async def test_generate_summary_with_llm(self, shard_with_llm):
        """Test generating summary with LLM."""
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            summary_type=SummaryType.DETAILED,
            target_length=SummaryLength.MEDIUM,
        )

        result = await shard_with_llm.generate_summary(request)

        assert result.status == SummaryStatus.COMPLETED
        assert result.summary_id is not None
        assert result.content != ""
        assert result.confidence == 1.0
        assert result.word_count > 0
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_generate_summary_without_llm(self, shard_without_llm):
        """Test generating summary without LLM (extractive fallback)."""
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            summary_type=SummaryType.DETAILED,
            target_length=SummaryLength.MEDIUM,
        )

        result = await shard_without_llm.generate_summary(request)

        assert result.status == SummaryStatus.COMPLETED
        assert result.summary_id is not None
        assert result.content != ""
        assert result.confidence == 0.7  # Lower confidence for extractive
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_generate_summary_with_focus_areas(self, shard_with_llm):
        """Test generating summary with focus areas."""
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            summary_type=SummaryType.DETAILED,
            focus_areas=["key findings", "methodology"],
            exclude_topics=["acknowledgments"],
        )

        result = await shard_with_llm.generate_summary(request)

        assert result.status == SummaryStatus.COMPLETED
        assert result.summary_id is not None

    @pytest.mark.asyncio
    async def test_generate_different_types(self, shard_with_llm):
        """Test generating different summary types."""
        types = [
            SummaryType.BRIEF,
            SummaryType.DETAILED,
            SummaryType.EXECUTIVE,
            SummaryType.BULLET_POINTS,
            SummaryType.ABSTRACT,
        ]

        for summary_type in types:
            request = SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-123"],
                summary_type=summary_type,
            )

            result = await shard_with_llm.generate_summary(request)
            assert result.status == SummaryStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_generate_different_lengths(self, shard_with_llm):
        """Test generating summaries with different target lengths."""
        lengths = [
            SummaryLength.VERY_SHORT,
            SummaryLength.SHORT,
            SummaryLength.MEDIUM,
            SummaryLength.LONG,
            SummaryLength.VERY_LONG,
        ]

        for length in lengths:
            request = SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-123"],
                target_length=length,
            )

            result = await shard_with_llm.generate_summary(request)
            assert result.status == SummaryStatus.COMPLETED


class TestBatchSummarization:
    """Test batch summary generation."""

    @pytest.mark.asyncio
    async def test_batch_summaries(self, shard_with_llm):
        """Test batch summarization."""
        requests = [
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-1"],
                summary_type=SummaryType.BRIEF,
            ),
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-2"],
                summary_type=SummaryType.DETAILED,
            ),
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-3"],
                summary_type=SummaryType.EXECUTIVE,
            ),
        ]

        batch_request = BatchSummaryRequest(
            requests=requests,
            parallel=False,
            stop_on_error=False,
        )

        result = await shard_with_llm.generate_batch_summaries(batch_request)

        assert result.total == 3
        assert result.successful == 3
        assert result.failed == 0
        assert len(result.summaries) == 3
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_batch_summaries_stop_on_error(self, shard_with_llm):
        """Test batch summarization with stop_on_error."""
        # This would require mocking a failure, which we'll skip for now
        pass


class TestCRUDOperations:
    """Test CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_summary(self, shard_with_llm):
        """Test getting a summary by ID."""
        # Generate a summary first
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
        )
        result = await shard_with_llm.generate_summary(request)
        summary_id = result.summary_id

        # Now retrieve it
        summary = await shard_with_llm.get_summary(summary_id)

        assert summary is not None
        assert summary.id == summary_id
        assert isinstance(summary, Summary)

    @pytest.mark.asyncio
    async def test_get_nonexistent_summary(self, shard_with_llm):
        """Test getting a summary that doesn't exist."""
        summary = await shard_with_llm.get_summary("nonexistent-id")
        assert summary is None

    @pytest.mark.asyncio
    async def test_list_summaries(self, shard_with_llm):
        """Test listing summaries."""
        # Generate a few summaries
        for i in range(5):
            request = SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=[f"doc-{i}"],
            )
            await shard_with_llm.generate_summary(request)

        summaries = await shard_with_llm.list_summaries()

        assert len(summaries) == 5

    @pytest.mark.asyncio
    async def test_list_summaries_with_filter(self, shard_with_llm):
        """Test listing summaries with filter."""
        # Generate summaries of different types
        await shard_with_llm.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-1"],
                summary_type=SummaryType.BRIEF,
            )
        )
        await shard_with_llm.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-2"],
                summary_type=SummaryType.DETAILED,
            )
        )

        # Filter for brief summaries
        filter = SummaryFilter(summary_type=SummaryType.BRIEF)
        summaries = await shard_with_llm.list_summaries(filter)

        assert len(summaries) == 1
        assert summaries[0].summary_type == SummaryType.BRIEF

    @pytest.mark.asyncio
    async def test_list_summaries_pagination(self, shard_with_llm):
        """Test listing summaries with pagination."""
        # Generate 10 summaries
        for i in range(10):
            request = SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=[f"doc-{i}"],
            )
            await shard_with_llm.generate_summary(request)

        # Get page 1
        page1 = await shard_with_llm.list_summaries(page=1, page_size=5)
        assert len(page1) == 5

        # Get page 2
        page2 = await shard_with_llm.list_summaries(page=2, page_size=5)
        assert len(page2) == 5

        # Pages should be different
        assert page1[0].id != page2[0].id

    @pytest.mark.asyncio
    async def test_delete_summary(self, shard_with_llm):
        """Test deleting a summary."""
        # Generate a summary
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
        )
        result = await shard_with_llm.generate_summary(request)
        summary_id = result.summary_id

        # Delete it
        deleted = await shard_with_llm.delete_summary(summary_id)
        assert deleted is True

        # Verify it's gone
        summary = await shard_with_llm.get_summary(summary_id)
        assert summary is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_summary(self, shard_with_llm):
        """Test deleting a summary that doesn't exist."""
        deleted = await shard_with_llm.delete_summary("nonexistent-id")
        assert deleted is True  # delete_summary always returns True (delete is idempotent)

    @pytest.mark.asyncio
    async def test_get_count(self, shard_with_llm):
        """Test getting summary count."""
        # Initially should be 0
        count = await shard_with_llm.get_count()
        assert count == 0

        # Generate a few summaries
        for i in range(3):
            request = SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=[f"doc-{i}"],
            )
            await shard_with_llm.generate_summary(request)

        # Count should be 3
        count = await shard_with_llm.get_count()
        assert count == 3


class TestStatistics:
    """Test statistics generation."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, shard_with_llm):
        """Test getting summary statistics."""
        # Generate summaries with different types
        await shard_with_llm.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-1"],
                summary_type=SummaryType.BRIEF,
            )
        )
        await shard_with_llm.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENT,
                source_ids=["doc-2"],
                summary_type=SummaryType.DETAILED,
            )
        )
        await shard_with_llm.generate_summary(
            SummaryRequest(
                source_type=SourceType.DOCUMENTS,
                source_ids=["doc-3", "doc-4"],
                summary_type=SummaryType.DETAILED,
            )
        )

        stats = await shard_with_llm.get_statistics()

        assert stats.total_summaries == 3
        assert stats.by_type["brief"] == 1
        assert stats.by_type["detailed"] == 2
        assert stats.by_source_type["document"] == 2
        assert stats.by_source_type["documents"] == 1
        assert stats.avg_confidence > 0
        assert stats.avg_word_count > 0


class TestPromptBuilding:
    """Test LLM prompt building."""

    def test_build_prompt_basic(self):
        """Test building basic prompt."""
        shard = SummaryShard()
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            summary_type=SummaryType.DETAILED,
            target_length=SummaryLength.MEDIUM,
        )

        prompt = shard._build_prompt("This is test text.", request)

        assert "Summarize the following text" in prompt
        assert "comprehensive summary" in prompt
        assert "medium-length" in prompt
        assert "This is test text" in prompt

    def test_build_prompt_with_focus(self):
        """Test building prompt with focus areas."""
        shard = SummaryShard()
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            focus_areas=["key findings", "methodology"],
            exclude_topics=["acknowledgments"],
        )

        prompt = shard._build_prompt("This is test text.", request)

        assert "Focus on: key findings, methodology" in prompt
        assert "Exclude: acknowledgments" in prompt

    def test_build_prompt_with_options(self):
        """Test building prompt with options."""
        shard = SummaryShard()
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            include_key_points=True,
            include_title=True,
        )

        prompt = shard._build_prompt("This is test text.", request)

        assert "key points" in prompt
        assert "title" in prompt


class TestExtractiveSummarization:
    """Test extractive summarization fallback."""

    @pytest.mark.asyncio
    async def test_extractive_summary(self):
        """Test extractive summarization."""
        shard = SummaryShard()
        request = SummaryRequest(
            source_type=SourceType.DOCUMENT,
            source_ids=["doc-123"],
            target_length=SummaryLength.SHORT,
        )

        text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        content, key_points, title = await shard._generate_extractive_summary(text, request)

        assert content != ""
        assert "First sentence" in content
        assert isinstance(key_points, list)
        assert title is not None
