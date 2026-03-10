"""LLM integration for Comms shard analysis.

Provides AI-assisted features:
- Communication pattern analysis (coordination, evasion, obstruction)
- Message intent classification (tactical intent of each message)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class PatternAnalysis:
    """Result of analysing communication patterns in a thread."""

    patterns_detected: list[dict[str, Any]] = field(default_factory=list)
    overall_assessment: str = ""
    confidence: float = 0.0
    raw_response: str = ""


@dataclass
class MessageIntent:
    """Classified tactical intent of a message."""

    message_id: str = ""
    intent: str = "informational"  # informational | directive | evasive | escalatory | conciliatory | obstructive
    confidence: float = 0.0
    reasoning: str = ""


# =============================================================================
# Prompts
# =============================================================================


PATTERN_ANALYSIS_PROMPT = """Analyze the following email thread for communication patterns
relevant to litigation. Look for:

1. **Coordination**: Are multiple parties coordinating responses? Look for
   similar language, synchronized timing, or aligned positions that suggest
   pre-arrangement.

2. **Evasion**: Is anyone avoiding answering direct questions, deflecting,
   or providing non-responsive answers?

3. **Obstruction**: Is anyone delaying, creating procedural barriers, or
   making information harder to access?

4. **Selective disclosure**: Are there signs that information is being
   withheld from certain participants?

Thread messages:
{thread_text}

Return a JSON object with format:
{{
  "patterns": [
    {{
      "type": "coordination|evasion|obstruction|selective_disclosure",
      "description": "...",
      "messages_involved": ["msg_id_1", "msg_id_2"],
      "confidence": 0.0-1.0,
      "legal_significance": "..."
    }}
  ],
  "overall_assessment": "...",
  "confidence": 0.0-1.0
}}"""


MESSAGE_INTENT_PROMPT = """Classify the tactical intent of each message in
this email thread. For each message, determine:

- **informational**: Neutral sharing of facts or updates
- **directive**: Giving instructions or assigning actions
- **evasive**: Avoiding answering, deflecting, or providing non-responses
- **escalatory**: Raising stakes, making threats, or increasing tension
- **conciliatory**: Attempting resolution, de-escalation, or compromise
- **obstructive**: Creating barriers, delaying, or making things harder

Messages:
{messages_text}

Return a JSON array:
[
  {{
    "message_id": "...",
    "intent": "informational|directive|evasive|escalatory|conciliatory|obstructive",
    "confidence": 0.0-1.0,
    "reasoning": "..."
  }}
]"""


# =============================================================================
# LLM Wrapper
# =============================================================================


class CommsLLM:
    """
    LLM wrapper for communication analysis.

    Gracefully degrades when LLM service is unavailable --
    returns empty/default results instead of raising errors.
    """

    def __init__(self, llm_service=None):
        """
        Initialize the LLM wrapper.

        Args:
            llm_service: Frame LLM service. If None, all methods return defaults.
        """
        self._llm = llm_service

    @property
    def available(self) -> bool:
        """Whether LLM analysis is available."""
        return self._llm is not None

    async def analyze_patterns(self, thread_messages: list[dict]) -> PatternAnalysis:
        """
        Analyze communication patterns in a thread.

        Args:
            thread_messages: List of message dicts with id, from, to, body_summary, date.

        Returns:
            PatternAnalysis with detected patterns. Empty if LLM unavailable.
        """
        if not self._llm:
            logger.debug("LLM not available -- skipping pattern analysis")
            return PatternAnalysis()

        # Format thread text for the prompt
        thread_text = self._format_thread(thread_messages)
        prompt = PATTERN_ANALYSIS_PROMPT.format(thread_text=thread_text)

        try:
            response = await self._llm.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)

            parsed = json.loads(response_text) if response_text else {}

            return PatternAnalysis(
                patterns_detected=parsed.get("patterns", []),
                overall_assessment=parsed.get("overall_assessment", ""),
                confidence=parsed.get("confidence", 0.0),
                raw_response=response_text,
            )

        except Exception as e:
            logger.error(f"LLM pattern analysis failed: {e}")
            return PatternAnalysis()

    async def classify_intents(self, messages: list[dict]) -> list[MessageIntent]:
        """
        Classify the tactical intent of each message.

        Args:
            messages: List of message dicts with id, from, body_summary.

        Returns:
            List of MessageIntent objects. Empty if LLM unavailable.
        """
        if not self._llm:
            logger.debug("LLM not available -- skipping intent classification")
            return []

        messages_text = self._format_messages(messages)
        prompt = MESSAGE_INTENT_PROMPT.format(messages_text=messages_text)

        try:
            response = await self._llm.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)

            parsed = json.loads(response_text) if response_text else []

            return [
                MessageIntent(
                    message_id=item.get("message_id", ""),
                    intent=item.get("intent", "informational"),
                    confidence=item.get("confidence", 0.0),
                    reasoning=item.get("reasoning", ""),
                )
                for item in parsed
            ]

        except Exception as e:
            logger.error(f"LLM intent classification failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_thread(self, messages: list[dict]) -> str:
        """Format thread messages for prompt inclusion."""
        lines = []
        for msg in messages:
            lines.append(
                f"[{msg.get('id', 'unknown')}] "
                f"From: {msg.get('from_address', 'unknown')} | "
                f"To: {msg.get('to_addresses', [])} | "
                f"Date: {msg.get('sent_at', 'unknown')}\n"
                f"  {msg.get('body_summary', '(no content)')}"
            )
        return "\n\n".join(lines)

    def _format_messages(self, messages: list[dict]) -> str:
        """Format messages for intent classification prompt."""
        lines = []
        for msg in messages:
            lines.append(
                f"Message ID: {msg.get('id', 'unknown')}\n"
                f"From: {msg.get('from_address', 'unknown')}\n"
                f"Content: {msg.get('body_summary', '(no content)')}"
            )
        return "\n---\n".join(lines)
