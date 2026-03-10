"""LLM integration for Redline semantic diff analysis.

Provides prompts and parsing for LLM-assisted features:
- Semantic diff analysis: distinguish substantive vs formatting changes
- UK Employment Tribunal document context
"""

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


SEMANTIC_DIFF_SYSTEM_PROMPT = """You are a legal document analysis expert specialising in UK Employment Tribunal cases.
Your task is to compare two versions of a legal document and identify the semantic significance of each change.

Classify each change as one of:
- "substantive": Changes that alter legal meaning, obligations, dates, amounts, parties, or outcomes
- "formatting": Changes to whitespace, punctuation, capitalisation, or layout with no legal effect
- "clarification": Changes that reword without altering legal meaning

For each change, provide:
- change_type: one of "substantive", "formatting", "clarification"
- description: brief description of the change
- significance: float from 0.0 (trivial) to 1.0 (critical legal impact)

Return a JSON array of change objects."""


def build_semantic_diff_prompt(text_a: str, text_b: str) -> str:
    """
    Build the LLM prompt for semantic diff analysis.

    Args:
        text_a: Original document text
        text_b: Revised document text

    Returns:
        Formatted prompt string for LLM
    """
    # Truncate very long documents to avoid token limits
    max_chars = 8000
    if len(text_a) > max_chars:
        text_a = text_a[:max_chars] + "\n... [truncated]"
    if len(text_b) > max_chars:
        text_b = text_b[:max_chars] + "\n... [truncated]"

    return f"""{SEMANTIC_DIFF_SYSTEM_PROMPT}

--- ORIGINAL DOCUMENT ---
{text_a}

--- REVISED DOCUMENT ---
{text_b}

--- ANALYSIS ---
Identify all changes between the original and revised documents.
Return your analysis as a JSON array:
[
  {{"change_type": "substantive|formatting|clarification", "description": "...", "significance": 0.0-1.0}},
  ...
]"""


def parse_semantic_diff_response(response_text: str) -> list[dict]:
    """
    Parse LLM response into structured semantic diff results.

    Args:
        response_text: Raw LLM response text

    Returns:
        List of change dicts with change_type, description, significance
    """
    if not response_text:
        return []

    try:
        # Try to extract JSON from the response
        # LLM may wrap in markdown code blocks
        text = response_text.strip()
        if text.startswith("```"):
            # Remove code block markers
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines)

        results = json.loads(text)
        if not isinstance(results, list):
            results = [results]

        validated = []
        valid_types = {"substantive", "formatting", "clarification"}

        for item in results:
            change_type = item.get("change_type", "substantive")
            if change_type not in valid_types:
                change_type = "substantive"

            significance = item.get("significance", 0.5)
            try:
                significance = max(0.0, min(1.0, float(significance)))
            except (TypeError, ValueError):
                significance = 0.5

            validated.append(
                {
                    "change_type": change_type,
                    "description": str(item.get("description", "")),
                    "significance": significance,
                }
            )

        return validated

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse LLM semantic diff response: {e}")
        return []


@dataclass
class SemanticChange:
    """A semantic change identified by LLM analysis."""

    change_type: str = "substantive"  # substantive | formatting | clarification
    description: str = ""
    significance: float = 0.5
