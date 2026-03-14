"""
Tests for Letters Shard - Shard Implementation
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_letters.models import (
    ExportFormat,
    Letter,
    LetterStatus,
    LetterTemplate,
    LetterType,
    PlaceholderValue,
)
from arkham_shard_letters.shard import LettersShard


@pytest.fixture
def mock_frame():
    """Create a mock frame for testing."""
    frame = MagicMock()
    frame.database = AsyncMock()
    frame.events = AsyncMock()
    frame.llm = None
    frame.storage = None
    return frame


@pytest.fixture
async def shard(mock_frame):
    """Create a letters shard instance."""
    shard = LettersShard()
    await shard.initialize(mock_frame)
    return shard


class TestShardInitialization:
    """Test shard initialization."""

    @pytest.mark.asyncio
    async def test_initialize(self, mock_frame):
        """Test shard initialization."""
        shard = LettersShard()
        assert shard.name == "letters"
        assert shard.version == "0.1.0"
        assert not shard._initialized

        await shard.initialize(mock_frame)

        assert shard._initialized
        assert shard.frame == mock_frame
        assert shard._db == mock_frame.database
        assert shard._events == mock_frame.events

    @pytest.mark.asyncio
    async def test_shutdown(self, shard):
        """Test shard shutdown."""
        assert shard._initialized

        await shard.shutdown()

        assert not shard._initialized

    def test_get_routes(self, shard):
        """Test getting routes."""
        router = shard.get_routes()
        assert router is not None
        assert router.prefix == "/api/letters"


class TestPlaceholderExtraction:
    """Test placeholder extraction from templates."""

    def test_extract_placeholders(self, shard):
        """Test extracting placeholders."""
        template = "Dear {{name}}, I request {{documents}} from {{department}}."
        placeholders = shard._extract_placeholders(template)

        assert "name" in placeholders
        assert "documents" in placeholders
        assert "department" in placeholders
        assert len(placeholders) == 3

    def test_extract_no_placeholders(self, shard):
        """Test template with no placeholders."""
        template = "This is a plain text template."
        placeholders = shard._extract_placeholders(template)

        assert len(placeholders) == 0

    def test_extract_duplicate_placeholders(self, shard):
        """Test template with duplicate placeholders."""
        template = "Hello {{name}}, welcome {{name}}!"
        placeholders = shard._extract_placeholders(template)

        # Should only have one instance
        assert len(placeholders) == 1
        assert "name" in placeholders


class TestTemplateRendering:
    """Test template rendering with placeholders."""

    def test_render_template(self, shard):
        """Test rendering template with placeholders."""
        template = "Dear {{name}}, your request for {{item}} is approved."
        placeholder_map = {
            "name": "John Doe",
            "item": "documents",
        }

        result = shard._render_template(template, placeholder_map)

        assert result == "Dear John Doe, your request for documents is approved."

    def test_render_template_partial(self, shard):
        """Test rendering with partial placeholders."""
        template = "Hello {{name}}, you requested {{item}}."
        placeholder_map = {"name": "Jane"}

        result = shard._render_template(template, placeholder_map)

        # Unfilled placeholder remains
        assert "Hello Jane" in result
        assert "{{item}}" in result

    def test_render_template_empty(self, shard):
        """Test rendering with no placeholder values."""
        template = "Static {{content}} here."
        placeholder_map = {}

        result = shard._render_template(template, placeholder_map)

        assert result == template


class TestLetterCreation:
    """Test letter CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_letter(self, shard, mock_frame):
        """Test creating a letter."""
        # Mock database
        mock_frame.database.execute = AsyncMock()

        letter = await shard.create_letter(
            title="Test Letter",
            letter_type=LetterType.FOIA,
            content="Test content",
        )

        assert letter.title == "Test Letter"
        assert letter.letter_type == LetterType.FOIA
        assert letter.content == "Test content"
        assert letter.status == LetterStatus.DRAFT
        assert letter.id is not None

        # Verify database was called
        assert mock_frame.database.execute.called

        # Verify event was emitted
        assert mock_frame.events.emit.called

    @pytest.mark.asyncio
    async def test_create_letter_with_recipient(self, shard, mock_frame):
        """Test creating letter with recipient."""
        mock_frame.database.execute = AsyncMock()

        letter = await shard.create_letter(
            title="FOIA Request",
            letter_type=LetterType.FOIA,
            recipient_name="FOIA Officer",
            recipient_address="123 Main St",
        )

        assert letter.recipient_name == "FOIA Officer"
        assert letter.recipient_address == "123 Main St"


