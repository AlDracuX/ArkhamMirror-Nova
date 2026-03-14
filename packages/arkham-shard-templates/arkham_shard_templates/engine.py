"""
TemplateEngine — Pure algorithmic template rendering with {{variable}} syntax.

No Jinja2 dependency. Uses regex for variable extraction and substitution.
Stdlib only, under 200 LOC.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# Match {{variable}}, {{ variable }}, {{var_name}}, {{ var_123 }}
_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class TemplateEngine:
    """Template engine with {{variable}} placeholder rendering and validation."""

    def extract_variables(self, template_text: str) -> List[str]:
        """
        Extract all unique {{variable}} placeholder names from template text.

        Args:
            template_text: Template string with {{variable}} placeholders.

        Returns:
            Sorted, deduplicated list of variable names.
        """
        if not template_text:
            return []

        matches = _VAR_PATTERN.findall(template_text)
        # Deduplicate preserving first-occurrence order
        seen: set[str] = set()
        result: list[str] = []
        for name in matches:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def render_template(self, template_text: str, variables: Dict[str, Any]) -> str:
        """
        Render a template by substituting {{variable}} placeholders.

        Unknown placeholders are left untouched. Values are converted to str.

        Args:
            template_text: Template string with {{variable}} placeholders.
            variables: Mapping of variable names to values.

        Returns:
            Rendered string with known placeholders replaced.
        """
        if not template_text:
            return ""

        def _replacer(match: re.Match) -> str:
            name = match.group(1)
            if name in variables:
                return str(variables[name])
            return match.group(0)  # Leave unknown placeholders untouched

        return _VAR_PATTERN.sub(_replacer, template_text)

    def validate_template(self, template_text: str, variables: Dict[str, Any]) -> List[str]:
        """
        Check for undefined variables — placeholders in template not in variables.

        Args:
            template_text: Template string with {{variable}} placeholders.
            variables: Mapping of provided variable names to values.

        Returns:
            Sorted list of placeholder names that are missing from variables.
        """
        required = self.extract_variables(template_text)
        missing = [name for name in required if name not in variables]
        return sorted(missing)
