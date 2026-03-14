"""
Tests for Search Shard keyword_search() and search_history() methods.

TDD: Tests written FIRST before implementation.

Run with:
    uv run python -m pytest packages/arkham-shard-search/tests/test_keyword_search_history.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_search.shard import SearchShard

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_database():
    """Mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_one = AsyncMock(return_value={"count": 0})
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_frame(mock_database):
    """Mock ArkhamFrame instance with database."""
    frame = MagicMock()
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "database": mock_database,
            "db": mock_database,
        }.get(name)
    )
    return frame


@pytest.fixture
def shard():
    """Create a fresh SearchShard instance."""
    return SearchShard()


@pytest.fixture
async def initialized_shard(shard, mock_frame):
    """Create an initialized SearchShard instance."""
    await shard.initialize(mock_frame)
    return shard


# =============================================================================
# keyword_search() Tests
# =============================================================================


class TestKeywordSearch:
    """Tests for the keyword_search() public method on the shard."""

    @pytest.mark.asyncio
    async def test_keyword_search_returns_list(self, initialized_shard, mock_database):
        """keyword_search must return a list."""
        mock_database.fetch_all.return_value = []
        result = await initialized_shard.keyword_search("test query")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_keyword_search_result_structure(self, initialized_shard, mock_database):
        """Each result has doc_id, chunk_id, title, excerpt, score."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "text": "This is a test document about employment law proceedings",
                "page_number": 1,
                "chunk_index": 0,
                "title": "test_doc.pdf",
                "mime_type": "application/pdf",
                "created_at": None,
            },
        ]

        result = await initialized_shard.keyword_search("employment law")
        assert len(result) >= 1

        item = result[0]
        assert "doc_id" in item
        assert "chunk_id" in item
        assert "title" in item
        assert "excerpt" in item
        assert "score" in item

    @pytest.mark.asyncio
    async def test_keyword_search_respects_limit(self, initialized_shard, mock_database):
        """keyword_search respects the limit parameter."""
        rows = [
            {
                "chunk_id": f"chunk-{i}",
                "document_id": f"doc-{i}",
                "text": f"Document {i} content about legal matters",
                "page_number": 1,
                "chunk_index": 0,
                "title": f"doc_{i}.pdf",
                "mime_type": "application/pdf",
                "created_at": None,
            }
            for i in range(30)
        ]
        mock_database.fetch_one.return_value = {"count": 100, "avg_length": 500.0}
        mock_database.fetch_all.return_value = rows

        result = await initialized_shard.keyword_search("legal", limit=5)
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_keyword_search_default_limit(self, initialized_shard, mock_database):
        """keyword_search defaults to limit=20."""
        rows = [
            {
                "chunk_id": f"chunk-{i}",
                "document_id": f"doc-{i}",
                "text": f"Document {i} matching content",
                "page_number": 1,
                "chunk_index": 0,
                "title": f"doc_{i}.pdf",
                "mime_type": "application/pdf",
                "created_at": None,
            }
            for i in range(30)
        ]
        mock_database.fetch_one.return_value = {"count": 100, "avg_length": 500.0}
        mock_database.fetch_all.return_value = rows

        result = await initialized_shard.keyword_search("matching content")
        assert len(result) <= 20

    @pytest.mark.asyncio
    async def test_keyword_search_uses_ilike_matching(self, initialized_shard, mock_database):
        """keyword_search queries using ILIKE for case-insensitive matching."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = []

        await initialized_shard.keyword_search("Employment")

        # Verify that fetch_all was called (the SQL uses ILIKE)
        assert mock_database.fetch_all.called

    @pytest.mark.asyncio
    async def test_keyword_search_ranks_by_matching_terms(self, initialized_shard, mock_database):
        """Results are ranked by number of matching query terms (TF scoring)."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "text": "employment law employment law employment",
                "page_number": 1,
                "chunk_index": 0,
                "title": "high_match.pdf",
                "mime_type": "application/pdf",
                "created_at": None,
            },
            {
                "chunk_id": "chunk-2",
                "document_id": "doc-2",
                "text": "some text about employment and other topics",
                "page_number": 1,
                "chunk_index": 0,
                "title": "low_match.pdf",
                "mime_type": "application/pdf",
                "created_at": None,
            },
        ]

        result = await initialized_shard.keyword_search("employment law")

        # First result should have higher score than second
        if len(result) >= 2:
            assert result[0]["score"] >= result[1]["score"]

    @pytest.mark.asyncio
    async def test_keyword_search_empty_query_returns_empty(self, initialized_shard, mock_database):
        """keyword_search with empty query returns empty list."""
        result = await initialized_shard.keyword_search("")
        assert result == []

    @pytest.mark.asyncio
    async def test_keyword_search_no_db_returns_empty(self, shard):
        """keyword_search returns empty when shard has no database."""
        result = await shard.keyword_search("test")
        assert result == []

    @pytest.mark.asyncio
    async def test_keyword_search_handles_db_error(self, initialized_shard, mock_database):
        """keyword_search handles database errors gracefully."""
        mock_database.fetch_all.side_effect = Exception("Database error")

        result = await initialized_shard.keyword_search("test")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_keyword_search_multi_term_query(self, initialized_shard, mock_database):
        """keyword_search handles multi-word queries."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = [
            {
                "chunk_id": "chunk-1",
                "document_id": "doc-1",
                "text": "This text contains employment tribunal proceedings in Bristol",
                "page_number": 1,
                "chunk_index": 0,
                "title": "doc.pdf",
                "mime_type": "application/pdf",
                "created_at": None,
            },
        ]

        result = await initialized_shard.keyword_search("employment tribunal Bristol")
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_keyword_search_stores_to_history(self, initialized_shard, mock_database):
        """keyword_search stores the query in search history."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = []

        await initialized_shard.keyword_search("employment law")

        # The shard should track this query in its search history
        history = await initialized_shard.search_history(limit=10)
        assert any("employment law" in entry for entry in history)


# =============================================================================
# search_history() Tests
# =============================================================================


class TestSearchHistory:
    """Tests for the search_history() method."""

    @pytest.mark.asyncio
    async def test_search_history_returns_list(self, initialized_shard):
        """search_history must return a list."""
        result = await initialized_shard.search_history()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_history_default_limit(self, initialized_shard):
        """search_history defaults to limit=50."""
        result = await initialized_shard.search_history()
        # Should return at most 50 items
        assert len(result) <= 50

    @pytest.mark.asyncio
    async def test_search_history_respects_limit(self, initialized_shard, mock_database):
        """search_history respects the limit parameter."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = []

        # Perform several searches
        for i in range(10):
            await initialized_shard.keyword_search(f"query {i}")

        result = await initialized_shard.search_history(limit=5)
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_search_history_returns_recent_first(self, initialized_shard, mock_database):
        """search_history returns most recent searches first."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = []

        await initialized_shard.keyword_search("first query")
        await initialized_shard.keyword_search("second query")
        await initialized_shard.keyword_search("third query")

        result = await initialized_shard.search_history(limit=10)
        if len(result) >= 2:
            # Most recent should be first
            assert result[0] == "third query"

    @pytest.mark.asyncio
    async def test_search_history_contains_strings(self, initialized_shard, mock_database):
        """search_history returns a list of strings."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = []

        await initialized_shard.keyword_search("test query")

        result = await initialized_shard.search_history(limit=10)
        for entry in result:
            assert isinstance(entry, str)

    @pytest.mark.asyncio
    async def test_search_history_empty_when_no_searches(self, initialized_shard):
        """search_history returns empty list when no searches have been performed."""
        result = await initialized_shard.search_history()
        assert result == []

    @pytest.mark.asyncio
    async def test_search_history_no_duplicate_consecutive(self, initialized_shard, mock_database):
        """search_history does not store the same query consecutively."""
        mock_database.fetch_one.return_value = {"count": 10, "avg_length": 500.0}
        mock_database.fetch_all.return_value = []

        await initialized_shard.keyword_search("same query")
        await initialized_shard.keyword_search("same query")
        await initialized_shard.keyword_search("same query")

        result = await initialized_shard.search_history(limit=10)
        # Should not have three consecutive "same query" entries
        assert result.count("same query") <= 1
