"""ComparatorEngine - Core domain logic for s.13/s.26 treatment comparison.

Builds treatment matrices, scores divergences, tracks legal element checklists,
and aggregates significance across incidents for Equality Act 2010 discrimination analysis.
"""

import logging
import uuid
from typing import Any

from .models import (
    DiscriminationElement,
    HarassmentElement,
    TreatmentOutcome,
)

logger = logging.getLogger(__name__)

# Outcome scoring: how "favourable" each outcome is on a 0-1 scale.
_OUTCOME_SCORES: dict[str, float] = {
    TreatmentOutcome.FAVOURABLE.value: 1.0,
    TreatmentOutcome.NEUTRAL.value: 0.5,
    TreatmentOutcome.UNKNOWN.value: 0.5,
    TreatmentOutcome.UNFAVOURABLE.value: 0.0,
}

# s.13 direct discrimination elements
S13_ELEMENTS = [e.value for e in DiscriminationElement]

# s.26 harassment elements
S26_ELEMENTS = [e.value for e in HarassmentElement]


class ComparatorEngine:
    """Core analysis engine for the Comparator shard.

    Operates against the arkham_comparator schema using the frame database service.
    All methods are async and DB-backed.
    """

    def __init__(self, db, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Treatment Matrix
    # ------------------------------------------------------------------

    async def build_treatment_matrix(self, incident_id: str) -> dict:
        """Build side-by-side claimant vs comparator treatment matrix for an incident.

        Returns::

            {
                "incident_id": str,
                "incident": {...} | None,
                "treatments": [
                    {"subject": str, "treatment": str, "outcome": str, "evidence": [...]},
                    ...
                ],
                "divergences": [
                    {"claimant_outcome": str, "comparator_subject": str,
                     "comparator_outcome": str, "score": float},
                    ...
                ],
            }
        """
        incident = None
        if self._db:
            row = await self._db.fetch_one(
                "SELECT * FROM arkham_comparator.incidents WHERE id = :id",
                {"id": incident_id},
            )
            if row:
                incident = dict(row)

        treatments: list[dict] = []
        if self._db:
            rows = await self._db.fetch_all(
                "SELECT * FROM arkham_comparator.treatments WHERE incident_id = :incident_id ORDER BY created_at",
                {"incident_id": incident_id},
            )
            treatments = [dict(r) for r in rows]

        # Group treatments by subject
        by_subject: dict[str, dict] = {}
        for t in treatments:
            sid = t.get("subject_id", "")
            by_subject[sid] = t

        # Compute divergences between claimant and each comparator
        divergences: list[dict] = []
        claimant_treatment = by_subject.get("claimant")
        if claimant_treatment:
            claimant_outcome = claimant_treatment.get("outcome", "unknown")
            for sid, t in by_subject.items():
                if sid == "claimant":
                    continue
                comp_outcome = t.get("outcome", "unknown")
                score = self._compute_divergence_score(claimant_outcome, comp_outcome)
                divergences.append(
                    {
                        "claimant_outcome": claimant_outcome,
                        "comparator_subject": sid,
                        "comparator_outcome": comp_outcome,
                        "score": score,
                    }
                )

        formatted_treatments = [
            {
                "subject": t.get("subject_id", ""),
                "treatment": t.get("treatment_description", ""),
                "outcome": t.get("outcome", "unknown"),
                "evidence": t.get("evidence_ids", []),
            }
            for t in treatments
        ]

        return {
            "incident_id": incident_id,
            "incident": incident,
            "treatments": formatted_treatments,
            "divergences": divergences,
        }

    # ------------------------------------------------------------------
    # Divergence Scoring
    # ------------------------------------------------------------------

    def score_divergence(self, outcome_a: str, outcome_b: str) -> float:
        """Score divergence between two treatment outcomes.

        0.0 = identical treatment outcomes.
        1.0 = maximally opposite outcomes (favourable vs unfavourable).

        Works purely on outcome strings -- no DB call required.
        """
        return self._compute_divergence_score(outcome_a, outcome_b)

    async def score_divergence_by_ids(self, treatment_a_id: str, treatment_b_id: str) -> float:
        """Score divergence between two treatments looked up by ID."""
        if not self._db:
            return 0.0

        row_a = await self._db.fetch_one(
            "SELECT outcome FROM arkham_comparator.treatments WHERE id = :id",
            {"id": treatment_a_id},
        )
        row_b = await self._db.fetch_one(
            "SELECT outcome FROM arkham_comparator.treatments WHERE id = :id",
            {"id": treatment_b_id},
        )
        if not row_a or not row_b:
            return 0.0

        return self._compute_divergence_score(row_a["outcome"], row_b["outcome"])

    # ------------------------------------------------------------------
    # s.13 / s.26 Element Checklists
    # ------------------------------------------------------------------

    async def check_s13_elements(self, case_id: str) -> dict:
        """Track s.13 direct discrimination four elements.

        Returns::

            {
                "elements": [
                    {"element": str, "status": "met"|"unmet", "evidence_count": int},
                    ...
                ],
                "complete": bool,
            }
        """
        return await self._check_elements(case_id, S13_ELEMENTS, "s13")

    async def check_s26_elements(self, case_id: str) -> dict:
        """Track s.26 harassment five elements.

        Returns same structure as check_s13_elements.
        """
        return await self._check_elements(case_id, S26_ELEMENTS, "s26")

    async def _check_elements(self, case_id: str, element_names: list[str], element_type: str) -> dict:
        """Generic element checker.

        Queries the arkham_comparator.legal_elements table for evidence counts.
        Falls back to all-unmet if no DB or no table.
        """
        element_results = []

        if self._db:
            try:
                for element_name in element_names:
                    row = await self._db.fetch_one(
                        "SELECT COUNT(*) as cnt FROM arkham_comparator.legal_elements "
                        "WHERE case_id = :case_id AND element_type = :element_type "
                        "AND element_name = :element_name",
                        {"case_id": case_id, "element_type": element_type, "element_name": element_name},
                    )
                    count = row["cnt"] if row else 0
                    element_results.append(
                        {
                            "element": element_name,
                            "status": "met" if count > 0 else "unmet",
                            "evidence_count": count,
                        }
                    )
            except Exception:
                logger.warning("legal_elements table query failed; returning unmet defaults")
                element_results = [{"element": e, "status": "unmet", "evidence_count": 0} for e in element_names]
        else:
            element_results = [{"element": e, "status": "unmet", "evidence_count": 0} for e in element_names]

        complete = all(el["status"] == "met" for el in element_results)
        return {"elements": element_results, "complete": complete}

    # ------------------------------------------------------------------
    # Aggregate Significance
    # ------------------------------------------------------------------

    async def aggregate_significance(self, case_id: str) -> dict:
        """Aggregate divergence scores across all incidents for a case.

        Returns::

            {
                "incident_count": int,
                "avg_divergence": float,
                "max_divergence": float,
                "overall_significance": "low"|"medium"|"high"|"critical",
            }
        """
        if not self._db:
            return {
                "incident_count": 0,
                "avg_divergence": 0.0,
                "max_divergence": 0.0,
                "overall_significance": "low",
            }

        rows = await self._db.fetch_all(
            "SELECT significance_score FROM arkham_comparator.divergences "
            "WHERE incident_id IN ("
            "  SELECT id FROM arkham_comparator.incidents WHERE project_id = :case_id"
            ") ORDER BY significance_score DESC",
            {"case_id": case_id},
        )

        if not rows:
            return {
                "incident_count": 0,
                "avg_divergence": 0.0,
                "max_divergence": 0.0,
                "overall_significance": "low",
            }

        scores = [r["significance_score"] for r in rows]
        avg = sum(scores) / len(scores) if scores else 0.0
        mx = max(scores) if scores else 0.0

        return {
            "incident_count": len(scores),
            "avg_divergence": round(avg, 4),
            "max_divergence": round(mx, 4),
            "overall_significance": self._classify_significance(avg),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_divergence_score(outcome_a: str, outcome_b: str) -> float:
        """Compute divergence score between two outcome strings.

        Uses absolute difference of numeric outcome scores.
        favourable=1.0, neutral/unknown=0.5, unfavourable=0.0
        """
        score_a = _OUTCOME_SCORES.get(outcome_a, 0.5)
        score_b = _OUTCOME_SCORES.get(outcome_b, 0.5)
        return round(abs(score_a - score_b), 4)

    @staticmethod
    def _classify_significance(avg_score: float) -> str:
        """Classify an average divergence score into a significance level."""
        if avg_score >= 0.8:
            return "critical"
        if avg_score >= 0.6:
            return "high"
        if avg_score >= 0.3:
            return "medium"
        return "low"
