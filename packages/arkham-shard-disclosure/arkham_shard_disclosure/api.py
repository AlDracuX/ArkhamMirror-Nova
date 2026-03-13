"""Disclosure Shard API endpoints."""

import logging
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .models import VALID_STATUSES

if TYPE_CHECKING:
    from .engine import DisclosureEngine
    from .llm import DisclosureLLMHelper
    from .shard import DisclosureShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "DisclosureShard":
    """Get the Disclosure shard instance from app state."""
    shard = getattr(request.app.state, "disclosure_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Disclosure shard not available")
    return shard


router = APIRouter(prefix="/api/disclosure", tags=["disclosure"])

# Module-level references set during initialization
_db = None
_event_bus = None
_llm_service = None
_shard = None
_engine: Optional["DisclosureEngine"] = None
_llm_helper: Optional["DisclosureLLMHelper"] = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    engine=None,
    llm_helper=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _engine, _llm_helper
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _engine = engine
    _llm_helper = llm_helper


# --- Request/Response Models ---


class CreateDisclosureRequest(BaseModel):
    """Create a new disclosure request."""

    case_id: Optional[str] = None
    category: str = ""
    description: str = ""
    requesting_party: str = ""
    status: str = "pending"
    deadline: Optional[str] = None
    document_ids: List[str] = Field(default_factory=list)
    response_text: Optional[str] = None


class UpdateDisclosureRequest(BaseModel):
    """Update an existing disclosure request."""

    case_id: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    requesting_party: Optional[str] = None
    status: Optional[str] = None
    deadline: Optional[str] = None
    document_ids: Optional[List[str]] = None
    response_text: Optional[str] = None


class ScheduleRequest(BaseModel):
    """Request body for schedule generation."""

    case_id: str


class GapDetectRequest(BaseModel):
    """Request body for gap detection."""

    case_id: str


class EvasionScoreRequest(BaseModel):
    """Request body for evasion scoring."""

    respondent_id: str
    case_id: str


class DeadlineCalculateRequest(BaseModel):
    """Request body for deadline calculation."""

    order_date: str  # ISO format date string
    deadline_days: int = 14
    deadline_type: str = "calendar_days"


class ClassifyDocumentRequest(BaseModel):
    """Request body for document classification."""

    document_id: str
    metadata: dict = Field(default_factory=dict)


class ScheduleGenerateRequest(BaseModel):
    """Request body for enhanced schedule generation."""

    case_id: str


# --- CRUD Endpoints ---


@router.get("/")
async def list_disclosure_requests(
    case_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """List disclosure requests with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = "SELECT * FROM arkham_disclosure.disclosure_requests WHERE 1=1"
    params: dict = {}

    if case_id:
        query += " AND case_id = :case_id"
        params["case_id"] = case_id
    if status:
        query += " AND status = :status"
        params["status"] = status
    if category:
        query += " AND category = :category"
        params["category"] = category

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "requests": [dict(r) for r in rows]}


# --- Domain Endpoints (MUST be before /{request_id} to avoid path conflicts) ---


@router.post("/gaps/detect")
async def detect_gaps(request: GapDetectRequest):
    """Run gap detection for a case."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Disclosure engine not initialized")

    gaps = await _engine.detect_gaps(request.case_id)
    return {"case_id": request.case_id, "gap_count": len(gaps), "gaps": gaps}


@router.get("/gaps")
async def list_gaps(
    case_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """List disclosure gaps with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = "SELECT * FROM arkham_disclosure.gaps WHERE 1=1"
    params: dict = {}

    if status:
        query += " AND status = :status"
        params["status"] = status

    if case_id:
        query += (
            " AND request_id IN (SELECT id::text FROM arkham_disclosure.disclosure_requests WHERE case_id = :case_id)"
        )
        params["case_id"] = case_id

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "gaps": [dict(r) for r in rows]}


@router.post("/evasion/score")
async def score_evasion(request: EvasionScoreRequest):
    """Score respondent evasion patterns."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Disclosure engine not initialized")

    result = await _engine.score_evasion(request.respondent_id, request.case_id)
    return result


@router.get("/evasion/{respondent_id}")
async def get_evasion_history(respondent_id: str):
    """Get evasion score history for a respondent."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    rows = await _db.fetch_all(
        """
        SELECT id, respondent_id, score, reason, created_at
        FROM arkham_disclosure.evasion_scores
        WHERE respondent_id = :respondent_id
        ORDER BY created_at DESC
        """,
        {"respondent_id": respondent_id},
    )
    return {"respondent_id": respondent_id, "scores": [dict(r) for r in rows]}


@router.post("/deadlines/calculate")
async def calculate_deadline(request: DeadlineCalculateRequest):
    """Calculate disclosure deadline from order date."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Disclosure engine not initialized")

    try:
        order_date = date.fromisoformat(request.order_date)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {request.order_date}")

    deadline = await _engine.calculate_deadline(
        order_date=order_date,
        deadline_days=request.deadline_days,
        deadline_type=request.deadline_type,
    )
    return {
        "order_date": order_date.isoformat(),
        "deadline": deadline.isoformat(),
        "deadline_days": request.deadline_days,
        "deadline_type": request.deadline_type,
    }


