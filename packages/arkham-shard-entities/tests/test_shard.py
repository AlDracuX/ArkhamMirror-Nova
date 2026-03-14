"""Tests for EntitiesShard implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_entities.shard import EntitiesShard


@pytest.fixture
def mock_frame():
    """Create a mock ArkhamFrame for testing."""
    frame = MagicMock()

    # Mock database service
    frame.db = AsyncMock()
    frame.db.execute = AsyncMock()

    # Mock event bus
    frame.events = AsyncMock()
    frame.events.subscribe = AsyncMock()
    frame.events.unsubscribe = AsyncMock()
    frame.events.emit = AsyncMock()

    # Mock vectors service (optional)
    frame.vectors = MagicMock()

    # Mock entity service (optional)
    frame.entities = MagicMock()

    # Mock get_service method
    def get_service(name):
        services = {
            "database": frame.db,
            "events": frame.events,
            "vectors": frame.vectors,
            "entities": frame.entities,
        }
        return services.get(name)

    frame.get_service = MagicMock(side_effect=get_service)

    return frame


@pytest.fixture
def shard():
    """Create an EntitiesShard instance."""
    return EntitiesShard()


class TestEntitiesShardInit:
    """Test shard initialization."""

    def test_shard_creation(self, shard):
        """Test basic shard creation."""
        assert shard.name == "entities"
        assert shard.version == "0.1.0"
        assert shard.description == "Entity browser with merge/link/edit capabilities for entity resolution workflow"

    def test_shard_initial_state(self, shard):
        """Test shard initial state before initialization."""
        assert shard._frame is None
        assert shard._db is None
        assert shard._event_bus is None
        assert shard._vectors_service is None
        assert shard._entity_service is None


class TestEntitiesShardInitialization:
    """Test shard initialization with Frame."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, shard, mock_frame):
        """Test successful initialization with all services."""
        await shard.initialize(mock_frame)

        # Check frame reference
        assert shard._frame == mock_frame

        # Check required services
        assert shard._db == mock_frame.db
        assert shard._event_bus == mock_frame.events

        # Check optional services
        assert shard._vectors_service == mock_frame.vectors
        assert shard._entity_service == mock_frame.entities

        # Verify get_service was called
        assert mock_frame.get_service.call_count >= 2

    @pytest.mark.asyncio
    async def test_initialize_without_database_fails(self, shard):
        """Test initialization fails without database service."""
        frame = MagicMock()
        frame.get_service = MagicMock(return_value=None)

        with pytest.raises(RuntimeError, match="Database service required"):
            await shard.initialize(frame)

    @pytest.mark.asyncio
    async def test_initialize_without_optional_services(self, shard, mock_frame):
        """Test initialization succeeds without optional services."""
        # Remove optional services
        mock_frame.vectors = None
        mock_frame.entities = None

        def get_service(name):
            if name == "database":
                return mock_frame.db
            elif name == "events":
                return mock_frame.events
            return None

        mock_frame.get_service = MagicMock(side_effect=get_service)

        await shard.initialize(mock_frame)

        # Should initialize successfully
        assert shard._db == mock_frame.db
        assert shard._vectors_service is None
        assert shard._entity_service is None


