"""BurdenEngine -- domain logic for burden of proof element tracking.

Handles:
- Auto-population of burden elements from UK employment claim types
- Traffic-light computation per element
- Dashboard aggregation across a case
- s.136 EA 2010 burden shift detection
- Gap analysis for evidence gaps
"""

import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA = "arkham_burden_map"

# === Claim-type element templates ===
# Each maps a statutory claim to the elements the claimant must establish.

CLAIM_ELEMENTS: dict[str, list[dict[str, str]]] = {
    "s.13": [
        {
            "element": "protected_characteristic",
            "legal_standard": "EA 2010 s.4 -- Claimant possesses a protected characteristic",
        },
        {
            "element": "less_favourable_treatment",
            "legal_standard": "EA 2010 s.13(1) -- Treated less favourably than actual/hypothetical comparator",
        },
        {
            "element": "comparable_circumstances",
            "legal_standard": "EA 2010 s.23 -- Comparator in same or not materially different circumstances",
        },
        {
            "element": "reason_why",
            "legal_standard": "EA 2010 s.13(1) -- Treatment was because of the protected characteristic",
        },
    ],
    "s.26": [
        {
            "element": "unwanted_conduct",
            "legal_standard": "EA 2010 s.26(1)(a) -- Conduct was unwanted",
        },
        {
            "element": "related_to_protected_characteristic",
            "legal_standard": "EA 2010 s.26(1)(a) -- Conduct related to a protected characteristic",
        },
        {
            "element": "purpose_or_effect",
            "legal_standard": "EA 2010 s.26(1)(b) -- Purpose or effect of violating dignity or hostile environment",
        },
        {
            "element": "violating_dignity",
            "legal_standard": "EA 2010 s.26(1)(b)(i) -- Violating the claimant's dignity",
        },
        {
            "element": "creating_hostile_environment",
            "legal_standard": (
                "EA 2010 s.26(1)(b)(ii) -- Creating an intimidating, hostile, "
                "degrading, humiliating or offensive environment"
            ),
        },
    ],
    "s.27": [
        {
            "element": "protected_act",
            "legal_standard": "EA 2010 s.27(2) -- Claimant did a protected act",
        },
        {
            "element": "detriment",
            "legal_standard": "EA 2010 s.27(1) -- Claimant subjected to a detriment",
        },
        {
            "element": "reason_for_detriment",
            "legal_standard": "EA 2010 s.27(1) -- Detriment was because claimant did a protected act",
        },
    ],
}


