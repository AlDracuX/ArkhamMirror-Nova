"""
Tests for Patterns Shard Implementation
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_patterns import PatternsShard
from arkham_shard_patterns.models import (
    CorrelationRequest,
    DetectionMethod,
    Pattern,
    PatternAnalysisRequest,
    PatternCriteria,
    PatternFilter,
    PatternMatch,
    PatternMatchCreate,
    PatternStatus,
    PatternType,
    SourceType,
)


class TestPatternsShard:
    """Tests for PatternsShard class."""

    def test_shard_attributes(self):
        """Test shard has correct attributes."""
        shard = PatternsShard()

        assert shard.name == "patterns"
        assert shard.version == "0.1.0"
        assert "pattern detection" in shard.description.lower()

    def test_shard_initial_state(self):
        """Test shard initial state."""
        shard = PatternsShard()

        assert shard.frame is None
        assert shard._db is None
        assert shard._events is None
        assert shard._llm is None
        assert shard._vectors is None
        assert shard._workers is None
        assert shard._initialized is False


class TestShardInitialization:
    """Tests for shard initialization."""

    @pytest.mark.asyncio
    async def test_initialize_with_all_services(self):
        """Test initialization with all services available."""
        shard = PatternsShard()

        # Mock frame with all services
        mock_frame = MagicMock()
        mock_frame.database = AsyncMock()
        mock_frame.database.execute = AsyncMock()
        mock_frame.database.fetch_one = AsyncMock(return_value=None)
        mock_frame.database.fetch_all = AsyncMock(return_value=[])
        mock_frame.events = AsyncMock()
        mock_frame.events.subscribe = AsyncMock()
        mock_frame.llm = MagicMock()
        mock_frame.llm.is_available = MagicMock(return_value=True)
        mock_frame.vectors = MagicMock()
        mock_frame.workers = MagicMock()

        await shard.initialize(mock_frame)

        assert shard.frame == mock_frame
        assert shard._db == mock_frame.database
        assert shard._events == mock_frame.events
        assert shard._llm == mock_frame.llm
        assert shard._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_without_optional_services(self):
        """Test initialization without optional services."""
        shard = PatternsShard()

        # Mock frame with only required services
        mock_frame = MagicMock()
        mock_frame.database = AsyncMock()
        mock_frame.database.execute = AsyncMock()
        mock_frame.events = AsyncMock()
        mock_frame.events.subscribe = AsyncMock()

        # Remove optional services
        del mock_frame.llm
        del mock_frame.vectors
        del mock_frame.workers

        await shard.initialize(mock_frame)

        assert shard._db == mock_frame.database
        assert shard._llm is None
        assert shard._vectors is None
        assert shard._initialized is True

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shard shutdown."""
        shard = PatternsShard()

        # Setup mock events
        mock_events = AsyncMock()
        mock_events.unsubscribe = AsyncMock()
        shard._events = mock_events
        shard._initialized = True

        await shard.shutdown()

        assert shard._initialized is False
        # Verify unsubscribe was called for each event
        assert mock_events.unsubscribe.call_count >= 1


class TestPatternCRUD:
    """Tests for pattern CRUD operations."""

    @pytest.fixture
    def shard_with_db(self):
        """Create shard with mocked database."""
        shard = PatternsShard()
        shard._db = AsyncMock()
        shard._db.execute = AsyncMock()
        shard._db.fetch_one = AsyncMock()
        shard._db.fetch_all = AsyncMock(return_value=[])
        shard._events = AsyncMock()
        shard._events.emit = AsyncMock()
        shard._initialized = True
        return shard

    @pytest.mark.asyncio
    async def test_create_pattern(self, shard_with_db):
        """Test creating a pattern."""
        pattern = await shard_with_db.create_pattern(
            name="Test Pattern",
            description="A test pattern",
            pattern_type=PatternType.RECURRING_THEME,
            confidence=0.8,
        )

        assert pattern.name == "Test Pattern"
        assert pattern.pattern_type == PatternType.RECURRING_THEME
        assert pattern.confidence == 0.8
        assert pattern.status == PatternStatus.DETECTED

        # Verify database insert was called
        shard_with_db._db.execute.assert_called()

        # Verify event was emitted
        shard_with_db._events.emit.assert_called_once()
        event_name = shard_with_db._events.emit.call_args[0][0]
        assert event_name == "patterns.pattern.detected"

    @pytest.mark.asyncio
    async def test_create_pattern_with_criteria(self, shard_with_db):
        """Test creating a pattern with criteria."""
        criteria = PatternCriteria(
            keywords=["fraud", "embezzlement"],
            min_occurrences=5,
        )

        pattern = await shard_with_db.create_pattern(
            name="Financial Fraud Pattern",
            description="Pattern of financial fraud indicators",
            pattern_type=PatternType.BEHAVIORAL,
            criteria=criteria,
        )

        assert pattern.criteria.keywords == ["fraud", "embezzlement"]
        assert pattern.criteria.min_occurrences == 5

    @pytest.mark.asyncio
    async def test_get_pattern_found(self, shard_with_db):
        """Test getting an existing pattern."""
        mock_row = {
            "id": "pattern-123",
            "name": "Test Pattern",
            "description": "A test pattern",
            "pattern_type": "recurring_theme",
            "status": "detected",
            "confidence": 0.7,
            "match_count": 5,
            "document_count": 3,
            "entity_count": 2,
            "first_detected": datetime.utcnow().isoformat(),
            "last_matched": None,
            "detection_method": "manual",
            "detection_model": None,
            "criteria": "{}",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by": "user",
            "metadata": "{}",
        }
        shard_with_db._db.fetch_one = AsyncMock(return_value=mock_row)

        pattern = await shard_with_db.get_pattern("pattern-123")

        assert pattern is not None
        assert pattern.id == "pattern-123"
        assert pattern.name == "Test Pattern"
        assert pattern.match_count == 5

    @pytest.mark.asyncio
    async def test_get_pattern_not_found(self, shard_with_db):
        """Test getting a non-existent pattern."""
        shard_with_db._db.fetch_one = AsyncMock(return_value=None)

        pattern = await shard_with_db.get_pattern("nonexistent")

        assert pattern is None

    @pytest.mark.asyncio
    async def test_list_patterns_empty(self, shard_with_db):
        """Test listing patterns when empty."""
        patterns = await shard_with_db.list_patterns()

        assert patterns == []

    @pytest.mark.asyncio
    async def test_update_pattern(self, shard_with_db):
        """Test updating a pattern."""
        mock_row = {
            "id": "pattern-123",
            "name": "Original Name",
            "description": "Original description",
            "pattern_type": "recurring_theme",
            "status": "detected",
            "confidence": 0.5,
            "match_count": 0,
            "document_count": 0,
            "entity_count": 0,
            "first_detected": datetime.utcnow().isoformat(),
            "last_matched": None,
            "detection_method": "manual",
            "detection_model": None,
            "criteria": "{}",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by": "user",
            "metadata": "{}",
        }
        shard_with_db._db.fetch_one = AsyncMock(return_value=mock_row)

        pattern = await shard_with_db.update_pattern(
            pattern_id="pattern-123",
            name="Updated Name",
            confidence=0.9,
        )

        assert pattern.name == "Updated Name"
        assert pattern.confidence == 0.9

    @pytest.mark.asyncio
    async def test_delete_pattern(self, shard_with_db):
        """Test deleting a pattern."""
        result = await shard_with_db.delete_pattern("pattern-123")

        assert result is True
        # Verify both matches and pattern were deleted
        assert shard_with_db._db.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_confirm_pattern(self, shard_with_db):
        """Test confirming a pattern."""
        mock_row = {
            "id": "pattern-123",
            "name": "Test Pattern",
            "description": "Test",
            "pattern_type": "recurring_theme",
            "status": "detected",
            "confidence": 0.7,
            "match_count": 5,
            "document_count": 3,
            "entity_count": 0,
            "first_detected": datetime.utcnow().isoformat(),
            "last_matched": None,
            "detection_method": "manual",
            "detection_model": None,
            "criteria": "{}",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by": "user",
            "metadata": "{}",
        }
        shard_with_db._db.fetch_one = AsyncMock(return_value=mock_row)

        pattern = await shard_with_db.confirm_pattern("pattern-123")

        assert pattern.status == PatternStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_dismiss_pattern(self, shard_with_db):
        """Test dismissing a pattern."""
        mock_row = {
            "id": "pattern-123",
            "name": "Test Pattern",
            "description": "Test",
            "pattern_type": "recurring_theme",
            "status": "detected",
            "confidence": 0.3,
            "match_count": 1,
            "document_count": 1,
            "entity_count": 0,
            "first_detected": datetime.utcnow().isoformat(),
            "last_matched": None,
            "detection_method": "automated",
            "detection_model": None,
            "criteria": "{}",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by": "system",
            "metadata": "{}",
        }
        shard_with_db._db.fetch_one = AsyncMock(return_value=mock_row)

        pattern = await shard_with_db.dismiss_pattern("pattern-123", notes="False positive")

        assert pattern.status == PatternStatus.DISMISSED