class TestEntitiesShardShutdown:
    """Test shard shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_clears_services(self, shard, mock_frame):
        """Test shutdown clears service references."""
        # Initialize first
        await shard.initialize(mock_frame)

        # Verify services are set
        assert shard._db is not None
        assert shard._event_bus is not None

        # Shutdown
        await shard.shutdown()

        # Verify services are cleared
        assert shard._db is None
        assert shard._event_bus is None
        assert shard._vectors_service is None
        assert shard._entity_service is None

    @pytest.mark.asyncio
    async def test_shutdown_without_initialize(self, shard):
        """Test shutdown works even without initialization."""
        # Should not raise error
        await shard.shutdown()

        assert shard._db is None
        assert shard._event_bus is None


class TestEntitiesShardRoutes:
    """Test shard routes."""

    def test_get_routes(self, shard):
        """Test get_routes returns router."""
        router = shard.get_routes()
        assert router is not None
        assert hasattr(router, "prefix")
        assert router.prefix == "/api/entities"


class TestEntitiesShardPublicMethods:
    """Test shard public methods."""

    @pytest.mark.asyncio
    async def test_get_entity_not_initialized(self, shard):
        """Test get_entity fails if shard not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await shard.get_entity("test-id")

    @pytest.mark.asyncio
    async def test_get_entity_stub(self, shard, mock_frame):
        """Test get_entity stub implementation."""
        await shard.initialize(mock_frame)

        # Mock db to return None (entity not found)
        shard._db.fetch_one = AsyncMock(return_value=None)

        result = await shard.get_entity("test-id")

        # Returns None when not found
        assert result is None

    @pytest.mark.asyncio
    async def test_get_entity_mentions_not_initialized(self, shard):
        """Test get_entity_mentions fails if shard not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await shard.get_entity_mentions("test-id")

    @pytest.mark.asyncio
    async def test_get_entity_mentions_stub(self, shard, mock_frame):
        """Test get_entity_mentions implementation."""
        await shard.initialize(mock_frame)

        # Mock db to return empty list
        shard._db.fetch_all = AsyncMock(return_value=[])

        result = await shard.get_entity_mentions("test-id")

        # Returns empty list
        assert result == []

    @pytest.mark.asyncio
    async def test_merge_entities_not_initialized(self, shard):
        """Test merge_entities fails if shard not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await shard.merge_entities(
                source_id="id2",
                target_id="id1",
            )

    @pytest.mark.asyncio
    async def test_merge_entities_stub(self, shard, mock_frame):
        """Test merge_entities implementation."""
        await shard.initialize(mock_frame)

        # Mock the entity service link_to_canonical
        shard._entity_service = AsyncMock()
        shard._entity_service.link_to_canonical = AsyncMock()

        # Mock get_entity to return a mock entity for the canonical
        mock_entity = MagicMock()
        mock_entity.id = "id1"
        mock_entity.name = "John Doe"
        mock_entity.entity_type = MagicMock()
        mock_entity.entity_type.value = "PERSON"
        shard._db.fetch_one = AsyncMock(
            return_value={
                "id": "id1",
                "text": "John Doe",
                "entity_type": "PERSON",
                "canonical_id": None,
                "metadata": "{}",
                "created_at": "2024-01-01T00:00:00",
            }
        )

        result = await shard.merge_entities(
            source_id="id2",
            target_id="id1",
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_create_relationship_not_initialized(self, shard):
        """Test create_relationship fails if shard not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await shard.create_relationship(
                source_id="person-id",
                target_id="org-id",
                relationship_type="WORKS_FOR",
            )

    @pytest.mark.asyncio
    async def test_create_relationship_stub(self, shard, mock_frame):
        """Test create_relationship implementation."""
        await shard.initialize(mock_frame)

        result = await shard.create_relationship(
            source_id="person-id",
            target_id="org-id",
            relationship_type="WORKS_FOR",
            confidence=0.9,
            metadata={"position": "Engineer"},
        )

        # Returns dict with relationship data
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_create_relationship_default_params(self, shard, mock_frame):
        """Test create_relationship with default parameters."""
        await shard.initialize(mock_frame)

        result = await shard.create_relationship(
            source_id="person-id",
            target_id="org-id",
            relationship_type="WORKS_FOR",
        )

        # Should work with minimal params
        assert isinstance(result, dict)


class TestEntitiesShardEventHandlers:
    """Test shard event handlers."""

    @pytest.mark.asyncio
    async def test_on_entity_extracted_handler(self, shard, mock_frame):
        """Test _on_entity_extracted event handler."""
        await shard.initialize(mock_frame)

        # Mock db returns for the handler
        shard._db.fetch_one = AsyncMock(return_value=None)

        event_data = {
            "document_id": "doc-123",
            "entities": [
                {
                    "text": "John Doe",
                    "entity_type": "PERSON",
                    "confidence": 0.95,
                    "start_offset": 0,
                    "end_offset": 8,
                }
            ],
        }

        # Should not raise error
        await shard._on_entity_extracted(event_data)

    @pytest.mark.asyncio
    async def test_on_relationships_extracted_handler(self, shard, mock_frame):
        """Test _on_relationships_extracted event handler."""
        await shard.initialize(mock_frame)

        event_data = {
            "document_id": "doc-123",
            "relationships": [],
        }

        # Should not raise error
        await shard._on_relationships_extracted(event_data)


class TestEntitiesShardSchema:
    """Test database schema creation."""

    @pytest.mark.asyncio
    async def test_create_schema_called_on_init(self, shard, mock_frame):
        """Test _create_schema is called during initialization."""
        with patch.object(shard, "_create_schema", new_callable=AsyncMock) as mock_create:
            await shard.initialize(mock_frame)
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_schema_stub(self, shard, mock_frame):
        """Test _create_schema stub implementation."""
        await shard.initialize(mock_frame)

        # Should not raise error
        await shard._create_schema()


class TestEntitiesShardManifest:
    """Test shard manifest loading."""

    def test_shard_has_manifest(self, shard):
        """Test shard has manifest loaded."""
        # The manifest is auto-loaded in __init__ via super().__init__()
        assert hasattr(shard, "manifest")
        assert shard.manifest is not None

    def test_manifest_metadata(self, shard):
        """Test manifest has expected metadata."""
        assert shard.name == "entities"
        assert shard.version == "0.1.0"
        assert len(shard.description) > 0


class TestFindMergeCandidates:
    """Test find_merge_candidates method for string-similarity deduplication."""

    @pytest.mark.asyncio
    async def test_find_merge_candidates_not_initialized(self, shard):
        """Test find_merge_candidates fails if shard not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await shard.find_merge_candidates()

    @pytest.mark.asyncio
    async def test_find_merge_candidates_empty_db(self, shard, mock_frame):
        """Test find_merge_candidates returns empty list when no entities exist."""
        await shard.initialize(mock_frame)
        shard._db.fetch_all = AsyncMock(return_value=[])

        result = await shard.find_merge_candidates()
        assert result == []

    @pytest.mark.asyncio
    async def test_find_merge_candidates_sequence_match(self, shard, mock_frame):
        """Test finds similar names via SequenceMatcher (e.g., 'Stuart Griffiths' vs 'Stuart Griffith')."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Stuart Griffiths",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "Stuart Griffith",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 3,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(threshold=0.85)
        assert len(result) >= 1
        pair = result[0]
        assert pair["similarity_score"] >= 0.85
        assert pair["reason"] != ""
        # Both entity names should appear in the pair
        names = {pair["entity_a"]["name"], pair["entity_b"]["name"]}
        assert "Stuart Griffiths" in names
        assert "Stuart Griffith" in names

    @pytest.mark.asyncio
    async def test_find_merge_candidates_substring_match(self, shard, mock_frame):
        """Test finds substring matches (e.g., 'Griffiths' is contained in 'Stuart Griffiths')."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Stuart Griffiths",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "Griffiths",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 2,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(threshold=0.85)
        assert len(result) >= 1
        # Should flag substring match
        found_substring = any("substring" in r["reason"].lower() for r in result)
        assert found_substring

    @pytest.mark.asyncio
    async def test_find_merge_candidates_case_insensitive(self, shard, mock_frame):
        """Test finds case-insensitive exact matches (e.g., 'Bylor Ltd' vs 'bylor ltd')."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Bylor Ltd",
                    "entity_type": "ORGANIZATION",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 10,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "bylor ltd",
                    "entity_type": "ORGANIZATION",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 1,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(threshold=0.85)
        assert len(result) >= 1
        found_case = any("case" in r["reason"].lower() for r in result)
        assert found_case

    @pytest.mark.asyncio
    async def test_find_merge_candidates_no_cross_type(self, shard, mock_frame):
        """Test does NOT match entities of different types."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Bristol",
                    "entity_type": "LOCATION",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "Bristol",
                    "entity_type": "ORGANIZATION",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 2,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(threshold=0.85)
        # These are different types, so should NOT be paired
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_find_merge_candidates_filter_by_type(self, shard, mock_frame):
        """Test entity_type filter only queries that type."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "TLT Solicitors",
                    "entity_type": "ORGANIZATION",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "TLT Solicitor",
                    "entity_type": "ORGANIZATION",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 2,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(entity_type="ORGANIZATION", threshold=0.85)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_find_merge_candidates_threshold_filtering(self, shard, mock_frame):
        """Test threshold properly filters low-similarity pairs."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Alex Dalton",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "John Smith",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 3,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(threshold=0.85)
        # These names are very different, should not match
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_find_merge_candidates_skips_already_merged(self, shard, mock_frame):
        """Test that entities with canonical_id set are excluded from comparison."""
        await shard.initialize(mock_frame)

        # The query should filter out entities with canonical_id IS NOT NULL
        # We verify by returning only canonical entities
        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Stuart Griffiths",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates()
        # Only one entity, no pairs possible
        assert result == []

    @pytest.mark.asyncio
    async def test_find_merge_candidates_return_structure(self, shard, mock_frame):
        """Test returned dicts have correct structure."""
        await shard.initialize(mock_frame)

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "name": "Stuart Griffiths",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 5,
                    "created_at": None,
                    "updated_at": None,
                },
                {
                    "id": "e2",
                    "name": "Stuart Griffith",
                    "entity_type": "PERSON",
                    "canonical_id": None,
                    "aliases": "[]",
                    "metadata": "{}",
                    "mention_count": 3,
                    "created_at": None,
                    "updated_at": None,
                },
            ]
        )

        result = await shard.find_merge_candidates(threshold=0.80)
        assert len(result) >= 1
        pair = result[0]
        # Verify structure
        assert "entity_a" in pair
        assert "entity_b" in pair
        assert "id" in pair["entity_a"]
        assert "name" in pair["entity_a"]
        assert "id" in pair["entity_b"]
        assert "name" in pair["entity_b"]
        assert "similarity_score" in pair
        assert "reason" in pair
        assert isinstance(pair["similarity_score"], float)


