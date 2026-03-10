"""BurdenMap Shard API endpoints.

CRUD for burden_elements plus domain endpoints:
- /populate: auto-populate from claim type
- /dashboard/{case_id}: traffic-light dashboard
- /shift/detect: burden shift detection
- /gaps/{case_id}: gap analysis
- /suggest: LLM evidence suggestions
"""

import logging
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .engine import BurdenEngine
    from .llm import BurdenLLM
    from .shard import BurdenMapShard

logger = logging.getLogger(__name__)

VALID_STATUSES = {"unmet", "partial", "met", "disputed"}

SCHEMA = "arkham_burden_map"


def get_shard(request: Request) -> "BurdenMapShard":
    """Get the BurdenMap shard instance from app state."""
    shard = getattr(request.app.state, "burden_map_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="BurdenMap shard not available")
    return shard


router = APIRouter(prefix="/api/burden-map", tags=["burden-map"])

# Module-level references set during initialization
_db = None
_event_bus = None
_llm_service = None
_shard = None
_engine: "BurdenEngine | None" = None
_burden_llm: "BurdenLLM | None" = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    engine=None,
    burden_llm=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _engine, _burden_llm
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _engine = engine
    _burden_llm = burden_llm


# --- Request/Response Models ---


class CreateElementRequest(BaseModel):
    case_id: Optional[str] = None
    claim: str
    element: str
    legal_standard: str = ""
    burden_party: str = "claimant"
    evidence_ids: List[str] = Field(default_factory=list)
    status: str = "unmet"
    notes: Optional[str] = None


class UpdateElementRequest(BaseModel):
    case_id: Optional[str] = None
    claim: Optional[str] = None
    element: Optional[str] = None
    legal_standard: Optional[str] = None
    burden_party: Optional[str] = None
    evidence_ids: Optional[List[str]] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PopulateRequest(BaseModel):
    case_id: str
    claim_type: str  # 's.13', 's.26', 's.27'


class ShiftDetectRequest(BaseModel):
    case_id: str


class SuggestRequest(BaseModel):
    case_id: str
    case_context: str = ""


# --- Helper ---


def _ensure_db():
    if not _db:
        raise HTTPException(status_code=503, detail="Burden service not initialized")


def _ensure_engine():
    if not _engine:
        raise HTTPException(status_code=503, detail="BurdenEngine not initialized")


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )


# --- Domain Endpoints ---


@router.post("/populate")
async def populate_from_claims(request: PopulateRequest):
    """Auto-populate burden elements based on claim type."""
    _ensure_engine()

    try:
        elements = await _engine.populate_from_claims(
            case_id=request.case_id,
            claim_type=request.claim_type,
        )
        return {"count": len(elements), "elements": elements}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard/{case_id}")
async def get_dashboard(case_id: str):
    """Traffic-light dashboard for a case."""
    _ensure_engine()

    dashboard = await _engine.compute_dashboard(case_id)
    return dashboard


@router.post("/shift/detect")
async def detect_shift(request: ShiftDetectRequest):
    """Check if burden has shifted under s.136 EA 2010."""
    _ensure_engine()

    result = await _engine.detect_burden_shift(request.case_id)
    return result


@router.get("/gaps/{case_id}")
async def get_gaps(case_id: str):
    """Gap analysis -- find unmet/partial elements."""
    _ensure_engine()

    gaps = await _engine.gap_analysis(case_id)
    return {"count": len(gaps), "gaps": gaps}


@router.post("/suggest")
async def suggest_evidence(request: SuggestRequest):
    """LLM: suggest evidence for burden gaps."""
    _ensure_engine()

    if not _burden_llm or not _burden_llm.is_available:
        raise HTTPException(status_code=503, detail="LLM service not available")

    gaps = await _engine.gap_analysis(request.case_id)
    if not gaps:
        return {"suggestions": [], "message": "No gaps found -- all burden elements are met."}

    suggestions = await _burden_llm.suggest_evidence(gaps, case_context=request.case_context)
    return {
        "count": len(suggestions),
        "suggestions": [
            {
                "element": s.element,
                "suggestion": s.suggestion,
                "evidence_type": s.evidence_type,
                "priority": s.priority,
                "reasoning": s.reasoning,
            }
            for s in suggestions
        ],
    }


# --- CRUD Endpoints ---


@router.get("/")
async def list_elements(
    case_id: Optional[str] = Query(None),
    claim: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """List burden elements with optional filters."""
    _ensure_db()

    query = f"SELECT * FROM {SCHEMA}.burden_elements WHERE 1=1"
    params: dict = {}

    if case_id and isinstance(case_id, str):
        query += " AND case_id = :case_id"
        params["case_id"] = case_id
    if claim and isinstance(claim, str):
        query += " AND claim = :claim"
        params["claim"] = claim
    if status is not None and isinstance(status, str):
        _validate_status(status)
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at"

    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "elements": [dict(r) for r in rows]}


@router.get("/matrix")
async def get_matrix(case_id: str = Query(...)):
    """Return burden elements grouped by claim with met/total counts."""
    _ensure_db()

    rows = await _db.fetch_all(
        f"SELECT * FROM {SCHEMA}.burden_elements WHERE case_id = :case_id ORDER BY claim, created_at",
        {"case_id": case_id},
    )

    claims_map: dict = defaultdict(list)
    for row in rows:
        claims_map[row["claim"]].append(dict(row))

    claims = []
    for claim_name, elements in claims_map.items():
        met_count = sum(1 for e in elements if e.get("status") == "met")
        claims.append(
            {
                "claim": claim_name,
                "elements": elements,
                "met_count": met_count,
                "total": len(elements),
            }
        )

    return {"claims": claims}


@router.get("/{element_id}")
async def get_element(element_id: str):
    """Get a single burden element by ID."""
    _ensure_db()

    row = await _db.fetch_one(
        f"SELECT * FROM {SCHEMA}.burden_elements WHERE id = :id",
        {"id": element_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Element not found")

    return dict(row)


@router.post("/")
async def create_element(request: CreateElementRequest):
    """Create a new burden element."""
    _ensure_db()
    _validate_status(request.status)

    eid = str(uuid.uuid4())

    await _db.execute(
        f"""
        INSERT INTO {SCHEMA}.burden_elements
            (id, case_id, claim, element, legal_standard, burden_party,
             evidence_ids, status, notes, created_at, updated_at)
        VALUES
            (:id, :case_id, :claim, :element, :legal_standard, :burden_party,
             :evidence_ids, :status, :notes, NOW(), NOW())
        """,
        {
            "id": eid,
            "case_id": request.case_id,
            "claim": request.claim,
            "element": request.element,
            "legal_standard": request.legal_standard,
            "burden_party": request.burden_party,
            "evidence_ids": request.evidence_ids,
            "status": request.status,
            "notes": request.notes,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "burden-map.item.created",
            {"element_id": eid, "claim": request.claim},
            source="burden-map-shard",
        )

    return {"element_id": eid, "status": "created"}


@router.put("/{element_id}")
async def update_element(element_id: str, request: UpdateElementRequest):
    """Update an existing burden element."""
    _ensure_db()

    # Check element exists
    existing = await _db.fetch_one(
        f"SELECT * FROM {SCHEMA}.burden_elements WHERE id = :id",
        {"id": element_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Element not found")

    # Build dynamic SET clause from non-None fields
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return dict(existing)

    if "status" in updates:
        _validate_status(updates["status"])

    set_parts = []
    params: dict = {"id": element_id}
    for field_name, value in updates.items():
        set_parts.append(f"{field_name} = :{field_name}")
        params[field_name] = value

    set_parts.append("updated_at = NOW()")
    set_clause = ", ".join(set_parts)

    await _db.execute(
        f"UPDATE {SCHEMA}.burden_elements SET {set_clause} WHERE id = :id",
        params,
    )

    if _event_bus:
        await _event_bus.emit(
            "burden-map.item.updated",
            {"element_id": element_id},
            source="burden-map-shard",
        )

    # Re-fetch updated row
    updated = await _db.fetch_one(
        f"SELECT * FROM {SCHEMA}.burden_elements WHERE id = :id",
        {"id": element_id},
    )
    return dict(updated)


@router.delete("/{element_id}")
async def delete_element(element_id: str):
    """Delete a burden element."""
    _ensure_db()

    existing = await _db.fetch_one(
        f"SELECT * FROM {SCHEMA}.burden_elements WHERE id = :id",
        {"id": element_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Element not found")

    await _db.execute(
        f"DELETE FROM {SCHEMA}.burden_elements WHERE id = :id",
        {"id": element_id},
    )

    if _event_bus:
        await _event_bus.emit(
            "burden-map.item.deleted",
            {"element_id": element_id},
            source="burden-map-shard",
        )

    return {"status": "deleted", "element_id": element_id}


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    _ensure_db()
    result = await _db.fetch_one(f"SELECT COUNT(*) as count FROM {SCHEMA}.burden_elements")
    return {"count": result["count"] if result else 0}
