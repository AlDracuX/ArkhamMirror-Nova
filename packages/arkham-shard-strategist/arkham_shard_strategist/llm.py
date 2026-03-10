"""LLM integration for Strategist shard.

Provides UK Employment Tribunal-specific prompts for:
- Predicting respondent arguments (TLT Solicitors pattern)
- Red team hostile assessment of claimant's case
- SWOT litigation position analysis
- Tactical respondent modelling
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompts — UK Employment Tribunal context
# =============================================================================

SYSTEM_PROMPTS = {
    "predict_arguments": (
        "You are a senior employment law solicitor at a large UK law firm acting for the respondent "
        "in an Employment Tribunal case. Your task is to predict the most likely defence arguments "
        "the respondent's legal team will raise. Consider standard defence strategies in unfair "
        "dismissal, discrimination, whistleblowing, and constructive dismissal claims. Think about "
        "procedural defences, substantive defences, and tactical arguments. Return your analysis as "
        "a JSON array of objects with keys: argument, confidence (0.0-1.0), reasoning, "
        "likely_evidence (array of strings)."
    ),
    "counterarguments": (
        "You are a specialist employment tribunal advocate preparing counterarguments to the "
        "respondent's predicted defence. For each defence argument, identify the strongest rebuttal "
        "with specific references to documentary evidence, witness testimony, or legal principles "
        "under the Employment Rights Act 1996, Equality Act 2010, or relevant case law. Return a "
        "JSON array of objects with keys: counterargument, evidence_refs (array of document IDs or "
        "descriptions), strength (0.0-1.0)."
    ),
    "swot": (
        "You are a litigation strategist conducting a SWOT analysis of the claimant's position in "
        "a UK Employment Tribunal case. Assess strengths (strong evidence, clear legal basis), "
        "weaknesses (gaps in evidence, credibility issues), opportunities (respondent's errors, "
        "procedural advantages), and threats (limitation issues, cost risks, witness problems). "
        "Return a JSON object with keys: strengths, weaknesses, opportunities, threats — each an "
        "array of objects with 'item' and 'detail' string fields."
    ),
    "red_team": (
        "You are hostile opposing counsel (a senior partner at a large law firm) tasked with "
        "destroying the claimant's case in a UK Employment Tribunal. Attack every weakness "
        "ruthlessly. Identify vulnerabilities in evidence, witness credibility, legal arguments, "
        "procedural compliance, and timeline consistency. Be adversarial and thorough. Return a "
        "JSON object with keys: weaknesses (array of objects with 'area', 'vulnerability', "
        "'exploitation_method'), overall_risk (float 0.0-1.0 where 1.0 means the case is "
        "indefensible)."
    ),
    "tactical_model": (
        "You are an intelligence analyst building a tactical profile of the respondent's likely "
        "behaviour in a UK Employment Tribunal case. Based on the respondent's legal "
        "representation, previous conduct, and standard litigation tactics for employment cases, "
        "predict their likely moves at each stage (response, disclosure, witness statements, "
        "preliminary hearing, final hearing). Return a JSON object with keys: tactics (array of "
        "objects with 'tactic', 'likelihood' float 0.0-1.0, 'counter_strategy'), "
        "profile_summary (string overview of respondent's likely approach)."
    ),
}


class StrategistLLM:
    """LLM wrapper for strategist-specific prompts."""

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
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Any:
        """Generate LLM response.

        Returns the raw response object (has .text attribute).
        """
        if not self.llm_service:
            raise RuntimeError("LLM service not available")

        return await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _parse_json(self, response: Any) -> Any:
        """Extract and parse JSON from LLM response."""
        text = getattr(response, "text", "")
        if not text:
            return None

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        import re

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse LLM response as JSON")
        return None

    async def predict_arguments(self, project_id: str, claim_id: str | None = None, context: str = "") -> list[dict]:
        """Predict respondent arguments using LLM."""
        prompt_parts = [f"Project ID: {project_id}"]
        if claim_id:
            prompt_parts.append(f"Claim ID: {claim_id}")
        if context:
            prompt_parts.append(f"\nCase context:\n{context}")
        prompt_parts.append("\nPredict the respondent's most likely arguments and defences.")

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["predict_arguments"],
            user_prompt="\n".join(prompt_parts),
        )

        parsed = self._parse_json(response)
        if isinstance(parsed, list):
            return parsed
        return []

    async def generate_counterarguments(self, prediction: dict) -> list[dict]:
        """Generate counterarguments for a predicted argument."""
        prompt = (
            f"The respondent is predicted to argue:\n"
            f"Argument: {prediction.get('predicted_argument', '')}\n"
            f"Confidence: {prediction.get('confidence', 'unknown')}\n"
            f"Reasoning: {prediction.get('reasoning', '')}\n\n"
            f"Generate strong counterarguments with evidence references."
        )

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["counterarguments"],
            user_prompt=prompt,
        )

        parsed = self._parse_json(response)
        if isinstance(parsed, list):
            return parsed
        return []

    async def build_swot(self, project_id: str, context: str = "") -> dict:
        """Build SWOT analysis using LLM."""
        prompt = f"Project ID: {project_id}\n"
        if context:
            prompt += f"\nCase context:\n{context}\n"
        prompt += "\nConduct a comprehensive SWOT analysis of the claimant's litigation position."

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["swot"],
            user_prompt=prompt,
        )

        parsed = self._parse_json(response)
        if isinstance(parsed, dict):
            return {
                "strengths": parsed.get("strengths", []),
                "weaknesses": parsed.get("weaknesses", []),
                "opportunities": parsed.get("opportunities", []),
                "threats": parsed.get("threats", []),
            }
        return {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}

    async def red_team(self, project_id: str, target_id: str, context: str = "") -> dict:
        """Red team assessment using LLM."""
        prompt = f"Project ID: {project_id}\nTarget: {target_id}\n"
        if context:
            prompt += f"\nCase context:\n{context}\n"
        prompt += "\nAttack the claimant's case from the respondent's perspective. Be ruthless."

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["red_team"],
            user_prompt=prompt,
        )

        parsed = self._parse_json(response)
        if isinstance(parsed, dict):
            risk = parsed.get("overall_risk", 0.5)
            return {
                "weaknesses": parsed.get("weaknesses", []),
                "overall_risk": min(1.0, max(0.0, float(risk))),
            }
        return {"weaknesses": [], "overall_risk": 0.5}

    async def build_tactical_model(self, project_id: str, respondent_id: str, context: str = "") -> dict:
        """Build tactical model using LLM."""
        prompt = f"Project ID: {project_id}\nRespondent ID: {respondent_id}\n"
        if context:
            prompt += f"\nKnown respondent behaviour:\n{context}\n"
        prompt += "\nBuild a tactical profile of the respondent's likely litigation strategy."

        response = await self._generate(
            system_prompt=SYSTEM_PROMPTS["tactical_model"],
            user_prompt=prompt,
        )

        parsed = self._parse_json(response)
        if isinstance(parsed, dict):
            return {
                "tactics": parsed.get("tactics", []),
                "profile_summary": parsed.get("profile_summary", ""),
            }
        return {"tactics": [], "profile_summary": ""}