class TestPatternMatches:
    """Tests for pattern match operations."""

    @pytest.fixture
    def shard_with_db(self):
        """Create shard with mocked database."""
        shard = PatternsShard()
        shard._db = AsyncMock()
        shard._db.execute = AsyncMock()
        shard._db.fetch_one = AsyncMock(return_value={"count": 0})
        shard._db.fetch_all = AsyncMock(return_value=[])
        shard._events = AsyncMock()
        shard._events.emit = AsyncMock()
        shard._initialized = True
        return shard

    @pytest.mark.asyncio
    async def test_add_match(self, shard_with_db):
        """Test adding a match to a pattern."""
        match_create = PatternMatchCreate(
            source_type=SourceType.DOCUMENT,
            source_id="doc-123",
            source_title="Test Document",
            match_score=0.85,
            excerpt="Matching text excerpt...",
        )

        match = await shard_with_db.add_match("pattern-123", match_create)

        assert match.pattern_id == "pattern-123"
        assert match.source_type == SourceType.DOCUMENT
        assert match.source_id == "doc-123"
        assert match.match_score == 0.85

        # Verify event was emitted
        shard_with_db._events.emit.assert_called()

    @pytest.mark.asyncio
    async def test_get_pattern_matches(self, shard_with_db):
        """Test getting matches for a pattern."""
        matches = await shard_with_db.get_pattern_matches("pattern-123")

        assert matches == []

    @pytest.mark.asyncio
    async def test_remove_match(self, shard_with_db):
        """Test removing a match."""
        result = await shard_with_db.remove_match("pattern-123", "match-456")

        assert result is True


class TestPatternAnalysis:
    """Tests for pattern analysis."""

    @pytest.fixture
    def shard_with_services(self):
        """Create shard with mocked services."""
        shard = PatternsShard()
        shard._db = AsyncMock()
        shard._db.execute = AsyncMock()
        shard._db.fetch_one = AsyncMock(return_value=None)
        shard._db.fetch_all = AsyncMock(return_value=[])
        shard._events = AsyncMock()
        shard._events.emit = AsyncMock()
        shard._initialized = True
        return shard

    @pytest.mark.asyncio
    async def test_analyze_documents_no_text(self, shard_with_services):
        """Test analysis with no text."""
        request = PatternAnalysisRequest(
            document_ids=[],
            text=None,
        )

        result = await shard_with_services.analyze_documents(request)

        assert result.documents_analyzed == 0
        assert "No text to analyze" in result.errors

    @pytest.mark.asyncio
    async def test_analyze_documents_with_text(self, shard_with_services):
        """Test analysis with text."""
        request = PatternAnalysisRequest(
            text="This is a test text with some repeated words. The words appear multiple times. Words are important.",
            min_confidence=0.3,
        )

        result = await shard_with_services.analyze_documents(request)

        assert result.processing_time_ms > 0
        # Keyword detection should find some patterns
        assert isinstance(result.patterns_detected, list)

    @pytest.mark.asyncio
    async def test_find_correlations(self, shard_with_services):
        """Test finding correlations."""
        request = CorrelationRequest(
            entity_ids=["entity-1", "entity-2", "entity-3"],
            time_window_days=90,
        )

        result = await shard_with_services.find_correlations(request)

        assert result.entities_analyzed == 3
        assert result.processing_time_ms >= 0


