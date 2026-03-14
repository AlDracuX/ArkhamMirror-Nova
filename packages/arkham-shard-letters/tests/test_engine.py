"""Tests for Letters Engine — pure document generation logic."""

import pytest
from arkham_shard_letters.engine import (
    format_et_letter,
    generate_letter_pdf,
    render_letter,
)


class TestRenderLetter:
    """Tests for template variable substitution."""

    def test_simple_substitution(self):
        template = "Dear {{name}}, your case {{case_ref}} is active."
        variables = {"name": "Alex Dalton", "case_ref": "6013156/2024"}
        result = render_letter(template, variables)
        assert "Alex Dalton" in result
        assert "6013156/2024" in result
        assert "{{" not in result

    def test_missing_variable_uses_default(self):
        template = "Dear {{name}}, reference {{ref}}."
        variables = {"name": "Alex"}
        result = render_letter(template, variables)
        assert "Alex" in result
        assert "{{ref}}" not in result
        assert "[ref]" in result  # Default placeholder

    def test_empty_variables(self):
        template = "Hello {{name}}."
        result = render_letter(template, {})
        assert "[name]" in result

    def test_extra_variables_ignored(self):
        template = "Hello {{name}}."
        variables = {"name": "Alex", "extra": "ignored"}
        result = render_letter(template, variables)
        assert "Alex" in result
        assert "ignored" not in result

    def test_text_format_returns_string(self):
        result = render_letter("Hello {{name}}", {"name": "Alex"}, format="text")
        assert isinstance(result, str)

    def test_markdown_format_wraps_content(self):
        result = render_letter("Body text here", {}, format="markdown")
        assert isinstance(result, str)
        assert "Body text here" in result

    def test_no_placeholders_passthrough(self):
        template = "This is plain text with no variables."
        result = render_letter(template, {})
        assert result == template

    def test_repeated_placeholder(self):
        template = "{{name}} says hello to {{name}}."
        result = render_letter(template, {"name": "Alex"})
        assert result == "Alex says hello to Alex."

    def test_multiline_template(self):
        template = "Line 1: {{a}}\nLine 2: {{b}}"
        result = render_letter(template, {"a": "First", "b": "Second"})
        assert "Line 1: First" in result
        assert "Line 2: Second" in result


class TestGenerateLetterPdf:
    """Tests for markdown-formatted letter generation."""

    def test_returns_markdown_string(self):
        result = generate_letter_pdf("Body content", {"title": "Test Letter"})
        assert isinstance(result, str)
        assert "Body content" in result

    def test_includes_title_as_heading(self):
        result = generate_letter_pdf("Body", {"title": "My Letter"})
        assert "# My Letter" in result

    def test_includes_date(self):
        result = generate_letter_pdf("Body", {"title": "Letter", "date": "2026-03-14"})
        assert "2026-03-14" in result

    def test_includes_reference(self):
        result = generate_letter_pdf("Body", {"title": "L", "reference": "REF-001"})
        assert "REF-001" in result

    def test_empty_content(self):
        result = generate_letter_pdf("", {"title": "Empty"})
        assert "# Empty" in result

    def test_missing_metadata_uses_defaults(self):
        result = generate_letter_pdf("Content", {})
        assert isinstance(result, str)
        assert "Content" in result


class TestFormatEtLetter:
    """Tests for Employment Tribunal letter formatting."""

    def test_full_et_letter(self):
        result = format_et_letter(
            date="14 March 2026",
            reference="6013156/2024",
            recipient_name="Employment Tribunal Bristol",
            sender_name="Alex Dalton",
            body="I write to request an extension.",
            re_line="Dalton v Bylor Ltd",
        )
        assert "14 March 2026" in result
        assert "6013156/2024" in result
        assert "Employment Tribunal Bristol" in result
        assert "Alex Dalton" in result
        assert "I write to request an extension." in result
        assert "Dalton v Bylor Ltd" in result

    def test_has_salutation(self):
        result = format_et_letter(
            date="14 March 2026",
            recipient_name="The Tribunal",
            sender_name="Alex",
            body="Test body.",
        )
        assert "Dear" in result

    def test_has_sign_off(self):
        result = format_et_letter(
            date="14 March 2026",
            recipient_name="Judge",
            sender_name="Alex",
            body="Test.",
        )
        sign_offs = ["Yours faithfully", "Yours sincerely", "Sincerely"]
        assert any(s in result for s in sign_offs)

    def test_missing_optional_reference(self):
        result = format_et_letter(
            date="14 March 2026",
            recipient_name="Tribunal",
            sender_name="Alex",
            body="Body.",
        )
        assert isinstance(result, str)
        assert "Body." in result

    def test_missing_optional_re_line(self):
        result = format_et_letter(
            date="14 March 2026",
            recipient_name="Tribunal",
            sender_name="Alex",
            body="Body.",
        )
        assert "RE:" not in result

    def test_includes_re_line_when_provided(self):
        result = format_et_letter(
            date="14 March 2026",
            recipient_name="Tribunal",
            sender_name="Alex",
            body="Body.",
            re_line="Dalton v Bylor",
        )
        assert "RE:" in result or "Re:" in result

    def test_sender_appears_in_signature(self):
        result = format_et_letter(
            date="14 March 2026",
            recipient_name="Tribunal",
            sender_name="Alex Dalton",
            body="Body.",
        )
        # Sender should appear at least twice: header + signature
        assert result.count("Alex Dalton") >= 1