class TestTemplateCreation:
    """Test template CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_template(self, shard, mock_frame):
        """Test creating a template."""
        mock_frame.database.execute = AsyncMock()

        template = await shard.create_template(
            name="FOIA Template",
            letter_type=LetterType.FOIA,
            description="Standard FOIA request",
            content_template="Dear {{recipient}}, I request {{documents}}.",
        )

        assert template.name == "FOIA Template"
        assert template.letter_type == LetterType.FOIA
        assert template.description == "Standard FOIA request"
        assert "recipient" in template.placeholders
        assert "documents" in template.placeholders
        assert template.id is not None

        # Verify database was called
        assert mock_frame.database.execute.called

        # Verify event was emitted
        assert mock_frame.events.emit.called

    @pytest.mark.asyncio
    async def test_create_template_with_subject(self, shard, mock_frame):
        """Test creating template with subject."""
        mock_frame.database.execute = AsyncMock()

        template = await shard.create_template(
            name="Template with Subject",
            letter_type=LetterType.INQUIRY,
            description="Test",
            content_template="Content {{field}}",
            subject_template="Subject {{field}}",
        )

        # Both content and subject placeholders extracted
        assert "field" in template.placeholders
        assert template.subject_template == "Subject {{field}}"


class TestTemplateApplication:
    """Test applying templates to create letters."""

    @pytest.mark.asyncio
    async def test_apply_template(self, shard, mock_frame):
        """Test applying template to create letter."""
        # Setup mock template
        mock_template = LetterTemplate(
            id="template-1",
            name="Test Template",
            letter_type=LetterType.FOIA,
            description="Test",
            content_template="Dear {{name}}, I request {{item}}.",
            placeholders=["name", "item"],
            required_placeholders=[],
        )

        # Mock get_template
        shard.get_template = AsyncMock(return_value=mock_template)
        mock_frame.database.execute = AsyncMock()

        # Apply template
        placeholder_values = [
            PlaceholderValue(key="name", value="FOIA Officer"),
            PlaceholderValue(key="item", value="documents"),
        ]

        letter = await shard.apply_template(
            template_id="template-1",
            title="My FOIA Request",
            placeholder_values=placeholder_values,
        )

        assert letter.title == "My FOIA Request"
        assert letter.letter_type == LetterType.FOIA
        assert "FOIA Officer" in letter.content
        assert "documents" in letter.content
        assert letter.template_id == "template-1"
        assert letter.metadata["from_template"] == "template-1"

    @pytest.mark.asyncio
    async def test_apply_template_not_found(self, shard):
        """Test applying non-existent template."""
        shard.get_template = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Template .* not found"):
            await shard.apply_template(
                template_id="nonexistent",
                title="Test",
                placeholder_values=[],
            )


class TestDraftLetter:
    """Test draft_letter method with built-in and stored templates."""

    @pytest.mark.asyncio
    async def test_draft_directions_response(self, shard, mock_frame):
        """Test drafting a directions response letter."""
        variables = {
            "case_number": "6013156/2024",
            "directions_date": "1 March 2026",
            "response_body": "The Claimant has complied with paragraph 1 of the directions.",
            "party_name": "Claimant",
        }

        result = await shard.draft_letter("directions_response", variables)

        assert isinstance(result, str)
        assert "6013156/2024" in result
        assert "1 March 2026" in result
        assert "Claimant" in result
        assert "Subject:" in result

    @pytest.mark.asyncio
    async def test_draft_disclosure_request(self, shard, mock_frame):
        """Test drafting a disclosure request letter."""
        variables = {
            "case_number": "6013156/2024",
            "party_name": "Claimant",
            "document_list": "1. Employment contract\n2. Payslips for 2023-2024",
            "relevance_explanation": "These documents are essential to the unfair dismissal claim.",
            "response_deadline": "14",
        }

        result = await shard.draft_letter("disclosure_request", variables)

        assert "Employment contract" in result
        assert "Rule 31" in result
        assert "14 days" in result

    @pytest.mark.asyncio
    async def test_draft_witness_order(self, shard, mock_frame):
        """Test drafting a witness order application."""
        variables = {
            "case_number": "6013156/2024",
            "witness_name": "Jane Smith",
            "witness_address": "123 High Street, Bristol",
            "necessity_explanation": "The witness has direct knowledge of the dismissal meeting.",
            "voluntary_attempts": "Three written requests were made and ignored.",
            "hearing_dates": "7-10 July 2026",
            "attendance_date": "8 July 2026",
        }

        result = await shard.draft_letter("witness_order", variables)

        assert "Jane Smith" in result
        assert "Rule 32" in result
        assert "7-10 July 2026" in result

    @pytest.mark.asyncio
    async def test_draft_costs_warning(self, shard, mock_frame):
        """Test drafting a costs warning letter."""
        variables = {
            "case_number": "6013156/2024",
            "party_name": "Bylor Ltd",
            "costs_grounds": "The response has no reasonable prospect of success.",
            "costs_amount": "15,000 GBP",
            "respondent_name": "Bylor Ltd",
        }

        result = await shard.draft_letter("costs_warning", variables)

        assert "Rule 76" in result
        assert "15,000 GBP" in result
        assert "Bylor Ltd" in result

    @pytest.mark.asyncio
    async def test_draft_unknown_template_raises(self, shard, mock_frame):
        """Test that unknown template ID raises ValueError."""
        shard.get_template = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Template .* not found"):
            await shard.draft_letter("nonexistent_template", {})

    @pytest.mark.asyncio
    async def test_draft_stored_template(self, shard, mock_frame):
        """Test draft_letter falls back to stored template."""
        stored_template = LetterTemplate(
            id="stored-1",
            name="Custom Template",
            letter_type=LetterType.CUSTOM,
            description="Test stored template",
            content_template="Dear {{recipient}}, this is about {{topic}}.",
            placeholders=["recipient", "topic"],
            required_placeholders=[],
        )
        shard.get_template = AsyncMock(return_value=stored_template)

        result = await shard.draft_letter("stored-1", {"recipient": "Judge", "topic": "costs"})

        assert "Dear Judge" in result
        assert "costs" in result

    @pytest.mark.asyncio
    async def test_draft_with_unfilled_placeholders(self, shard, mock_frame):
        """Test that unfilled placeholders remain as-is in output."""
        variables = {
            "case_number": "6013156/2024",
            # Missing: directions_date, response_body, party_name
        }

        result = await shard.draft_letter("directions_response", variables)

        assert "6013156/2024" in result
        # Unfilled placeholders remain
        assert "{{directions_date}}" in result

    @pytest.mark.asyncio
    async def test_draft_with_llm_enhancement(self, shard, mock_frame):
        """Test that draft_letter uses LLM enhancement when available."""
        # Set up a mock LLM
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Enhanced letter content with better phrasing.")
        shard._llm = mock_llm

        variables = {
            "case_number": "6013156/2024",
            "directions_date": "1 March 2026",
            "response_body": "Complied.",
            "party_name": "Claimant",
        }

        result = await shard.draft_letter("directions_response", variables)

        # LLM should have been called
        mock_llm.generate.assert_called_once()
        assert "Enhanced letter content" in result

    @pytest.mark.asyncio
    async def test_draft_llm_failure_falls_back(self, shard, mock_frame):
        """Test that LLM failure falls back to raw template."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM error"))
        shard._llm = mock_llm

        variables = {
            "case_number": "6013156/2024",
            "directions_date": "1 March 2026",
            "response_body": "Complied.",
            "party_name": "Claimant",
        }

        result = await shard.draft_letter("directions_response", variables)

        # Should still have the raw template content
        assert "6013156/2024" in result
        assert "1 March 2026" in result

    def test_et_templates_exist(self, shard):
        """Test that all required ET templates are defined."""
        expected = {"directions_response", "disclosure_request", "witness_order", "costs_warning"}
        assert expected == set(shard.ET_LETTER_TEMPLATES.keys())

    def test_et_templates_have_required_fields(self, shard):
        """Test that all ET templates have name, letter_type, and content_template."""
        for key, tmpl in shard.ET_LETTER_TEMPLATES.items():
            assert "name" in tmpl, f"{key} missing name"
            assert "letter_type" in tmpl, f"{key} missing letter_type"
            assert "content_template" in tmpl, f"{key} missing content_template"
            assert "{{" in tmpl["content_template"], f"{key} has no placeholders"