@router.post("/schedule/generate")
async def generate_enhanced_schedule(request: ScheduleGenerateRequest):
    """Generate full disclosure schedule with gaps and evasion data."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Disclosure engine not initialized")

    schedule = await _engine.generate_schedule(request.case_id)
    return {"case_id": request.case_id, "schedule": schedule}


@router.post("/classify")
async def classify_document(request: ClassifyDocumentRequest):
    """Classify a document against disclosure request categories using LLM."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Disclosure engine not initialized")

    matched_ids = await _engine.match_document_to_request(request.document_id, request.metadata)
    return {
        "document_id": request.document_id,
        "matched_request_ids": matched_ids,
        "match_count": len(matched_ids),
    }


# --- Individual Request Endpoints ---


@router.get("/{request_id}")
async def get_disclosure_request(request_id: str):
    """Get a single disclosure request by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_disclosure.disclosure_requests WHERE id = :id",
        {"id": request_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Disclosure request not found")
    return dict(row)


@router.post("/")
async def create_disclosure_request(request: CreateDisclosureRequest):
    """Create a new disclosure request."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    # Validate status
    if request.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    req_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Parse deadline string to date object for PostgreSQL DATE column
    deadline_val = None
    if request.deadline:
        try:
            deadline_val = date.fromisoformat(request.deadline)
        except (ValueError, TypeError):
            deadline_val = None

    await _db.execute(
        """
        INSERT INTO arkham_disclosure.disclosure_requests
            (id, case_id, category, description, requesting_party, status, deadline, document_ids, response_text, created_at, updated_at)
        VALUES
            (:id, :case_id, :category, :description, :requesting_party, :status, :deadline, :document_ids, :response_text, :created_at, :updated_at)
        """,
        {
            "id": req_id,
            "case_id": request.case_id,
            "category": request.category,
            "description": request.description,
            "requesting_party": request.requesting_party,
            "status": request.status,
            "deadline": deadline_val,
            "document_ids": request.document_ids if request.document_ids else [],
            "response_text": request.response_text,
            "created_at": now,
            "updated_at": now,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "disclosure.request.created",
            {"request_id": req_id, "case_id": request.case_id, "category": request.category},
            source="disclosure",
        )

    return {"request_id": req_id}


@router.put("/{request_id}")
async def update_disclosure_request(request_id: str, request: UpdateDisclosureRequest):
    """Update an existing disclosure request."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    # Check exists
    existing = await _db.fetch_one(
        "SELECT * FROM arkham_disclosure.disclosure_requests WHERE id = :id",
        {"id": request_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Disclosure request not found")

    # Validate status if provided
    if request.status is not None and request.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    # Build dynamic update
    updates = []
    params = {"id": request_id, "updated_at": datetime.utcnow()}

    if request.case_id is not None:
        updates.append("case_id = :case_id")
        params["case_id"] = request.case_id
    if request.category is not None:
        updates.append("category = :category")
        params["category"] = request.category
    if request.description is not None:
        updates.append("description = :description")
        params["description"] = request.description
    if request.requesting_party is not None:
        updates.append("requesting_party = :requesting_party")
        params["requesting_party"] = request.requesting_party
    if request.status is not None:
        updates.append("status = :status")
        params["status"] = request.status
    if request.deadline is not None:
        updates.append("deadline = :deadline")
        try:
            params["deadline"] = date.fromisoformat(request.deadline)
        except (ValueError, TypeError):
            params["deadline"] = None
    if request.document_ids is not None:
        updates.append("document_ids = :document_ids")
        params["document_ids"] = request.document_ids
    if request.response_text is not None:
        updates.append("response_text = :response_text")
        params["response_text"] = request.response_text

    updates.append("updated_at = :updated_at")

    if updates:
        query = f"UPDATE arkham_disclosure.disclosure_requests SET {', '.join(updates)} WHERE id = :id"
        await _db.execute(query, params)

    if _event_bus:
        await _event_bus.emit(
            "disclosure.request.updated",
            {"request_id": request_id},
            source="disclosure",
        )

    return {"updated": True, "request_id": request_id}


@router.delete("/{request_id}")
async def delete_disclosure_request(request_id: str):
    """Delete a disclosure request."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    existing = await _db.fetch_one(
        "SELECT * FROM arkham_disclosure.disclosure_requests WHERE id = :id",
        {"id": request_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Disclosure request not found")

    await _db.execute(
        "DELETE FROM arkham_disclosure.disclosure_requests WHERE id = :id",
        {"id": request_id},
    )

    if _event_bus:
        await _event_bus.emit("disclosure.request.deleted", {"request_id": request_id}, source="disclosure")

    return {"deleted": True, "request_id": request_id}


# --- Domain Endpoint ---


@router.post("/schedule")
async def generate_disclosure_schedule(request: ScheduleRequest):
    """Generate a disclosure timeline ordered by deadline for a case."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    rows = await _db.fetch_all(
        """
        SELECT id, category, deadline, status
        FROM arkham_disclosure.disclosure_requests
        WHERE case_id = :case_id
        ORDER BY
            CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
            deadline ASC
        """,
        {"case_id": request.case_id},
    )

    timeline = [
        {
            "request_id": str(row["id"]),
            "category": row["category"],
            "deadline": row["deadline"].isoformat() if row.get("deadline") else None,
            "status": row["status"],
        }
        for row in rows
    ]

    return {"timeline": timeline}


# --- Badge Endpoint ---


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_disclosure.disclosure_requests")
    return {"count": result["count"] if result else 0}
