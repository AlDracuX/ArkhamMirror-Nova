"""
Tests for Documents Shard scan_duplicates() and get_dedup_stats() methods.

TDD: Tests written FIRST before implementation.

Run with:
    uv run python -m pytest packages/arkham-shard-documents/tests/test_scan_duplicates.py -v
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from arkham_shard_documents.shard import DocumentsShard

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
def mock_events():
    """Mock event bus service."""
    events = AsyncMock()
    events.publish = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_frame(mock_database, mock_events):
    """Mock ArkhamFrame instance."""
    frame = Mock()
    frame.get_service = Mock(
        side_effect=lambda name: {
            "database": mock_database,
            "events": mock_events,
            "storage": None,
            "documents": None,
        }.get(name)
    )
    return frame


@pytest.fixture
def shard():
    """Create a fresh DocumentsShard instance."""
    return DocumentsShard()


@pytest.fixture
async def initialized_shard(shard, mock_frame):
    """Create an initialized DocumentsShard instance."""
    await shard.initialize(mock_frame)
    return shard


# =============================================================================
# scan_duplicates() Tests
# =============================================================================


class TestScanDuplicates:
    """Tests for the scan_duplicates() method."""

    @pytest.mark.asyncio
    async def test_scan_duplicates_returns_list(self, initialized_shard):
        """scan_duplicates must return a list."""
        result = await initialized_shard.scan_duplicates()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_scan_duplicates_empty_when_no_documents(self, initialized_shard, mock_database):
        """scan_duplicates returns empty list when no documents exist."""
        mock_database.fetch_all.return_value = []
        result = await initialized_shard.scan_duplicates()
        assert result == []

    @pytest.mark.asyncio
    async def test_scan_duplicates_finds_exact_duplicates(self, initialized_shard, mock_database):
        """scan_duplicates detects documents with identical SHA-256 hashes."""
        # Two documents sharing the same SHA-256 hash
        mock_database.fetch_all.return_value = [
            {
                "document_id": "doc-1",
                "filename": "report.pdf",
                "content_sha256": "abc123hash",
                "file_size": 1024,
            },
            {
                "document_id": "doc-2",
                "filename": "report_copy.pdf",
                "content_sha256": "abc123hash",
                "file_size": 1024,
            },
            {
                "document_id": "doc-3",
                "filename": "unique.pdf",
                "content_sha256": "def456hash",
                "file_size": 2048,
            },
        ]

        result = await initialized_shard.scan_duplicates()

        # Should find one group of exact duplicates
        exact_groups = [g for g in result if g["type"] == "exact"]
        assert len(exact_groups) == 1
        assert exact_groups[0]["hash"] == "abc123hash"
        assert len(exact_groups[0]["documents"]) == 2

    @pytest.mark.asyncio
    async def test_scan_duplicates_exact_group_structure(self, initialized_shard, mock_database):
        """Each duplicate group has correct structure: hash, documents, type."""
        mock_database.fetch_all.return_value = [
            {
                "document_id": "doc-1",
                "filename": "report.pdf",
                "content_sha256": "abc123",
                "file_size": 1024,
            },
            {
                "document_id": "doc-2",
                "filename": "report2.pdf",
                "content_sha256": "abc123",
                "file_size": 1024,
            },
        ]

        result = await initialized_shard.scan_duplicates()
        assert len(result) >= 1

        group = result[0]
        assert "hash" in group
        assert "documents" in group
        assert "type" in group
        assert group["type"] in ("exact", "near")

    @pytest.mark.asyncio
    async def test_scan_duplicates_document_entries_have_id_and_filename(self, initialized_shard, mock_database):
        """Each document in a group has id and filename fields."""
        mock_database.fetch_all.return_value = [
            {
                "document_id": "doc-1",
                "filename": "report.pdf",
                "content_sha256": "abc123",
                "file_size": 1024,
            },
            {
                "document_id": "doc-2",
                "filename": "report_v2.pdf",
                "content_sha256": "abc123",
                "file_size": 1024,
            },
        ]

        result = await initialized_shard.scan_duplicates()
        assert len(result) >= 1

        for doc in result[0]["documents"]:
            assert "id" in doc
            assert "filename" in doc

    @pytest.mark.asyncio
    async def test_scan_duplicates_finds_near_duplicates(self, initialized_shard, mock_database):
        """scan_duplicates detects near-duplicates by file size and filename similarity."""
        # Two documents with different hashes but similar size (+/-5%) and similar names
        mock_database.fetch_all.return_value = [
            {
                "document_id": "doc-1",
                "filename": "annual_report_2024.pdf",
                "content_sha256": "hash_aaa",
                "file_size": 10000,
            },
            {
                "document_id": "doc-2",
                "filename": "annual_report_2024_v2.pdf",
                "content_sha256": "hash_bbb",
                "file_size": 10200,  # Within 5% of 10000
            },
            {
                "document_id": "doc-3",
                "filename": "completely_different.txt",
                "content_sha256": "hash_ccc",
                "file_size": 50000,  # Very different size
            },
        ]

        result = await initialized_shard.scan_duplicates()

        near_groups = [g for g in result if g["type"] == "near"]
        assert len(near_groups) >= 1

        # The near-duplicate group should contain doc-1 and doc-2
        near_doc_ids = set()
        for group in near_groups:
            for doc in group["documents"]:
                near_doc_ids.add(doc["id"])
        assert "doc-1" in near_doc_ids
        assert "doc-2" in near_doc_ids

    @pytest.mark.asyncio
    async def test_scan_duplicates_near_duplicate_size_threshold(self, initialized_shard, mock_database):
        """Near-duplicates require file_size within +/-5%."""
        # doc-2 is 6% larger than doc-1 => NOT a near-duplicate
        mock_database.fetch_all.return_value = [
            {
                "document_id": "doc-1",
                "filename": "report.pdf",
                "content_sha256": "hash_aaa",
                "file_size": 10000,
            },
            {
                "document_id": "doc-2",
                "filename": "report_copy.pdf",
                "content_sha256": "hash_bbb",
                "file_size": 10600,  # 6% larger - outside threshold
            },
        ]

        result = await initialized_shard.scan_duplicates()

        near_groups = [g for g in result if g["type"] == "near"]
        assert len(near_groups) == 0

    @pytest.mark.asyncio
    async def test_scan_duplicates_near_duplicate_name_threshold(self, initialized_shard, mock_database):
        """Near-duplicates require SequenceMatcher ratio > 0.8."""
        # Two documents with similar size but completely different names
        mock_database.fetch_all.return_value = [
            {
                "document_id": "doc-1",
                "filename": "alpha_beta_gamma.pdf",
                "content_sha256": "hash_aaa",
                "file_size": 10000,
            },
            {
                "document_id": "doc-2",
                "filename": "xyz_123_456.pdf",
                "content_sha256": "hash_bbb",
                "file_size": 10100,  # Similar size
            },
        ]

        result = await initialized_shard.scan_duplicates()

        near_groups = [g for g in result if g["type"] == "near"]
        assert len(near_groups) == 0

    @pytest.mark.asyncio
    async def test_scan_duplicates_multiple_exact_groups(self, initialized_shard, mock_database):
        """scan_duplicates can return multiple exact duplicate groups."""
        mock_database.fetch_all.return_value = [
            {"document_id": "doc-1", "filename": "a.pdf", "content_sha256": "hash_A", "file_size": 100},
            {"document_id": "doc-2", "filename": "a2.pdf", "content_sha256": "hash_A", "file_size": 100},
            {"document_id": "doc-3", "filename": "b.pdf", "content_sha256": "hash_B", "file_size": 200},
            {"document_id": "doc-4", "filename": "b2.pdf", "content_sha256": "hash_B", "file_size": 200},
            {"document_id": "doc-5", "filename": "unique.pdf", "content_sha256": "hash_C", "file_size": 300},
        ]

        result = await initialized_shard.scan_duplicates()

        exact_groups = [g for g in result if g["type"] == "exact"]
        assert len(exact_groups) == 2

    @pytest.mark.asyncio
    async def test_scan_duplicates_both_exact_and_near(self, initialized_shard, mock_database):
        """scan_duplicates can find both exact and near duplicates."""
        mock_database.fetch_all.return_value = [
            # Exact duplicate pair
            {"document_id": "doc-1", "filename": "a.pdf", "content_sha256": "hash_A", "file_size": 100},
            {"document_id": "doc-2", "filename": "a2.pdf", "content_sha256": "hash_A", "file_size": 100},
            # Near-duplicate pair (similar size, similar name, different hash)
            {"document_id": "doc-3", "filename": "my_report.pdf", "content_sha256": "hash_B", "file_size": 5000},
            {"document_id": "doc-4", "filename": "my_report_v2.pdf", "content_sha256": "hash_C", "file_size": 5100},
        ]

        result = await initialized_shard.scan_duplicates()

        exact_groups = [g for g in result if g["type"] == "exact"]
        near_groups = [g for g in result if g["type"] == "near"]
        assert len(exact_groups) >= 1
        assert len(near_groups) >= 1

    @pytest.mark.asyncio
    async def test_scan_duplicates_no_db_returns_empty(self, shard):
        """scan_duplicates returns empty when shard is not initialized."""
        result = await shard.scan_duplicates()
        assert result == []

    @pytest.mark.asyncio
    async def test_scan_duplicates_handles_db_error(self, initialized_shard, mock_database):
        """scan_duplicates handles database errors gracefully."""
        mock_database.fetch_all.side_effect = Exception("Database connection lost")

        result = await initialized_shard.scan_duplicates()
        assert result == []

    @pytest.mark.asyncio
    async def test_scan_duplicates_excludes_exact_from_near(self, initialized_shard, mock_database):
        """Documents already in exact groups should not appear in near-duplicate groups."""
        mock_database.fetch_all.return_value = [
            {"document_id": "doc-1", "filename": "report.pdf", "content_sha256": "hash_A", "file_size": 1000},
            {"document_id": "doc-2", "filename": "report.pdf", "content_sha256": "hash_A", "file_size": 1000},
        ]

        result = await initialized_shard.scan_duplicates()

        # These two are exact duplicates - should not ALSO appear as near duplicates
        near_groups = [g for g in result if g["type"] == "near"]
        for group in near_groups:
            doc_ids = {d["id"] for d in group["documents"]}
            # If doc-1 and doc-2 form an exact group, they should not ALSO form a near group
            assert not ({"doc-1", "doc-2"}.issubset(doc_ids))


# =============================================================================
# get_dedup_stats() Tests
# =============================================================================


class TestGetDedupStats:
    """Tests for the get_dedup_stats() method."""

    @pytest.mark.asyncio
    async def test_get_dedup_stats_returns_dict(self, initialized_shard):
        """get_dedup_stats must return a dict."""
        result = await initialized_shard.get_dedup_stats()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_dedup_stats_required_keys(self, initialized_shard, mock_database):
        """get_dedup_stats must contain required keys."""
        mock_database.fetch_one.return_value = {
            "total_documents": 10,
            "unique_hashes": 8,
            "duplicate_count": 2,
            "total_size": 102400,
            "duplicate_size": 20480,
        }

        result = await initialized_shard.get_dedup_stats()

        assert "total_documents" in result
        assert "unique_hashes" in result
        assert "duplicate_count" in result
        assert "estimated_wasted_bytes" in result

    @pytest.mark.asyncio
    async def test_get_dedup_stats_correct_counts(self, initialized_shard, mock_database):
        """get_dedup_stats returns correct total docs and unique hashes."""
        mock_database.fetch_one.return_value = {
            "total_documents": 50,
            "unique_hashes": 45,
            "duplicate_count": 5,
            "total_size": 500000,
            "duplicate_size": 50000,
        }

        result = await initialized_shard.get_dedup_stats()

        assert result["total_documents"] == 50
        assert result["unique_hashes"] == 45
        assert result["duplicate_count"] == 5

    @pytest.mark.asyncio
    async def test_get_dedup_stats_wasted_bytes_calculated(self, initialized_shard, mock_database):
        """get_dedup_stats calculates estimated wasted bytes."""
        mock_database.fetch_one.return_value = {
            "total_documents": 10,
            "unique_hashes": 8,
            "duplicate_count": 2,
            "total_size": 102400,
            "duplicate_size": 20480,
        }

        result = await initialized_shard.get_dedup_stats()

        assert result["estimated_wasted_bytes"] >= 0

    @pytest.mark.asyncio
    async def test_get_dedup_stats_zero_when_no_duplicates(self, initialized_shard, mock_database):
        """get_dedup_stats shows zero duplicates when all hashes are unique."""
        mock_database.fetch_one.return_value = {
            "total_documents": 5,
            "unique_hashes": 5,
            "duplicate_count": 0,
            "total_size": 50000,
            "duplicate_size": 0,
        }

        result = await initialized_shard.get_dedup_stats()

        assert result["duplicate_count"] == 0
        assert result["estimated_wasted_bytes"] == 0

    @pytest.mark.asyncio
    async def test_get_dedup_stats_no_db_returns_empty(self, shard):
        """get_dedup_stats returns empty/zeros when shard is not initialized."""
        result = await shard.get_dedup_stats()

        assert isinstance(result, dict)
        assert result.get("total_documents", 0) == 0

    @pytest.mark.asyncio
    async def test_get_dedup_stats_handles_db_error(self, initialized_shard, mock_database):
        """get_dedup_stats handles database errors gracefully."""
        mock_database.fetch_one.side_effect = Exception("Database error")

        result = await initialized_shard.get_dedup_stats()
        assert isinstance(result, dict)
        assert result.get("total_documents", 0) == 0

    @pytest.mark.asyncio
    async def test_get_dedup_stats_empty_database(self, initialized_shard, mock_database):
        """get_dedup_stats handles empty database."""
        mock_database.fetch_one.return_value = {
            "total_documents": 0,
            "unique_hashes": 0,
            "duplicate_count": 0,
            "total_size": 0,
            "duplicate_size": 0,
        }

        result = await initialized_shard.get_dedup_stats()

        assert result["total_documents"] == 0
        assert result["unique_hashes"] == 0
        assert result["duplicate_count"] == 0
        assert result["estimated_wasted_bytes"] == 0
