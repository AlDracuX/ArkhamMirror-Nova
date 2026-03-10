"""LLM integration for Costs shard.

Provides AI-assisted features:
- Draft costs application text under Rule 76 ET Rules
- Assess strength of costs argument

All methods gracefully degrade when LLM service is unavailable.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Response models
# =============================================================================


@dataclass
class DraftApplicationResult:
    """Result of a costs application draft."""

    text: str
    rule_references: list[str]
    success: bool = True
    error: str = ""


@dataclass
class StrengthAssessment:
    """Result of a costs argument strength assessment."""

    strength: str  # weak, moderate, strong, very_strong
    reasoning: str
    recommendations: list[str]
    success: bool = True
    error: str = ""


# =============================================================================
# Prompts
# =============================================================================

DRAFT_APPLICATION_PROMPT = """You are a UK Employment Tribunal costs specialist.
Draft a costs application under Rule 76 of the Employment Tribunals (Constitution and Rules of Procedure) Regulations 2013.

The application is based on the following conduct by the respondent:

{conduct_summary}

Time costs claimed: {time_total}
Expenses claimed: {expense_total}
Total amount claimed: {total_claimed}

Requirements:
1. Cite Rule 76(1)(a) and/or (b) as appropriate
2. Reference specific conduct instances with dates
3. Follow the standard ET costs application structure
4. Be precise about the legal test for unreasonable conduct
5. Include a prayer for relief specifying the amount claimed

Return a JSON object with:
{{
    "application_text": "Full text of the drafted application",
    "rule_references": ["Rule 76(1)(a)", "Rule 76(1)(b)"]
}}"""

ASSESS_STRENGTH_PROMPT = """You are a UK Employment Tribunal costs specialist.
Assess the strength of the following costs argument.

Conduct log summary:
{conduct_summary}

Scoring data:
- Total conduct score: {total_score}
- Conduct entries: {conduct_count}
- Costs basis strength rating: {costs_basis_strength}

Time and expenses:
- Time costs: {time_total}
- Expenses: {expense_total}
- Total claimed: {total_claimed}

Evaluate the argument considering:
1. Whether the conduct meets the "unreasonable" threshold under Rule 76(1)(a)
2. Whether any conduct constitutes non-compliance with tribunal orders under Rule 76(1)(b)
3. The proportionality of the amount claimed
4. Likelihood of success based on ET case law

Return a JSON object with:
{{
    "strength": "weak|moderate|strong|very_strong",
    "reasoning": "Detailed reasoning",
    "recommendations": ["List of recommendations to strengthen the application"]
}}"""


# =============================================================================
# CostsLLM class
# =============================================================================


class CostsLLM:
    """LLM integration for costs analysis and drafting."""

    def __init__(self, llm_service=None):
        self._llm = llm_service

    @property
    def available(self) -> bool:
        """Check if LLM service is available."""
        return self._llm is not None

    async def draft_application(
        self,
        conduct_summary: str,
        time_total: float,
        expense_total: float,
        total_claimed: float,
    ) -> DraftApplicationResult:
        """Draft a costs application under Rule 76 ET Rules.

        Args:
            conduct_summary: Summary of respondent conduct instances
            time_total: Total time costs claimed
            expense_total: Total expenses claimed
            total_claimed: Grand total amount claimed

        Returns:
            DraftApplicationResult with application text and rule references.
        """
        if not self._llm:
            return DraftApplicationResult(
                text="",
                rule_references=[],
                success=False,
                error="LLM service not available",
            )

        prompt = DRAFT_APPLICATION_PROMPT.format(
            conduct_summary=conduct_summary,
            time_total=f"{time_total:.2f}",
            expense_total=f"{expense_total:.2f}",
            total_claimed=f"{total_claimed:.2f}",
        )

        try:
            response = await self._llm.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)
            result = json.loads(response_text) if response_text else {}

            return DraftApplicationResult(
                text=result.get("application_text", ""),
                rule_references=result.get("rule_references", []),
                success=True,
            )
        except Exception as e:
            logger.error(f"LLM draft application failed: {e}")
            return DraftApplicationResult(
                text="",
                rule_references=[],
                success=False,
                error=str(e),
            )

    async def assess_strength(
        self,
        conduct_summary: str,
        total_score: int,
        conduct_count: int,
        costs_basis_strength: str,
        time_total: float,
        expense_total: float,
        total_claimed: float,
    ) -> StrengthAssessment:
        """Assess the strength of a costs argument.

        Args:
            conduct_summary: Summary of respondent conduct
            total_score: Weighted conduct score
            conduct_count: Number of conduct entries
            costs_basis_strength: Current strength rating
            time_total: Total time costs
            expense_total: Total expenses
            total_claimed: Grand total

        Returns:
            StrengthAssessment with strength rating, reasoning, and recommendations.
        """
        if not self._llm:
            return StrengthAssessment(
                strength="unknown",
                reasoning="LLM service not available for assessment",
                recommendations=["Enable LLM service for AI-assisted strength assessment"],
                success=False,
                error="LLM service not available",
            )

        prompt = ASSESS_STRENGTH_PROMPT.format(
            conduct_summary=conduct_summary,
            total_score=total_score,
            conduct_count=conduct_count,
            costs_basis_strength=costs_basis_strength,
            time_total=f"{time_total:.2f}",
            expense_total=f"{expense_total:.2f}",
            total_claimed=f"{total_claimed:.2f}",
        )

        try:
            response = await self._llm.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)
            result = json.loads(response_text) if response_text else {}

            return StrengthAssessment(
                strength=result.get("strength", "unknown"),
                reasoning=result.get("reasoning", ""),
                recommendations=result.get("recommendations", []),
                success=True,
            )
        except Exception as e:
            logger.error(f"LLM strength assessment failed: {e}")
            return StrengthAssessment(
                strength="unknown",
                reasoning=f"Assessment failed: {e}",
                recommendations=[],
                success=False,
                error=str(e),
            )
