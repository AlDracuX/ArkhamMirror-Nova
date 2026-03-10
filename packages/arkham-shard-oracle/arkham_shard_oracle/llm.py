"""LLM integration for Oracle shard legal research.

Provides AI-assisted features:
- Case law summarization with focus on ratio decidendi
- Relevance scoring of authorities against case facts
- Comprehensive legal research queries
- UK employment law specific, referencing Equality Act 2010
"""

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class CaseSummaryResult:
    """Structured case summary from LLM."""

    facts: str = ""
    decision: str = ""
    legal_principles: list[str] = field(default_factory=list)


@dataclass
class RelevanceResult:
    """Relevance scoring result from LLM."""

    score: float = 0.0
    reasoning: str = ""


@dataclass
class ResearchResult:
    """Comprehensive research result from LLM."""

    analysis: str = ""
    key_authorities: list[str] = field(default_factory=list)
    legal_principles: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# Prompt Templates
# =============================================================================

SUMMARIZE_CASE_PROMPT = """You are a UK employment law specialist. Summarize the following legal authority
with focus on the ratio decidendi and its application to Employment Tribunal proceedings.

Authority: {title}
Court: {court}
Citation: {citation}

Text:
{text}

Return a JSON object with exactly these fields:
{{
  "facts": "A concise summary of the material facts",
  "decision": "The court's decision and key holdings",
  "legal_principles": ["List of legal principles established, especially ratio decidendi"]
}}

Focus on principles relevant to:
- Equality Act 2010 (discrimination, harassment, victimisation)
- Employment Rights Act 1996 (unfair dismissal, whistleblowing)
- ACAS Code of Practice
- Burden of proof in discrimination claims

Return ONLY valid JSON, no additional text."""

SCORE_RELEVANCE_PROMPT = """You are a UK employment law specialist assessing the relevance of a legal
authority to current case facts.

Authority title: {title}
Authority summary: {summary}
Authority court: {court}
Authority claim types: {claim_types}

Current case facts:
{case_facts}

Score the relevance of this authority to the current case on a scale of 0.0 to 1.0 where:
- 0.0 = completely irrelevant (different area of law entirely)
- 0.3 = tangentially relevant (same broad area but different specific issues)
- 0.5 = moderately relevant (similar issues but distinguishable facts)
- 0.7 = highly relevant (similar facts and legal issues)
- 1.0 = directly on point (same legal test, analogous facts)

Consider relevance to:
- Equality Act 2010 claims (direct/indirect discrimination, harassment, victimisation)
- Employment Rights Act 1996 (unfair dismissal, constructive dismissal, whistleblowing)
- Procedural requirements and burden of proof

Return ONLY a JSON object:
{{
  "score": 0.0,
  "reasoning": "Brief explanation of relevance assessment"
}}"""

RESEARCH_PROMPT = """You are a UK employment law specialist conducting comprehensive legal research.

Research query: {query}

Context (if provided): {context}

Provide a thorough analysis covering:
1. Relevant legal principles and statutory framework
2. Key authorities and their holdings
3. How the law applies to the query
4. Practical recommendations

Focus areas:
- Equality Act 2010 (Part 5 - Work, ss. 13-27 protected characteristics and prohibited conduct)
- Employment Rights Act 1996
- Employment Tribunal procedure and practice
- ACAS Code of Practice on Disciplinary and Grievance Procedures
- Burden of proof (Igen v Wong, Barton v Investec)

Return a JSON object:
{{
  "analysis": "Detailed legal analysis",
  "key_authorities": ["List of key case names and citations"],
  "legal_principles": ["List of applicable legal principles"],
  "recommendations": ["Practical recommendations for the case"]
}}"""


# =============================================================================
# LLM Wrapper
# =============================================================================


class OracleLLM:
    """LLM wrapper for Oracle shard legal research tasks."""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    @property
    def available(self) -> bool:
        """Check if LLM service is available."""
        return self.llm_service is not None

    async def summarize_case(
        self,
        title: str,
        court: str = "",
        citation: str = "",
        text: str = "",
    ) -> CaseSummaryResult:
        """Generate a structured case summary using LLM."""
        if not self.available:
            logger.warning("LLM not available for case summarization")
            return CaseSummaryResult()

        prompt = SUMMARIZE_CASE_PROMPT.format(
            title=title,
            court=court or "Unknown",
            citation=citation or "Unknown",
            text=text or "No full text available",
        )

        try:
            response = await self.llm_service.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)
            data = _parse_json_response(response_text)

            return CaseSummaryResult(
                facts=data.get("facts", ""),
                decision=data.get("decision", ""),
                legal_principles=data.get("legal_principles", []),
            )
        except Exception as e:
            logger.error(f"LLM case summarization failed: {e}")
            return CaseSummaryResult()

    async def score_relevance(
        self,
        title: str,
        summary: str = "",
        court: str = "",
        claim_types: list[str] | None = None,
        case_facts: str = "",
    ) -> RelevanceResult:
        """Score relevance of authority to case facts using LLM."""
        if not self.available:
            logger.warning("LLM not available for relevance scoring")
            return RelevanceResult()

        prompt = SCORE_RELEVANCE_PROMPT.format(
            title=title,
            summary=summary or "No summary available",
            court=court or "Unknown",
            claim_types=", ".join(claim_types or []) or "Not specified",
            case_facts=case_facts,
        )

        try:
            response = await self.llm_service.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)
            data = _parse_json_response(response_text)

            score = float(data.get("score", 0.0))
            score = max(0.0, min(1.0, score))

            return RelevanceResult(
                score=score,
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.error(f"LLM relevance scoring failed: {e}")
            return RelevanceResult()

    async def research(self, query: str, context: str = "") -> ResearchResult:
        """Conduct comprehensive legal research using LLM."""
        if not self.available:
            logger.warning("LLM not available for research")
            return ResearchResult()

        prompt = RESEARCH_PROMPT.format(
            query=query,
            context=context or "No additional context",
        )

        try:
            response = await self.llm_service.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)
            data = _parse_json_response(response_text)

            return ResearchResult(
                analysis=data.get("analysis", ""),
                key_authorities=data.get("key_authorities", []),
                legal_principles=data.get("legal_principles", []),
                recommendations=data.get("recommendations", []),
            )
        except Exception as e:
            logger.error(f"LLM research failed: {e}")
            return ResearchResult()


# =============================================================================
# Helpers
# =============================================================================


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    if not text:
        return {}

    # Strip markdown code blocks if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove ```json or ``` prefix and trailing ```
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning(f"Failed to parse JSON from LLM response: {text[:100]}...")
        return {}
