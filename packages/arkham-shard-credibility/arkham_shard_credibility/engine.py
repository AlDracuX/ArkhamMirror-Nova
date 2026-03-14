"""
Credibility Scoring Engine - Witness credibility assessment.

Pure algorithmic scoring (no LLM required) that evaluates witness credibility
across four dimensions: consistency, corroboration, specificity, and timeliness.

Designed for Employment Tribunal litigation analysis.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Date/time patterns for extraction
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    re.compile(
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
]

TIME_PATTERNS = [
    re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)?\b"),
    re.compile(r"\b\d{1,2}\s*(?:am|pm|AM|PM)\b"),
]

# Named entity-like patterns (proper nouns, reference numbers)
SPECIFIC_DETAIL_PATTERNS = [
    re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"),  # Proper names like "Sarah Jones"
    re.compile(r"\b(?:Room|Office|Building)\s+\w+\b", re.IGNORECASE),  # Location refs
    re.compile(r"\b[A-Z]{2,}-\d{4}-\d+\b"),  # Reference numbers like GR-2024-015
    re.compile(r"\b(?:email|letter|memo|report|minutes|contract)\b", re.IGNORECASE),  # Document refs
]

# Hedging / vagueness indicators
HEDGE_WORDS = frozenset(
    [
        "perhaps",
        "maybe",
        "possibly",
        "probably",
        "might",
        "could",
        "i think",
        "i believe",
        "i'm not sure",
        "not certain",
        "cannot recall",
        "do not remember",
        "don't remember",
        "cannot remember",
        "not really",
        "sort of",
        "kind of",
        "around",
        "sometime",
        "somehow",
        "somewhere",
        "someone",
        "something",
        "i guess",
        "i suppose",
    ]
)

# Negation patterns for contradiction detection
# Each pair: (positive_pattern, negative_pattern) -- if one statement matches
# positive and another matches negative, that's a contradiction.
NEGATION_PAIRS = [
    # Receiving/attending/seeing actions
    (
        re.compile(
            r"\bi\s+(?:did\s+)?(?:receive[d]?|attend(?:ed)?|se(?:e|en|aw)|hear[d]?|send|sent|submit(?:ted)?|go|went)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bi\s+(?:never|did\s+not|didn'?t|have\s+not|haven'?t)\s+\w*\s*(?:receive[d]?|attend(?:ed)?|se(?:e|en|aw)|hear[d]?|send|sent|submit(?:ted)?|go|went)\b",
            re.IGNORECASE,
        ),
    ),
    # Presence
    (
        re.compile(r"\bi\s+(?:was\s+(?:present|there)|attended|was\s+at)\b", re.IGNORECASE),
        re.compile(
            r"\bi\s+(?:was\s+not\s+(?:present|there)|wasn'?t\s+(?:present|there)|did\s+not\s+attend|didn'?t\s+attend)\b",
            re.IGNORECASE,
        ),
    ),
]


def _extract_dates(text: str) -> list[str]:
    """Extract date strings from text."""
    dates = []
    for pattern in DATE_PATTERNS:
        dates.extend(pattern.findall(text))
    return dates


def _extract_key_phrases(text: str) -> set[str]:
    """Extract key content phrases for overlap comparison."""
    # Normalize and extract significant word n-grams
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    # Remove common stop words
    stops = frozenset(
        [
            "the",
            "and",
            "was",
            "were",
            "that",
            "this",
            "with",
            "for",
            "from",
            "have",
            "has",
            "had",
            "not",
            "but",
            "are",
            "been",
            "being",
            "they",
            "their",
            "which",
            "about",
            "would",
            "could",
            "should",
            "also",
            "than",
            "other",
            "into",
            "some",
            "very",
            "just",
            "may",
            "any",
        ]
    )
    filtered = [w for w in words if w not in stops]
    bigrams = {f"{filtered[i]} {filtered[i + 1]}" for i in range(len(filtered) - 1)}
    return set(filtered) | bigrams


class CredibilityEngine:
    """
    Witness credibility scoring engine for Employment Tribunal analysis.

    Scores witnesses on four dimensions:
    - Consistency: Do their statements contradict each other?
    - Corroboration: Is their testimony supported by documents?
    - Specificity: Do they give specific dates/details vs vague answers?
    - Timeliness: Were statements made close to the events described?

    Produces an overall credibility score 0-100.
    """

    # Default 3-factor weights (sum to 1.0) -- used when no events provided
    DEFAULT_WEIGHTS = {
        "consistency": 0.40,
        "corroboration": 0.35,
        "specificity": 0.25,
    }

    # 4-factor weights (sum to 1.0) -- used when events are provided
    FOUR_FACTOR_WEIGHTS = {
        "consistency": 0.30,
        "corroboration": 0.30,
        "specificity": 0.20,
        "timeliness": 0.20,
    }

    def __init__(self, event_bus=None):
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Public: score a witness across all factors
    # ------------------------------------------------------------------

    def score_witness(
        self,
        statements: list[str],
        documents: list[dict[str, str]],
        weights: dict[str, float] | None = None,
        events: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Score a witness across all credibility factors.

        Args:
            statements: List of witness statement texts.
            documents: List of {"title": ..., "text": ...} supporting documents.
            weights: Optional custom weights (overrides defaults).
            events: Optional list of {"text": ..., "date": ...} timeline events.
                    When provided, enables 4-factor scoring with timeliness.

        Returns:
            {
                "overall_score": int 0-100,
                "level": str (unreliable/low/medium/high/verified),
                "factors": [{"name": str, "score": int, "weight": float, "evidence": list[str]}]
            }
        """
        use_timeliness = events is not None

        if not statements:
            base_weights = self.FOUR_FACTOR_WEIGHTS if use_timeliness else self.DEFAULT_WEIGHTS
            factors = [
                {
                    "name": "consistency",
                    "score": 0,
                    "weight": base_weights["consistency"],
                    "evidence": ["No statements provided"],
                },
                {
                    "name": "corroboration",
                    "score": 0,
                    "weight": base_weights["corroboration"],
                    "evidence": ["No statements provided"],
                },
                {
                    "name": "specificity",
                    "score": 0,
                    "weight": base_weights["specificity"],
                    "evidence": ["No statements provided"],
                },
            ]
            if use_timeliness:
                factors.append(
                    {
                        "name": "timeliness",
                        "score": 0,
                        "weight": base_weights["timeliness"],
                        "evidence": ["No statements provided"],
                    }
                )
            return {
                "overall_score": 0,
                "level": "unreliable",
                "factors": factors,
            }

        if weights:
            w = weights
        elif use_timeliness:
            w = self.FOUR_FACTOR_WEIGHTS
        else:
            w = self.DEFAULT_WEIGHTS

        consistency = self.score_consistency(statements)
        corroboration = self.score_corroboration(statements, documents)
        specificity = self.score_specificity(statements)

        overall = (
            consistency["score"] * w["consistency"]
            + corroboration["score"] * w["corroboration"]
            + specificity["score"] * w["specificity"]
        )

        factors = [
            {
                "name": "consistency",
                "score": consistency["score"],
                "weight": w["consistency"],
                "evidence": consistency["evidence"],
            },
            {
                "name": "corroboration",
                "score": corroboration["score"],
                "weight": w["corroboration"],
                "evidence": corroboration["evidence"],
            },
            {
                "name": "specificity",
                "score": specificity["score"],
                "weight": w["specificity"],
                "evidence": specificity["evidence"],
            },
        ]

        if use_timeliness:
            timeliness = self.score_timeliness(statements, events)
            overall += timeliness["score"] * w["timeliness"]
            factors.append(
                {
                    "name": "timeliness",
                    "score": timeliness["score"],
                    "weight": w["timeliness"],
                    "evidence": timeliness["evidence"],
                }
            )

        overall = max(0, min(100, int(overall)))

        return {
            "overall_score": overall,
            "level": self._score_to_level(overall),
            "factors": factors,
        }

    # ------------------------------------------------------------------
    # Public: consistency scoring
    # ------------------------------------------------------------------

    def score_consistency(self, statements: list[str]) -> dict[str, Any]:
        """
        Score consistency between multiple witness statements.

        Checks for:
        - Negation contradictions (said X, then said not X)
        - Temporal contradictions (different dates for same event)
        - Content overlap (statements referencing same events should align)

        Returns: {"score": int 0-100, "evidence": list[str]}
        """
        if not statements:
            return {"score": 0, "evidence": ["No statements provided"]}

        if len(statements) == 1:
            return {"score": 70, "evidence": ["Single statement -- consistency cannot be fully assessed"]}

        contradictions: list[str] = []
        consistency_signals: list[str] = []

        # 1. Check negation contradictions
        for i in range(len(statements)):
            for j in range(i + 1, len(statements)):
                neg_hits = self._detect_negation_contradictions(statements[i], statements[j])
                contradictions.extend(neg_hits)

        # 2. Check temporal contradictions
        date_by_context = self._extract_dates_with_context(statements)
        temporal_hits = self._detect_temporal_contradictions(date_by_context)
        contradictions.extend(temporal_hits)

        # 3. Check content overlap (consistent references)
        phrase_sets = [_extract_key_phrases(s) for s in statements]
        if len(phrase_sets) >= 2:
            total_overlap = 0
            pair_count = 0
            for i in range(len(phrase_sets)):
                for j in range(i + 1, len(phrase_sets)):
                    if phrase_sets[i] and phrase_sets[j]:
                        overlap = len(phrase_sets[i] & phrase_sets[j])
                        union = len(phrase_sets[i] | phrase_sets[j])
                        if union > 0:
                            total_overlap += overlap / union
                            pair_count += 1
            if pair_count > 0:
                avg_overlap = total_overlap / pair_count
                if avg_overlap > 0.15:
                    consistency_signals.append(f"Statements share consistent terminology (overlap: {avg_overlap:.0%})")

        # Calculate score
        base_score = 80  # Start high, deduct for contradictions
        contradiction_penalty = min(len(contradictions) * 30, 75)
        # Consistency bonus only applies when no contradictions found
        consistency_bonus = min(len(consistency_signals) * 10, 20) if not contradictions else 0

        score = max(0, min(100, base_score - contradiction_penalty + consistency_bonus))

        evidence = contradictions + consistency_signals
        if not evidence:
            evidence = ["No contradictions detected"]

        return {"score": score, "evidence": evidence}

    # ------------------------------------------------------------------
    # Public: corroboration scoring
    # ------------------------------------------------------------------

    def score_corroboration(
        self,
        statements: list[str],
        documents: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Score how well witness statements are corroborated by documents.

        Checks keyword/date overlap between statements and document texts.

        Returns: {"score": int 0-100, "evidence": list[str]}
        """
        if not statements:
            return {"score": 0, "evidence": ["No statements provided"]}

        if not documents:
            return {"score": 20, "evidence": ["No supporting documents provided"]}

        doc_texts = [d.get("text", "") for d in documents]
        doc_titles = [d.get("title", "") for d in documents]
        doc_phrases = [_extract_key_phrases(t) for t in doc_texts]
        doc_dates = [set(_extract_dates(t)) for t in doc_texts]

        corroborated_count = 0
        evidence: list[str] = []

        for stmt in statements:
            stmt_phrases = _extract_key_phrases(stmt)
            stmt_dates = set(_extract_dates(stmt))
            best_match = 0.0
            best_doc = ""

            for idx, (dp, dd) in enumerate(zip(doc_phrases, doc_dates)):
                # Phrase overlap
                if stmt_phrases and dp:
                    overlap = len(stmt_phrases & dp) / max(len(stmt_phrases), 1)
                else:
                    overlap = 0.0

                # Date match bonus
                date_match = len(stmt_dates & dd) > 0 if stmt_dates and dd else False
                if date_match:
                    overlap += 0.3

                if overlap > best_match:
                    best_match = overlap
                    best_doc = doc_titles[idx] if idx < len(doc_titles) else f"Document {idx + 1}"

            if best_match >= 0.15:
                corroborated_count += 1
                evidence.append(f"Statement corroborated by '{best_doc}' (match: {best_match:.0%})")

        if not evidence:
            evidence = ["No corroboration found between statements and documents"]

        # Score: proportion of statements corroborated, scaled to 0-100
        corroboration_ratio = corroborated_count / len(statements)
        score = int(corroboration_ratio * 80 + 20 * min(corroboration_ratio, 0.5) * 2)
        score = max(0, min(100, score))

        return {"score": score, "evidence": evidence}

    # ------------------------------------------------------------------
    # Public: specificity scoring
    # ------------------------------------------------------------------

    def score_specificity(self, statements: list[str]) -> dict[str, Any]:
        """
        Score the specificity/detail level of witness statements.

        Rewards: specific dates, times, names, reference numbers, locations.
        Penalises: hedging language, vague terms, lack of detail.

        Returns: {"score": int 0-100, "evidence": list[str]}
        """
        if not statements:
            return {"score": 0, "evidence": ["No statements provided"]}

        total_specifics = 0
        total_hedges = 0
        total_words = 0
        evidence: list[str] = []

        for stmt in statements:
            words = stmt.split()
            total_words += len(words)
            stmt_lower = stmt.lower()

            # Count specific details
            date_count = sum(len(p.findall(stmt)) for p in DATE_PATTERNS)
            time_count = sum(len(p.findall(stmt)) for p in TIME_PATTERNS)
            detail_count = sum(len(p.findall(stmt)) for p in SPECIFIC_DETAIL_PATTERNS)

            specifics = date_count + time_count + detail_count
            total_specifics += specifics

            if date_count > 0:
                evidence.append(f"Contains {date_count} specific date reference(s)")
            if time_count > 0:
                evidence.append(f"Contains {time_count} specific time reference(s)")

            # Count hedging language
            hedge_count = 0
            for hedge in HEDGE_WORDS:
                if hedge in stmt_lower:
                    hedge_count += 1
            total_hedges += hedge_count

            if hedge_count > 0:
                evidence.append(f"Contains {hedge_count} hedging/vague term(s)")

        if total_words == 0:
            return {"score": 0, "evidence": ["Empty statements"]}

        # Specificity density: specifics per 100 words
        specificity_density = (total_specifics / max(total_words, 1)) * 100

        # Hedge density: hedges per 100 words
        hedge_density = (total_hedges / max(total_words, 1)) * 100

        # Score calculation
        # Base from specificity: each specific detail per 100 words adds points
        specificity_score = min(specificity_density * 12, 70)  # Cap contribution at 70

        # Hedge penalty: each hedge per 100 words removes points
        hedge_penalty = min(hedge_density * 15, 50)  # Cap penalty at 50

        # Base score so even moderately specific text scores reasonably
        base = 30
        score = int(base + specificity_score - hedge_penalty)
        score = max(0, min(100, score))

        if not evidence:
            evidence = ["No specific details or hedging detected"]

        return {"score": score, "evidence": evidence}

    # ------------------------------------------------------------------
    # Public: timeliness scoring
    # ------------------------------------------------------------------

    def score_timeliness(
        self,
        statements: list[str],
        events: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Score how timely witness statements are relative to events.

        Compares dates mentioned in statements against event dates.
        Statements referencing dates close to actual events score higher.

        Args:
            statements: List of witness statement texts.
            events: List of {"text": ..., "date": "YYYY-MM-DD"} timeline events.

        Returns: {"score": int 0-100, "evidence": list[str]}
        """
        if not statements:
            return {"score": 0, "evidence": ["No statements provided"]}

        if not events:
            return {"score": 50, "evidence": ["No timeline events to compare against"]}

        # Extract dates from statements
        statement_dates: list[datetime] = []
        for stmt in statements:
            for pattern in DATE_PATTERNS:
                for match in pattern.finditer(stmt):
                    parsed = self._try_parse_date(match.group())
                    if parsed:
                        statement_dates.append(parsed)

        # Parse event dates
        event_dates: list[datetime] = []
        for ev in events:
            date_str = ev.get("date", "")
            parsed = self._try_parse_date(date_str)
            if parsed:
                event_dates.append(parsed)

        evidence: list[str] = []

        if not statement_dates:
            # No dates in statements -- moderate penalty
            evidence.append("No specific dates found in statements")
            return {"score": 40, "evidence": evidence}

        if not event_dates:
            evidence.append("No parseable event dates")
            return {"score": 50, "evidence": evidence}

        # Calculate average proximity between statement dates and nearest event dates
        total_days_gap = 0
        matched_count = 0

        for s_date in statement_dates:
            # Find nearest event date
            min_gap = min(abs((s_date - e_date).days) for e_date in event_dates)
            total_days_gap += min_gap
            matched_count += 1

            if min_gap <= 7:
                evidence.append(f"Statement date within {min_gap} day(s) of event")
            elif min_gap <= 30:
                evidence.append(f"Statement date within {min_gap} days of event")
            elif min_gap > 365:
                evidence.append(f"Statement date {min_gap} days from nearest event (over 1 year)")

        avg_gap = total_days_gap / matched_count if matched_count > 0 else 365

        # Score based on average gap
        # 0 days -> 100, 7 days -> 85, 30 days -> 65, 90 days -> 45, 365+ -> 20
        if avg_gap <= 7:
            score = 100 - int(avg_gap * 2)
        elif avg_gap <= 30:
            score = 85 - int((avg_gap - 7) * 0.87)
        elif avg_gap <= 90:
            score = 65 - int((avg_gap - 30) * 0.33)
        elif avg_gap <= 365:
            score = 45 - int((avg_gap - 90) * 0.09)
        else:
            score = max(10, 20 - int((avg_gap - 365) * 0.01))

        score = max(0, min(100, score))

        if not evidence:
            evidence = [f"Average gap between statement and event dates: {avg_gap:.0f} days"]

        return {"score": score, "evidence": evidence}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _try_parse_date(date_str: str) -> datetime | None:
        """Try to parse a date string in various formats."""
        formats = [
            "%d %B %Y",  # 14 March 2024
            "%B %d, %Y",  # March 14, 2024
            "%B %d %Y",  # March 14 2024
            "%Y-%m-%d",  # 2024-03-14
            "%d/%m/%Y",  # 14/03/2024
            "%m/%d/%Y",  # 03/14/2024
        ]
        date_str = date_str.strip().rstrip(".")
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _detect_negation_contradictions(self, stmt_a: str, stmt_b: str) -> list[str]:
        """Detect negation-based contradictions between two statements."""
        hits = []
        for pos_pattern, neg_pattern in NEGATION_PAIRS:
            a_pos = pos_pattern.search(stmt_a)
            b_neg = neg_pattern.search(stmt_b)
            if a_pos and b_neg:
                hits.append(f"Contradiction: '{a_pos.group()}' vs '{b_neg.group()}'")
            a_neg = neg_pattern.search(stmt_a)
            b_pos = pos_pattern.search(stmt_b)
            if a_neg and b_pos:
                hits.append(f"Contradiction: '{a_neg.group()}' vs '{b_pos.group()}'")
        return hits

    def _extract_dates_with_context(self, statements: list[str]) -> dict[str, list[str]]:
        """Extract dates and their surrounding context from statements."""
        date_contexts: dict[str, list[str]] = defaultdict(list)
        for stmt in statements:
            for pattern in DATE_PATTERNS:
                for match in pattern.finditer(stmt):
                    date_str = match.group()
                    # Get surrounding context (30 chars each side)
                    start = max(0, match.start() - 40)
                    end = min(len(stmt), match.end() + 40)
                    context = stmt[start:end].strip()
                    date_contexts[date_str.lower()].append(context)
        return dict(date_contexts)

    def _detect_temporal_contradictions(self, date_contexts: dict[str, list[str]]) -> list[str]:
        """Detect if different dates are used for apparently the same event."""
        hits = []
        contexts = list(date_contexts.items())
        for i in range(len(contexts)):
            for j in range(i + 1, len(contexts)):
                date_a, ctx_a = contexts[i]
                date_b, ctx_b = contexts[j]
                if date_a == date_b:
                    continue
                # Check if contexts describe the same event (keyword overlap)
                # Use individual words for short contexts, not just bigrams
                words_a = set(re.findall(r"\b[a-z]{3,}\b", " ".join(ctx_a).lower()))
                words_b = set(re.findall(r"\b[a-z]{3,}\b", " ".join(ctx_b).lower()))
                stops = frozenset(
                    ["the", "and", "was", "were", "that", "this", "with", "for", "from", "held", "took", "place"]
                )
                words_a -= stops
                words_b -= stops
                if words_a and words_b:
                    shared = words_a & words_b
                    # Even 2 shared meaningful words in short context suggests same event
                    if len(shared) >= 2 or (len(shared) >= 1 and len(words_a | words_b) <= 8):
                        hits.append(f"Temporal inconsistency: '{date_a}' vs '{date_b}' for similar event")
        return hits

    @staticmethod
    def _score_to_level(score: int) -> str:
        """Convert numeric score to credibility level."""
        if score <= 20:
            return "unreliable"
        elif score <= 40:
            return "low"
        elif score <= 60:
            return "medium"
        elif score <= 80:
            return "high"
        else:
            return "verified"