class BurdenEngine:
    """Core domain logic for burden of proof tracking."""

    def __init__(self, db, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Populate from claims
    # ------------------------------------------------------------------

    async def populate_from_claims(self, case_id: str, claim_type: str) -> list[dict]:
        """Auto-populate burden elements based on claim type.

        Args:
            case_id: UUID of the case.
            claim_type: One of 's.13', 's.26', 's.27'.

        Returns:
            List of created element dicts with id, element, legal_standard, status.

        Raises:
            ValueError: If claim_type is not recognised.
        """
        templates = CLAIM_ELEMENTS.get(claim_type)
        if not templates:
            raise ValueError(
                f"Unknown claim type '{claim_type}'. Supported: {', '.join(sorted(CLAIM_ELEMENTS.keys()))}"
            )

        created: list[dict] = []
        for tmpl in templates:
            eid = str(uuid.uuid4())
            record = {
                "id": eid,
                "case_id": case_id,
                "claim": claim_type,
                "element": tmpl["element"],
                "legal_standard": tmpl["legal_standard"],
                "burden_party": "claimant",
                "evidence_ids": [],
                "status": "unmet",
                "notes": None,
            }

            if self._db:
                await self._db.execute(
                    f"""
                    INSERT INTO {SCHEMA}.burden_elements
                        (id, case_id, claim, element, legal_standard, burden_party,
                         evidence_ids, status, notes, created_at, updated_at)
                    VALUES
                        (:id, :case_id, :claim, :element, :legal_standard, :burden_party,
                         :evidence_ids, :status, :notes, NOW(), NOW())
                    """,
                    record,
                )

            created.append(record)

        if self._event_bus:
            await self._event_bus.emit(
                "burden.status.updated",
                {"case_id": case_id, "claim_type": claim_type, "elements_created": len(created)},
                source="burden-map-shard",
            )

        logger.info(f"Populated {len(created)} elements for case={case_id} claim_type={claim_type}")
        return created

    # ------------------------------------------------------------------
    # Traffic-light computation
    # ------------------------------------------------------------------

    async def compute_traffic_light(self, element_id: str) -> str:
        """Compute traffic-light status for a burden element.

        GREEN: status='met' and evidence_ids has 2+ items
        AMBER: status='partial' or evidence_ids has exactly 1 item
        RED:   status='unmet' and evidence_ids empty

        Updates the element status column and returns the colour string.
        """
        row = None
        if self._db:
            row = await self._db.fetch_one(
                f"SELECT * FROM {SCHEMA}.burden_elements WHERE id = :id",
                {"id": element_id},
            )

        if not row:
            raise ValueError(f"Element {element_id} not found")

        status = row["status"]
        evidence_ids = row.get("evidence_ids") or []

        # Determine colour
        if status == "met" and len(evidence_ids) >= 2:
            colour = "green"
        elif status == "partial" or len(evidence_ids) == 1:
            colour = "amber"
        else:
            colour = "red"

        # Persist updated status
        if self._db:
            await self._db.execute(
                f"UPDATE {SCHEMA}.burden_elements SET status = :status, updated_at = NOW() WHERE id = :id",
                {"id": element_id, "status": colour},
            )

        return colour

    # ------------------------------------------------------------------
    # Dashboard aggregation
    # ------------------------------------------------------------------

    async def compute_dashboard(self, case_id: str) -> dict:
        """Aggregate all elements for a case into a dashboard view.

        Returns:
            {total, green_count, amber_count, red_count, shift_detected, claims: [{claim, elements}]}
        """
        rows: list = []
        if self._db:
            rows = await self._db.fetch_all(
                f"SELECT * FROM {SCHEMA}.burden_elements WHERE case_id = :case_id ORDER BY claim, created_at",
                {"case_id": case_id},
            )

        green = 0
        amber = 0
        red = 0
        claims_map: dict[str, list[dict]] = {}

        for row in rows:
            r = dict(row) if not isinstance(row, dict) else row
            status = r.get("status", "unmet")
            if status == "green" or status == "met":
                green += 1
            elif status == "amber" or status == "partial":
                amber += 1
            else:
                red += 1

            claim_name = r.get("claim", "unknown")
            claims_map.setdefault(claim_name, []).append(r)

        claims_list = [{"claim": k, "elements": v} for k, v in claims_map.items()]

        # Detect shift
        shift_result = await self.detect_burden_shift(case_id)

        return {
            "total": len(rows),
            "green_count": green,
            "amber_count": amber,
            "red_count": red,
            "shift_detected": shift_result.get("shifted", False),
            "claims": claims_list,
        }

    # ------------------------------------------------------------------
    # s.136 EA 2010 burden shift detection
    # ------------------------------------------------------------------

    async def detect_burden_shift(self, case_id: str) -> dict:
        """Under s.136 EA 2010: if all claimant elements are GREEN or AMBER,
        prima facie case is established and burden shifts to respondent.

        Returns:
            {shifted: bool, claim: str|None, reasoning: str}
        """
        rows: list = []
        if self._db:
            rows = await self._db.fetch_all(
                f"SELECT * FROM {SCHEMA}.burden_elements WHERE case_id = :case_id",
                {"case_id": case_id},
            )

        if not rows:
            return {"shifted": False, "claim": None, "reasoning": "No elements found for case."}

        # Group by claim
        claims_map: dict[str, list[dict]] = {}
        for row in rows:
            r = dict(row) if not isinstance(row, dict) else row
            claim_name = r.get("claim", "unknown")
            claims_map.setdefault(claim_name, []).append(r)

        # Check each claim independently
        for claim_name, elements in claims_map.items():
            all_met = all(e.get("status") in ("green", "met", "amber", "partial") for e in elements)
            if all_met and len(elements) > 0:
                reasoning = (
                    f"All {len(elements)} elements for '{claim_name}' are GREEN or AMBER. "
                    f"Under s.136 EA 2010, prima facie case established -- burden shifts to respondent."
                )

                if self._event_bus:
                    await self._event_bus.emit(
                        "burden.shifted",
                        {"case_id": case_id, "claim": claim_name, "reasoning": reasoning},
                        source="burden-map-shard",
                    )

                return {"shifted": True, "claim": claim_name, "reasoning": reasoning}

        return {
            "shifted": False,
            "claim": None,
            "reasoning": "Not all elements are GREEN/AMBER for any claim -- burden remains with claimant.",
        }

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    async def gap_analysis(self, case_id: str) -> list[dict]:
        """Find elements with status 'unmet' or 'partial' -- these are evidence gaps.

        Returns:
            List of {element_id, element, claim, status, gap_description, suggested_evidence}
        """
        rows: list = []
        if self._db:
            rows = await self._db.fetch_all(
                f"""
                SELECT * FROM {SCHEMA}.burden_elements
                WHERE case_id = :case_id AND status IN ('unmet', 'partial', 'red', 'amber')
                ORDER BY claim, created_at
                """,
                {"case_id": case_id},
            )

        gaps: list[dict] = []
        for row in rows:
            r = dict(row) if not isinstance(row, dict) else row
            element_name = r.get("element", "unknown")
            claim_name = r.get("claim", "unknown")
            status = r.get("status", "unmet")
            legal_std = r.get("legal_standard", "")

            gap_desc = f"Element '{element_name}' for claim '{claim_name}' is {status}."
            if legal_std:
                gap_desc += f" Legal standard: {legal_std}"

            suggested = f"Obtain evidence demonstrating {element_name} for {claim_name}."

            gap = {
                "element_id": r.get("id"),
                "element": element_name,
                "claim": claim_name,
                "status": status,
                "gap_description": gap_desc,
                "suggested_evidence": suggested,
            }
            gaps.append(gap)

        if self._event_bus and any(g["status"] in ("unmet", "red") for g in gaps):
            await self._event_bus.emit(
                "burden.gap.critical",
                {"case_id": case_id, "critical_gaps": len([g for g in gaps if g["status"] in ("unmet", "red")])},
                source="burden-map-shard",
            )

        return gaps