class TestLetterExport:
    """Test letter export functionality."""

    @pytest.mark.asyncio
    async def test_export_letter_txt(self, shard, mock_frame):
        """Test exporting letter to TXT format."""
        # Create a test letter
        test_letter = Letter(
            id="letter-1",
            title="Test Letter",
            letter_type=LetterType.CUSTOM,
            content="This is the letter body.",
            sender_name="John Doe",
            sender_address="123 Oak St",
            recipient_name="Jane Smith",
        )

        shard.get_letter = AsyncMock(return_value=test_letter)
        mock_frame.database.execute = AsyncMock()

        result = await shard.export_letter(
            letter_id="letter-1",
            export_format=ExportFormat.TXT,
        )

        assert result.success is True
        assert result.export_format == ExportFormat.TXT
        assert result.file_path is not None
        assert result.file_size > 0
        assert result.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_export_letter_not_found(self, shard):
        """Test exporting non-existent letter."""
        shard.get_letter = AsyncMock(return_value=None)

        result = await shard.export_letter(
            letter_id="nonexistent",
            export_format=ExportFormat.PDF,
        )

        assert result.success is False
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()


class TestStatistics:
    """Test statistics gathering."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, shard, mock_frame):
        """Test getting statistics."""
        # Mock database responses
        mock_frame.database.fetch_one = AsyncMock(return_value={"count": 42})
        mock_frame.database.fetch_all = AsyncMock(return_value=[])

        stats = await shard.get_statistics()

        assert stats.total_letters == 42
        assert isinstance(stats.by_status, dict)
        assert isinstance(stats.by_type, dict)
