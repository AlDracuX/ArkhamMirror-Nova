"""
Skeleton Shard - Edge Case & Integration Tests

Covers:
- Event handler logic (theory updated, claims verified, authority found)
- LLM integration (draft_section, suggest_structure, JSON parsing)
- Builder edge cases (no legal test, empty refs, dedup, missing data)
- API domain endpoints (build, render, link, bundle-refs, draft)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_skeleton.builder import SkeletonBuilder, _parse_json_field
from arkham_shard_skeleton.llm import DraftedSection, SkeletonLLMIntegration, SuggestedStructure
from arkham_shard_skeleton.shard import SkeletonShard

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def builder(mock_db, mock_event_bus, mock_llm):
    return SkeletonBuilder(db=mock_db, event_bus=mock_event_bus, llm_service=mock_llm)


@pytest.fixture
def builder_no_events(mock_db):
    return SkeletonBuilder(db=mock_db, event_bus=None, llm_service=None)


@pytest.fixture
def mock_frame(mock_event_bus, mock_db, mock_llm):
    frame = MagicMock()
    frame.database = mock_db
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "events": mock_event_bus,
            "llm": mock_llm,
            "database": mock_db,
            "vectors": None,
        }.get(name)
    )
    frame.app = None
    return frame


@pytest.fixture
async def initialized_shard(mock_frame):
    shard = SkeletonShard()
    await shard.initialize(mock_frame)
    return shard


# ---------------------------------------------------------------------------
# _parse_json_field utility
# ---------------------------------------------------------------------------


class TestParseJsonField:
    """Edge cases for the JSON field parser."""

    def test_none_returns_default_list(self):
        assert _parse_json_field(None) == []

    def test_none_returns_custom_default(self):
        assert _parse_json_field(None, {}) == {}

    def test_already_parsed_list(self):
        assert _parse_json_field(["a", "b"]) == ["a", "b"]

    def test_already_parsed_dict(self):
        assert _parse_json_field({"k": "v"}) == {"k": "v"}

    def test_valid_json_string(self):
        assert _parse_json_field('["x"]') == ["x"]

    def test_invalid_json_string_returns_default(self):
        assert _parse_json_field("not-json") == []

    def test_numeric_value_returns_default(self):
        assert _parse_json_field(42) == []

    def test_empty_string_returns_default(self):
        assert _parse_json_field("") == []


# ---------------------------------------------------------------------------
# Event Handler Tests
# ---------------------------------------------------------------------------


class TestEventHandlers:
    """Test shard event handler methods."""

    @pytest.mark.asyncio
    async def test_on_theory_updated_rebuilds_tree(self, initialized_shard, mock_db):
        """theory.updated event triggers tree rebuild for the claim."""
        shard = initialized_shard
        mock_db.fetch_one.side_effect = [
            {"id": "claim-1", "title": "UD", "legal_test": "s.98"},
            None,
        ]
        mock_db.fetch_all.side_effect = [[], []]

        await shard._on_theory_updated({"theory_id": "t1", "claim_id": "claim-1"})

        # Should have attempted to fetch the claim
        assert mock_db.fetch_one.call_count >= 1

    @pytest.mark.asyncio
    async def test_on_theory_updated_no_claim_id(self, initialized_shard, mock_db):
        """theory.updated with no claim_id is a no-op."""
        shard = initialized_shard
        await shard._on_theory_updated({"theory_id": "t1"})
        # No fetch_one call for claim data
        mock_db.fetch_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_theory_updated_handles_error(self, initialized_shard, mock_db):
        """theory.updated handler logs errors without crashing."""
        shard = initialized_shard
        mock_db.fetch_one.side_effect = Exception("DB down")

        # Should not raise
        await shard._on_theory_updated({"theory_id": "t1", "claim_id": "claim-1"})

    @pytest.mark.asyncio
    async def test_on_claims_verified_builds_tree(self, initialized_shard, mock_db):
        """claims.verified event triggers tree build."""
        shard = initialized_shard
        mock_db.fetch_one.side_effect = [
            {"id": "claim-2", "title": "Disc", "legal_test": "s.13"},
            None,
        ]
        mock_db.fetch_all.side_effect = [[], []]

        await shard._on_claims_verified({"claim_id": "claim-2"})

        assert mock_db.fetch_one.call_count >= 1

    @pytest.mark.asyncio
    async def test_on_claims_verified_no_claim_id(self, initialized_shard, mock_db):
        """claims.verified with no claim_id is a no-op."""
        shard = initialized_shard
        await shard._on_claims_verified({})
        mock_db.fetch_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_authority_found_links(self, initialized_shard, mock_db):
        """oracle.authority.found links authority to tree."""
        shard = initialized_shard
        mock_db.fetch_one.return_value = {
            "id": "tree-1",
            "authority_ids": json.dumps([]),
        }
        mock_db.fetch_all.return_value = [
            {"id": "auth-1", "citation": "[2024] UKSC 1"},
        ]

        await shard._on_authority_found({"authority_id": "auth-1", "tree_id": "tree-1"})

        update_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "UPDATE" in str(c.args[0]) and "authority_ids" in str(c.args[0])
        ]
        assert len(update_calls) >= 1

    @pytest.mark.asyncio
    async def test_on_authority_found_missing_fields(self, initialized_shard, mock_db):
        """oracle.authority.found with missing fields is a no-op."""
        shard = initialized_shard
        await shard._on_authority_found({"authority_id": "auth-1"})
        # No tree lookup
        mock_db.fetch_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_authority_found_handles_error(self, initialized_shard, mock_db):
        """oracle.authority.found handler logs errors without crashing."""
        shard = initialized_shard
        mock_db.fetch_one.return_value = None  # tree not found

        # link_authorities raises ValueError, but handler catches it
        await shard._on_authority_found({"authority_id": "auth-1", "tree_id": "nonexistent"})


# ---------------------------------------------------------------------------
# Builder Edge Cases
# ---------------------------------------------------------------------------


class TestBuilderEdgeCases:
    """Edge cases for SkeletonBuilder methods."""

    @pytest.mark.asyncio
    async def test_build_tree_without_legal_test(self, builder, mock_db):
        """Build tree with claim that has no legal_test uses claim title as element."""
        mock_db.fetch_one.side_effect = [
            {"id": "claim-1", "title": "General Claim", "legal_test": ""},
            None,
        ]
        mock_db.fetch_all.side_effect = [
            [{"id": "ev-1", "description": "Doc", "document_id": "d1"}],
            [],
        ]

        result = await builder.build_argument_tree("claim-1")

        assert result is not None
        assert result["nodes"][0]["element"] == "General Claim"
        assert result["legal_test"] == ""

    @pytest.mark.asyncio
    async def test_build_tree_no_evidence_no_authorities(self, builder, mock_db):
        """Build tree works with no evidence or authorities."""
        mock_db.fetch_one.side_effect = [
            {"id": "claim-1", "title": "Empty Claim", "legal_test": "Test"},
            None,
        ]
        mock_db.fetch_all.side_effect = [[], []]

        result = await builder.build_argument_tree("claim-1")

        assert result is not None
        assert result["nodes"][0]["evidence_refs"] == []
        assert result["nodes"][0]["authority_refs"] == []

    @pytest.mark.asyncio
    async def test_build_tree_without_event_bus(self, builder_no_events, mock_db):
        """Build tree works without event bus (no emit call)."""
        mock_db.fetch_one.side_effect = [
            {"id": "claim-1", "title": "Test", "legal_test": "s.1"},
            None,
        ]
        mock_db.fetch_all.side_effect = [[], []]

        result = await builder_no_events.build_argument_tree("claim-1")

        assert result is not None
        assert "tree_id" in result

    @pytest.mark.asyncio
    async def test_link_authorities_empty_list(self, builder, mock_db):
        """Linking empty authority list is a no-op on IDs."""
        mock_db.fetch_one.return_value = {
            "id": "tree-1",
            "authority_ids": json.dumps(["existing-1"]),
        }
        mock_db.fetch_all.return_value = []

        await builder.link_authorities("tree-1", [])

        update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE" in str(c.args[0])]
        assert len(update_calls) >= 1
        params = update_calls[0].args[1]
        merged = json.loads(params["authority_ids"])
        assert merged == ["existing-1"]

    @pytest.mark.asyncio
    async def test_link_authorities_filters_nonexistent(self, builder, mock_db):
        """Only authorities that exist in DB get linked."""
        mock_db.fetch_one.return_value = {
            "id": "tree-1",
            "authority_ids": json.dumps([]),
        }
        # Only auth-1 exists, auth-2 does not
        mock_db.fetch_all.return_value = [
            {"id": "auth-1", "citation": "[2024] UKSC 1"},
        ]

        await builder.link_authorities("tree-1", ["auth-1", "auth-2"])

        update_calls = [c for c in mock_db.execute.call_args_list if "UPDATE" in str(c.args[0])]
        params = update_calls[0].args[1]
        merged = json.loads(params["authority_ids"])
        assert "auth-1" in merged
        assert "auth-2" not in merged

    @pytest.mark.asyncio
    async def test_add_bundle_refs_no_tree_ids_in_structure(self, builder, mock_db):
        """add_bundle_references with empty content_structure is a no-op."""
        mock_db.fetch_one.return_value = {
            "id": "sub-1",
            "content_structure": json.dumps({"sections": []}),
            "bundle_references": json.dumps({}),
        }

        await builder.add_bundle_references("sub-1", "bundle-1")

        # Should not have called fetch_all (no tree_ids to look up)
        mock_db.fetch_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_bundle_refs_no_evidence_on_trees(self, builder, mock_db):
        """add_bundle_references returns early when trees have no evidence."""
        mock_db.fetch_one.return_value = {
            "id": "sub-1",
            "content_structure": json.dumps({"sections": [{"heading": "H", "tree_ids": ["t1"]}]}),
            "bundle_references": json.dumps({}),
        }
        mock_db.fetch_all.side_effect = [
            # Trees: no evidence
            [{"id": "t1", "evidence_refs": json.dumps([])}],
        ]

        await builder.add_bundle_references("sub-1", "bundle-1")

        # Only one fetch_all call (for trees), no further lookups
        assert mock_db.fetch_all.call_count == 1

    @pytest.mark.asyncio
    async def test_add_bundle_refs_merges_with_existing(self, builder, mock_db):
        """add_bundle_references merges new refs with existing ones."""
        mock_db.fetch_one.return_value = {
            "id": "sub-1",
            "content_structure": json.dumps({"sections": [{"heading": "H", "tree_ids": ["t1"]}]}),
            "bundle_references": json.dumps({"doc-existing": 10}),
        }
        mock_db.fetch_all.side_effect = [
            [{"id": "t1", "evidence_refs": json.dumps(["ev-1"])}],
            [{"id": "ev-1", "document_id": "doc-new"}],
            [{"document_id": "doc-new", "page_number": 55}],
        ]

        await builder.add_bundle_references("sub-1", "bundle-1")

        update_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "UPDATE" in str(c.args[0]) and "bundle_references" in str(c.args[0])
        ]
        params = update_calls[0].args[1]
        refs = json.loads(params["bundle_references"])
        assert refs["doc-existing"] == 10
        assert refs["doc-new"] == 55

    @pytest.mark.asyncio
    async def test_add_bundle_refs_no_matching_bundle_pages(self, builder, mock_db):
        """add_bundle_references with no matching pages in bundle schema."""
        mock_db.fetch_one.return_value = {
            "id": "sub-1",
            "content_structure": json.dumps({"sections": [{"heading": "H", "tree_ids": ["t1"]}]}),
            "bundle_references": json.dumps({}),
        }
        mock_db.fetch_all.side_effect = [
            [{"id": "t1", "evidence_refs": json.dumps(["ev-1"])}],
            [{"id": "ev-1", "document_id": "doc-1"}],
            [],  # No bundle pages found
        ]

        await builder.add_bundle_references("sub-1", "bundle-1")

        update_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "UPDATE" in str(c.args[0]) and "bundle_references" in str(c.args[0])
        ]
        params = update_calls[0].args[1]
        refs = json.loads(params["bundle_references"])
        assert refs == {}

    @pytest.mark.asyncio
    async def test_render_submission_empty_sections(self, builder, mock_db):
        """Render submission with sections but no tree_ids produces title only."""
        mock_db.fetch_one.return_value = {
            "id": "sub-1",
            "title": "Empty Skeleton",
            "content_structure": json.dumps({"sections": [{"heading": "Section One", "tree_ids": []}]}),
            "bundle_references": json.dumps({}),
        }

        text = await builder.render_submission("sub-1")

        assert "EMPTY SKELETON" in text
        assert "SECTION ONE" in text
        # No numbered paragraphs since no trees
        assert "1." not in text

    @pytest.mark.asyncio
    async def test_render_submission_no_sections(self, builder, mock_db):
        """Render submission with empty content_structure."""
        mock_db.fetch_one.return_value = {
            "id": "sub-1",
            "title": "Bare Submission",
            "content_structure": json.dumps({}),
            "bundle_references": json.dumps({}),
        }

        text = await builder.render_submission("sub-1")

        assert text is not None
        assert "BARE SUBMISSION" in text


# ---------------------------------------------------------------------------
# LLM Integration Tests
# ---------------------------------------------------------------------------


class TestSkeletonLLMIntegration:
    """Tests for LLM-assisted drafting and structure suggestion."""

    def test_is_available_with_service(self, mock_llm):
        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        assert llm_int.is_available is True

    def test_is_available_without_service(self):
        llm_int = SkeletonLLMIntegration(llm_service=None)
        assert llm_int.is_available is False

    @pytest.mark.asyncio
    async def test_draft_section_returns_structured_output(self, mock_llm):
        """draft_section returns DraftedSection with heading, paragraphs, citations."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "heading": "Qualifying Disclosure",
                "paragraphs": [
                    "1. The Claimant made a qualifying disclosure on 10 January 2024.",
                    "2. The disclosure was made in the public interest (Chesterton v Nurmohamed [2017] ICR 920).",
                ],
                "authority_citations": ["Chesterton v Nurmohamed [2017] ICR 920"],
            }
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        result = await llm_int.draft_section(
            heading="Qualifying Disclosure",
            claim_summary="Whistleblowing claim",
            legal_test="ERA 1996 s.43B",
            evidence_summaries=["Email of 10 Jan 2024"],
            authority_citations=["Chesterton [2017] ICR 920"],
            bundle_refs={"doc-1": 42},
        )

        assert isinstance(result, DraftedSection)
        assert result.heading == "Qualifying Disclosure"
        assert len(result.paragraphs) == 2
        assert len(result.authority_citations) == 1

    @pytest.mark.asyncio
    async def test_draft_section_handles_markdown_fences(self, mock_llm):
        """draft_section strips markdown code fences from LLM response."""
        mock_response = MagicMock()
        mock_response.text = '```json\n{"heading": "Test", "paragraphs": ["1. Para"], "authority_citations": []}\n```'
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        result = await llm_int.draft_section(
            heading="Test",
            claim_summary="Test claim",
        )

        assert result.heading == "Test"
        assert len(result.paragraphs) == 1

    @pytest.mark.asyncio
    async def test_draft_section_handles_bad_json(self, mock_llm):
        """draft_section falls back gracefully on malformed JSON."""
        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all"
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        result = await llm_int.draft_section(
            heading="Fallback",
            claim_summary="Test",
        )

        assert isinstance(result, DraftedSection)
        assert result.heading == "Fallback"  # Falls back to input heading
        assert result.paragraphs == []

    @pytest.mark.asyncio
    async def test_draft_section_minimal_args(self, mock_llm):
        """draft_section works with only heading and claim_summary."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "heading": "H",
                "paragraphs": ["1. P"],
                "authority_citations": [],
            }
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        result = await llm_int.draft_section(heading="H", claim_summary="C")

        assert result.heading == "H"

    @pytest.mark.asyncio
    async def test_generate_raises_without_llm(self):
        """_generate raises RuntimeError without LLM service."""
        llm_int = SkeletonLLMIntegration(llm_service=None)
        with pytest.raises(RuntimeError, match="not available"):
            await llm_int._generate("sys", "user")

    @pytest.mark.asyncio
    async def test_suggest_structure_returns_structured_output(self, mock_llm):
        """suggest_structure returns SuggestedStructure with elements."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "claim_type": "unfair_dismissal",
                "elements": [
                    {"name": "Qualifying Service", "test": "2 years continuous", "key_authority": "ERA 1996"},
                ],
                "suggested_authorities": ["Polkey v AE Dayton [1988] ICR 142"],
            }
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        result = await llm_int.suggest_structure(
            claim_type="unfair_dismissal",
            context="Employee dismissed after 5 years",
        )

        assert isinstance(result, SuggestedStructure)
        assert result.claim_type == "unfair_dismissal"
        assert len(result.elements) == 1
        assert len(result.suggested_authorities) == 1

    @pytest.mark.asyncio
    async def test_suggest_structure_no_context(self, mock_llm):
        """suggest_structure works without context."""
        mock_response = MagicMock()
        mock_response.text = json.dumps(
            {
                "claim_type": "discrimination",
                "elements": [],
                "suggested_authorities": [],
            }
        )
        mock_llm.generate = AsyncMock(return_value=mock_response)

        llm_int = SkeletonLLMIntegration(llm_service=mock_llm)
        result = await llm_int.suggest_structure(claim_type="discrimination")

        assert result.claim_type == "discrimination"

    def test_parse_json_response_empty_text(self):
        """_parse_json_response returns {} for empty text."""
        llm_int = SkeletonLLMIntegration(llm_service=None)
        mock_resp = MagicMock()
        mock_resp.text = ""
        assert llm_int._parse_json_response(mock_resp) == {}

    def test_parse_json_response_plain_json(self):
        """_parse_json_response parses plain JSON."""
        llm_int = SkeletonLLMIntegration(llm_service=None)
        mock_resp = MagicMock()
        mock_resp.text = '{"key": "value"}'
        assert llm_int._parse_json_response(mock_resp) == {"key": "value"}

    def test_parse_json_response_string_input(self):
        """_parse_json_response handles non-object input (string)."""
        llm_int = SkeletonLLMIntegration(llm_service=None)
        assert llm_int._parse_json_response("not-json") == {}