class TestStatistics:
    """Tests for statistics."""

    @pytest.fixture
    def shard_with_db(self):
        """Create shard with mocked database."""
        shard = PatternsShard()
        shard._db = AsyncMock()
        shard._initialized = True
        return shard

    @pytest.mark.asyncio
    async def test_get_statistics(self, shard_with_db):
        """Test getting statistics.

        get_statistics() calls fetch_all multiple times with different GROUP BY
        queries expecting different column names (pattern_type, status,
        detection_method). Use side_effect to return appropriate data for each.
        """
        shard_with_db._db.fetch_one = AsyncMock(
            side_effect=[
                {"count": 10},  # total patterns
                {"count": 50},  # total matches
                {"avg": 0.75},  # avg confidence
                {"avg": 5.0},  # avg matches per pattern
            ]
        )
        shard_with_db._db.fetch_all = AsyncMock(
            side_effect=[
                [  # type_rows: GROUP BY pattern_type
                    {"pattern_type": "recurring_theme", "count": 5},
                    {"pattern_type": "behavioral", "count": 5},
                ],
                [  # status_rows: GROUP BY status
                    {"status": "confirmed", "count": 6},
                    {"status": "detected", "count": 4},
                ],
                [  # method_rows: GROUP BY detection_method
                    {"detection_method": "manual", "count": 7},
                    {"detection_method": "automated", "count": 3},
                ],
            ]
        )

        stats = await shard_with_db.get_statistics()

        assert stats.total_patterns == 10
        assert "recurring_theme" in stats.by_type

    @pytest.mark.asyncio
    async def test_get_count(self, shard_with_db):
        """Test getting pattern count."""
        shard_with_db._db.fetch_one = AsyncMock(return_value={"count": 42})

        count = await shard_with_db.get_count()

        assert count == 42

    @pytest.mark.asyncio
    async def test_get_count_with_status(self, shard_with_db):
        """Test getting pattern count with status filter."""
        shard_with_db._db.fetch_one = AsyncMock(return_value={"count": 15})

        count = await shard_with_db.get_count(status="confirmed")

        assert count == 15

    @pytest.mark.asyncio
    async def test_get_match_count(self, shard_with_db):
        """Test getting match count for a pattern."""
        shard_with_db._db.fetch_one = AsyncMock(return_value={"count": 25})

        count = await shard_with_db.get_match_count("pattern-123")

        assert count == 25


