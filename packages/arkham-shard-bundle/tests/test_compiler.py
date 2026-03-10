"""
Bundle Shard - Compiler Tests

Tests for BundleCompiler domain logic: page numbering, compilation,
index generation, document add/remove, version comparison.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_bundle.compiler import BundleCompiler

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    db.transaction = MagicMock()
    db.transaction.return_value.__aenter__ = AsyncMock()
    db.transaction.return_value.__aexit__ = AsyncMock()
    return db


@pytest.fixture
def compiler(mock_db, mock_events):
    return BundleCompiler(db=mock_db, event_bus=mock_events)


# ---------------------------------------------------------------------------
# 1. assign_page_numbers (pure function)
# ---------------------------------------------------------------------------


class TestAssignPageNumbers:
    """Tests for continuous page number assignment."""

    def test_assign_page_numbers_continuous(self, compiler):
        """3 docs (5pp, 3pp, 2pp) = pp.1-5, pp.6-8, pp.9-10."""
        docs = [
            {"document_id": "d1", "page_count": 5},
            {"document_id": "d2", "page_count": 3},
            {"document_id": "d3", "page_count": 2},
        ]
        result = compiler.assign_page_numbers(docs)

        assert len(result) == 3
        assert result[0]["bundle_page_start"] == 1
        assert result[0]["bundle_page_end"] == 5
        assert result[1]["bundle_page_start"] == 6
        assert result[1]["bundle_page_end"] == 8
        assert result[2]["bundle_page_start"] == 9
        assert result[2]["bundle_page_end"] == 10

    def test_assign_page_numbers_single_doc(self, compiler):
        """Single document gets pages 1 to page_count."""
        docs = [{"document_id": "d1", "page_count": 7}]
        result = compiler.assign_page_numbers(docs)

        assert result[0]["bundle_page_start"] == 1
        assert result[0]["bundle_page_end"] == 7

    def test_assign_page_numbers_empty_list(self, compiler):
        """Empty list returns empty list."""
        result = compiler.assign_page_numbers([])
        assert result == []

    def test_assign_page_numbers_default_page_count(self, compiler):
        """Missing page_count defaults to 1."""
        docs = [{"document_id": "d1"}, {"document_id": "d2"}]
        result = compiler.assign_page_numbers(docs)

        assert result[0]["bundle_page_start"] == 1
        assert result[0]["bundle_page_end"] == 1
        assert result[1]["bundle_page_start"] == 2
        assert result[1]["bundle_page_end"] == 2

    def test_assign_page_numbers_zero_page_count_treated_as_one(self, compiler):
        """Zero page_count is treated as 1 (minimum)."""
        docs = [{"document_id": "d1", "page_count": 0}]
        result = compiler.assign_page_numbers(docs)

        assert result[0]["bundle_page_start"] == 1
        assert result[0]["bundle_page_end"] == 1

    def test_assign_page_numbers_preserves_original_keys(self, compiler):
        """Original dict keys are preserved in output."""
        docs = [{"document_id": "d1", "page_count": 3, "title": "My Doc"}]
        result = compiler.assign_page_numbers(docs)

        assert result[0]["document_id"] == "d1"
        assert result[0]["title"] == "My Doc"
        assert result[0]["page_count"] == 3


# ---------------------------------------------------------------------------
# 2. compile
# ---------------------------------------------------------------------------


class TestCompile:
    """Tests for full bundle compilation."""

    @pytest.mark.asyncio
    async def test_compile_creates_version(self, compiler, mock_db):
        """Verify compilation creates a new version with incremented number."""
        # Mock bundle row with version=1
        mock_db.fetch_one.return_value = {
            "id": "b1",
            "version": 1,
            "current_version_id": "v-old",
            "title": "Test Bundle",
        }

        # Mock existing pages (from previous version)
        mock_db.fetch_all.return_value = [
            {
                "document_id": "d1",
                "document_title": "Doc 1",
                "document_filename": "doc1.pdf",
                "document_page_count": 3,
                "document_status": "agreed",
                "section_label": "",
                "notes": "",
                "position": 0,
            },
            {
                "document_id": "d2",
                "document_title": "Doc 2",
                "document_filename": "doc2.pdf",
                "document_page_count": 2,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
                "position": 1,
            },
        ]

        result = await compiler.compile("b1")

        assert result["version_number"] == 2
        assert result["total_pages"] == 5
        assert result["document_count"] == 2
        assert result["bundle_id"] == "b1"
        assert "version_id" in result
        assert "index" in result

    @pytest.mark.asyncio
    async def test_compile_not_found(self, compiler, mock_db):
        """Compile raises ValueError for non-existent bundle."""
        mock_db.fetch_one.return_value = None

        with pytest.raises(ValueError, match="Bundle not found"):
            await compiler.compile("nonexistent")

    @pytest.mark.asyncio
    async def test_compile_emits_event(self, compiler, mock_db, mock_events):
        """Compilation emits bundle.compiled event."""
        mock_db.fetch_one.return_value = {
            "id": "b1",
            "version": 0,
            "current_version_id": "",
        }
        mock_db.fetch_all.return_value = [
            {
                "document_id": "d1",
                "document_title": "Doc",
                "document_filename": "",
                "document_page_count": 1,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
                "position": 0,
            }
        ]

        await compiler.compile("b1")

        mock_events.emit.assert_called_once()
        call_args = mock_events.emit.call_args
        assert call_args[0][0] == "bundle.compiled"
        assert call_args[0][1]["bundle_id"] == "b1"

    @pytest.mark.asyncio
    async def test_compile_empty_bundle(self, compiler, mock_db):
        """Compiling an empty bundle produces zero pages."""
        mock_db.fetch_one.return_value = {
            "id": "b1",
            "version": 0,
            "current_version_id": "",
        }
        mock_db.fetch_all.return_value = []

        result = await compiler.compile("b1")

        assert result["total_pages"] == 0
        assert result["document_count"] == 0


# ---------------------------------------------------------------------------
# 3. generate_index
# ---------------------------------------------------------------------------


class TestGenerateIndex:
    """Tests for index generation."""

    @pytest.mark.asyncio
    async def test_index_generation_includes_all_docs(self, compiler, mock_db):
        """Generated index document_count matches actual page records."""
        mock_db.fetch_all.return_value = [
            {
                "position": 0,
                "document_id": "d1",
                "document_title": "Doc 1",
                "document_filename": "doc1.pdf",
                "bundle_page_start": 1,
                "bundle_page_end": 3,
                "document_status": "agreed",
                "section_label": "",
                "notes": "",
            },
            {
                "position": 1,
                "document_id": "d2",
                "document_title": "Doc 2",
                "document_filename": "doc2.pdf",
                "bundle_page_start": 4,
                "bundle_page_end": 6,
                "document_status": "disputed",
                "section_label": "",
                "notes": "",
            },
            {
                "position": 2,
                "document_id": "d3",
                "document_title": "Doc 3",
                "document_filename": "doc3.pdf",
                "bundle_page_start": 7,
                "bundle_page_end": 10,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
            },
        ]

        result = await compiler.generate_index("b1", "v1")

        assert result["document_count"] == 3
        assert result["total_pages"] == 10
        assert len(result["entries"]) == 3

    @pytest.mark.asyncio
    async def test_index_generation_emits_event(self, compiler, mock_db, mock_events):
        """Index generation emits bundle.index.generated event."""
        mock_db.fetch_all.return_value = [
            {
                "position": 0,
                "document_id": "d1",
                "document_title": "Doc 1",
                "document_filename": "",
                "bundle_page_start": 1,
                "bundle_page_end": 1,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
            },
        ]

        await compiler.generate_index("b1", "v1")

        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "bundle.index.generated"


# ---------------------------------------------------------------------------
# 4. index to_text format
# ---------------------------------------------------------------------------


class TestIndexToText:
    """Tests for index text export formatting."""

    @pytest.mark.asyncio
    async def test_index_to_text_format(self, compiler, mock_db):
        """Verify text output contains header, document rows, and totals."""
        # Mock bundle
        mock_db.fetch_one.side_effect = [
            # First call: bundle lookup
            {"id": "b1", "current_version_id": "v1"},
            # Second call: index lookup
            {
                "id": "idx1",
                "entries": json.dumps(
                    [
                        {
                            "entry_type": "section_header",
                            "position": 0,
                            "header_text": "Claim and Response",
                            "document_id": None,
                            "document_title": "",
                            "document_filename": "",
                            "bundle_page_start": None,
                            "bundle_page_end": None,
                            "document_status": "unknown",
                            "section_label": "",
                            "notes": "",
                            "page_range": "",
                        },
                        {
                            "entry_type": "document",
                            "position": 1,
                            "document_id": "d1",
                            "document_title": "ET1 Claim Form",
                            "document_filename": "et1.pdf",
                            "bundle_page_start": 1,
                            "bundle_page_end": 5,
                            "document_status": "agreed",
                            "section_label": "",
                            "notes": "",
                            "page_range": "pp.1-5",
                        },
                    ]
                ),
                "document_count": 1,
                "total_pages": 5,
            },
        ]

        text = await compiler.export_index_text("b1")

        assert "BUNDLE INDEX" in text
        assert "CLAIM AND RESPONSE" in text
        assert "ET1 Claim Form" in text
        assert "pp.1-5" in text
        assert "1 documents" in text
        assert "5 pages" in text


# ---------------------------------------------------------------------------
# 5. add_document
# ---------------------------------------------------------------------------


class TestAddDocument:
    """Tests for adding documents to a bundle."""

    @pytest.mark.asyncio
    async def test_add_document_renumbers(self, compiler, mock_db):
        """Insert at position 1, verify pages shift for subsequent docs."""
        # Mock bundle
        mock_db.fetch_one.return_value = {
            "id": "b1",
            "current_version_id": "v1",
        }

        # Existing pages: d1 (3pp), d2 (2pp)
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "bundle_id": "b1",
                "version_id": "v1",
                "document_id": "d1",
                "document_title": "Doc 1",
                "document_filename": "",
                "position": 0,
                "document_page_count": 3,
                "bundle_page_start": 1,
                "bundle_page_end": 3,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
            },
            {
                "id": "p2",
                "bundle_id": "b1",
                "version_id": "v1",
                "document_id": "d2",
                "document_title": "Doc 2",
                "document_filename": "",
                "position": 1,
                "document_page_count": 2,
                "bundle_page_start": 4,
                "bundle_page_end": 5,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
            },
        ]

        # Add new doc (4pp) at position 1
        result = await compiler.add_document("b1", "d-new", position=1, page_count=4, title="New Doc")

        # d1: pp.1-3 (unchanged), d-new: pp.4-7, d2: pp.8-9
        assert result["position"] == 1
        assert result["bundle_page_start"] == 4
        assert result["bundle_page_end"] == 7
        assert result["total_pages"] == 9

    @pytest.mark.asyncio
    async def test_add_document_appends_when_no_position(self, compiler, mock_db):
        """When position is None, document appends to end."""
        mock_db.fetch_one.return_value = {
            "id": "b1",
            "current_version_id": "v1",
        }
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "bundle_id": "b1",
                "version_id": "v1",
                "document_id": "d1",
                "document_title": "Doc 1",
                "document_filename": "",
                "position": 0,
                "document_page_count": 5,
                "bundle_page_start": 1,
                "bundle_page_end": 5,
                "document_status": "unknown",
                "section_label": "",
                "notes": "",
            },
        ]

        result = await compiler.add_document("b1", "d-new", page_count=3)

        assert result["position"] == 1
        assert result["bundle_page_start"] == 6
        assert result["bundle_page_end"] == 8
        assert result["total_pages"] == 8

    @pytest.mark.asyncio
    async def test_add_document_not_found(self, compiler, mock_db):
        """Adding to non-existent bundle raises ValueError."""
        mock_db.fetch_one.return_value = None

        with pytest.raises(ValueError, match="Bundle not found"):
            await compiler.add_document("nonexistent", "d1")


# ---------------------------------------------------------------------------
# 6. remove_document
# ---------------------------------------------------------------------------


class TestRemoveDocument:
    """Tests for removing documents from a bundle."""

    @pytest.mark.asyncio
    async def test_remove_document_renumbers(self, compiler, mock_db):
        """Remove middle doc, verify continuous page numbering restored."""
        # Mock bundle
        mock_db.fetch_one.return_value = {
            "id": "b1",
            "current_version_id": "v1",
        }

        # After deletion, remaining docs returned by fetch_all
        mock_db.fetch_all.return_value = [
            {
                "id": "p1",
                "document_id": "d1",
                "document_page_count": 3,
                "position": 0,
                "bundle_page_start": 1,
                "bundle_page_end": 3,
            },
            {
                "id": "p3",
                "document_id": "d3",
                "document_page_count": 2,
                "position": 2,  # old position, will be renumbered
                "bundle_page_start": 8,
                "bundle_page_end": 9,
            },
        ]

        await compiler.remove_document("b1", "d2")

        # Verify renumber calls
        update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE arkham_bundle.pages SET" in str(c)]
        assert len(update_calls) == 2

        # Check d3 got renumbered to position 1, pages 4-5
        d3_call = update_calls[1]
        params = d3_call[0][1] if len(d3_call[0]) > 1 else d3_call[1]
        assert params["position"] == 1
        assert params["page_start"] == 4
        assert params["page_end"] == 5

    @pytest.mark.asyncio
    async def test_remove_document_not_found_bundle(self, compiler, mock_db):
        """Removing from non-existent bundle raises ValueError."""
        mock_db.fetch_one.return_value = None

        with pytest.raises(ValueError, match="Bundle not found"):
            await compiler.remove_document("nonexistent", "d1")


# ---------------------------------------------------------------------------
# 7. compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    """Tests for version comparison."""

    @pytest.mark.asyncio
    async def test_compare_versions_detects_additions(self, compiler, mock_db):
        """Version B has 1 new doc compared to version A."""
        # Version A: d1, d2
        # Version B: d1, d2, d3
        call_count = 0

        async def mock_fetch_all(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Version A
                return [
                    {"document_id": "d1", "position": 0, "bundle_page_end": 3},
                    {"document_id": "d2", "position": 1, "bundle_page_end": 5},
                ]
            else:
                # Version B
                return [
                    {"document_id": "d1", "position": 0, "bundle_page_end": 3},
                    {"document_id": "d2", "position": 1, "bundle_page_end": 5},
                    {"document_id": "d3", "position": 2, "bundle_page_end": 8},
                ]

        mock_db.fetch_all.side_effect = mock_fetch_all

        result = await compiler.compare_versions("va", "vb")

        assert "d3" in result["added_docs"]
        assert result["removed_docs"] == []
        assert result["page_count_a"] == 5
        assert result["page_count_b"] == 8
        assert result["page_count_diff"] == 3

    @pytest.mark.asyncio
    async def test_compare_versions_detects_removals(self, compiler, mock_db):
        """Version B has 1 less doc compared to version A."""
        call_count = 0

        async def mock_fetch_all(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    {"document_id": "d1", "position": 0, "bundle_page_end": 3},
                    {"document_id": "d2", "position": 1, "bundle_page_end": 5},
                ]
            else:
                return [
                    {"document_id": "d1", "position": 0, "bundle_page_end": 3},
                ]

        mock_db.fetch_all.side_effect = mock_fetch_all

        result = await compiler.compare_versions("va", "vb")

        assert "d2" in result["removed_docs"]
        assert result["added_docs"] == []

    @pytest.mark.asyncio
    async def test_compare_versions_detects_reordering(self, compiler, mock_db):
        """Version B has same docs but in different order."""
        call_count = 0

        async def mock_fetch_all(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    {"document_id": "d1", "position": 0, "bundle_page_end": 3},
                    {"document_id": "d2", "position": 1, "bundle_page_end": 5},
                ]
            else:
                return [
                    {"document_id": "d2", "position": 0, "bundle_page_end": 2},
                    {"document_id": "d1", "position": 1, "bundle_page_end": 5},
                ]

        mock_db.fetch_all.side_effect = mock_fetch_all

        result = await compiler.compare_versions("va", "vb")

        assert result["added_docs"] == []
        assert result["removed_docs"] == []
        assert len(result["reordered_docs"]) > 0
