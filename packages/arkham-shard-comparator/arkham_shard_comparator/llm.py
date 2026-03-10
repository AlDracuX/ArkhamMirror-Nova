"""LLM integration for Comparator shard.

Provides AI-assisted features for UK employment discrimination analysis:
- Identify potential comparators under s.13/s.23 Equality Act 2010
- Assess whether treatment constitutes "less favourable treatment"
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class ComparatorSuggestion:
    """A suggested comparator identified by LLM."""

    name: str
    role: str = ""
    reasoning: str = ""
    comparator_type: str = "actual"  # actual | hypothetical


@dataclass
class TreatmentAssessment:
    """LLM assessment of whether treatment constitutes less favourable treatment."""

    is_less_favourable: bool = False
    reasoning: str = ""
    confidence: float = 0.0
    relevant_factors: list[str] = field(default_factory=list)
    legal_references: list[str] = field(default_factory=list)


# =============================================================================
# Prompts
# =============================================================================

IDENTIFY_COMPARATORS_PROMPT = """You are a UK employment law expert specialising in Equality Act 2010 discrimination claims.

Analyse the following workplace situation and identify potential comparators for a direct discrimination claim under s.13 EA 2010.

Per s.23 EA 2010, a comparator must be in a "materially similar situation" to the claimant except for the protected characteristic. Consider:
1. Actual comparators — real colleagues in comparable roles/circumstances
2. Hypothetical comparators — how a person without the protected characteristic would have been treated

Context:
{context}

Protected characteristic: {characteristic}
Claimant role/position: {claimant_role}

Return a JSON array of potential comparators:
[
  {{
    "name": "Name or description",
    "role": "Their role/position",
    "reasoning": "Why they are a valid comparator under s.23",
    "comparator_type": "actual or hypothetical"
  }}
]

Only return the JSON array, no other text."""

ASSESS_TREATMENT_PROMPT = """You are a UK employment law expert specialising in Equality Act 2010 discrimination claims.

Assess whether the following treatment constitutes "less favourable treatment" under s.13 EA 2010 (direct discrimination).

The test is: was the claimant treated less favourably than a comparator was or would have been treated in materially similar circumstances? The reason for the treatment must be the protected characteristic (the "reason why" test from Nagarajan v London Regional Transport [1999]).

Claimant's treatment:
{claimant_treatment}

Comparator's treatment:
{comparator_treatment}

Incident context:
{context}

Protected characteristic: {characteristic}

Return a JSON object:
{{
  "is_less_favourable": true/false,
  "reasoning": "Detailed legal reasoning",
  "confidence": 0.0-1.0,
  "relevant_factors": ["factor1", "factor2"],
  "legal_references": ["case name or statute reference"]
}}

Only return the JSON object, no other text."""


# =============================================================================
# LLM Wrapper
# =============================================================================


class ComparatorLLM:
    """LLM wrapper for Comparator shard analysis."""

    def __init__(self, llm_service=None):
        self._llm = llm_service

    @property
    def available(self) -> bool:
        """Whether the LLM service is available."""
        return self._llm is not None

    async def identify_comparators(
        self,
        context: str,
        characteristic: str,
        claimant_role: str = "",
    ) -> list[ComparatorSuggestion]:
        """Identify potential comparators using LLM.

        Falls back to empty list if LLM is unavailable.
        """
        if not self._llm:
            logger.warning("LLM service not available for comparator identification")
            return []

        prompt = IDENTIFY_COMPARATORS_PROMPT.format(
            context=context,
            characteristic=characteristic,
            claimant_role=claimant_role,
        )

        try:
            response = await self._llm.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)

            parsed = self._parse_json_array(response_text)
            suggestions = []
            for item in parsed:
                suggestions.append(
                    ComparatorSuggestion(
                        name=item.get("name", "Unknown"),
                        role=item.get("role", ""),
                        reasoning=item.get("reasoning", ""),
                        comparator_type=item.get("comparator_type", "actual"),
                    )
                )
            logger.info(f"LLM identified {len(suggestions)} potential comparators")
            return suggestions

        except Exception as e:
            logger.error(f"LLM comparator identification failed: {e}")
            return []

    async def assess_treatment(
        self,
        claimant_treatment: str,
        comparator_treatment: str,
        context: str = "",
        characteristic: str = "",
    ) -> TreatmentAssessment:
        """Assess whether treatment constitutes less favourable treatment.

        Falls back to neutral assessment if LLM is unavailable.
        """
        if not self._llm:
            logger.warning("LLM service not available for treatment assessment")
            return TreatmentAssessment()

        prompt = ASSESS_TREATMENT_PROMPT.format(
            claimant_treatment=claimant_treatment,
            comparator_treatment=comparator_treatment,
            context=context,
            characteristic=characteristic,
        )

        try:
            response = await self._llm.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)

            parsed = self._parse_json_object(response_text)
            return TreatmentAssessment(
                is_less_favourable=parsed.get("is_less_favourable", False),
                reasoning=parsed.get("reasoning", ""),
                confidence=float(parsed.get("confidence", 0.0)),
                relevant_factors=parsed.get("relevant_factors", []),
                legal_references=parsed.get("legal_references", []),
            )

        except Exception as e:
            logger.error(f"LLM treatment assessment failed: {e}")
            return TreatmentAssessment()

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_array(text: str) -> list[dict]:
        """Extract a JSON array from LLM response text."""
        if not text:
            return []
        # Try direct parse first
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        # Try to find JSON array in text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        """Extract a JSON object from LLM response text."""
        if not text:
            return {}
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}
