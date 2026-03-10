"""LLM integration for Respondent Intelligence analysis.

Provides prompt construction for:
- Profile synthesis from document mentions
- Position inconsistency detection
- Strengths/weaknesses assessment

All prompts are tailored for UK Employment Tribunal litigation intelligence.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt: Synthesise Profile
# ---------------------------------------------------------------------------


def build_profile_prompt(respondent_name: str, mentions: list[dict]) -> str:
    """
    Build a prompt to synthesise a respondent profile from entity mentions.

    Args:
        respondent_name: Name of the respondent/witness
        mentions: List of entity mention dicts with context and document_date

    Returns:
        Prompt string for LLM
    """
    mention_texts = []
    for m in mentions:
        doc_id = m.get("document_id", "unknown")
        context = m.get("context", "")
        date = m.get("document_date", "")
        mention_texts.append(f"- Document {doc_id} ({date}): {context}")

    mentions_block = "\n".join(mention_texts) if mention_texts else "No mentions found."

    return f"""You are a UK Employment Tribunal litigation analyst.

Analyse the following document mentions of "{respondent_name}" and synthesise a respondent profile.

Document mentions:
{mentions_block}

Based on these mentions, produce a JSON object with:
- "background": A brief summary of the respondent's background and role (1-3 sentences)
- "role": Their role/position (e.g., "Line Manager", "HR Director")
- "positions": An array of positions/claims they have taken, each with:
  - "position": What they claimed or stated
  - "date": The date of the document (ISO format if available)
  - "document_id": The source document ID
  - "context": Brief context for the position

Focus on:
- Employment relationship and management responsibilities
- Key decisions they were involved in
- Statements or positions they have taken in the litigation
- Any procedural steps they claim to have followed

Return ONLY valid JSON, no explanation text."""


# ---------------------------------------------------------------------------
# Prompt: Detect Position Inconsistencies
# ---------------------------------------------------------------------------


def detect_inconsistencies_prompt(positions: list[dict]) -> str:
    """
    Build a prompt to detect inconsistencies between respondent positions.

    Args:
        positions: List of position dicts with id, position, date, context

    Returns:
        Prompt string for LLM
    """
    position_texts = []
    for p in positions:
        pos_id = p.get("id", "unknown")
        position = p.get("position", "")
        date = p.get("date", "")
        doc_id = p.get("document_id", "")
        context = p.get("context", "")
        position_texts.append(f'- [{pos_id}] ({date}, doc: {doc_id}): "{position}" (context: {context})')

    positions_block = "\n".join(position_texts)

    return f"""You are a UK Employment Tribunal litigation analyst specialising in identifying
inconsistencies in respondent evidence.

Analyse the following positions taken by the respondent across different documents:

{positions_block}

Identify ANY inconsistencies, contradictions, or shifts in position. Consider:
- Direct contradictions (e.g., "was dismissed for redundancy" vs "was dismissed for performance")
- Temporal inconsistencies (e.g., dates that don't align)
- Shifting rationale (e.g., changing the reason given for a decision)
- Omissions (e.g., a key fact mentioned in one document but absent in another)
- Contradictions with legal requirements under the Employment Rights Act 1996

Return a JSON array of inconsistencies. Each item must have:
- "position_a": ID of the first position
- "position_b": ID of the second position
- "inconsistency": Description of the inconsistency (1-2 sentences)

If no inconsistencies are found, return an empty array: []

Return ONLY valid JSON, no explanation text."""


# ---------------------------------------------------------------------------
# Prompt: Assess Strengths & Weaknesses
# ---------------------------------------------------------------------------


def assess_strengths_weaknesses_prompt(profile: dict, positions: list[dict]) -> str:
    """
    Build a prompt to assess respondent strengths and weaknesses.

    Args:
        profile: Respondent profile dict
        positions: List of tracked positions

    Returns:
        Prompt string for LLM
    """
    name = profile.get("name", "the respondent")
    role = profile.get("role", "unknown role")
    org = profile.get("organization", "unknown organisation")
    background = profile.get("background", "")

    position_texts = []
    for p in positions:
        position = p.get("position", "")
        date = p.get("date", "")
        context = p.get("context", "")
        position_texts.append(f'- ({date}): "{position}" (context: {context})')

    positions_block = "\n".join(position_texts) if position_texts else "No positions tracked."

    return f"""You are a UK Employment Tribunal litigation analyst preparing a tactical assessment.

Respondent: {name}
Role: {role}
Organisation: {org}
Background: {background}

Positions taken:
{positions_block}

Assess the strengths and weaknesses of this respondent's case from the CLAIMANT's perspective.

Consider:
- Consistency of their account across documents
- Whether they followed statutory procedures (ACAS Code, ERA 1996)
- Quality and credibility of their evidence
- Whether their timeline holds up to scrutiny
- Potential vulnerabilities in cross-examination
- Documentary support (or lack thereof) for their claims
- Any duty of care or procedural failures

Return a JSON object with:
- "strengths": Array of strings describing case strengths (from respondent's perspective)
- "weaknesses": Array of strings describing case weaknesses (vulnerabilities for claimant to exploit)

Aim for 3-6 items in each category. Be specific and actionable.

Return ONLY valid JSON, no explanation text."""
