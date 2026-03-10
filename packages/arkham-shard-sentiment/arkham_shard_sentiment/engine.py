"""Sentiment analysis engine with keyword scoring, LLM enhancement, and persistence."""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import analyze_sentiment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tone category keyword/pattern definitions
# ---------------------------------------------------------------------------

TONE_PATTERNS: dict[str, dict[str, Any]] = {
    "hostile": {
        "keywords": frozenset(
            [
                "threatening",
                "aggressive",
                "hostile",
                "intimidation",
                "intimidate",
                "unacceptable",
                "outrageous",
                "disgraceful",
                "appalling",
                "abusive",
                "bullying",
                "harassing",
                "harassment",
                "coerce",
                "coercion",
                "demand",
                "demands",
                "ultimatum",
                "warn",
                "warning",
            ]
        ),
        "patterns": [
            re.compile(r"\b(?:you|your)\s+(?:will|must|shall)\s+(?:face|suffer|pay)", re.IGNORECASE),
            re.compile(r"\b(?:consequences|repercussions|action\s+against)\b", re.IGNORECASE),
        ],
    },
    "evasive": {
        "keywords": frozenset(
            [
                "unclear",
                "uncertain",
                "cannot recall",
                "do not remember",
                "unsure",
                "perhaps",
                "possibly",
                "vague",
                "ambiguous",
                "cannot confirm",
                "unable to confirm",
                "not certain",
                "may have",
                "might have",
                "could have",
            ]
        ),
        "patterns": [
            re.compile(r"\bcannot\s+(?:recall|remember|confirm|say)\b", re.IGNORECASE),
            re.compile(r"\bdo\s+not\s+(?:recall|remember)\b", re.IGNORECASE),
            re.compile(r"\bit\s+is\s+(?:unclear|uncertain)\b", re.IGNORECASE),
            re.compile(r"\bto\s+the\s+best\s+of\s+(?:my|our)\s+(?:knowledge|recollection)\b", re.IGNORECASE),
        ],
    },
    "condescending": {
        "keywords": frozenset(
            [
                "obviously",
                "clearly",
                "simply",
                "basic",
                "elementary",
                "as I have already explained",
                "as previously stated",
                "you should have known",
                "you should know",
                "self-evident",
                "trivial",
                "patronising",
                "patronizing",
            ]
        ),
        "patterns": [
            re.compile(r"\bas\s+(?:I|we)\s+have\s+already\s+(?:explained|stated|noted)\b", re.IGNORECASE),
            re.compile(r"\byou\s+should\s+(?:have\s+)?know[n]?\b", re.IGNORECASE),
            re.compile(r"\b(?:obviously|clearly|simply)\s+", re.IGNORECASE),
        ],
    },
    "professional": {
        "keywords": frozenset(
            [
                "formal",
                "acknowledge",
                "enclosed",
                "correspondence",
                "respectfully",
                "pursuant",
                "in accordance",
                "duly noted",
                "for your consideration",
                "kindly",
                "please find",
                "we note",
                "we acknowledge",
                "receipt",
            ]
        ),
        "patterns": [
            re.compile(r"\bplease\s+find\s+(?:enclosed|attached)\b", re.IGNORECASE),
            re.compile(r"\bwe\s+(?:acknowledge|note)\s+(?:receipt|your)\b", re.IGNORECASE),
            re.compile(r"\bin\s+accordance\s+with\b", re.IGNORECASE),
            re.compile(r"\bpursuant\s+to\b", re.IGNORECASE),
        ],
    },
    "supportive": {
        "keywords": frozenset(
            [
                "happy to assist",
                "cooperate",
                "cooperation",
                "cooperative",
                "support",
                "supporting",
                "grateful",
                "thank you",
                "appreciate",
                "patience",
                "understanding",
                "assist",
                "help",
                "welcome",
                "glad",
            ]
        ),
        "patterns": [
            re.compile(r"\bhappy\s+to\s+(?:assist|help|support)\b", re.IGNORECASE),
            re.compile(r"\bwill\s+(?:cooperate|assist)\s+fully\b", re.IGNORECASE),
            re.compile(r"\bthank\s+you\s+for\s+your\b", re.IGNORECASE),
        ],
    },
}


