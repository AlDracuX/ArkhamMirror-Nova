"""Respondent Intelligence Engine - core domain logic.

Aggregates respondent profiles from entity mentions, tracks positions
across documents, detects inconsistencies, and assesses strengths/weaknesses.
Designed for UK Employment Tribunal litigation intelligence.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class RespondentIntelEngine:
    """
    Core intelligence engine for respondent analysis.

    Aggregates data from entity extractions and document processing,
    builds respondent profiles, tracks positions across documents,
    and detects inconsistencies in the respondent's case.
    """

    def __init__(self, db, event_bus=None, llm_service=None):
        self._db = db
        self._event_bus = event_bus
        self._llm_service = llm_service

    # ------------------------------------------------------------------
    # build_profile
    # ------------------------------------------------------------------

    async def build_profile(self, case_id: str, respondent_name: str) -> dict:
        """
        Aggregate a respondent profile from entity mentions and documents.

        Queries entity extractions for mentions of the respondent,
        extracts positions from documents, and optionally uses LLM
        to synthesise a coherent profile.

        Returns:
            {profile_id, respondent_name, background, role, positions, documents}
        """
        profile_id = str(uuid.uuid4())

        # Fetch entity mentions for this respondent
        mentions = await self._fetch_entity_mentions(case_id, respondent_name)

        if not mentions:
            return {
                "profile_id": profile_id,
                "respondent_name": respondent_name,
                "background": "",
                "role": "",
                "positions": [],
                "documents": [],
            }

        # Collect unique document IDs
        document_ids = list({m["document_id"] for m in mentions})

        # Fetch any existing tracked positions
        existing_positions = await self._fetch_existing_positions(profile_id)

        # Synthesise profile using LLM or rule-based fallback
        if self._llm_service:
            profile_data = await self._synthesise_profile_llm(respondent_name, mentions)
        else:
            profile_data = self._synthesise_profile_rules(respondent_name, mentions)

        positions = profile_data.get("positions", []) + existing_positions

        return {
            "profile_id": profile_id,
            "respondent_name": respondent_name,
            "background": profile_data.get("background", ""),
            "role": profile_data.get("role", ""),
            "positions": positions,
            "documents": document_ids,
        }

    async def _fetch_entity_mentions(self, case_id: str, respondent_name: str) -> list[dict]:
        """Fetch entity mentions for a respondent from the database."""
        if not self._db:
            return []

        try:
            rows = await self._db.fetch_all(
                """
                SELECT document_id, entity_text, context, document_date
                FROM arkham_respondent_intel.entity_mentions
                WHERE case_id = :case_id
                  AND LOWER(entity_text) = LOWER(:name)
                ORDER BY document_date ASC
                """,
                {"case_id": case_id, "name": respondent_name},
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch entity mentions: {e}")
            return []

    async def _fetch_existing_positions(self, profile_id: str) -> list[dict]:
        """Fetch existing tracked positions for a profile."""
        if not self._db:
            return []

        try:
            rows = await self._db.fetch_all(
                """
                SELECT document_id, position, date, context
                FROM arkham_respondent_intel.respondent_positions
                WHERE profile_id = :profile_id
                ORDER BY date ASC
                """,
                {"profile_id": profile_id},
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch existing positions: {e}")
            return []

    async def _synthesise_profile_llm(self, respondent_name: str, mentions: list[dict]) -> dict:
        """Use LLM to synthesise a respondent profile from entity mentions."""
        from .llm import build_profile_prompt

        prompt = build_profile_prompt(respondent_name, mentions)

        try:
            response = await self._llm_service.generate(prompt)
            text = response.text if hasattr(response, "text") else str(response)
            return _parse_json_safe(text, {"background": "", "role": "", "positions": []})
        except Exception as e:
            logger.error(f"LLM profile synthesis failed: {e}")
            return self._synthesise_profile_rules(respondent_name, mentions)

    def _synthesise_profile_rules(self, respondent_name: str, mentions: list[dict]) -> dict:
        """Rule-based fallback for profile synthesis."""
        contexts = [m.get("context", "") for m in mentions if m.get("context")]
        background = "; ".join(contexts[:3]) if contexts else ""

        return {
            "background": background,
            "role": "",
            "positions": [],
        }

    # ------------------------------------------------------------------
    # track_positions
    # ------------------------------------------------------------------

    async def track_positions(self, profile_id: str) -> list[dict]:
        """
        Track what the respondent has claimed across different documents.

        Returns positions ordered chronologically (ascending by date).

        Returns:
            [{document_id, position, date, context}]
        """
        if not self._db:
            return []

        try:
            rows = await self._db.fetch_all(
                """
                SELECT document_id, position, date, context
                FROM arkham_respondent_intel.respondent_positions
                WHERE profile_id = :profile_id
                ORDER BY date ASC
                """,
                {"profile_id": profile_id},
            )
            positions = [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch positions: {e}")
            positions = []

        # Ensure chronological order (defensive, DB should already sort)
        positions.sort(key=lambda p: p.get("date") or datetime.min.replace(tzinfo=timezone.utc))
        return positions

    # ------------------------------------------------------------------
    # detect_inconsistencies
    # ------------------------------------------------------------------

    async def detect_inconsistencies(self, profile_id: str) -> list[dict]:
        """
        Compare positions across documents to find contradictions.

        Uses LLM when available, falls back to keyword-based heuristics.

        Returns:
            [{position_a, position_b, document_a, document_b, inconsistency}]
        """
        if not self._db:
            return []

        try:
            positions = await self._db.fetch_all(
                """
                SELECT id, document_id, position, date, context
                FROM arkham_respondent_intel.respondent_positions
                WHERE profile_id = :profile_id
                ORDER BY date ASC
                """,
                {"profile_id": profile_id},
            )
            positions = [dict(r) for r in positions]
        except Exception as e:
            logger.warning(f"Failed to fetch positions for inconsistency detection: {e}")
            return []

        if len(positions) < 2:
            return []

        if self._llm_service:
            inconsistencies = await self._detect_inconsistencies_llm(positions)
        else:
            inconsistencies = self._detect_inconsistencies_heuristic(positions)

        # Emit event if inconsistencies found
        if inconsistencies and self._event_bus:
            try:
                await self._event_bus.emit(
                    "respondent.inconsistency.detected",
                    {"profile_id": profile_id, "count": len(inconsistencies)},
                )
            except Exception as e:
                logger.warning(f"Failed to emit inconsistency event: {e}")

        return inconsistencies

    async def _detect_inconsistencies_llm(self, positions: list[dict]) -> list[dict]:
        """Use LLM to detect inconsistencies between positions."""
        from .llm import detect_inconsistencies_prompt

        prompt = detect_inconsistencies_prompt(positions)

        try:
            response = await self._llm_service.generate(prompt)
            text = response.text if hasattr(response, "text") else str(response)
            result = _parse_json_safe(text, [])
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error(f"LLM inconsistency detection failed: {e}")
            return self._detect_inconsistencies_heuristic(positions)

    def _detect_inconsistencies_heuristic(self, positions: list[dict]) -> list[dict]:
        """
        Keyword-based heuristic for detecting inconsistencies.

        Looks for negation patterns and contradictory keywords
        across position pairs.
        """
        inconsistencies = []

        negation_pairs = [
            (r"\bnot\b", r"\bwas\b"),
            (r"\bnever\b", r"\balways\b"),
            (r"\bdenied\b", r"\bconfirmed\b"),
            (r"\bnot given\b", r"\bgiven\b"),
            (r"\bdid not\b", r"\bdid\b"),
        ]

        for i, pos_a in enumerate(positions):
            for pos_b in positions[i + 1 :]:
                text_a = pos_a.get("position", "").lower()
                text_b = pos_b.get("position", "").lower()

                # Check for negation contradictions
                for neg_pattern, pos_pattern in negation_pairs:
                    if (re.search(neg_pattern, text_a) and re.search(pos_pattern, text_b)) or (
                        re.search(neg_pattern, text_b) and re.search(pos_pattern, text_a)
                    ):
                        # Verify topical overlap via word similarity
                        if self._word_overlap(text_a, text_b) > 0.3:
                            inconsistencies.append(
                                {
                                    "position_a": pos_a.get("id", ""),
                                    "position_b": pos_b.get("id", ""),
                                    "document_a": pos_a.get("document_id", ""),
                                    "document_b": pos_b.get("document_id", ""),
                                    "inconsistency": (
                                        f'Potential contradiction: "{pos_a.get("position", "")}" '
                                        f'vs "{pos_b.get("position", "")}"'
                                    ),
                                }
                            )
                            break  # One inconsistency per pair is enough

        return inconsistencies

    @staticmethod
    def _word_overlap(text_a: str, text_b: str) -> float:
        """Calculate Jaccard word overlap between two texts."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    # ------------------------------------------------------------------
    # assess_strengths_weaknesses
    # ------------------------------------------------------------------

    async def assess_strengths_weaknesses(self, profile_id: str) -> dict:
        """
        Generate a strengths/weaknesses assessment of the respondent's case.

        Uses LLM when available, falls back to rule-based analysis.

        Returns:
            {strengths: [...], weaknesses: [...]}
        """
        if not self._db:
            return {"strengths": [], "weaknesses": []}

        # Fetch profile
        try:
            profile = await self._db.fetch_one(
                "SELECT * FROM arkham_respondent_intel.respondent_profiles WHERE id = :id",
                {"id": profile_id},
            )
        except Exception as e:
            logger.warning(f"Failed to fetch profile: {e}")
            return {"strengths": [], "weaknesses": []}

        if not profile:
            return {"strengths": [], "weaknesses": []}

        profile = dict(profile)

        # Fetch positions
        try:
            positions = await self._db.fetch_all(
                """
                SELECT id, position, date, document_id, context
                FROM arkham_respondent_intel.respondent_positions
                WHERE profile_id = :profile_id
                ORDER BY date ASC
                """,
                {"profile_id": profile_id},
            )
            positions = [dict(r) for r in positions]
        except Exception as e:
            logger.warning(f"Failed to fetch positions for assessment: {e}")
            positions = []

        if self._llm_service:
            return await self._assess_llm(profile, positions)
        else:
            return self._assess_rules(profile, positions)

    async def _assess_llm(self, profile: dict, positions: list[dict]) -> dict:
        """Use LLM to assess strengths and weaknesses."""
        from .llm import assess_strengths_weaknesses_prompt

        prompt = assess_strengths_weaknesses_prompt(profile, positions)

        try:
            response = await self._llm_service.generate(prompt)
            text = response.text if hasattr(response, "text") else str(response)
            result = _parse_json_safe(text, {"strengths": [], "weaknesses": []})
            return {
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", []),
            }
        except Exception as e:
            logger.error(f"LLM assessment failed: {e}")
            return self._assess_rules(profile, positions)

    def _assess_rules(self, profile: dict, positions: list[dict]) -> dict:
        """Rule-based strengths/weaknesses assessment."""
        strengths = []
        weaknesses = []

        # Parse existing strengths/weaknesses from profile
        existing_strengths = _parse_json_field(profile.get("strengths", "[]"))
        existing_weaknesses = _parse_json_field(profile.get("weaknesses", "[]"))
        strengths.extend(existing_strengths)
        weaknesses.extend(existing_weaknesses)

        # Analyse positions for patterns
        if len(positions) >= 2:
            # Check consistency: if positions are very similar, that's a strength
            position_texts = [p.get("position", "") for p in positions]
            unique_themes = len(set(t.lower().strip() for t in position_texts))
            if unique_themes <= len(positions) * 0.5:
                strengths.append("Consistent account across multiple documents")
            else:
                weaknesses.append("Multiple different positions stated across documents")

        if not strengths and not weaknesses:
            weaknesses.append("Insufficient data for assessment")

        return {"strengths": strengths, "weaknesses": weaknesses}

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def handle_entities_extracted(self, event_data: dict[str, Any]) -> None:
        """Handle entities.extracted event - update relevant profiles."""
        case_id = event_data.get("case_id")
        entities = event_data.get("entities", [])

        if not case_id or not entities:
            return

        # Check if any extracted entities match known respondent names
        for entity in entities:
            name = entity.get("text", "")
            if name:
                logger.info(f"Entity extracted for potential respondent: {name}")
                # Emit profile update event
                if self._event_bus:
                    try:
                        await self._event_bus.emit(
                            "respondent.profile.updated",
                            {"case_id": case_id, "respondent_name": name},
                        )
                    except Exception as e:
                        logger.warning(f"Failed to emit profile update: {e}")

    async def handle_document_processed(self, event_data: dict[str, Any]) -> None:
        """Handle documents.processed event - check for respondent mentions."""
        document_id = event_data.get("document_id")
        if document_id:
            logger.info(f"Document processed, checking for respondent mentions: {document_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_safe(text: str, default: Any) -> Any:
    """Safely parse JSON from LLM response text, extracting from markdown fences."""
    if not text:
        return default
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return default


def _parse_json_field(value: Any) -> list:
    """Parse a JSON field that may be a string or already parsed."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []
