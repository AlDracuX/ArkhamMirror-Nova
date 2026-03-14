"""Tests for TemplateEngine — TDD RED phase first, then GREEN."""

import pytest
from arkham_shard_templates.engine import TemplateEngine


@pytest.fixture
def engine():
    return TemplateEngine()


class TestTemplateEngineInit:
    def test_engine_instantiates(self, engine):
        assert engine is not None

    def test_engine_is_template_engine(self, engine):
        assert isinstance(engine, TemplateEngine)


class TestExtractVariables:
    def test_single_variable(self, engine):
        result = engine.extract_variables("Hello {{name}}")
        assert result == ["name"]

    def test_multiple_variables(self, engine):
        result = engine.extract_variables("{{first}} and {{second}}")
        assert sorted(result) == ["first", "second"]

    def test_duplicate_variables_deduplicated(self, engine):
        result = engine.extract_variables("{{name}} is {{name}}")
        assert result == ["name"]

    def test_no_variables(self, engine):
        result = engine.extract_variables("Plain text with no variables")
        assert result == []

    def test_empty_string(self, engine):
        result = engine.extract_variables("")
        assert result == []

    def test_spaced_variables(self, engine):
        result = engine.extract_variables("Hello {{ name }}")
        assert result == ["name"]

    def test_underscore_variables(self, engine):
        result = engine.extract_variables("{{first_name}} {{last_name}}")
        assert sorted(result) == ["first_name", "last_name"]

    def test_nested_braces_not_matched(self, engine):
        result = engine.extract_variables("{{{not_a_var}}}")
        # Should still extract the inner variable
        assert "not_a_var" in result

    def test_variable_with_numbers(self, engine):
        result = engine.extract_variables("{{item1}} and {{item2}}")
        assert sorted(result) == ["item1", "item2"]

    def test_single_braces_ignored(self, engine):
        result = engine.extract_variables("{not_a_var}")
        assert result == []


class TestRenderTemplate:
    def test_simple_substitution(self, engine):
        result = engine.render_template("Hello {{name}}", {"name": "Alex"})
        assert result == "Hello Alex"

    def test_multiple_substitutions(self, engine):
        template = "{{greeting}} {{name}}, welcome to {{place}}"
        variables = {"greeting": "Hello", "name": "Alex", "place": "Arkham"}
        result = engine.render_template(template, variables)
        assert result == "Hello Alex, welcome to Arkham"

    def test_undefined_variable_left_untouched(self, engine):
        result = engine.render_template("Hello {{name}}", {})
        assert result == "Hello {{name}}"

    def test_partial_substitution(self, engine):
        result = engine.render_template("{{a}} and {{b}}", {"a": "X"})
        assert result == "X and {{b}}"

    def test_empty_template(self, engine):
        result = engine.render_template("", {"name": "Alex"})
        assert result == ""

    def test_empty_variables(self, engine):
        result = engine.render_template("Hello {{name}}", {})
        assert result == "Hello {{name}}"

    def test_no_placeholders_in_template(self, engine):
        result = engine.render_template("Plain text", {"name": "Alex"})
        assert result == "Plain text"

    def test_spaced_variable_substitution(self, engine):
        result = engine.render_template("Hello {{ name }}", {"name": "Alex"})
        assert result == "Hello Alex"

    def test_duplicate_variable_both_replaced(self, engine):
        result = engine.render_template("{{x}} and {{x}}", {"x": "Y"})
        assert result == "Y and Y"

    def test_value_with_special_characters(self, engine):
        result = engine.render_template("Case: {{ref}}", {"ref": "6013156/2024"})
        assert result == "Case: 6013156/2024"

    def test_multiline_template(self, engine):
        template = "Dear {{name}},\n\nRe: {{case}}\n\nSincerely,\n{{sender}}"
        variables = {"name": "Judge", "case": "Dalton v Bylor", "sender": "Alex"}
        result = engine.render_template(template, variables)
        assert "Dear Judge," in result
        assert "Re: Dalton v Bylor" in result
        assert "Alex" in result

    def test_integer_value_converted(self, engine):
        result = engine.render_template("Count: {{n}}", {"n": 42})
        assert result == "Count: 42"


class TestValidateTemplate:
    def test_all_variables_provided(self, engine):
        result = engine.validate_template("Hello {{name}}", {"name": "Alex"})
        assert result == []

    def test_missing_variable_reported(self, engine):
        result = engine.validate_template("{{a}} and {{b}}", {"a": "X"})
        assert result == ["b"]

    def test_all_missing(self, engine):
        result = engine.validate_template("{{a}} {{b}} {{c}}", {})
        assert sorted(result) == ["a", "b", "c"]

    def test_no_variables_no_errors(self, engine):
        result = engine.validate_template("Plain text", {})
        assert result == []

    def test_empty_template(self, engine):
        result = engine.validate_template("", {"name": "Alex"})
        assert result == []

    def test_extra_variables_not_reported(self, engine):
        result = engine.validate_template("Hello {{name}}", {"name": "Alex", "extra": "ignored"})
        assert result == []

    def test_duplicate_missing_reported_once(self, engine):
        result = engine.validate_template("{{x}} and {{x}}", {})
        assert result == ["x"]


class TestEdgeCases:
    def test_empty_variable_name_not_extracted(self, engine):
        result = engine.extract_variables("{{}}")
        assert result == []

    def test_whitespace_only_variable_not_extracted(self, engine):
        result = engine.extract_variables("{{   }}")
        assert result == []

    def test_render_preserves_non_matching_braces(self, engine):
        result = engine.render_template('JSON: {"key": "value"}', {})
        assert result == 'JSON: {"key": "value"}'

    def test_render_with_none_value(self, engine):
        result = engine.render_template("Value: {{x}}", {"x": None})
        assert result == "Value: None"

    def test_render_with_empty_string_value(self, engine):
        result = engine.render_template("Value: {{x}}", {"x": ""})
        assert result == "Value: "

    def test_complex_litigation_template(self, engine):
        template = (
            "IN THE EMPLOYMENT TRIBUNAL\n"
            "Case No: {{case_number}}\n"
            "BETWEEN:\n"
            "{{claimant}} (Claimant)\n"
            "and\n"
            "{{respondent}} (Respondent)\n"
            "\nDate: {{hearing_date}}"
        )
        variables = {
            "case_number": "6013156/2024",
            "claimant": "Alex Dalton",
            "respondent": "Bylor Ltd",
            "hearing_date": "2026-07-06",
        }
        result = engine.render_template(template, variables)
        assert "6013156/2024" in result
        assert "Alex Dalton" in result
        assert "Bylor Ltd" in result
        assert "2026-07-06" in result
        missing = engine.validate_template(template, variables)
        assert missing == []
