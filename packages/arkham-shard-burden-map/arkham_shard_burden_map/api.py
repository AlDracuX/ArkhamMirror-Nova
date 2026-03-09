"""BurdenMap Shard API endpoints."""

import logging
import uuid
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import BurdenMapShard

logger = logging.getLogger(__name__)


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
    title: str
    claim_type: str
    statutory_reference: str = ""
    description: str = ""
    burden_holder: str = "claimant"
    required: bool = True
    theory_id: Optional[str] = None
    linked_claim_id: Optional[str] = None
    project_id: Optional[str] = None


class AddEvidenceWeightRequest(BaseModel):
    element_id: str
    weight: str  # strong, moderate, weak, neutral, adverse
    source_type: str = "document"
    source_id: str
    source_title: str
    excerpt: Optional[str] = None
    supports_burden_holder: bool = True
    analyst_notes: str = ""


# --- Endpoints ---


@router.get("/elements")
async def list_elements(project_id: Optional[str] = None):
    """List all claim elements."""
    if not _db:
        raise HTTPException(status_code=503, detail="Burden service not initialized")

    query = "SELECT * FROM arkham_burden_map.claim_elements WHERE 1=1"
    params: dict = {}
    if project_id:
        query += " AND project_id = :pid"
        params["pid"] = project_id

    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "elements": [dict(r) for r in rows]}


@router.post("/elements")
async def create_element(request: CreateElementRequest):
    """Create a new legal element requirement."""
    if not _db:
        raise HTTPException(status_code=503, detail="Burden service not initialized")

    eid = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_burden_map.claim_elements
            (id, tenant_id, title, claim_type, statutory_reference, description, burden_holder, required, theory_id, linked_claim_id, project_id)
        VALUES
            (:id, :tenant_id, :title, :type, :ref, :desc, :holder, :req, :theory, :claim, :project)
        """,
        {
            "id": eid,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "title": request.title,
            "type": request.claim_type,
            "ref": request.statutory_reference,
            "desc": request.description,
            "holder": request.burden_holder,
            "req": request.required,
            "theory": request.theory_id,
            "claim": request.linked_claim_id,
            "project": request.project_id,
        },
    )
    return {"element_id": eid}


@router.get("/dashboard")
async def get_burden_dashboard(project_id: Optional[str] = None):
    """Get the full burden of proof matrix with traffic lights."""
    if not _db:
        raise HTTPException(status_code=503, detail="Burden service not initialized")

    # This joins elements with their assignments
    query = """
        SELECT ce.*, ba.traffic_light, ba.net_score, ba.supporting_count, ba.adverse_count, ba.gap_summary
        FROM arkham_burden_map.claim_elements ce
        LEFT JOIN arkham_burden_map.burden_assignments ba ON ba.element_id = ce.id
        WHERE ce.status = 'active'
    """
    params: dict = {}
    if project_id:
        query += " AND ce.project_id = :pid"
        params["pid"] = project_id

    rows = await _db.fetch_all(query, params)
    return {"elements": [dict(r) for r in rows]}


@router.post("/weights")
async def add_evidence_weight(request: AddEvidenceWeightRequest):
    """Link a piece of evidence to an element and assess its weight."""
    if not _db:
        raise HTTPException(status_code=503, detail="Burden service not initialized")

    wid = str(uuid.uuid4())
    await _db.execute(
        """
        INSERT INTO arkham_burden_map.evidence_weights
            (id, element_id, weight, source_type, source_id, source_title, excerpt, supports_burden_holder, analyst_notes)
        VALUES
            (:id, :eid, :weight, :stype, :sid, :stitle, :excerpt, :supports, :notes)
        """,
        {
            "id": wid,
            "eid": request.element_id,
            "weight": request.weight,
            "stype": request.source_type,
            "sid": request.source_id,
            "stitle": request.source_title,
            "excerpt": request.excerpt,
            "supports": request.supports_burden_holder,
            "notes": request.analyst_notes,
        },
    )

    # Trigger recalculation if shard available
    if _shard:
        await _shard._recalculate_assignment(request.element_id)

    return {"weight_id": wid, "status": "added"}
