"""BurdenMap Shard API endpoints.

CRUD for burden_elements plus a /matrix endpoint that groups by claim.
"""

import logging
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
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


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard


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


# --- Helper ---


def _ensure_db():
    if not _db:
        raise HTTPException(status_code=503, detail="Burden service not initialized")


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )


# --- Endpoints ---


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