class TestAutoResolveCanonical:
    """Test auto_resolve_canonical method for determining canonical name."""

    @pytest.mark.asyncio
    async def test_auto_resolve_not_initialized(self, shard):
        """Test auto_resolve_canonical fails if shard not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            await shard.auto_resolve_canonical("test-id")

    @pytest.mark.asyncio
    async def test_auto_resolve_entity_not_found(self, shard, mock_frame):
        """Test auto_resolve_canonical returns empty string for missing entity."""
        await shard.initialize(mock_frame)
        shard._db.fetch_one = AsyncMock(return_value=None)
        shard._db.fetch_all = AsyncMock(return_value=[])

        result = await shard.auto_resolve_canonical("nonexistent-id")
        assert result == ""

    @pytest.mark.asyncio
    async def test_auto_resolve_prefers_longest_form(self, shard, mock_frame):
        """Test canonical name is the longest form among mentions."""
        await shard.initialize(mock_frame)

        # Entity record
        shard._db.fetch_one = AsyncMock(
            return_value={
                "id": "e1",
                "name": "Griffiths",
                "entity_type": "PERSON",
                "canonical_id": None,
                "aliases": "[]",
                "metadata": "{}",
                "mention_count": 5,
                "created_at": None,
                "updated_at": None,
            }
        )

        # Mention texts
        shard._db.fetch_all = AsyncMock(
            return_value=[
                {"mention_text": "Griffiths", "cnt": 3},
                {"mention_text": "Stuart Griffiths", "cnt": 2},
            ]
        )

        result = await shard.auto_resolve_canonical("e1")
        # Should prefer longest form
        assert result == "Stuart Griffiths"

    @pytest.mark.asyncio
    async def test_auto_resolve_prefers_most_frequent(self, shard, mock_frame):
        """Test canonical name prefers most frequent form when lengths are similar."""
        await shard.initialize(mock_frame)

        shard._db.fetch_one = AsyncMock(
            return_value={
                "id": "e1",
                "name": "S. Griffiths",
                "entity_type": "PERSON",
                "canonical_id": None,
                "aliases": "[]",
                "metadata": "{}",
                "mention_count": 10,
                "created_at": None,
                "updated_at": None,
            }
        )

        shard._db.fetch_all = AsyncMock(
            return_value=[
                {"mention_text": "S. Griffiths", "cnt": 8},
                {"mention_text": "S Griffiths", "cnt": 2},
            ]
        )

        result = await shard.auto_resolve_canonical("e1")
        # Similar lengths, prefer most frequent
        assert result == "S. Griffiths"

    @pytest.mark.asyncio
    async def test_auto_resolve_returns_string(self, shard, mock_frame):
        """Test auto_resolve_canonical always returns a string."""
        await shard.initialize(mock_frame)

        shard._db.fetch_one = AsyncMock(
            return_value={
                "id": "e1",
                "name": "Test Entity",
                "entity_type": "PERSON",
                "canonical_id": None,
                "aliases": "[]",
                "metadata": "{}",
                "mention_count": 1,
                "created_at": None,
                "updated_at": None,
            }
        )
        shard._db.fetch_all = AsyncMock(return_value=[])

        result = await shard.auto_resolve_canonical("e1")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_auto_resolve_fallback_to_entity_name(self, shard, mock_frame):
        """Test falls back to entity name when no mentions exist."""
        await shard.initialize(mock_frame)

        shard._db.fetch_one = AsyncMock(
            return_value={
                "id": "e1",
                "name": "Test Entity",
                "entity_type": "PERSON",
                "canonical_id": None,
                "aliases": "[]",
                "metadata": "{}",
                "mention_count": 0,
                "created_at": None,
                "updated_at": None,
            }
        )
        shard._db.fetch_all = AsyncMock(return_value=[])

        result = await shard.auto_resolve_canonical("e1")
        assert result == "Test Entity"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
