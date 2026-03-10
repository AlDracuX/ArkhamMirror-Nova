"""LLM integration for Disclosure analysis.

Provides AI-assisted features:
- Document classification against disclosure request categories
- Extraction of disclosure categories and deadlines from tribunal orders
"""

import json
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPTS = {
    "classify_document": """You are a legal document classifier for Employment Tribunal disclosure proceedings.
Given a document's metadata and a list of disclosure request categories, determine which requests
this document is relevant to.

Return a JSON object with format:
{
    "matches": [
        {"request_id": "...", "confidence": 0.0-1.0, "reason": "..."}
    ]
}

Only include matches with confidence >= 0.5. If no matches, return {"matches": []}.
Be precise - disclosure in employment tribunals must be specific and relevant.""",
    "extract_categories": """You are a legal analyst extracting disclosure categories from Employment Tribunal orders.
Given the text of a tribunal order, extract each disclosure category with its deadline.

Return a JSON object with format:
{
    "categories": [
        {
            "category": "...",
            "description": "...",
            "deadline": "YYYY-MM-DD or null",
            "requesting_party": "claimant or respondent"
        }
    ]
}

Be thorough - extract every distinct disclosure obligation mentioned in the order.""",
}


# =============================================================================
# LLM Helper
# =============================================================================


class DisclosureLLMHelper:
    """LLM integration wrapper for disclosure analysis tasks."""

    def __init__(self, llm_service):
        """
        Initialize the LLM helper.

        Args:
            llm_service: The frame LLM service for generating responses
        """
        self._llm = llm_service

    @property
    def available(self) -> bool:
        """Check if LLM service is available."""
        return self._llm is not None

    async def classify_document(
        self,
        document_metadata: dict,
        request_categories: list[dict],
    ) -> list[str]:
        """Classify a document against disclosure request categories.

        Args:
            document_metadata: Document info (category, title, text)
            request_categories: List of {request_id, category, description}

        Returns:
            List of matching request_ids

        Raises:
            Exception: If LLM call fails
        """
        if not self._llm:
            raise RuntimeError("LLM service not available")

        categories_text = "\n".join(
            f"- Request {c['request_id']}: {c['category']} - {c.get('description', '')}" for c in request_categories
        )

        prompt = f"""Classify this document against the following disclosure requests.

Document:
- Category: {document_metadata.get("category", "unknown")}
- Title: {document_metadata.get("title", "untitled")}
- Summary: {document_metadata.get("text", "")[:500]}

Disclosure Requests:
{categories_text}

Which requests does this document satisfy or partially satisfy?"""

        response = await self._llm.generate(
            prompt,
            system_prompt=SYSTEM_PROMPTS["classify_document"],
        )

        # Parse response
        response_text = response.text if hasattr(response, "text") else str(response)
        result = _parse_json_response(response_text)

        matches = result.get("matches", [])
        return [m["request_id"] for m in matches if m.get("confidence", 0) >= 0.5]

    async def extract_categories_from_order(self, order_text: str) -> list[dict]:
        """Extract disclosure categories and deadlines from a tribunal order.

        Args:
            order_text: The text of the tribunal order

        Returns:
            List of category dicts with {category, description, deadline, requesting_party}
        """
        if not self._llm:
            raise RuntimeError("LLM service not available")

        prompt = f"""Extract all disclosure categories and deadlines from this tribunal order:

{order_text[:2000]}

List each distinct disclosure obligation with its deadline and which party must provide it."""

        response = await self._llm.generate(
            prompt,
            system_prompt=SYSTEM_PROMPTS["extract_categories"],
        )

        response_text = response.text if hasattr(response, "text") else str(response)
        result = _parse_json_response(response_text)

        return result.get("categories", [])


# =============================================================================
# Helpers
# =============================================================================


def _parse_json_response(text: str) -> dict:
    """Parse a JSON response from LLM, handling markdown code blocks.

    Args:
        text: Raw response text

    Returns:
        Parsed dict, or empty dict on failure
    """
    if not text:
        return {}

    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (code fences)
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1])
        elif len(lines) == 2:
            cleaned = lines[1] if not lines[1].startswith("```") else ""

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse LLM JSON response: {text[:200]}")
        return {}
