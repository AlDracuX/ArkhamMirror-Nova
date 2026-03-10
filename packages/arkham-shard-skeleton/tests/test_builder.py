"""
Skeleton Shard - Builder Tests

Tests for SkeletonBuilder domain logic.
All external dependencies are mocked.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_skeleton.builder import SkeletonBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    """Create a mock LLM service."""
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def builder(mock_db, mock_event_bus, mock_llm):
    """Create a SkeletonBuilder with mocked dependencies."""
    return SkeletonBuilder(db=mock_db, event_bus=mock_event_bus, llm_service=mock_llm)


@pytest.fixture
def builder_no_llm(mock_db, mock_event_bus):
    """Create a SkeletonBuilder without LLM."""
    return SkeletonBuilder(db=mock_db, event_bus=mock_event_bus, llm_service=None)


# ---------------------------------------------------------------------------
# test_build_argument_tree_structure
# ---------------------------------------------------------------------------


class TestBuildArgumentTree:
    """tree has claim + elements + refs."""

    @pytest.mark.asyncio
    async def test_build_argument_tree_structure(self, builder, mock_db):
        """Build returns tree with claim, nodes containing elements, evidence_refs, authority_refs."""
        claim_id = "claim-001"

        # Mock: fetch claim data from claims schema
        mock_db.fetch_one.side_effect = [
            # First call: fetch claim
            {"id": claim_id, "title": "Unfair Dismissal", "legal_test": "ERA 1996 s.98"},
            # Second call: fetch existing tree (none)
            None,
        ]
        mock_db.fetch_all.side_effect = [
            # evidence refs for this claim
            [
                {"id": "ev-1", "description": "Witness statement of X", "document_id": "doc-1"},
                {"id": "ev-2", "description": "Email dated 2024-01-15", "document_id": "doc-2"},
            ],
            # authority refs for this claim
            [
                {"id": "auth-1", "citation": "[2024] UKSC 1", "title": "Case A"},
            ],
        ]

        result = await builder.build_argument_tree(claim_id)

        assert result is not None
        assert "tree_id" in result
        assert result["claim_id"] == claim_id
        assert result["claim_title"] == "Unfair Dismissal"
        assert "nodes" in result
        assert isinstance(result["nodes"], list)
        # At minimum one node for the legal test element
        assert len(result["nodes"]) >= 1
        node = result["nodes"][0]
        assert "element" in node
        assert "evidence_refs" in node
        assert "authority_refs" in node

    @pytest.mark.asyncio
    async def test_build_tree_persists_to_db(self, builder, mock_db):
        """Building a tree writes it to the database."""
        mock_db.fetch_one.side_effect = [
            {"id": "claim-001", "title": "Discrimination", "legal_test": "EqA 2010 s.13"},
            None,
        ]
        mock_db.fetch_all.side_effect = [[], []]

        await builder.build_argument_tree("claim-001")

        # Should have called execute with INSERT
        insert_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "INSERT" in str(c.args[0]) and "argument_trees" in str(c.args[0])
        ]
        assert len(insert_calls) >= 1

    @pytest.mark.asyncio
    async def test_build_tree_emits_event(self, builder, mock_db, mock_event_bus):
        """Building a tree emits skeleton.argument.structured event."""
        mock_db.fetch_one.side_effect = [
            {"id": "claim-001", "title": "Whistleblowing", "legal_test": "ERA 1996 s.43B"},
            None,
        ]
        mock_db.fetch_all.side_effect = [[], []]

        await builder.build_argument_tree("claim-001")

        mock_event_bus.emit.assert_called_once()
        call_args = mock_event_bus.emit.call_args
        assert call_args[0][0] == "skeleton.argument.structured"

    @pytest.mark.asyncio
    async def test_build_tree_no_claim_returns_none(self, builder, mock_db):
        """Returns None when claim_id not found."""
        mock_db.fetch_one.return_value = None
        result = await builder.build_argument_tree("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# test_render_submission_numbered_paragraphs
# ---------------------------------------------------------------------------


class TestRenderSubmission:
    """output has numbered paragraphs."""

    @pytest.mark.asyncio
    async def test_render_submission_numbered_paragraphs(self, builder, mock_db):
        """Rendered text has numbered paragraphs (1., 2., etc.)."""
        submission_id = "sub-001"
        mock_db.fetch_one.return_value = {
            "id": submission_id,
            "title": "Skeleton Argument: Unfair Dismissal",
            "content_structure": json.dumps(
                {
                    "sections": [
                        {
                            "heading": "Introduction",
                            "tree_ids": ["tree-001"],
                        },
                        {
                            "heading": "Background Facts",
                            "tree_ids": ["tree-002"],
                        },
                    ],
                }
            ),
            "bundle_references": json.dumps({}),
        }
        # Mock tree fetches for rendering
        mock_db.fetch_all.side_effect = [
            # Trees for section 1
            [
                {
                    "id": "tree-001",
                    "title": "Jurisdiction",
                    "legal_test": "ERA 1996 s.98",
                    "logic_summary": "The Claimant was employed for over two years.",
                    "evidence_refs": json.dumps(["ev-1"]),
                    "authority_ids": json.dumps(["auth-1"]),
                }
            ],
            # Trees for section 2
            [
                {
                    "id": "tree-002",
                    "title": "Facts",
                    "legal_test": "",
                    "logic_summary": "The Claimant was dismissed on 15 January 2024.",
                    "evidence_refs": json.dumps([]),
                    "authority_ids": json.dumps([]),
                }
            ],
            # authorities
            [{"id": "auth-1", "citation": "[2024] UKSC 1", "title": "Case A"}],
        ]

        text = await builder.render_submission(submission_id)

        assert text is not None
        assert isinstance(text, str)
        # Check numbered paragraphs exist
        assert "1." in text
        assert "2." in text

    @pytest.mark.asyncio
    async def test_render_includes_authority_citations(self, builder, mock_db):
        """Rendered text includes neutral citations for authorities."""
        submission_id = "sub-002"
        mock_db.fetch_one.return_value = {
            "id": submission_id,
            "title": "Test Submission",
            "content_structure": json.dumps(
                {
                    "sections": [
                        {"heading": "Law", "tree_ids": ["tree-001"]},
                    ],
                }
            ),
            "bundle_references": json.dumps({}),
        }
        mock_db.fetch_all.side_effect = [
            [
                {
                    "id": "tree-001",
                    "title": "Jurisdiction",
                    "legal_test": "ERA 1996 s.98",
                    "logic_summary": "The test is set out in statute.",
                    "evidence_refs": json.dumps([]),
                    "authority_ids": json.dumps(["auth-1"]),
                }
            ],
            [{"id": "auth-1", "citation": "Buckland v Bournemouth [2010] ICR 908", "title": "Buckland"}],
        ]

        text = await builder.render_submission(submission_id)

        assert "Buckland v Bournemouth [2010] ICR 908" in text

    @pytest.mark.asyncio
    async def test_render_not_found(self, builder, mock_db):
        """Returns None for non-existent submission."""
        mock_db.fetch_one.return_value = None
        result = await builder.render_submission("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# test_render_with_bundle_references
# ---------------------------------------------------------------------------


class TestRenderWithBundleReferences:
    """[p.X] references present."""

    @pytest.mark.asyncio
    async def test_render_with_bundle_references(self, builder, mock_db):
        """Rendered text contains [p.X] bundle page references."""
        submission_id = "sub-003"
        mock_db.fetch_one.return_value = {
            "id": submission_id,
            "title": "Skeleton Argument with Bundle",
            "content_structure": json.dumps(
                {
                    "sections": [
                        {"heading": "Evidence", "tree_ids": ["tree-001"]},
                    ],
                }
            ),
            "bundle_references": json.dumps({"doc-1": 42, "doc-2": 87}),
        }
        mock_db.fetch_all.side_effect = [
            # 1. Trees for section
            [
                {
                    "id": "tree-001",
                    "title": "Facts",
                    "legal_test": "",
                    "logic_summary": "The email confirms the dismissal.",
                    "evidence_refs": json.dumps(["ev-1"]),
                    "authority_ids": json.dumps([]),
                }
            ],
            # 2. Evidence details with document_ids (fetched inside loop when bundle_refs exist)
            [{"id": "ev-1", "document_id": "doc-1", "description": "Email of 15 Jan 2024"}],
            # 3. Authorities (empty, fetched at end since no authority_ids)
        ]

        text = await builder.render_submission(submission_id)

        assert text is not None
        assert "[p.42]" in text


# ---------------------------------------------------------------------------
# test_link_authorities_updates_nodes
# ---------------------------------------------------------------------------


class TestLinkAuthorities:
    """authority_refs populated."""

    @pytest.mark.asyncio
    async def test_link_authorities_updates_nodes(self, builder, mock_db):
        """Linking authorities populates authority_refs on the tree."""
        tree_id = "tree-001"
        authority_ids = ["auth-1", "auth-2"]

        mock_db.fetch_one.return_value = {
            "id": tree_id,
            "authority_ids": json.dumps([]),
        }
        mock_db.fetch_all.return_value = [
            {"id": "auth-1", "citation": "[2024] UKSC 1"},
            {"id": "auth-2", "citation": "[2023] EWCA Civ 123"},
        ]

        await builder.link_authorities(tree_id, authority_ids)

        # Should have called execute with UPDATE
        update_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "UPDATE" in str(c.args[0]) and "authority_ids" in str(c.args[0])
        ]
        assert len(update_calls) >= 1
        # The merged authority_ids should contain both new IDs
        params = update_calls[0].args[1]
        merged = json.loads(params["authority_ids"])
        assert "auth-1" in merged
        assert "auth-2" in merged

    @pytest.mark.asyncio
    async def test_link_authorities_tree_not_found(self, builder, mock_db):
        """Raises ValueError when tree not found."""
        mock_db.fetch_one.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await builder.link_authorities("nonexistent", ["auth-1"])

    @pytest.mark.asyncio
    async def test_link_authorities_deduplicates(self, builder, mock_db):
        """Does not add duplicate authority IDs."""
        mock_db.fetch_one.return_value = {
            "id": "tree-001",
            "authority_ids": json.dumps(["auth-1"]),
        }
        mock_db.fetch_all.return_value = [
            {"id": "auth-1", "citation": "[2024] UKSC 1"},
        ]

        await builder.link_authorities("tree-001", ["auth-1"])

        update_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "UPDATE" in str(c.args[0]) and "authority_ids" in str(c.args[0])
        ]
        assert len(update_calls) >= 1
        params = update_calls[0].args[1]
        merged = json.loads(params["authority_ids"])
        assert merged.count("auth-1") == 1


# ---------------------------------------------------------------------------
# test_add_bundle_references_cross_schema
# ---------------------------------------------------------------------------


class TestAddBundleReferences:
    """queries bundle schema."""

    @pytest.mark.asyncio
    async def test_add_bundle_references_cross_schema(self, builder, mock_db):
        """Adds bundle page refs by querying arkham_bundle schema."""
        submission_id = "sub-001"
        bundle_id = "bundle-001"

        # Fetch submission
        mock_db.fetch_one.return_value = {
            "id": submission_id,
            "content_structure": json.dumps(
                {
                    "sections": [{"heading": "Facts", "tree_ids": ["tree-001"]}],
                }
            ),
            "bundle_references": json.dumps({}),
        }
        # Fetch evidence refs from trees, then bundle pages
        mock_db.fetch_all.side_effect = [
            # Trees for submission
            [{"id": "tree-001", "evidence_refs": json.dumps(["ev-1", "ev-2"])}],
            # Evidence with document_ids
            [
                {"id": "ev-1", "document_id": "doc-1"},
                {"id": "ev-2", "document_id": "doc-2"},
            ],
            # Bundle page lookup from arkham_bundle schema
            [
                {"document_id": "doc-1", "page_number": 42},
                {"document_id": "doc-2", "page_number": 87},
            ],
        ]

        await builder.add_bundle_references(submission_id, bundle_id)

        # Should have queried the bundle schema
        bundle_query_calls = [c for c in mock_db.fetch_all.call_args_list if "arkham_bundle" in str(c.args[0])]
        assert len(bundle_query_calls) >= 1

        # Should have updated submission with bundle_references
        update_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "UPDATE" in str(c.args[0]) and "bundle_references" in str(c.args[0])
        ]
        assert len(update_calls) >= 1
        params = update_calls[0].args[1]
        refs = json.loads(params["bundle_references"])
        assert refs.get("doc-1") == 42
        assert refs.get("doc-2") == 87

    @pytest.mark.asyncio
    async def test_add_bundle_references_submission_not_found(self, builder, mock_db):
        """Raises ValueError when submission not found."""
        mock_db.fetch_one.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await builder.add_bundle_references("nonexistent", "bundle-001")