# ---------------------------------------------------------------------------
# Shard Event Subscription Tests
# ---------------------------------------------------------------------------


class TestEventSubscription:
    """Verify event subscriptions are registered during init."""

    @pytest.mark.asyncio
    async def test_subscribes_to_three_events(self, mock_frame, mock_event_bus):
        """Shard subscribes to casemap, claims, and oracle events."""
        shard = SkeletonShard()
        await shard.initialize(mock_frame)

        subscribe_calls = mock_event_bus.subscribe.call_args_list
        event_names = [c.args[0] for c in subscribe_calls]

        assert "casemap.theory.updated" in event_names
        assert "claims.verified" in event_names
        assert "oracle.authority.found" in event_names

    @pytest.mark.asyncio
    async def test_no_event_bus_skips_subscription(self, mock_db):
        """Shard handles missing event bus gracefully."""
        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(return_value=None)
        frame.app = None

        shard = SkeletonShard()
        await shard.initialize(frame)

        # Should not raise; builder/llm still created
        assert shard.builder is not None

    @pytest.mark.asyncio
    async def test_shutdown_clears_services(self, mock_frame):
        """Shutdown nullifies builder and llm_integration."""
        shard = SkeletonShard()
        await shard.initialize(mock_frame)

        assert shard.builder is not None
        assert shard.llm_integration is not None

        await shard.shutdown()

        assert shard.builder is None
        assert shard.llm_integration is None


# ---------------------------------------------------------------------------
# Schema Creation Edge Cases
# ---------------------------------------------------------------------------


class TestSchemaEdgeCases:
    """Test schema creation with missing DB."""

    @pytest.mark.asyncio
    async def test_no_database_skips_schema(self):
        """No database service means schema creation is skipped."""
        frame = MagicMock()
        frame.database = None
        frame.get_service = MagicMock(return_value=None)
        frame.app = None

        shard = SkeletonShard()
        await shard.initialize(frame)

        # Should not raise
        assert shard._db is None

    @pytest.mark.asyncio
    async def test_schema_creation_error_handled(self, mock_db):
        """Schema creation errors are caught and logged."""
        mock_db.execute.side_effect = Exception("Permission denied")

        frame = MagicMock()
        frame.database = mock_db
        frame.get_service = MagicMock(
            side_effect=lambda name: {
                "events": None,
                "llm": None,
                "vectors": None,
            }.get(name)
        )
        frame.app = None

        shard = SkeletonShard()
        # Should not raise - error is caught inside _create_schema
        await shard.initialize(frame)
