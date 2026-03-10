"""
Contradictions Shard - Storage Tests

Tests for the ContradictionStore class.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from arkham_shard_contradictions.models import (
    Contradiction,
    ContradictionChain,
    ContradictionStatus,
    ContradictionType,
    Severity,
)
from arkham_shard_contradictions.storage import ContradictionStore


class TestContradictionStoreCRUD:
    """Tests for basic CRUD operations."""

    @pytest.fixture
    def store(self):
        """Create store with mock database."""
        return ContradictionStore(db_service=None)

    @pytest.fixture
    def sample_contradiction(self):
        """Create sample contradiction."""
        return Contradiction(
            id="c-123",
            doc_a_id="doc-1",
            doc_b_id="doc-2",
            claim_a="Claim A text",
            claim_b="Claim B text",
            contradiction_type=ContradictionType.DIRECT,
            severity=Severity.HIGH,
            status=ContradictionStatus.DETECTED,
            confidence_score=0.9,
        )

    @pytest.mark.asyncio
    async def test_create_contradiction(self, store, sample_contradiction):
        """Test creating a contradiction."""
        result = await store.create(sample_contradiction)

        assert result.id == "c-123"
        assert await store.get("c-123") is not None

    @pytest.mark.asyncio
    async def test_get_contradiction(self, store, sample_contradiction):
        """Test getting a contradiction by ID."""
        await store.create(sample_contradiction)

        result = await store.get("c-123")

        assert result is not None
        assert result.id == "c-123"
        assert result.doc_a_id == "doc-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_contradiction(self, store):
        """Test getting a nonexistent contradiction."""
        result = await store.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_contradiction(self, store, sample_contradiction):
        """Test updating a contradiction."""
        await store.create(sample_contradiction)

        sample_contradiction.status = ContradictionStatus.CONFIRMED
        sample_contradiction.explanation = "Updated explanation"

        result = await store.update(sample_contradiction)

        assert result.status == ContradictionStatus.CONFIRMED
        assert result.explanation == "Updated explanation"

    @pytest.mark.asyncio
    async def test_delete_contradiction(self, store, sample_contradiction):
        """Test deleting a contradiction."""
        await store.create(sample_contradiction)

        result = await store.delete("c-123")

        assert result is True
        assert await store.get("c-123") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store):
        """Test deleting a nonexistent contradiction."""
        result = await store.delete("nonexistent")
        assert result is False


class TestContradictionListing:
    """Tests for listing contradictions."""

    @pytest_asyncio.fixture
    async def populated_store(self):
        """Create store with sample data."""
        store = ContradictionStore(db_service=None)

        # Add sample contradictions
        for i in range(10):
            contradiction = Contradiction(
                id=f"c-{i}",
                doc_a_id=f"doc-a-{i}",
                doc_b_id=f"doc-b-{i}",
                claim_a=f"Claim A {i}",
                claim_b=f"Claim B {i}",
                status=ContradictionStatus.DETECTED if i % 2 == 0 else ContradictionStatus.CONFIRMED,
                severity=Severity.HIGH if i < 3 else Severity.MEDIUM,
            )
            await store.create(contradiction)

        return store

    @pytest.mark.asyncio
    async def test_list_all_basic(self, populated_store):
        """Test basic listing."""
        contradictions, total = await populated_store.list_all()

        assert total == 10
        assert len(contradictions) <= 50  # Default page size

    @pytest.mark.asyncio
    async def test_list_all_pagination(self, populated_store):
        """Test listing with pagination."""
        contradictions, total = await populated_store.list_all(page=1, page_size=3)

        assert total == 10
        assert len(contradictions) == 3

    @pytest.mark.asyncio
    async def test_list_all_filter_by_status(self, populated_store):
        """Test filtering by status."""
        contradictions, total = await populated_store.list_all(status=ContradictionStatus.CONFIRMED)

        assert total == 5  # 5 confirmed (odd indices)
        assert all(c.status == ContradictionStatus.CONFIRMED for c in contradictions)

    @pytest.mark.asyncio
    async def test_list_all_filter_by_severity(self, populated_store):
        """Test filtering by severity."""
        contradictions, total = await populated_store.list_all(severity=Severity.HIGH)

        assert total == 3  # First 3 have HIGH severity
        assert all(c.severity == Severity.HIGH for c in contradictions)


class TestDocumentQueries:
    """Tests for document-specific queries."""

    @pytest_asyncio.fixture
    async def store_with_document_data(self):
        """Create store with document-linked contradictions."""
        store = ContradictionStore(db_service=None)

        # Contradictions involving doc-1
        await store.create(
            Contradiction(
                id="c-1",
                doc_a_id="doc-1",
                doc_b_id="doc-2",
                claim_a="A",
                claim_b="B",
            )
        )
        await store.create(
            Contradiction(
                id="c-2",
                doc_a_id="doc-1",
                doc_b_id="doc-3",
                claim_a="A",
                claim_b="C",
            )
        )
        # Contradiction not involving doc-1
        await store.create(
            Contradiction(
                id="c-3",
                doc_a_id="doc-4",
                doc_b_id="doc-5",
                claim_a="D",
                claim_b="E",
            )
        )

        return store

    @pytest.mark.asyncio
    async def test_get_by_document(self, store_with_document_data):
        """Test getting contradictions by document."""
        contradictions = await store_with_document_data.get_by_document("doc-1")

        assert len(contradictions) == 2
        assert all(c.doc_a_id == "doc-1" or c.doc_b_id == "doc-1" for c in contradictions)

    @pytest.mark.asyncio
    async def test_get_by_document_no_matches(self, store_with_document_data):
        """Test getting contradictions for document with none."""
        contradictions = await store_with_document_data.get_by_document("doc-999")
        assert len(contradictions) == 0

    @pytest.mark.asyncio
    async def test_get_by_status(self, store_with_document_data):
        """Test getting contradictions by status."""
        contradictions = await store_with_document_data.get_by_status(ContradictionStatus.DETECTED)

        assert len(contradictions) == 3  # All are DETECTED by default

    @pytest.mark.asyncio
    async def test_get_by_severity(self, store_with_document_data):
        """Test getting contradictions by severity."""
        contradictions = await store_with_document_data.get_by_severity(Severity.MEDIUM)

        assert len(contradictions) == 3  # All are MEDIUM by default


class TestSearch:
    """Tests for search functionality."""

    @pytest_asyncio.fixture
    async def searchable_store(self):
        """Create store with searchable contradictions."""
        store = ContradictionStore(db_service=None)

        await store.create(
            Contradiction(
                id="c-1",
                doc_a_id="doc-1",
                doc_b_id="doc-2",
                claim_a="The revenue was $1 million",
                claim_b="The revenue was $2 million",
                explanation="Numeric discrepancy in revenue",
                status=ContradictionStatus.CONFIRMED,
                severity=Severity.HIGH,
                confidence_score=0.95,
            )
        )
        await store.create(
            Contradiction(
                id="c-2",
                doc_a_id="doc-3",
                doc_b_id="doc-4",
                claim_a="The meeting was on Monday",
                claim_b="The meeting was on Tuesday",
                explanation="Date contradiction",
                status=ContradictionStatus.DETECTED,
                severity=Severity.MEDIUM,
                confidence_score=0.7,
            )
        )

        return store

    @pytest.mark.asyncio
    async def test_search_by_query(self, searchable_store):
        """Test text search in claims."""
        results = await searchable_store.search(query="revenue")

        assert len(results) == 1
        assert results[0].id == "c-1"

    @pytest.mark.asyncio
    async def test_search_by_document_ids(self, searchable_store):
        """Test filtering by document IDs."""
        results = await searchable_store.search(document_ids=["doc-1", "doc-2"])

        assert len(results) == 1
        assert results[0].id == "c-1"

    @pytest.mark.asyncio
    async def test_search_by_status(self, searchable_store):
        """Test filtering by status."""
        results = await searchable_store.search(status=ContradictionStatus.CONFIRMED)

        assert len(results) == 1
        assert results[0].status == ContradictionStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_search_by_min_confidence(self, searchable_store):
        """Test filtering by minimum confidence."""
        results = await searchable_store.search(min_confidence=0.9)

        assert len(results) == 1
        assert results[0].confidence_score >= 0.9

    @pytest.mark.asyncio
    async def test_search_multiple_filters(self, searchable_store):
        """Test combining multiple filters."""
        results = await searchable_store.search(
            status=ContradictionStatus.DETECTED,
            severity=Severity.MEDIUM,
        )

        assert len(results) == 1
        assert results[0].id == "c-2"


class TestStatistics:
    """Tests for statistics calculation."""

    @pytest_asyncio.fixture
    async def stats_store(self):
        """Create store with data for statistics."""
        store = ContradictionStore(db_service=None)

        # Add varied contradictions for statistics
        statuses = [
            ContradictionStatus.DETECTED,
            ContradictionStatus.CONFIRMED,
            ContradictionStatus.DISMISSED,
            ContradictionStatus.INVESTIGATING,
        ]
        severities = [Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        types = [ContradictionType.DIRECT, ContradictionType.TEMPORAL, ContradictionType.NUMERIC]

        for i in range(12):
            contradiction = Contradiction(
                id=f"c-{i}",
                doc_a_id=f"doc-a-{i}",
                doc_b_id=f"doc-b-{i}",
                claim_a=f"Claim A {i}",
                claim_b=f"Claim B {i}",
                status=statuses[i % 4],
                severity=severities[i % 3],
                contradiction_type=types[i % 3],
            )
            await store.create(contradiction)

        return store

    @pytest.mark.asyncio
    async def test_get_statistics(self, stats_store):
        """Test getting statistics."""
        stats = await stats_store.get_statistics()

        assert stats["total_contradictions"] == 12
        assert "by_status" in stats
        assert "by_severity" in stats
        assert "by_type" in stats
        assert "chains_detected" in stats
        assert "recent_count" in stats

    @pytest.mark.asyncio
    async def test_statistics_by_status_counts(self, stats_store):
        """Test status counts in statistics."""
        stats = await stats_store.get_statistics()

        assert stats["by_status"]["detected"] == 3
        assert stats["by_status"]["confirmed"] == 3
        assert stats["by_status"]["dismissed"] == 3
        assert stats["by_status"]["investigating"] == 3

    @pytest.mark.asyncio
    async def test_statistics_by_severity_counts(self, stats_store):
        """Test severity counts in statistics."""
        stats = await stats_store.get_statistics()

        assert stats["by_severity"]["high"] == 4
        assert stats["by_severity"]["medium"] == 4
        assert stats["by_severity"]["low"] == 4


class TestChainOperations:
    """Tests for contradiction chain operations."""

    @pytest_asyncio.fixture
    async def store(self):
        """Create store for chain testing."""
        store = ContradictionStore(db_service=None)

        # Create contradictions
        await store.create(
            Contradiction(
                id="c-1",
                doc_a_id="doc-1",
                doc_b_id="doc-2",
                claim_a="A",
                claim_b="B",
            )
        )
        await store.create(
            Contradiction(
                id="c-2",
                doc_a_id="doc-2",
                doc_b_id="doc-3",
                claim_a="B",
                claim_b="C",
            )
        )

        return store

    @pytest.mark.asyncio
    async def test_create_chain(self, store):
        """Test creating a contradiction chain."""
        chain = ContradictionChain(
            id="chain-1",
            contradiction_ids=["c-1", "c-2"],
            description="Test chain",
            severity=Severity.HIGH,
        )

        result = await store.create_chain(chain)

        assert result.id == "chain-1"
        assert len(result.contradiction_ids) == 2

    @pytest.mark.asyncio
    async def test_create_chain_updates_contradictions(self, store):
        """Test that creating chain updates contradiction chain_ids."""
        chain = ContradictionChain(
            id="chain-1",
            contradiction_ids=["c-1", "c-2"],
        )

        await store.create_chain(chain)

        # Check contradictions have chain_id set
        c1 = await store.get("c-1")
        c2 = await store.get("c-2")

        assert c1.chain_id == "chain-1"
        assert c2.chain_id == "chain-1"

    @pytest.mark.asyncio
    async def test_get_chain(self, store):
        """Test getting a chain by ID."""
        chain = ContradictionChain(
            id="chain-1",
            contradiction_ids=["c-1", "c-2"],
        )
        await store.create_chain(chain)

        result = await store.get_chain("chain-1")

        assert result is not None
        assert result.id == "chain-1"

    @pytest.mark.asyncio
    async def test_get_chain_not_found(self, store):
        """Test getting a nonexistent chain."""
        result = await store.get_chain("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_chain_contradictions(self, store):
        """Test getting contradictions in a chain."""
        chain = ContradictionChain(
            id="chain-1",
            contradiction_ids=["c-1", "c-2"],
        )
        await store.create_chain(chain)

        contradictions = await store.get_chain_contradictions("chain-1")

        assert len(contradictions) == 2
        assert all(c.chain_id == "chain-1" for c in contradictions)

    @pytest.mark.asyncio
    async def test_list_chains(self, store):
        """Test listing all chains."""
        chain1 = ContradictionChain(id="chain-1", contradiction_ids=["c-1"])
        chain2 = ContradictionChain(id="chain-2", contradiction_ids=["c-2"])

        await store.create_chain(chain1)
        await store.create_chain(chain2)

        chains = await store.list_chains()

        assert len(chains) == 2


class TestAnalystWorkflow:
    """Tests for analyst workflow operations."""

    @pytest_asyncio.fixture
    async def store_with_contradiction(self):
        """Create store with a contradiction."""
        store = ContradictionStore(db_service=None)

        await store.create(
            Contradiction(
                id="c-1",
                doc_a_id="doc-1",
                doc_b_id="doc-2",
                claim_a="Claim A",
                claim_b="Claim B",
                status=ContradictionStatus.DETECTED,
            )
        )

        return store

    @pytest.mark.asyncio
    async def test_add_note(self, store_with_contradiction):
        """Test adding analyst note."""
        result = await store_with_contradiction.add_note(
            "c-1",
            "This needs investigation.",
            analyst_id="analyst@example.com",
        )

        assert result is not None
        assert len(result.analyst_notes) == 1
        assert "investigation" in result.analyst_notes[0]
        assert "analyst@example.com" in result.analyst_notes[0]

    @pytest.mark.asyncio
    async def test_add_note_not_found(self, store_with_contradiction):
        """Test adding note to nonexistent contradiction."""
        result = await store_with_contradiction.add_note(
            "nonexistent",
            "Note",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_update_status(self, store_with_contradiction):
        """Test updating contradiction status."""
        result = await store_with_contradiction.update_status(
            "c-1",
            ContradictionStatus.CONFIRMED,
            analyst_id="analyst@example.com",
        )

        assert result is not None
        assert result.status == ContradictionStatus.CONFIRMED
        assert result.confirmed_by == "analyst@example.com"
        assert result.confirmed_at is not None

    @pytest.mark.asyncio
    async def test_update_status_not_found(self, store_with_contradiction):
        """Test updating status of nonexistent contradiction."""
        result = await store_with_contradiction.update_status(
            "nonexistent",
            ContradictionStatus.CONFIRMED,
        )
        assert result is None


class TestBulkOperations:
    """Tests for bulk operations."""

    @pytest.fixture
    def store(self):
        """Create store for testing."""
        return ContradictionStore(db_service=None)

    @pytest.mark.asyncio
    async def test_bulk_create(self, store):
        """Test bulk creating contradictions."""
        contradictions = [
            Contradiction(id="c-1", doc_a_id="d1", doc_b_id="d2", claim_a="A", claim_b="B"),
            Contradiction(id="c-2", doc_a_id="d3", doc_b_id="d4", claim_a="C", claim_b="D"),
            Contradiction(id="c-3", doc_a_id="d5", doc_b_id="d6", claim_a="E", claim_b="F"),
        ]

        count = await store.bulk_create(contradictions)

        assert count == 3
        assert await store.get("c-1") is not None
        assert await store.get("c-2") is not None
        assert await store.get("c-3") is not None

    @pytest.mark.asyncio
    async def test_bulk_update_status(self, store):
        """Test bulk updating statuses."""
        # Create contradictions
        await store.create(Contradiction(id="c-1", doc_a_id="d1", doc_b_id="d2", claim_a="A", claim_b="B"))
        await store.create(Contradiction(id="c-2", doc_a_id="d3", doc_b_id="d4", claim_a="C", claim_b="D"))

        count = await store.bulk_update_status(
            ["c-1", "c-2"],
            ContradictionStatus.DISMISSED,
        )

        assert count == 2
        assert (await store.get("c-1")).status == ContradictionStatus.DISMISSED
        assert (await store.get("c-2")).status == ContradictionStatus.DISMISSED
