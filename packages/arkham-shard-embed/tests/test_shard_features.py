"""
Embed Shard - Embedding Stats, Unembedded Documents, and Similarity Tests

Tests for get_embedding_stats(), find_unembedded_documents(), and get_similarity().
TDD: Tests written BEFORE implementation.
"""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_embed.shard import EmbedShard


class TestGetEmbeddingStats:
    """Tests for get_embedding_stats() method."""

    @pytest.fixture
    def shard(self):
        """Create EmbedShard with mocked frame services."""
        s = EmbedShard()
        s.frame = MagicMock()

        # Mock database service
        mock_db = AsyncMock()
        s.frame.get_service.return_value = mock_db
        s._db_service = mock_db
        return s

    @pytest.mark.asyncio
    async def test_returns_dict(self, shard):
        """Stats returns a dictionary."""
        shard._db_service.fetch_all = AsyncMock(return_value=[])
        shard._db_service.fetch_one = AsyncMock(return_value={"count": 0})
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_embedding_stats()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_total_count(self, shard):
        """Stats includes total embedding count."""
        shard._db_service.fetch_one = AsyncMock(
            side_effect=[
                {"count": 150},  # total embeddings
                {"count": 50},  # total docs
                {"count": 30},  # docs with embeddings
            ]
        )
        shard._db_service.fetch_all = AsyncMock(return_value=[{"model": "all-MiniLM-L6-v2", "count": 150}])
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_embedding_stats()
        assert "total_embeddings" in result
        assert result["total_embeddings"] == 150

    @pytest.mark.asyncio
    async def test_contains_model_distribution(self, shard):
        """Stats includes which models were used and their counts."""
        shard._db_service.fetch_one = AsyncMock(
            side_effect=[
                {"count": 200},
                {"count": 50},
                {"count": 40},
            ]
        )
        shard._db_service.fetch_all = AsyncMock(
            return_value=[
                {"model": "all-MiniLM-L6-v2", "count": 150},
                {"model": "bge-m3", "count": 50},
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_embedding_stats()
        assert "model_distribution" in result
        assert isinstance(result["model_distribution"], list)

    @pytest.mark.asyncio
    async def test_contains_coverage(self, shard):
        """Stats includes coverage (docs with embeddings vs total docs)."""
        shard._db_service.fetch_one = AsyncMock(
            side_effect=[
                {"count": 100},  # total embeddings
                {"count": 50},  # total docs
                {"count": 30},  # docs with embeddings
            ]
        )
        shard._db_service.fetch_all = AsyncMock(return_value=[])
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_embedding_stats()
        assert "coverage" in result
        assert "total_documents" in result["coverage"]
        assert "documents_with_embeddings" in result["coverage"]

    @pytest.mark.asyncio
    async def test_no_db_service_returns_error(self, shard):
        """Returns error dict when database service unavailable."""
        shard.frame.get_service = MagicMock(return_value=None)

        result = await shard.get_embedding_stats()
        assert "error" in result


class TestFindUnembeddedDocuments:
    """Tests for find_unembedded_documents() method."""

    @pytest.fixture
    def shard(self):
        s = EmbedShard()
        s.frame = MagicMock()
        mock_db = AsyncMock()
        s._db_service = mock_db
        return s

    @pytest.mark.asyncio
    async def test_returns_list(self, shard):
        """Returns a list of documents."""
        shard._db_service.fetch_all = AsyncMock(return_value=[])
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.find_unembedded_documents()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_respects_limit(self, shard):
        """Limit parameter controls max results."""
        rows = [{"doc_id": f"doc-{i}", "chunk_count": 5} for i in range(10)]
        shard._db_service.fetch_all = AsyncMock(return_value=rows)
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.find_unembedded_documents(limit=10)
        assert len(result) <= 10

    @pytest.mark.asyncio
    async def test_default_limit_100(self, shard):
        """Default limit is 100."""
        shard._db_service.fetch_all = AsyncMock(return_value=[])
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        # Should not raise
        result = await shard.find_unembedded_documents()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_result_has_doc_id(self, shard):
        """Each result has a doc_id field."""
        shard._db_service.fetch_all = AsyncMock(
            return_value=[
                {"doc_id": "doc-1", "chunk_count": 3},
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.find_unembedded_documents()
        assert len(result) == 1
        assert "doc_id" in result[0]

    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, shard):
        """No database service returns empty list."""
        shard.frame.get_service = MagicMock(return_value=None)

        result = await shard.find_unembedded_documents()
        assert result == []


class TestGetSimilarity:
    """Tests for get_similarity() - cosine similarity between doc embeddings."""

    @pytest.fixture
    def shard(self):
        s = EmbedShard()
        s.frame = MagicMock()
        s.embedding_manager = MagicMock()
        mock_db = AsyncMock()
        s._db_service = mock_db
        return s

    @pytest.mark.asyncio
    async def test_returns_float(self, shard):
        """Similarity score is a float."""
        # Mock: both docs have embeddings
        shard._db_service.fetch_all = AsyncMock(
            side_effect=[
                [{"vector": [1.0, 0.0, 0.0]}],  # doc A
                [{"vector": [1.0, 0.0, 0.0]}],  # doc B
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_similarity("doc-a", "doc-b")
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_identical_docs_similarity_1(self, shard):
        """Identical embedding vectors should have similarity ~1.0."""
        vec = [1.0, 0.0, 0.0]
        shard._db_service.fetch_all = AsyncMock(
            side_effect=[
                [{"vector": vec}],
                [{"vector": vec}],
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_similarity("doc-a", "doc-b")
        assert abs(result - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_orthogonal_docs_similarity_0(self, shard):
        """Orthogonal vectors should have similarity ~0.0."""
        shard._db_service.fetch_all = AsyncMock(
            side_effect=[
                [{"vector": [1.0, 0.0, 0.0]}],
                [{"vector": [0.0, 1.0, 0.0]}],
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_similarity("doc-a", "doc-b")
        assert abs(result) < 0.01

    @pytest.mark.asyncio
    async def test_missing_doc_returns_negative(self, shard):
        """Missing document returns -1.0 to signal error."""
        shard._db_service.fetch_all = AsyncMock(
            side_effect=[
                [],  # doc A has no embeddings
                [{"vector": [1.0, 0.0, 0.0]}],
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_similarity("missing-doc", "doc-b")
        assert result == -1.0

    @pytest.mark.asyncio
    async def test_average_embedding_multiple_chunks(self, shard):
        """When doc has multiple chunks, averages their embeddings."""
        shard._db_service.fetch_all = AsyncMock(
            side_effect=[
                [{"vector": [1.0, 0.0]}, {"vector": [0.0, 1.0]}],  # doc A: avg = [0.5, 0.5]
                [{"vector": [0.5, 0.5]}],  # doc B
            ]
        )
        shard.frame.get_service = MagicMock(return_value=shard._db_service)

        result = await shard.get_similarity("doc-a", "doc-b")
        # Averaged vectors should be very similar
        assert result > 0.9

    @pytest.mark.asyncio
    async def test_no_db_returns_negative(self, shard):
        """No database service returns -1.0."""
        shard.frame.get_service = MagicMock(return_value=None)

        result = await shard.get_similarity("doc-a", "doc-b")
        assert result == -1.0
