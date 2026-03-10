"""LLM integration for the Rules shard.

Provides AI-assisted features:
- Date extraction from tribunal orders/judgments
- Applicable rule suggestion from situation descriptions
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPTS: dict[str, str] = {
    "extract_dates": """You are a legal date extraction specialist for UK Employment Tribunal proceedings.

Given a tribunal order, judgment, or correspondence, extract ALL dates mentioned along with their legal significance.

For each date, identify:
1. The date itself (ISO format: YYYY-MM-DD)
2. What the date represents (e.g., "hearing date", "compliance deadline", "order date")
3. Which ET Rule it relates to (if identifiable)
4. Whether it creates a deadline for either party

Return JSON array:
[
  {
    "date": "YYYY-MM-DD",
    "description": "what this date represents",
    "rule_reference": "Rule N or null",
    "creates_deadline": true/false,
    "deadline_for": "claimant|respondent|both|tribunal|null",
    "notes": "any additional context"
  }
]

Be precise. Only extract dates that are explicitly stated or clearly calculable from the text.
Do not invent dates. If a date is ambiguous, note this in the notes field.""",
    "suggest_rules": """You are a UK Employment Tribunal procedural rules expert.

Given a description of a situation in ET proceedings, identify which Employment Tribunal Rules of Procedure 2013 (SI 2013/1237) are most relevant.

For each applicable rule, provide:
1. The rule number (e.g., "Rule 37", "Rule 76")
2. The rule title
3. Why it applies to this situation
4. Any deadlines triggered
5. Risk assessment (what happens if not complied with)

Return JSON array:
[
  {
    "rule_number": "Rule N",
    "title": "Rule title",
    "relevance": "Why this rule applies",
    "deadline_days": N or null,
    "deadline_type": "calendar_days|working_days|months|weeks",
    "risk": "Consequence of non-compliance"
  }
]

Prioritise the most directly applicable rules. Include Practice Directions where relevant.
Consider both the immediate procedural requirements and any knock-on implications.""",
}


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class ExtractedDate:
    """A date extracted from a tribunal document."""

    date: str
    description: str
    rule_reference: str | None = None
    creates_deadline: bool = False
    deadline_for: str | None = None
    notes: str = ""


@dataclass
class SuggestedRule:
    """A rule suggested as applicable to a situation."""

    rule_number: str
    title: str
    relevance: str
    deadline_days: int | None = None
    deadline_type: str = "calendar_days"
    risk: str = ""


# =============================================================================
# LLM Wrapper
# =============================================================================


class RulesLLM:
    """LLM wrapper for Rules shard AI-assisted features."""

    def __init__(self, llm_service=None):
        self._llm = llm_service

    @property
    def available(self) -> bool:
        """Check if LLM service is available."""
        return self._llm is not None

    async def extract_dates(self, document_text: str) -> list[ExtractedDate]:
        """Extract dates and their legal significance from a tribunal document.

        Falls back to regex-based extraction if LLM is unavailable.
        """
        if not self._llm:
            logger.warning("LLM not available, using regex date extraction")
            return self._extract_dates_regex(document_text)

        try:
            response = await self._llm.generate(
                prompt=f"Extract all dates from this tribunal document:\n\n{document_text}",
                system_prompt=SYSTEM_PROMPTS["extract_dates"],
            )

            response_text = response.text if hasattr(response, "text") else str(response)
            dates_data = self._parse_json_response(response_text)

            return [
                ExtractedDate(
                    date=d.get("date", ""),
                    description=d.get("description", ""),
                    rule_reference=d.get("rule_reference"),
                    creates_deadline=d.get("creates_deadline", False),
                    deadline_for=d.get("deadline_for"),
                    notes=d.get("notes", ""),
                )
                for d in dates_data
                if d.get("date")
            ]

        except Exception as e:
            logger.error(f"LLM date extraction failed: {e}")
            return self._extract_dates_regex(document_text)

    async def suggest_rules(self, situation: str) -> list[SuggestedRule]:
        """Suggest applicable ET Rules for a described situation.

        Falls back to empty list if LLM is unavailable.
        """
        if not self._llm:
            logger.warning("LLM not available for rule suggestion")
            return []

        try:
            response = await self._llm.generate(
                prompt=f"What ET Rules apply to this situation?\n\n{situation}",
                system_prompt=SYSTEM_PROMPTS["suggest_rules"],
            )

            response_text = response.text if hasattr(response, "text") else str(response)
            rules_data = self._parse_json_response(response_text)

            return [
                SuggestedRule(
                    rule_number=r.get("rule_number", ""),
                    title=r.get("title", ""),
                    relevance=r.get("relevance", ""),
                    deadline_days=r.get("deadline_days"),
                    deadline_type=r.get("deadline_type", "calendar_days"),
                    risk=r.get("risk", ""),
                )
                for r in rules_data
                if r.get("rule_number")
            ]

        except Exception as e:
            logger.error(f"LLM rule suggestion failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Fallback: regex-based date extraction
    # ------------------------------------------------------------------

    def _extract_dates_regex(self, text: str) -> list[ExtractedDate]:
        """Extract dates using regex patterns when LLM is unavailable."""
        dates: list[ExtractedDate] = []

        # Pattern: DD Month YYYY or DD/MM/YYYY
        patterns = [
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            r"(\d{1,2})/(\d{1,2})/(\d{4})",
        ]

        month_map = {
            "January": "01",
            "February": "02",
            "March": "03",
            "April": "04",
            "May": "05",
            "June": "06",
            "July": "07",
            "August": "08",
            "September": "09",
            "October": "10",
            "November": "11",
            "December": "12",
        }

        # Named month pattern
        for match in re.finditer(patterns[0], text):
            day = match.group(1).zfill(2)
            month = month_map[match.group(2)]
            year = match.group(3)
            iso_date = f"{year}-{month}-{day}"

            # Try to determine context from surrounding text
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end]

            dates.append(
                ExtractedDate(
                    date=iso_date,
                    description=f"Date found in context: {context.strip()}",
                    creates_deadline=any(kw in context.lower() for kw in ["by", "before", "no later than", "deadline"]),
                )
            )

        # Numeric date pattern DD/MM/YYYY
        for match in re.finditer(patterns[1], text):
            day = match.group(1).zfill(2)
            month = match.group(2).zfill(2)
            year = match.group(3)
            iso_date = f"{year}-{month}-{day}"

            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end]

            dates.append(
                ExtractedDate(
                    date=iso_date,
                    description=f"Date found in context: {context.strip()}",
                    creates_deadline=any(kw in context.lower() for kw in ["by", "before", "no later than", "deadline"]),
                )
            )

        return dates

    # ------------------------------------------------------------------
    # JSON parsing helper
    # ------------------------------------------------------------------

    def _parse_json_response(self, text: str) -> list[dict]:
        """Parse JSON array from LLM response, handling markdown fences."""
        if not text:
            return []

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
            return [result] if isinstance(result, dict) else []
        except json.JSONDecodeError:
            # Try to find JSON array in the text
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Failed to parse LLM JSON response: {text[:200]}")
            return []
