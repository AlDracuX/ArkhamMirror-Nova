"""LLM integration for Digest shard.

Provides AI-assisted features:
- Case briefing generation (ADHD-friendly format)
- Action item extraction from change logs
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

SYSTEM_PROMPTS = {
    "briefing": """You are a litigation case analyst generating ADHD-friendly briefings.

Format rules:
- Short bullets (1-2 lines max)
- Bold key items with **asterisks**
- Number action steps clearly
- Priority-rank items (most urgent first)
- Use plain language, no legal jargon where possible
- Group by: URGENT, IMPORTANT, FYI

Output JSON with this structure:
{
  "summary": "2-3 sentence overview",
  "priority_items": [
    {"level": "urgent|important|fyi", "text": "short description"}
  ],
  "action_items": ["Action step 1", "Action step 2"],
  "key_changes": ["Change 1", "Change 2"]
}""",
    "action_items": """You are a litigation case analyst identifying urgent action items.

From the provided change log entries, identify items requiring user action.
Focus on:
- Deadline approaching or missed
- Disclosure breaches or gaps
- Rule violations or evasion patterns
- Cost risks or budget concerns
- Evidence gaps that need filling

Return a JSON array of action item strings, most urgent first.
Example: ["File response to disclosure breach by March 15", "Review witness statement gaps"]""",
}


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class BriefingResult:
    """Result from LLM briefing generation."""

    summary: str = ""
    priority_items: list[dict[str, str]] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    key_changes: list[str] = field(default_factory=list)


# =============================================================================
# LLM Service Wrapper
# =============================================================================


class DigestLLM:
    """LLM integration for the Digest shard."""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def generate_briefing_content(self, changes: list[dict], briefing_type: str = "daily") -> BriefingResult:
        """Generate a briefing from change log entries using LLM.

        Falls back to rule-based generation if LLM is unavailable.
        """
        if not self.llm_service or not changes:
            return self._generate_briefing_fallback(changes, briefing_type)

        changes_text = "\n".join(
            f"- [{c.get('action', 'unknown')}] {c.get('entity_type', '')}: {c.get('description', '')}" for c in changes
        )

        prompt = f"""Generate a {briefing_type} case briefing from these recent changes:

{changes_text}

Return ONLY valid JSON matching the required structure."""

        try:
            response = await self.llm_service.generate(
                prompt,
                system_prompt=SYSTEM_PROMPTS["briefing"],
            )
            response_text = response.text if hasattr(response, "text") else str(response)
            data = json.loads(response_text)

            return BriefingResult(
                summary=data.get("summary", ""),
                priority_items=data.get("priority_items", []),
                action_items=data.get("action_items", []),
                key_changes=data.get("key_changes", []),
            )
        except Exception as e:
            logger.error(f"LLM briefing generation failed: {e}")
            return self._generate_briefing_fallback(changes, briefing_type)

    async def extract_action_items_llm(self, changes: list[dict]) -> list[str]:
        """Extract action items from changes using LLM.

        Falls back to pattern matching if LLM is unavailable.
        """
        if not self.llm_service or not changes:
            return []

        changes_text = "\n".join(
            f"- [{c.get('action', 'unknown')}] {c.get('entity_type', '')}: {c.get('description', '')}" for c in changes
        )

        prompt = f"""Identify action items from these change log entries:

{changes_text}

Return ONLY a JSON array of action item strings."""

        try:
            response = await self.llm_service.generate(
                prompt,
                system_prompt=SYSTEM_PROMPTS["action_items"],
            )
            response_text = response.text if hasattr(response, "text") else str(response)
            items = json.loads(response_text)
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error(f"LLM action item extraction failed: {e}")
            return []

    def _generate_briefing_fallback(self, changes: list[dict], briefing_type: str) -> BriefingResult:
        """Rule-based briefing when LLM is unavailable."""
        if not changes:
            return BriefingResult(
                summary=f"No changes recorded for this {briefing_type} briefing.",
                priority_items=[],
                action_items=[],
                key_changes=[],
            )

        # Categorize changes by urgency
        urgent = []
        important = []
        fyi = []

        for change in changes:
            action = change.get("action", "").lower()
            desc = change.get("description", "")
            entity = change.get("entity_type", "")

            if any(kw in action for kw in ("breach", "violation", "evasion")):
                urgent.append({"level": "urgent", "text": desc or f"{entity} {action}"})
            elif any(kw in action for kw in ("deadline", "gap", "risk")):
                important.append({"level": "important", "text": desc or f"{entity} {action}"})
            else:
                fyi.append({"level": "fyi", "text": desc or f"{entity} {action}"})

        priority_items = urgent + important + fyi

        return BriefingResult(
            summary=f"{briefing_type.title()} briefing: {len(changes)} changes recorded. "
            f"{len(urgent)} urgent, {len(important)} important.",
            priority_items=priority_items,
            action_items=[item["text"] for item in urgent],
            key_changes=[c.get("description", "") for c in changes[:10]],
        )