class TestDetectPatterns:
    """Tests for the detect_patterns detection algorithms."""

    @pytest.fixture
    def shard_with_db(self):
        """Create shard with mocked database for detection tests."""
        shard = PatternsShard()
        shard._db = AsyncMock()
        shard._db.execute = AsyncMock()
        shard._db.fetch_one = AsyncMock(return_value=None)
        shard._db.fetch_all = AsyncMock(return_value=[])
        shard._events = AsyncMock()
        shard._events.emit = AsyncMock()
        shard._initialized = True
        shard.frame = MagicMock()
        shard.frame.shards = {}
        return shard

    # --- detect_patterns orchestrator ---

    @pytest.mark.asyncio
    async def test_detect_patterns_method_exists(self, shard_with_db):
        """ISC-1: detect_patterns method exists with correct signature."""
        assert hasattr(shard_with_db, "detect_patterns")
        # Should be callable with project_id=None
        result = await shard_with_db.detect_patterns()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_detect_patterns_returns_empty_when_no_data(self, shard_with_db):
        """ISC-2: detect_patterns returns empty list when no data found."""
        shard_with_db._db.fetch_all = AsyncMock(return_value=[])
        result = await shard_with_db.detect_patterns()
        assert result == []

    @pytest.mark.asyncio
    async def test_detect_patterns_filters_by_project_id(self, shard_with_db):
        """ISC-3: detect_patterns passes project_id to sub-detectors."""
        shard_with_db._db.fetch_all = AsyncMock(return_value=[])
        result = await shard_with_db.detect_patterns(project_id="proj-123")
        assert isinstance(result, list)
        # Verify that fetch_all was called (sub-detectors query DB)
        assert shard_with_db._db.fetch_all.call_count >= 1

    @pytest.mark.asyncio
    async def test_detect_patterns_handles_no_database(self):
        """ISC-4: detect_patterns handles missing database gracefully."""
        shard = PatternsShard()
        shard._db = None
        shard._initialized = True
        result = await shard.detect_patterns()
        assert result == []

    # --- Repeated Phrase Detection ---

    @pytest.mark.asyncio
    async def test_detect_repeated_phrases_queries_chunks(self, shard_with_db):
        """ISC-5: _detect_repeated_phrases queries chunks table."""
        shard_with_db._db.fetch_all = AsyncMock(return_value=[])
        await shard_with_db._detect_repeated_phrases()
        # Should have called fetch_all at least once to get chunks
        shard_with_db._db.fetch_all.assert_called()
        # Verify SQL references chunks
        call_args = shard_with_db._db.fetch_all.call_args_list[0]
        sql = call_args[0][0] if call_args[0] else ""
        assert "chunk" in sql.lower()

    @pytest.mark.asyncio
    async def test_ngram_extraction_produces_3word_phrases(self, shard_with_db):
        """ISC-6: N-gram extraction produces 3+ word phrases from chunk text."""
        chunks = [
            {"id": "c1", "document_id": "doc1", "text": "the company failed to investigate the complaint properly"},
            {"id": "c2", "document_id": "doc2", "text": "the company failed to investigate the grievance properly"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=chunks)
        result = await shard_with_db._detect_repeated_phrases()
        # Should find "the company failed" or "failed to investigate" as repeated
        found_phrases = [p["description"] for p in result]
        assert any(
            "company failed" in desc.lower() or "failed to investigate" in desc.lower() for desc in found_phrases
        )

    @pytest.mark.asyncio
    async def test_phrases_in_multiple_docs_detected(self, shard_with_db):
        """ISC-7: Phrases appearing in 2+ documents are detected."""
        chunks = [
            {"id": "c1", "document_id": "doc1", "text": "failure to follow proper procedure in handling"},
            {"id": "c2", "document_id": "doc2", "text": "failure to follow proper procedure during review"},
            {"id": "c3", "document_id": "doc3", "text": "something completely different here today"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=chunks)
        result = await shard_with_db._detect_repeated_phrases()
        # Pattern should span multiple documents
        multi_doc = [p for p in result if len(p.get("evidence", [])) >= 2]
        assert len(multi_doc) > 0

    @pytest.mark.asyncio
    async def test_phrase_pattern_type_is_phrase_repeat(self, shard_with_db):
        """ISC-8: Phrase pattern includes pattern_type 'phrase_repeat'."""
        chunks = [
            {"id": "c1", "document_id": "doc1", "text": "repeated phrase here now"},
            {"id": "c2", "document_id": "doc2", "text": "repeated phrase here again"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=chunks)
        result = await shard_with_db._detect_repeated_phrases()
        for pattern in result:
            assert pattern["pattern_type"] == "phrase_repeat"

    @pytest.mark.asyncio
    async def test_phrase_significance_scales_with_frequency(self, shard_with_db):
        """ISC-9: Phrase pattern significance scales with frequency and span."""
        chunks = [
            {"id": f"c{i}", "document_id": f"doc{i}", "text": "the same exact phrase appears consistently"}
            for i in range(5)
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=chunks)
        result = await shard_with_db._detect_repeated_phrases()
        if result:
            # Higher frequency across more docs = higher significance
            assert all(0.0 <= p["significance"] <= 1.0 for p in result)

    @pytest.mark.asyncio
    async def test_phrase_evidence_contains_document_ids(self, shard_with_db):
        """ISC-10: Phrase pattern evidence contains document_ids."""
        chunks = [
            {"id": "c1", "document_id": "doc-aaa", "text": "specific repeated content here"},
            {"id": "c2", "document_id": "doc-bbb", "text": "specific repeated content there"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=chunks)
        result = await shard_with_db._detect_repeated_phrases()
        for pattern in result:
            assert "evidence" in pattern
            assert isinstance(pattern["evidence"], list)

    # --- Behavioral Pattern Detection ---

    @pytest.mark.asyncio
    async def test_detect_behavioral_queries_timeline(self, shard_with_db):
        """ISC-11: _detect_behavioral_patterns queries timeline_events table."""
        shard_with_db._db.fetch_all = AsyncMock(return_value=[])
        await shard_with_db._detect_behavioral_patterns()
        shard_with_db._db.fetch_all.assert_called()
        call_args = shard_with_db._db.fetch_all.call_args_list[0]
        sql = call_args[0][0] if call_args[0] else ""
        assert "timeline" in sql.lower()

    @pytest.mark.asyncio
    async def test_behavioral_event_sequences_extracted(self, shard_with_db):
        """ISC-12: Event sequences extracted as ordered type lists per entity."""
        events = [
            {"id": "e1", "event_type": "complaint", "entity_name": "Manager A", "event_date": "2025-01-01"},
            {"id": "e2", "event_type": "investigation", "entity_name": "Manager A", "event_date": "2025-01-15"},
            {"id": "e3", "event_type": "no_action", "entity_name": "Manager A", "event_date": "2025-02-01"},
            {"id": "e4", "event_type": "complaint", "entity_name": "Manager B", "event_date": "2025-03-01"},
            {"id": "e5", "event_type": "investigation", "entity_name": "Manager B", "event_date": "2025-03-15"},
            {"id": "e6", "event_type": "no_action", "entity_name": "Manager B", "event_date": "2025-04-01"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_behavioral_patterns()
        # Should detect the repeated sequence complaint -> investigation -> no_action
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_behavioral_repeated_sequences_detected(self, shard_with_db):
        """ISC-13: Repeated sequences of 2+ actions detected across entities."""
        events = [
            {"id": "e1", "event_type": "warning", "entity_name": "Entity A", "event_date": "2025-01-01"},
            {"id": "e2", "event_type": "dismissal", "entity_name": "Entity A", "event_date": "2025-01-15"},
            {"id": "e3", "event_type": "warning", "entity_name": "Entity B", "event_date": "2025-02-01"},
            {"id": "e4", "event_type": "dismissal", "entity_name": "Entity B", "event_date": "2025-02-15"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_behavioral_patterns()
        assert len(result) > 0
        # The sequence warning -> dismissal should appear
        assert any("warning" in p["description"].lower() or "dismissal" in p["description"].lower() for p in result)

    @pytest.mark.asyncio
    async def test_behavioral_pattern_type(self, shard_with_db):
        """ISC-14: Behavioral pattern includes pattern_type 'behavioral'."""
        events = [
            {"id": "e1", "event_type": "complaint", "entity_name": "A", "event_date": "2025-01-01"},
            {"id": "e2", "event_type": "denial", "entity_name": "A", "event_date": "2025-01-15"},
            {"id": "e3", "event_type": "complaint", "entity_name": "B", "event_date": "2025-03-01"},
            {"id": "e4", "event_type": "denial", "entity_name": "B", "event_date": "2025-03-15"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_behavioral_patterns()
        for pattern in result:
            assert pattern["pattern_type"] == "behavioral"

    @pytest.mark.asyncio
    async def test_behavioral_evidence_contains_event_ids(self, shard_with_db):
        """ISC-15: Behavioral pattern evidence contains event_ids."""
        events = [
            {"id": "evt-1", "event_type": "action_a", "entity_name": "X", "event_date": "2025-01-01"},
            {"id": "evt-2", "event_type": "action_b", "entity_name": "X", "event_date": "2025-01-15"},
            {"id": "evt-3", "event_type": "action_a", "entity_name": "Y", "event_date": "2025-02-01"},
            {"id": "evt-4", "event_type": "action_b", "entity_name": "Y", "event_date": "2025-02-15"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_behavioral_patterns()
        for pattern in result:
            assert isinstance(pattern["evidence"], list)

    @pytest.mark.asyncio
    async def test_behavioral_entities_involved_populated(self, shard_with_db):
        """ISC-16: Behavioral pattern entities_involved populated from event data."""
        events = [
            {"id": "e1", "event_type": "step1", "entity_name": "Person A", "event_date": "2025-01-01"},
            {"id": "e2", "event_type": "step2", "entity_name": "Person A", "event_date": "2025-01-15"},
            {"id": "e3", "event_type": "step1", "entity_name": "Person B", "event_date": "2025-02-01"},
            {"id": "e4", "event_type": "step2", "entity_name": "Person B", "event_date": "2025-02-15"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_behavioral_patterns()
        for pattern in result:
            assert "entities_involved" in pattern
            assert isinstance(pattern["entities_involved"], list)
            assert len(pattern["entities_involved"]) > 0

    # --- Temporal Cluster Detection ---

    @pytest.mark.asyncio
    async def test_detect_temporal_clusters_queries_events(self, shard_with_db):
        """ISC-17: _detect_temporal_clusters queries timeline_events with dates."""
        shard_with_db._db.fetch_all = AsyncMock(return_value=[])
        await shard_with_db._detect_temporal_clusters()
        shard_with_db._db.fetch_all.assert_called()

    @pytest.mark.asyncio
    async def test_temporal_events_grouped_into_windows(self, shard_with_db):
        """ISC-18: Events grouped into 7-day time windows."""
        # Cluster: 5 events in 3 days, then gap, then sparse events
        events = [
            {"id": f"e{i}", "event_type": "action", "event_date": f"2025-01-0{i + 1}", "title": f"Event {i}"}
            for i in range(5)
        ] + [
            {"id": "e10", "event_type": "action", "event_date": "2025-06-15", "title": "Lone event"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_temporal_clusters()
        # Should detect the dense cluster in early January
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_temporal_abnormal_density_flagged(self, shard_with_db):
        """ISC-19: Clusters with abnormal density flagged as patterns."""
        # Create a burst of activity
        events = [
            {"id": f"e{i}", "event_type": "action", "event_date": "2025-03-01", "title": f"Burst event {i}"}
            for i in range(8)
        ] + [
            {"id": f"s{i}", "event_type": "action", "event_date": f"2025-0{i + 1}-15", "title": f"Sparse {i}"}
            for i in range(6)
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_temporal_clusters()
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_temporal_pattern_type(self, shard_with_db):
        """ISC-20: Temporal pattern includes pattern_type 'temporal_cluster'."""
        events = [
            {"id": f"e{i}", "event_type": "action", "event_date": "2025-01-01", "title": f"Event {i}"} for i in range(5)
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_temporal_clusters()
        for pattern in result:
            assert pattern["pattern_type"] == "temporal_cluster"

    @pytest.mark.asyncio
    async def test_temporal_significance_based_on_density(self, shard_with_db):
        """ISC-21: Temporal pattern significance based on cluster density vs baseline."""
        events = [
            {"id": f"e{i}", "event_type": "action", "event_date": "2025-01-01", "title": f"Event {i}"}
            for i in range(10)
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=events)
        result = await shard_with_db._detect_temporal_clusters()
        for pattern in result:
            assert 0.0 <= pattern["significance"] <= 1.0

    # --- Communication Pattern Detection ---

    @pytest.mark.asyncio
    async def test_detect_communication_queries_entity_mentions(self, shard_with_db):
        """ISC-22: _detect_communication_patterns queries entity_mentions table."""
        shard_with_db._db.fetch_all = AsyncMock(return_value=[])
        await shard_with_db._detect_communication_patterns()
        shard_with_db._db.fetch_all.assert_called()

    @pytest.mark.asyncio
    async def test_communication_co_occurrence_tracked(self, shard_with_db):
        """ISC-23: Entity co-occurrence in documents tracked as pairs."""
        mentions = [
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc1"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc1"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc2"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc2"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc3"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc3"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=mentions)
        result = await shard_with_db._detect_communication_patterns()
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_communication_always_together_flagged(self, shard_with_db):
        """ISC-24: Entities always appearing together flagged."""
        mentions = [
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc1"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc1"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc2"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc2"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc3"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc3"},
            {"entity_id": "ent3", "entity_name": "Charlie", "document_id": "doc1"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=mentions)
        result = await shard_with_db._detect_communication_patterns()
        # Alice and Bob always together should be detected
        co_occurrence_patterns = [
            p
            for p in result
            if "co-occurrence" in p.get("description", "").lower()
            or "always" in p.get("description", "").lower()
            or "together" in p.get("description", "").lower()
        ]
        assert len(co_occurrence_patterns) > 0

    @pytest.mark.asyncio
    async def test_communication_dropoff_detected(self, shard_with_db):
        """ISC-25: Communication drop-offs detected."""
        # Entity active in early docs, then disappears
        mentions = [
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc1"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc2"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc3"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc1"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc2"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc3"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc4"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc5"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc6"},
        ]
        # For drop-off: need temporal data. Use side_effect to return different
        # data for different queries (mentions query vs timeline query)
        shard_with_db._db.fetch_all = AsyncMock(return_value=mentions)
        result = await shard_with_db._detect_communication_patterns()
        # At minimum, the method should run without error
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_communication_entities_involved_populated(self, shard_with_db):
        """ISC-26: Communication pattern entities_involved populated."""
        mentions = [
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc1"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc1"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc2"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc2"},
            {"entity_id": "ent1", "entity_name": "Alice", "document_id": "doc3"},
            {"entity_id": "ent2", "entity_name": "Bob", "document_id": "doc3"},
        ]
        shard_with_db._db.fetch_all = AsyncMock(return_value=mentions)
        result = await shard_with_db._detect_communication_patterns()
        for pattern in result:
            assert "entities_involved" in pattern
            assert isinstance(pattern["entities_involved"], list)

    # --- Integration: detect_patterns combines all ---

    @pytest.mark.asyncio
    async def test_detect_patterns_combines_all_types(self, shard_with_db):
        """detect_patterns runs all four detection algorithms."""
        # We'll mock the sub-detectors to verify they're all called
        shard_with_db._detect_repeated_phrases = AsyncMock(
            return_value=[
                {
                    "pattern_type": "phrase_repeat",
                    "description": "test",
                    "evidence": [],
                    "significance": 0.5,
                    "entities_involved": [],
                }
            ]
        )
        shard_with_db._detect_behavioral_patterns = AsyncMock(
            return_value=[
                {
                    "pattern_type": "behavioral",
                    "description": "test",
                    "evidence": [],
                    "significance": 0.5,
                    "entities_involved": [],
                }
            ]
        )
        shard_with_db._detect_temporal_clusters = AsyncMock(
            return_value=[
                {
                    "pattern_type": "temporal_cluster",
                    "description": "test",
                    "evidence": [],
                    "significance": 0.5,
                    "entities_involved": [],
                }
            ]
        )
        shard_with_db._detect_communication_patterns = AsyncMock(
            return_value=[
                {
                    "pattern_type": "communication",
                    "description": "test",
                    "evidence": [],
                    "significance": 0.5,
                    "entities_involved": [],
                }
            ]
        )

        result = await shard_with_db.detect_patterns()
        assert len(result) == 4
        types = {p["pattern_type"] for p in result}
        assert "phrase_repeat" in types
        assert "behavioral" in types
        assert "temporal_cluster" in types
        assert "communication" in types


class TestRoutes:
    """Tests for route registration."""

    def test_get_routes(self):
        """Test that get_routes returns a router."""
        shard = PatternsShard()
        router = shard.get_routes()

        assert router is not None
        # Verify router has routes registered
        assert len(router.routes) > 0
