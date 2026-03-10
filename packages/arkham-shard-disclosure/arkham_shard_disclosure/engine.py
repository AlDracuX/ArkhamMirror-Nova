"""Disclosure Engine - Core domain logic for disclosure analysis.

Provides:
- Gap detection between disclosure requests and responses
- Evasion scoring for respondent behaviour patterns
- Deadline calculation respecting calendar/working days
- Schedule generation for tribunal applications
- Document-to-request matching with LLM fallback
"""

import logging
import uuid
from datetime import date, timedelta

from .models import EvasionCategory, GapStatus

logger = logging.getLogger(__name__)

# Evasion weights for scoring
EVASION_WEIGHTS = {
    "delay": 0.2,
    "partial": 0.3,
    "redaction": 0.3,
    "refusal": 0.5,
}
MAX_EVASION_SCORE = sum(EVASION_WEIGHTS.values())


class DisclosureEngine:
    """Core engine for disclosure gap analysis and evasion detection."""

    def __init__(self, db, event_bus=None, llm_helper=None):
        """
        Initialize the disclosure engine.

        Args:
            db: Database service for queries
            event_bus: Optional event bus for emitting events
            llm_helper: Optional LLM helper for document classification
        """
        self._db = db
        self._event_bus = event_bus
        self._llm_helper = llm_helper

    async def detect_gaps(self, case_id: str) -> list[dict]:
        """Compare disclosure requests vs responses and identify gaps.

        For each request with status 'pending'/'requested' that has no matching
        response or has a partial response, create/update a gap record.

        Args:
            case_id: The case identifier to check

        Returns:
            List of gap dicts with {request_id, missing_items_description, status}
        """
        if not self._db:
            logger.warning("No database available for gap detection")
            return []

        # Fetch all requests for this case that are pending or requested
        requests = await self._db.fetch_all(
            """
            SELECT id, category, description, status
            FROM arkham_disclosure.disclosure_requests
            WHERE case_id = :case_id
              AND status IN ('pending', 'requested', 'partial')
            ORDER BY created_at
            """,
            {"case_id": case_id},
        )

        if not requests:
            return []

        gaps = []
        for req in requests:
            req_id = str(req["id"])

            # Check if a response exists for this request
            response = await self._db.fetch_one(
                """
                SELECT id, response_text
                FROM arkham_disclosure.responses
                WHERE request_id = :request_id
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"request_id": req_id},
            )

            gap_status = GapStatus.OPEN.value
            if req["status"] == "partial" or (response and not response.get("response_text")):
                missing_desc = f"Partial or empty response for: {req['description'] or req['category']}"
            elif response is None:
                missing_desc = f"No response received for: {req['description'] or req['category']}"
            else:
                # Response exists and is not empty - no gap
                continue

            gap_id = str(uuid.uuid4())

            # Upsert gap record
            existing_gap = await self._db.fetch_one(
                """
                SELECT id FROM arkham_disclosure.gaps
                WHERE request_id = :request_id AND status != 'resolved'
                """,
                {"request_id": req_id},
            )

            if existing_gap:
                gap_id = str(existing_gap["id"])
                await self._db.execute(
                    """
                    UPDATE arkham_disclosure.gaps
                    SET missing_items_description = :desc, status = :status
                    WHERE id = :id
                    """,
                    {"id": gap_id, "desc": missing_desc, "status": gap_status},
                )
            else:
                await self._db.execute(
                    """
                    INSERT INTO arkham_disclosure.gaps (id, request_id, missing_items_description, status)
                    VALUES (:id, :request_id, :desc, :status)
                    """,
                    {"id": gap_id, "request_id": req_id, "desc": missing_desc, "status": gap_status},
                )

            gaps.append(
                {
                    "request_id": req_id,
                    "gap_id": gap_id,
                    "missing_items_description": missing_desc,
                    "status": gap_status,
                }
            )

        # Emit event if gaps found
        if gaps and self._event_bus:
            await self._event_bus.emit(
                "disclosure.gap.detected",
                {"case_id": case_id, "gap_count": len(gaps), "gaps": gaps},
            )

        logger.info(f"Detected {len(gaps)} disclosure gaps for case {case_id}")
        return gaps

    async def score_evasion(self, respondent_id: str, case_id: str) -> dict:
        """Compute evasion score for a respondent across disclosure responses.

        Pattern detection: count partial_responses, redactions, delays, refusals.
        Score = weighted sum / max_possible.

        Args:
            respondent_id: The respondent to score
            case_id: The case context

        Returns:
            Dict with {respondent_id, score, breakdown, category}
        """
        if not self._db:
            return {
                "respondent_id": respondent_id,
                "score": 0.0,
                "breakdown": {},
                "category": EvasionCategory.NONE.value,
            }

        # Fetch all requests where this respondent is the responding party
        requests = await self._db.fetch_all(
            """
            SELECT id, status, deadline, created_at
            FROM arkham_disclosure.disclosure_requests
            WHERE case_id = :case_id
            ORDER BY created_at
            """,
            {"case_id": case_id},
        )

        if not requests:
            return {
                "respondent_id": respondent_id,
                "score": 0.0,
                "breakdown": {},
                "category": EvasionCategory.NONE.value,
            }

        total = len(requests)
        breakdown = {
            "delay": 0,
            "partial": 0,
            "redaction": 0,
            "refusal": 0,
            "total_requests": total,
        }

        for req in requests:
            status = req["status"]
            if status == "overdue" or (req.get("deadline") and req["deadline"] < date.today()):
                breakdown["delay"] += 1
            if status == "partial":
                breakdown["partial"] += 1
            if status == "refused":
                breakdown["refusal"] += 1

        # Check responses for redaction indicators
        responses = await self._db.fetch_all(
            """
            SELECT response_text FROM arkham_disclosure.responses
            WHERE request_id IN (
                SELECT id::text FROM arkham_disclosure.disclosure_requests
                WHERE case_id = :case_id
            )
            """,
            {"case_id": case_id},
        )

        for resp in responses:
            text = (resp.get("response_text") or "").lower()
            if "redacted" in text or "[redacted]" in text or "withheld" in text:
                breakdown["redaction"] += 1

        # Calculate weighted score
        if total == 0:
            score = 0.0
        else:
            weighted = (
                (breakdown["delay"] / total) * EVASION_WEIGHTS["delay"]
                + (breakdown["partial"] / total) * EVASION_WEIGHTS["partial"]
                + (breakdown["redaction"] / total) * EVASION_WEIGHTS["redaction"]
                + (breakdown["refusal"] / total) * EVASION_WEIGHTS["refusal"]
            )
            score = round(min(weighted / MAX_EVASION_SCORE, 1.0), 3)

        # Determine category
        if score >= 0.6:
            category = EvasionCategory.REFUSAL.value
        elif score >= 0.4:
            category = EvasionCategory.DELAY.value
        elif score >= 0.2:
            category = EvasionCategory.PARTIAL_RESPONSE.value
        elif score > 0:
            category = EvasionCategory.DELAY.value
        else:
            category = EvasionCategory.NONE.value

        result = {
            "respondent_id": respondent_id,
            "score": score,
            "breakdown": breakdown,
            "category": category,
        }

        # Store score
        if self._db:
            score_id = str(uuid.uuid4())
            await self._db.execute(
                """
                INSERT INTO arkham_disclosure.evasion_scores (id, respondent_id, score, reason)
                VALUES (:id, :respondent_id, :score, :reason)
                """,
                {
                    "id": score_id,
                    "respondent_id": respondent_id,
                    "score": score,
                    "reason": f"Auto-scored: {breakdown}",
                },
            )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "disclosure.evasion.scored",
                {"respondent_id": respondent_id, "case_id": case_id, "score": score},
            )

        return result

    async def calculate_deadline(
        self,
        order_date: date,
        deadline_days: int = 14,
        deadline_type: str = "calendar_days",
    ) -> date:
        """Calculate disclosure deadline from order date.

        ET default: 14 calendar days from date of order.

        Args:
            order_date: Date the order was made
            deadline_days: Number of days allowed
            deadline_type: 'calendar_days' or 'working_days'

        Returns:
            The calculated deadline date
        """
        if deadline_type == "working_days":
            current = order_date
            days_added = 0
            while days_added < deadline_days:
                current += timedelta(days=1)
                # Skip Saturday (5) and Sunday (6)
                if current.weekday() < 5:
                    days_added += 1
            result = current
        else:
            # calendar_days (default)
            result = order_date + timedelta(days=deadline_days)

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "disclosure.deadline.calculated",
                {
                    "order_date": order_date.isoformat(),
                    "deadline": result.isoformat(),
                    "deadline_days": deadline_days,
                    "deadline_type": deadline_type,
                },
            )

        return result

    async def generate_schedule(self, case_id: str) -> list[dict]:
        """Generate disclosure schedule with gaps and evasion data.

        Joins requests with gap and evasion information, ordered by deadline.

        Args:
            case_id: The case to generate schedule for

        Returns:
            List of schedule entry dicts ordered by deadline
        """
        if not self._db:
            return []

        # Fetch requests ordered by deadline
        requests = await self._db.fetch_all(
            """
            SELECT r.id, r.category, r.description, r.deadline, r.status,
                   r.requesting_party
            FROM arkham_disclosure.disclosure_requests r
            WHERE r.case_id = :case_id
            ORDER BY
                CASE WHEN r.deadline IS NULL THEN 1 ELSE 0 END,
                r.deadline ASC
            """,
            {"case_id": case_id},
        )

        schedule = []
        for req in requests:
            req_id = str(req["id"])

            # Check for gap
            gap = await self._db.fetch_one(
                """
                SELECT missing_items_description, status
                FROM arkham_disclosure.gaps
                WHERE request_id = :request_id AND status != 'resolved'
                """,
                {"request_id": req_id},
            )

            entry = {
                "request_id": req_id,
                "category": req["category"],
                "description": req.get("description", ""),
                "deadline": req["deadline"].isoformat() if req.get("deadline") else None,
                "status": req["status"],
                "requesting_party": req.get("requesting_party", ""),
                "has_gap": gap is not None,
                "gap_description": gap["missing_items_description"] if gap else None,
                "gap_status": gap["status"] if gap else None,
            }
            schedule.append(entry)

        return schedule

    async def match_document_to_request(self, document_id: str, document_metadata: dict) -> list[str]:
        """Find disclosure requests a document may satisfy.

        Uses LLM classification if available, falls back to keyword matching
        on category strings.

        Args:
            document_id: The processed document ID
            document_metadata: Metadata including category, title, text, etc.

        Returns:
            List of request_ids where document matches request category
        """
        if not self._db:
            return []

        # Get all pending/requested disclosure requests
        requests = await self._db.fetch_all(
            """
            SELECT id, category, description
            FROM arkham_disclosure.disclosure_requests
            WHERE status IN ('pending', 'requested', 'partial')
            """,
        )

        if not requests:
            return []

        # Try LLM classification first
        if self._llm_helper:
            try:
                matches = await self._llm_helper.classify_document(
                    document_metadata=document_metadata,
                    request_categories=[
                        {"request_id": str(r["id"]), "category": r["category"], "description": r.get("description", "")}
                        for r in requests
                    ],
                )
                if matches:
                    return matches
            except Exception as e:
                logger.warning(f"LLM classification failed, falling back to keywords: {e}")

        # Fallback: keyword matching on category
        doc_category = (document_metadata.get("category") or "").lower()
        doc_title = (document_metadata.get("title") or "").lower()
        doc_text = (document_metadata.get("text") or "").lower()
        doc_terms = f"{doc_category} {doc_title} {doc_text}"

        matched_ids = []
        for req in requests:
            req_category = (req["category"] or "").lower()
            req_description = (req.get("description") or "").lower()

            # Check if any significant words from the request category appear in the document
            req_words = set(req_category.split()) | set(req_description.split())
            # Filter out very short words
            req_words = {w for w in req_words if len(w) > 2}

            if not req_words:
                continue

            matches = sum(1 for w in req_words if w in doc_terms)
            if matches > 0 and matches / len(req_words) >= 0.3:
                matched_ids.append(str(req["id"]))

        return matched_ids
