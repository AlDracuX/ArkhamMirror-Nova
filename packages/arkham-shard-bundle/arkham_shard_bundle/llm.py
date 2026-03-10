"""LLM integration for Bundle shard.

Provides AI-assisted features:
- Suggest optimal document ordering per ET Presidential Guidance
- Standard sections: Claim & Response, Case management orders,
  Claimant's documents, Respondent's documents, Witness statements, Authorities
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Standard ET Presidential Guidance section ordering
ET_SECTIONS = [
    "Claim and Response",
    "Case management orders",
    "Claimant's documents",
    "Respondent's documents",
    "Witness statements",
    "Authorities",
]


@dataclass
class OrderingSuggestion:
    """A suggested document ordering from LLM."""

    section: str
    document_ids: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class OrderingResult:
    """Complete ordering suggestion result."""

    sections: list[OrderingSuggestion] = field(default_factory=list)
    ordered_document_ids: list[str] = field(default_factory=list)
    reasoning: str = ""


class BundleLLMIntegration:
    """
    LLM integration for bundle document ordering.

    Works with Frame's LLM service to suggest optimal document
    ordering following ET Presidential Guidance conventions.
    """

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
        """
        Generate LLM response.

        Args:
            system_prompt: System prompt defining behavior.
            user_prompt: User's request.
            temperature: Sampling temperature (low for structured output).
            max_tokens: Maximum response tokens.

        Returns:
            Response dict with 'text' and 'model' keys.
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

    async def suggest_ordering(self, documents: list[dict]) -> OrderingResult:
        """
        Suggest optimal document ordering following ET Presidential Guidance.

        Standard bundle sections:
        1. Claim and Response
        2. Case management orders
        3. Claimant's documents (chronological)
        4. Respondent's documents (chronological)
        5. Witness statements
        6. Authorities

        Args:
            documents: List of document dicts with at minimum 'id' and 'title'.
                       May also include 'type', 'date', 'party', 'description'.

        Returns:
            OrderingResult with sections and ordered document IDs.
        """
        if not self.is_available:
            # Fallback: return documents in original order with no sectioning
            return OrderingResult(
                sections=[],
                ordered_document_ids=[d.get("id", d.get("document_id", "")) for d in documents],
                reasoning="LLM not available - returning original order",
            )

        system_prompt = """You are an expert Employment Tribunal (ET) bundle organiser.
Your task is to organise hearing bundle documents following the ET Presidential Guidance.

Standard bundle sections (in order):
1. Claim and Response (ET1, ET3, any amendments)
2. Case management orders (tribunal orders, unless orders, case management agendas)
3. Claimant's documents (in chronological order)
4. Respondent's documents (in chronological order)
5. Witness statements
6. Authorities (legal cases, statutes, ACAS code of practice)

Rules:
- Every document must appear in exactly one section.
- Within each section, order chronologically unless stated otherwise.
- If a document's section is unclear, place it in the closest matching section.
- Return ONLY valid JSON, no commentary."""

        doc_descriptions = []
        for d in documents:
            doc_id = d.get("id", d.get("document_id", "unknown"))
            title = d.get("title", d.get("document_title", "Untitled"))
            doc_type = d.get("type", d.get("document_type", ""))
            date = d.get("date", d.get("document_date", ""))
            party = d.get("party", "")
            desc = f"ID: {doc_id} | Title: {title}"
            if doc_type:
                desc += f" | Type: {doc_type}"
            if date:
                desc += f" | Date: {date}"
            if party:
                desc += f" | Party: {party}"
            doc_descriptions.append(desc)

        user_prompt = f"""Organise these {len(documents)} documents into ET Presidential Guidance bundle sections.

Documents:
{chr(10).join(doc_descriptions)}

Return JSON:
{{
  "sections": [
    {{
      "section": "Section name",
      "document_ids": ["id1", "id2"],
      "reasoning": "Why these documents belong here"
    }}
  ],
  "reasoning": "Overall ordering rationale"
}}"""

        try:
            response = await self._generate(system_prompt, user_prompt)
            response_text = (
                response.get("text", "") if isinstance(response, dict) else getattr(response, "text", str(response))
            )

            # Parse JSON
            result_data = json.loads(response_text) if response_text else {}

            sections = []
            ordered_ids = []
            for s in result_data.get("sections", []):
                suggestion = OrderingSuggestion(
                    section=s.get("section", ""),
                    document_ids=s.get("document_ids", []),
                    reasoning=s.get("reasoning", ""),
                )
                sections.append(suggestion)
                ordered_ids.extend(suggestion.document_ids)

            return OrderingResult(
                sections=sections,
                ordered_document_ids=ordered_ids,
                reasoning=result_data.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"LLM ordering suggestion failed: {e}")
            # Fallback
            return OrderingResult(
                sections=[],
                ordered_document_ids=[d.get("id", d.get("document_id", "")) for d in documents],
                reasoning=f"LLM failed ({e}) - returning original order",
            )
