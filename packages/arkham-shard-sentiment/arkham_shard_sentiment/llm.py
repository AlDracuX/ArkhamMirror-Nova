"""LLM integration for sentiment analysis.

Provides AI-assisted features:
- Tone classification in employment dispute context
- Tone pattern detection across document series
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS = {
    "classify_tone": """You are a legal communications analyst specialising in employment tribunal cases.
Your role is to classify the tone of communications in employment dispute contexts.

Classify the text into these categories, scoring each 0.0-1.0:
- hostile: threatening, aggressive, intimidating language
- evasive: hedging, vague, non-committal, avoidance of specifics
- condescending: patronising, dismissive, belittling language
- professional: formal, appropriate, business-like communication
- supportive: cooperative, helpful, empathetic language

For each category with score > 0, provide specific evidence segments from the text.

Return JSON format:
{
  "categories": [
    {"category": "hostile", "score": 0.0, "evidence": []},
    {"category": "evasive", "score": 0.0, "evidence": []},
    {"category": "condescending", "score": 0.0, "evidence": []},
    {"category": "professional", "score": 0.0, "evidence": []},
    {"category": "supportive", "score": 0.0, "evidence": []}
  ]
}""",
    "detect_patterns": """You are a legal communications analyst specialising in employment tribunal cases.
Your role is to identify tone shifts and patterns across a series of documents in an employment dispute.

Analyse the document series for:
- Significant shifts in tone between time periods
- Escalation or de-escalation patterns
- Communication style changes that may indicate strategic shifts
- Patterns that might be relevant to tribunal proceedings

Return JSON format:
{
  "patterns": [
    {
      "type": "escalation|de-escalation|shift|consistent",
      "description": "...",
      "period_from": "YYYY-MM",
      "period_to": "YYYY-MM",
      "significance": 0.0-1.0
    }
  ],
  "summary": "Overall narrative of tone progression"
}""",
}


class SentimentLLM:
    """LLM integration for enhanced sentiment analysis."""

    def __init__(self, llm_service=None):
        """
        Initialize LLM integration.

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
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Generate LLM response with error handling.

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
            )

            # Handle both dict and object responses
            if isinstance(response, dict):
                return response
            if hasattr(response, "text"):
                return {"text": response.text, "model": getattr(response, "model", "unknown")}
            return {"text": str(response), "model": "unknown"}

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    def _parse_json_response(self, response: dict[str, Any]) -> dict[str, Any] | None:
        """Parse JSON from LLM response text."""
        text = response.get("text", "")
        if not text:
            return None

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        import re

        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse JSON from LLM response")
        return None

    # ------------------------------------------------------------------
    # Tone Classification
    # ------------------------------------------------------------------

    async def classify_tone(self, text: str) -> list[dict] | None:
        """
        Classify communication tone using LLM.

        Args:
            text: The communication text to classify

        Returns:
            List of {category, score, evidence} dicts, or None on failure
        """
        if not self.is_available:
            return None

        prompt = f"""Classify the tone of the following communication:

---
{text[:4000]}
---

Provide your classification in the JSON format specified."""

        try:
            response = await self._generate(prompt, SYSTEM_PROMPTS["classify_tone"])
            parsed = self._parse_json_response(response)

            if parsed and "categories" in parsed:
                return parsed["categories"]

        except Exception as e:
            logger.error(f"Tone classification failed: {e}")

        return None

    # ------------------------------------------------------------------
    # Tone Pattern Detection
    # ------------------------------------------------------------------

    async def detect_tone_patterns(self, document_summaries: list[dict]) -> dict | None:
        """
        Detect tone patterns across a series of documents.

        Args:
            document_summaries: List of {period, avg_score, text_samples} dicts

        Returns:
            Pattern analysis dict, or None on failure
        """
        if not self.is_available:
            return None

        # Build summary text for LLM
        lines = []
        for doc in document_summaries:
            lines.append(f"Period: {doc.get('period', 'unknown')}")
            lines.append(f"  Average Score: {doc.get('avg_score', 0.0)}")
            if doc.get("text_samples"):
                for sample in doc["text_samples"][:3]:
                    lines.append(f"  Sample: {sample[:200]}")
            lines.append("")

        prompt = f"""Analyse the following document series for tone patterns:

{chr(10).join(lines)}

Identify any significant shifts, escalation, or de-escalation patterns."""

        try:
            response = await self._generate(prompt, SYSTEM_PROMPTS["detect_patterns"])
            parsed = self._parse_json_response(response)
            return parsed

        except Exception as e:
            logger.error(f"Pattern detection failed: {e}")

        return None
