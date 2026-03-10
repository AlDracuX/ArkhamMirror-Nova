"""LLM integration for burden of proof analysis.

Provides AI-assisted features:
- Suggest specific evidence for unmet burden elements
- Assess whether prima facie threshold is met under s.136 EA 2010

Both prompts are specific to UK employment discrimination law.
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
class EvidenceGapSuggestion:
    """A suggested piece of evidence to fill a burden gap."""

    element: str
    suggestion: str
    evidence_type: str = "document"
    priority: str = "high"
    reasoning: str = ""


@dataclass
class PrimaFacieAssessment:
    """Assessment of whether prima facie case is established under s.136."""

    established: bool = False
    confidence: float = 0.0
    reasoning: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPTS = {
    "suggest_evidence": """You are a UK employment law specialist advising on burden of proof.
Your role is to suggest specific, concrete evidence that would help establish unmet burden elements.

Context: Under UK employment discrimination law (Equality Act 2010), the claimant must
first establish facts from which the tribunal could conclude discrimination occurred.
This is the 'prima facie case' under s.136 EA 2010.

Guidelines:
- Suggest 2-4 specific evidence items per unmet element
- Each item should be concrete: a document, witness statement, data, or record
- Prioritise evidence that would be most persuasive to an Employment Tribunal
- Consider what evidence the respondent is likely to hold (disclosure requests)
- Reference relevant case law where applicable (e.g. Igen v Wong, Madarassy v Nomura)
- Be practical -- suggest obtainable evidence, not theoretical ideals

Return JSON array:
[
  {
    "element": "element_name",
    "suggestion": "specific evidence description",
    "evidence_type": "document|witness|data|record|disclosure",
    "priority": "high|medium|low",
    "reasoning": "why this evidence matters"
  }
]""",
    "assess_prima_facie": """You are a UK employment law specialist assessing prima facie case strength.

Under s.136 Equality Act 2010, the burden of proof operates in two stages:
1. The claimant must prove facts from which the tribunal could conclude that discrimination occurred
2. If stage 1 is satisfied, the burden shifts to the respondent to prove non-discrimination

Key case law:
- Igen Ltd v Wong [2005] EWCA Civ 142 -- the two-stage burden shift test
- Madarassy v Nomura International plc [2007] EWCA Civ 33 -- 'could conclude' threshold
- Royal Mail Group v Efobi [2021] UKSC 33 -- claimant's initial burden

Assess whether the claimant has established enough to shift the burden.

Return JSON:
{
  "established": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "detailed legal reasoning",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1"],
  "recommendations": ["recommendation 1"]
}""",
}


# =============================================================================
# LLM Wrapper
# =============================================================================


class BurdenLLM:
    """LLM integration for burden of proof analysis."""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    @property
    def is_available(self) -> bool:
        """Check if LLM service is available."""
        return self.llm_service is not None

    async def _generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Generate LLM response.

        Args:
            system_prompt: System prompt defining behaviour.
            user_prompt: User's request.
            temperature: Sampling temperature (lower for legal analysis).
            max_tokens: Maximum response tokens.

        Returns:
            Response dict with 'text' and 'model' keys.

        Raises:
            RuntimeError: If LLM service is not available.
        """
        if not self.llm_service:
            raise RuntimeError("LLM service not available")

        try:
            response = await self.llm_service.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    def _parse_json_response(self, response: Any) -> Any:
        """Extract and parse JSON from LLM response text."""
        if response is None:
            return None

        text = response.get("text", "") if isinstance(response, dict) else str(response)
        if hasattr(response, "text"):
            text = response.text

        if not text:
            return None

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first [ or { and parsing from there
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass

        logger.warning("Failed to parse JSON from LLM response")
        return None

    # =========================================================================
    # Suggest Evidence for Gaps
    # =========================================================================

    async def suggest_evidence(self, gaps: list[dict], case_context: str = "") -> list[EvidenceGapSuggestion]:
        """Suggest specific evidence for unmet burden elements.

        Args:
            gaps: List of gap dicts from BurdenEngine.gap_analysis().
            case_context: Optional case description for better suggestions.

        Returns:
            List of EvidenceGapSuggestion objects.
        """
        if not gaps:
            return []

        # Build prompt
        gap_lines = []
        for g in gaps:
            gap_lines.append(
                f"- Element: {g.get('element', 'unknown')} "
                f"(Claim: {g.get('claim', 'unknown')}, Status: {g.get('status', 'unmet')})"
            )

        user_prompt = "Suggest specific evidence for the following unmet burden elements:\n\n"
        user_prompt += "\n".join(gap_lines)

        if case_context:
            user_prompt += f"\n\nCase context: {case_context}"

        try:
            response = await self._generate(
                system_prompt=SYSTEM_PROMPTS["suggest_evidence"],
                user_prompt=user_prompt,
            )

            parsed = self._parse_json_response(response)
            if not parsed or not isinstance(parsed, list):
                logger.warning("LLM returned non-list for evidence suggestions")
                return []

            suggestions = []
            for item in parsed:
                suggestions.append(
                    EvidenceGapSuggestion(
                        element=item.get("element", ""),
                        suggestion=item.get("suggestion", ""),
                        evidence_type=item.get("evidence_type", "document"),
                        priority=item.get("priority", "high"),
                        reasoning=item.get("reasoning", ""),
                    )
                )
            return suggestions

        except Exception as e:
            logger.error(f"Evidence suggestion failed: {e}")
            return []

    # =========================================================================
    # Assess Prima Facie Threshold
    # =========================================================================

    async def assess_prima_facie(self, elements: list[dict], case_context: str = "") -> PrimaFacieAssessment:
        """Assess if claimant has established prima facie case under s.136 EA 2010.

        Args:
            elements: List of element dicts with status, evidence_ids, etc.
            case_context: Optional case description.

        Returns:
            PrimaFacieAssessment with legal analysis.
        """
        if not elements:
            return PrimaFacieAssessment(
                established=False,
                confidence=0.0,
                reasoning="No elements provided for assessment.",
            )

        # Build prompt
        element_lines = []
        for e in elements:
            evidence_count = len(e.get("evidence_ids", []))
            element_lines.append(
                f"- {e.get('element', 'unknown')} ({e.get('claim', 'unknown')}): "
                f"status={e.get('status', 'unmet')}, evidence_items={evidence_count}, "
                f"legal_standard={e.get('legal_standard', 'N/A')}"
            )

        user_prompt = "Assess whether the following burden elements establish a prima facie case:\n\n"
        user_prompt += "\n".join(element_lines)

        if case_context:
            user_prompt += f"\n\nCase context: {case_context}"

        try:
            response = await self._generate(
                system_prompt=SYSTEM_PROMPTS["assess_prima_facie"],
                user_prompt=user_prompt,
            )

            parsed = self._parse_json_response(response)
            if not parsed or not isinstance(parsed, dict):
                logger.warning("LLM returned non-dict for prima facie assessment")
                return PrimaFacieAssessment(
                    established=False,
                    reasoning="Failed to parse LLM assessment.",
                )

            return PrimaFacieAssessment(
                established=parsed.get("established", False),
                confidence=parsed.get("confidence", 0.0),
                reasoning=parsed.get("reasoning", ""),
                strengths=parsed.get("strengths", []),
                weaknesses=parsed.get("weaknesses", []),
                recommendations=parsed.get("recommendations", []),
            )

        except Exception as e:
            logger.error(f"Prima facie assessment failed: {e}")
            return PrimaFacieAssessment(
                established=False,
                reasoning=f"Assessment failed: {e}",
            )