class SentimentEngine:
    """
    Production sentiment analysis engine.

    Combines keyword-based scoring with optional LLM tone classification.
    Persists results to the arkham_sentiment schema and emits events.
    """

    def __init__(self, db=None, event_bus=None, llm_service=None):
        self._db = db
        self._event_bus = event_bus
        self._llm_service = llm_service

    # ------------------------------------------------------------------
    # Public: analyse a single document
    # ------------------------------------------------------------------

    async def analyze_document(
        self,
        document_id: str,
        text: str,
        case_id: str | None = None,
    ) -> dict:
        """
        Full analysis: keyword scoring + tone classification.

        Stores result in DB. Returns {document_id, overall_score, tone_categories, keywords_found}.
        """
        # 1. Keyword-based sentiment score
        keyword_result = analyze_sentiment(text)

        # 2. Tone classification (keyword baseline)
        tone_categories = self.classify_tone_categories(text)

        # 3. Optional LLM enhancement
        if self._llm_service:
            tone_categories = await self._enhance_with_llm(text, tone_categories)

        # 4. Build result
        result = {
            "document_id": document_id,
            "overall_score": keyword_result["score"],
            "label": keyword_result["label"],
            "confidence": keyword_result["confidence"],
            "tone_categories": tone_categories,
            "keywords_found": keyword_result["key_passages"],
        }

        # 5. Persist
        result_id = str(uuid.uuid4())
        if self._db:
            await self._db.execute(
                """
                INSERT INTO arkham_sentiment.sentiment_results
                (id, document_id, case_id, overall_score, label, confidence, passages, entity_sentiments, analyzed_at, created_at, updated_at)
                VALUES (:id, :document_id, :case_id, :overall_score, :label, :confidence, :passages, :entity_sentiments, :analyzed_at, :created_at, :updated_at)
                """,
                {
                    "id": result_id,
                    "document_id": document_id,
                    "case_id": case_id,
                    "overall_score": keyword_result["score"],
                    "label": keyword_result["label"],
                    "confidence": keyword_result["confidence"],
                    "passages": json.dumps(keyword_result["key_passages"]),
                    "entity_sentiments": json.dumps({c["category"]: c["score"] for c in tone_categories}),
                    "analyzed_at": datetime.now(timezone.utc),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            )

        # 6. Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "sentiment.analysis.completed",
                {
                    "document_id": document_id,
                    "result_id": result_id,
                    "overall_score": keyword_result["score"],
                    "label": keyword_result["label"],
                },
                source="sentiment-shard",
            )

        return result

    # ------------------------------------------------------------------
    # Public: temporal pattern detection
    # ------------------------------------------------------------------

    async def detect_temporal_patterns(self, case_id: str) -> list[dict]:
        """
        Detect tone changes over time for a case.

        Groups results by month, computes moving average, flags >0.3 shifts.
        Returns [{period, avg_score, shift_magnitude, shift_direction}].
        """
        if not self._db:
            return []

        rows = await self._db.fetch_all(
            """
            SELECT document_id, overall_score, analyzed_at
            FROM arkham_sentiment.sentiment_results
            WHERE case_id = :case_id AND analyzed_at IS NOT NULL
            ORDER BY analyzed_at ASC
            """,
            {"case_id": case_id},
        )

        if not rows:
            return []

        # Group by month
        periods: dict[str, list[float]] = {}
        for row in rows:
            analyzed_at = row["analyzed_at"]
            if isinstance(analyzed_at, str):
                analyzed_at = datetime.fromisoformat(analyzed_at)
            period_key = analyzed_at.strftime("%Y-%m")
            periods.setdefault(period_key, []).append(row["overall_score"])

        # Compute per-period averages
        period_avgs: list[dict] = []
        for period_key in sorted(periods.keys()):
            scores = periods[period_key]
            avg = sum(scores) / len(scores)
            period_avgs.append({"period": period_key, "avg_score": round(avg, 4)})

        # Detect shifts between adjacent periods
        results: list[dict] = []
        for i, entry in enumerate(period_avgs):
            shift_magnitude = 0.0
            shift_direction = "stable"
            if i > 0:
                prev_avg = period_avgs[i - 1]["avg_score"]
                curr_avg = entry["avg_score"]
                shift_magnitude = round(abs(curr_avg - prev_avg), 4)
                if curr_avg < prev_avg:
                    shift_direction = "negative"
                elif curr_avg > prev_avg:
                    shift_direction = "positive"
                else:
                    shift_direction = "stable"

            results.append(
                {
                    "period": entry["period"],
                    "avg_score": entry["avg_score"],
                    "shift_magnitude": shift_magnitude,
                    "shift_direction": shift_direction,
                }
            )

        # Emit event if significant pattern detected
        significant = [r for r in results if r["shift_magnitude"] > 0.3]
        if significant and self._event_bus:
            await self._event_bus.emit(
                "sentiment.pattern.detected",
                {"case_id": case_id, "shifts": significant},
                source="sentiment-shard",
            )

        return results

    # ------------------------------------------------------------------
    # Public: compare claimant vs respondent
    # ------------------------------------------------------------------

    async def compare_parties(self, case_id: str) -> dict:
        """
        Compare claimant vs respondent communication styles.

        Expects the entity_sentiments JSONB to tag party role, or uses
        two queries with party filter. Returns {claimant_avg, respondent_avg,
        divergence, key_differences}.
        """
        if not self._db:
            return {"claimant_avg": 0.0, "respondent_avg": 0.0, "divergence": 0.0, "key_differences": []}

        # Fetch claimant results
        claimant_rows = await self._db.fetch_all(
            """
            SELECT overall_score, document_id, label
            FROM arkham_sentiment.sentiment_results
            WHERE case_id = :case_id
            AND entity_sentiments::text LIKE :party_filter
            ORDER BY created_at ASC
            """,
            {"case_id": case_id, "party_filter": "%claimant%"},
        )

        # Fetch respondent results
        respondent_rows = await self._db.fetch_all(
            """
            SELECT overall_score, document_id, label
            FROM arkham_sentiment.sentiment_results
            WHERE case_id = :case_id
            AND entity_sentiments::text LIKE :party_filter
            ORDER BY created_at ASC
            """,
            {"case_id": case_id, "party_filter": "%respondent%"},
        )

        claimant_avg = 0.0
        respondent_avg = 0.0
        key_differences: list[str] = []

        if claimant_rows:
            claimant_scores = [r["overall_score"] for r in claimant_rows]
            claimant_avg = round(sum(claimant_scores) / len(claimant_scores), 4)

        if respondent_rows:
            respondent_scores = [r["overall_score"] for r in respondent_rows]
            respondent_avg = round(sum(respondent_scores) / len(respondent_scores), 4)

        divergence = round(abs(claimant_avg - respondent_avg), 4)

        # Generate key differences narrative
        if divergence > 0.3:
            if claimant_avg > respondent_avg:
                key_differences.append("Claimant communications significantly more positive than respondent")
            else:
                key_differences.append("Respondent communications significantly more positive than claimant")

        if claimant_rows and respondent_rows:
            claimant_labels = {r["label"] for r in claimant_rows}
            respondent_labels = {r["label"] for r in respondent_rows}
            label_diff = claimant_labels.symmetric_difference(respondent_labels)
            if label_diff:
                key_differences.append(f"Label divergence: {', '.join(sorted(label_diff))}")

        return {
            "claimant_avg": claimant_avg,
            "respondent_avg": respondent_avg,
            "divergence": divergence,
            "key_differences": key_differences,
        }

    # ------------------------------------------------------------------
    # Public: classify tone categories (keyword + pattern based)
    # ------------------------------------------------------------------

    def classify_tone_categories(self, text: str) -> list[dict]:
        """
        Classify text into tone categories: hostile, evasive, condescending,
        professional, supportive.

        Returns [{category, score, evidence_segments}].
        """
        text_lower = text.lower()
        results: list[dict] = []

        for category, definition in TONE_PATTERNS.items():
            evidence_segments: list[str] = []
            keyword_hits = 0

            # Keyword matching
            keywords: frozenset = definition["keywords"]
            for keyword in keywords:
                if keyword in text_lower:
                    keyword_hits += 1
                    # Extract surrounding context as evidence
                    idx = text_lower.find(keyword)
                    start = max(0, idx - 30)
                    end = min(len(text), idx + len(keyword) + 30)
                    segment = text[start:end].strip()
                    if segment and segment not in evidence_segments:
                        evidence_segments.append(segment)

            # Pattern matching
            patterns: list[re.Pattern] = definition["patterns"]
            for pattern in patterns:
                matches = pattern.findall(text)
                keyword_hits += len(matches)
                for match in matches:
                    match_text = match if isinstance(match, str) else match[0] if match else ""
                    if match_text and match_text not in evidence_segments:
                        evidence_segments.append(match_text)

            # Score: normalise hits to 0.0-1.0 range (cap at 5 hits = 1.0)
            score = min(keyword_hits / 5.0, 1.0)

            results.append(
                {
                    "category": category,
                    "score": round(score, 4),
                    "evidence_segments": evidence_segments,
                }
            )

        return results

    # ------------------------------------------------------------------
    # Private: LLM enhancement
    # ------------------------------------------------------------------

    async def _enhance_with_llm(self, text: str, baseline_categories: list[dict]) -> list[dict]:
        """Attempt LLM-based tone classification; fall back to baseline on failure."""
        if not self._llm_service:
            return baseline_categories

        try:
            from .llm import SentimentLLM

            llm_integration = SentimentLLM(self._llm_service)
            llm_categories = await llm_integration.classify_tone(text)

            if llm_categories:
                # Merge: LLM scores weighted 0.6, keyword scores 0.4
                merged = []
                llm_map = {c["category"]: c for c in llm_categories}
                for baseline in baseline_categories:
                    cat = baseline["category"]
                    if cat in llm_map:
                        blended_score = round(baseline["score"] * 0.4 + llm_map[cat]["score"] * 0.6, 4)
                        evidence = list(set(baseline["evidence_segments"] + llm_map[cat].get("evidence", [])))
                        merged.append({"category": cat, "score": blended_score, "evidence_segments": evidence})
                    else:
                        merged.append(baseline)
                return merged

        except Exception as e:
            logger.warning(f"LLM tone enhancement failed, using keyword baseline: {e}")

        return baseline_categories
