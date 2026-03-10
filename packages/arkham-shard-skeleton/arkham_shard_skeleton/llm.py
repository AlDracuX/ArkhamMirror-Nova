"""LLM integration for Skeleton shard.

Provides AI-assisted features:
- Drafting argument sections with numbered paragraphs and legal citations
- Suggesting argument tree structure from claim type
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
class DraftedSection:
    """A drafted argument section from LLM."""

    heading: str
    paragraphs: list[str] = field(default_factory=list)
    authority_citations: list[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class SuggestedStructure:
    """A suggested argument tree structure from LLM."""

    claim_type: str
    elements: list[dict[str, str]] = field(default_factory=list)
    suggested_authorities: list[str] = field(default_factory=list)
    raw_text: str = ""


# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPTS = {
    "draft_section": """You are a UK Employment Tribunal legal drafter.
Your task is to draft a section of a skeleton argument following these conventions:

- Use numbered paragraphs (1., 2., 3., etc.)
- Cite authorities using neutral citations (e.g. [2024] UKSC 1)
- Reference bundle pages as [p.X] where X is the page number
- Use precise, concise legal language
- Structure: proposition of law -> authority -> application to facts -> evidence reference
- Do NOT include any preamble or explanation outside the drafted text

Return your draft as a JSON object:
{
  "heading": "Section heading",
  "paragraphs": ["1. First paragraph...", "2. Second paragraph..."],
  "authority_citations": ["Case Name [Year] Court Ref"]
}""",
    "suggest_structure": """You are a UK Employment Tribunal legal strategist.
Given a claim type, suggest the optimal argument tree structure.

For each element of the legal test, identify:
- The element name (e.g. "Qualifying Disclosure" for whistleblowing)
- The legal test to satisfy
- Key authorities that establish or clarify the test
- Types of evidence typically needed

Return your suggestion as a JSON object:
{
  "claim_type": "the claim type",
  "elements": [
    {"name": "Element name", "test": "Legal test description", "key_authority": "Leading case"},
    ...
  ],
  "suggested_authorities": ["Authority 1", "Authority 2"]
}""",
}


# =============================================================================
# LLM Integration Class
# =============================================================================


class SkeletonLLMIntegration:
    """LLM integration for skeleton argument drafting.

    Works with Frame's LLM service to provide AI-assisted argument drafting.
    """

    def __init__(self, llm_service=None):
        """Initialize LLM integration.

        Args:
            llm_service: Frame's LLM service instance
        """
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
            system_prompt: System prompt defining behavior
            user_prompt: User's request
            temperature: Sampling temperature (lower for legal precision)
            max_tokens: Maximum response tokens

        Returns:
            Response dict with 'text' and 'model' keys
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

    def _parse_json_response(self, response: Any) -> dict:
        """Extract JSON from LLM response, handling markdown fences."""
        text = response.text if hasattr(response, "text") else str(response)
        if not text:
            return {}

        # Strip markdown code fences
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response")
            return {}

    # =========================================================================
    # Draft Argument Section
    # =========================================================================

    async def draft_section(
        self,
        heading: str,
        claim_summary: str,
        legal_test: str = "",
        evidence_summaries: list[str] | None = None,
        authority_citations: list[str] | None = None,
        bundle_refs: dict[str, int] | None = None,
    ) -> DraftedSection:
        """Draft an argument section using LLM.

        Args:
            heading: Section heading
            claim_summary: Summary of the claim being argued
            legal_test: The legal test to apply
            evidence_summaries: Brief descriptions of available evidence
            authority_citations: Available authority citations
            bundle_refs: Mapping of document_id -> bundle page number

        Returns:
            DraftedSection with structured output
        """
        prompt_parts = [
            f"Section Heading: {heading}",
            f"Claim Summary: {claim_summary}",
        ]

        if legal_test:
            prompt_parts.append(f"Legal Test: {legal_test}")

        if evidence_summaries:
            prompt_parts.append("Available Evidence:")
            for i, ev in enumerate(evidence_summaries, 1):
                prompt_parts.append(f"  {i}. {ev}")

        if authority_citations:
            prompt_parts.append("Available Authorities:")
            for auth in authority_citations:
                prompt_parts.append(f"  - {auth}")

        if bundle_refs:
            prompt_parts.append("Bundle Page References:")
            for doc_id, page in bundle_refs.items():
                prompt_parts.append(f"  {doc_id}: p.{page}")

        user_prompt = "\n".join(prompt_parts)

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["draft_section"],
            user_prompt=user_prompt,
        )

        data = self._parse_json_response(response)

        return DraftedSection(
            heading=data.get("heading", heading),
            paragraphs=data.get("paragraphs", []),
            authority_citations=data.get("authority_citations", []),
            raw_text=response.text if hasattr(response, "text") else str(response),
        )

    # =========================================================================
    # Suggest Argument Structure
    # =========================================================================

    async def suggest_structure(
        self,
        claim_type: str,
        context: str = "",
    ) -> SuggestedStructure:
        """Suggest argument tree structure for a given claim type.

        Args:
            claim_type: Type of claim (e.g. "unfair dismissal", "discrimination")
            context: Additional context about the case

        Returns:
            SuggestedStructure with elements and authorities
        """
        prompt_parts = [
            f"Claim Type: {claim_type}",
        ]
        if context:
            prompt_parts.append(f"Case Context: {context}")

        user_prompt = "\n".join(prompt_parts)

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["suggest_structure"],
            user_prompt=user_prompt,
        )

        data = self._parse_json_response(response)

        return SuggestedStructure(
            claim_type=data.get("claim_type", claim_type),
            elements=data.get("elements", []),
            suggested_authorities=data.get("suggested_authorities", []),
            raw_text=response.text if hasattr(response, "text") else str(response),
        )
