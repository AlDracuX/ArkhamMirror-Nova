"""LLM integration for CrossExam shard.

Provides AI-assisted features:
- Question generation from witness statements
- Impeachment point identification
- Damage scoring for cross-examination questions

All prompts are UK Employment Tribunal specific.
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
class GeneratedQuestion:
    """A question generated from witness statement analysis."""

    question: str
    expected_answer: str = ""
    alternative_answer: str = ""
    damage_potential: float = 0.0


@dataclass
class ImpeachmentStep:
    """A single step in an impeachment sequence."""

    step: int
    type: str  # "commit", "introduce", "confront"
    question: str


@dataclass
class DamageAssessment:
    """LLM-assessed damage potential for a question."""

    score: float
    reasoning: str
    factors: dict[str, bool] = field(default_factory=dict)


# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPTS = {
    "generate_questions": """You are an experienced UK Employment Tribunal cross-examination specialist.
Your role is to generate probing cross-examination questions from a witness statement.

Context: UK Employment Tribunal proceedings under the Employment Tribunals (Constitution and Rules
of Procedure) Regulations 2013. Cross-examination must be firm but fair, and questions should
expose weaknesses, inconsistencies, and areas where the witness statement conflicts with
documentary evidence.

Guidelines:
- Generate 3-8 targeted questions that probe the weakest points of the statement
- Each question should have an expected answer and an alternative (unexpected) answer
- Assign a damage_potential score from 0.0 to 1.0 based on how damaging a successful
  challenge on this point would be to the witness's credibility
- Focus on: factual inconsistencies, vague timeframes, unsupported assertions,
  contradictions with likely documentary evidence
- Questions should follow the principle of "one fact per question"
- Do NOT use leading questions that put words in the witness's mouth unfairly

Return JSON:
{
  "questions": [
    {
      "question": "...",
      "expected_answer": "...",
      "alternative_answer": "...",
      "damage_potential": 0.0-1.0
    }
  ]
}""",
    "suggest_impeachment": """You are an experienced UK Employment Tribunal advocate.
Your role is to construct a three-step impeachment sequence when a witness statement
contradicts documentary evidence.

The classic impeachment structure is:
1. COMMIT: Get the witness to firmly commit to their position under oath
2. INTRODUCE: Present the contradicting document to the witness
3. CONFRONT: Ask the witness to explain the contradiction

Context: UK Employment Tribunal. The questioning must be professional, clear, and
designed to highlight the contradiction without being unnecessarily aggressive.

Given two contradicting claims and their source documents, generate the three-step sequence.

Return JSON:
{
  "steps": [
    {"step": 1, "type": "commit", "question": "..."},
    {"step": 2, "type": "introduce", "question": "..."},
    {"step": 3, "type": "confront", "question": "..."}
  ]
}""",
    "score_damage": """You are an experienced UK Employment Tribunal litigation analyst.
Your role is to assess the damage potential of a cross-examination question.

Score from 0.0 to 1.0 based on these factors:
- material_fact: Does this contradict the witness on a material fact relevant to the claim?
- undermines_credibility: Would a successful challenge undermine the witness's overall credibility?
- supports_case_theory: Does this line of questioning support the cross-examiner's case theory?

High scores (0.7-1.0): Material contradictions with documentary evidence
Medium scores (0.4-0.69): Important but not decisive points
Low scores (0.0-0.39): Peripheral details, credibility nibbles

Return JSON:
{
  "score": 0.0-1.0,
  "reasoning": "...",
  "factors": {
    "material_fact": true/false,
    "undermines_credibility": true/false,
    "supports_case_theory": true/false
  }
}""",
}


# =============================================================================
# LLM Integration Class
# =============================================================================


class CrossExamLLM:
    """
    LLM integration for CrossExam analysis features.

    Works with Frame's LLM service to provide AI-assisted cross-examination planning.
    """

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
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Generate LLM response."""
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
        """Parse JSON from LLM response, handling markdown fences and extra text."""
        text = response.text if hasattr(response, "text") else str(response)
        if not text:
            return {}
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON object or array in the text
        for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue
        logger.warning(f"Failed to parse LLM response as JSON: {text[:100]}")
        return {}

    async def generate_questions(self, statement_text: str) -> list[GeneratedQuestion]:
        """Generate cross-examination questions from a witness statement."""
        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["generate_questions"],
            user_prompt=f"Witness statement:\n\n{statement_text}",
        )

        data = self._parse_json_response(response)
        questions = []
        for q in data.get("questions", []):
            questions.append(
                GeneratedQuestion(
                    question=q.get("question", ""),
                    expected_answer=q.get("expected_answer", ""),
                    alternative_answer=q.get("alternative_answer", ""),
                    damage_potential=float(q.get("damage_potential", 0.0)),
                )
            )
        return questions

    async def suggest_impeachment(
        self, claim_a: str, claim_b: str, doc_a_ref: str, doc_b_ref: str
    ) -> list[ImpeachmentStep]:
        """Generate 3-step impeachment sequence from contradicting claims."""
        user_prompt = (
            f"Witness statement claim: {claim_a}\n"
            f"Source: {doc_a_ref}\n\n"
            f"Contradicting documentary evidence: {claim_b}\n"
            f"Source: {doc_b_ref}\n"
        )

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["suggest_impeachment"],
            user_prompt=user_prompt,
        )

        data = self._parse_json_response(response)
        steps = []
        for s in data.get("steps", []):
            steps.append(
                ImpeachmentStep(
                    step=s.get("step", 0),
                    type=s.get("type", ""),
                    question=s.get("question", ""),
                )
            )
        return steps

    async def assess_damage(self, question_text: str, context: str = "") -> DamageAssessment:
        """Assess damage potential of a cross-examination question."""
        user_prompt = f"Question: {question_text}"
        if context:
            user_prompt += f"\n\nContext: {context}"

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["score_damage"],
            user_prompt=user_prompt,
        )

        data = self._parse_json_response(response)
        return DamageAssessment(
            score=float(data.get("score", 0.0)),
            reasoning=data.get("reasoning", ""),
            factors=data.get("factors", {}),
        )
