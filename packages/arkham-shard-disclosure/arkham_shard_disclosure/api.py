"""Disclosure Shard API endpoints."""

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
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


class CreateRequestRequest(BaseModel):
    respondent_id: str
    request_text: str
    deadline: Optional[str] = None


class CreateResponseRequest(BaseModel):
    request_id: str
    response_text: str
    document_ids: List[str] = Field(default_factory=list)
    received_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CreateGapRequest(BaseModel):
    request_id: str
    missing_items_description: str
    status: str = "open"


class CreateEvasionScoreRequest(BaseModel):
    respondent_id: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


# --- Endpoints ---


@router.get("/requests")
async def list_disclosure_requests(respondent_id: Optional[str] = None):
    """List all disclosure requests."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = "SELECT * FROM arkham_disclosure.requests WHERE 1=1"
    params: dict = {}
    if respondent_id:
        query += " AND respondent_id = :rid"
        params["rid"] = respondent_id

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "requests": [dict(r) for r in rows]}


@router.post("/requests")
async def create_disclosure_request(request: CreateRequestRequest):
    """Create a new disclosure request."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    req_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_disclosure.requests (id, tenant_id, respondent_id, request_text, deadline)
        VALUES (:id, :tenant_id, :respondent_id, :text, :deadline)
        """,
        {
            "id": req_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "respondent_id": request.respondent_id,
            "text": request.request_text,
            "deadline": request.deadline,
        },
    )
    return {"request_id": req_id}


@router.get("/responses")
async def list_disclosure_responses(request_id: Optional[str] = None):
    """List all disclosure responses."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = "SELECT * FROM arkham_disclosure.responses WHERE 1=1"
    params: dict = {}
    if request_id:
        query += " AND request_id = :rid"
        params["rid"] = request_id

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "responses": [dict(r) for r in rows]}


@router.post("/responses")
async def create_disclosure_response(request: CreateResponseRequest):
    """Create a new disclosure response."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    res_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_disclosure.responses (id, tenant_id, request_id, response_text, document_ids, received_at)
        VALUES (:id, :tenant_id, :request_id, :text, :doc_ids, :received)
        """,
        {
            "id": res_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "request_id": request.request_id,
            "text": request.response_text,
            "doc_ids": request.document_ids,
            "received": request.received_at,
        },
    )

    # Update request status to fulfilled if all items provided (simplified)
    await _db.execute(
        "UPDATE arkham_disclosure.requests SET status = 'fulfilled' WHERE id = :rid",
        {"rid": request.request_id},
    )

    if _event_bus:
        await _event_bus.emit("disclosure.response.received", {"request_id": request.request_id, "response_id": res_id})

    return {"response_id": res_id}


@router.get("/gaps")
async def list_disclosure_gaps(request_id: Optional[str] = None):
    """List all disclosure gaps."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = "SELECT * FROM arkham_disclosure.gaps WHERE 1=1"
    params: dict = {}
    if request_id:
        query += " AND request_id = :rid"
        params["rid"] = request_id

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "gaps": [dict(r) for r in rows]}


@router.post("/gaps")
async def create_disclosure_gap(request: CreateGapRequest):
    """Record a new disclosure gap."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    gap_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_disclosure.gaps (id, tenant_id, request_id, missing_items_description, status)
        VALUES (:id, :tenant_id, :request_id, :desc, :status)
        """,
        {
            "id": gap_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "request_id": request.request_id,
            "desc": request.missing_items_description,
            "status": request.status,
        },
    )

    # Update request status to partial
    await _db.execute(
        "UPDATE arkham_disclosure.requests SET status = 'partial' WHERE id = :rid",
        {"rid": request.request_id},
    )

    if _event_bus:
        await _event_bus.emit("disclosure.gap.detected", {"request_id": request.request_id, "gap_id": gap_id})

    return {"gap_id": gap_id}


@router.get("/evasion")
async def list_evasion_scores(respondent_id: Optional[str] = None):
    """List evasion scores."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = "SELECT * FROM arkham_disclosure.evasion_scores WHERE 1=1"
    params: dict = {}
    if respondent_id:
        query += " AND respondent_id = :rid"
        params["rid"] = respondent_id

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "scores": [dict(r) for r in rows]}


@router.post("/evasion")
async def create_evasion_score(request: CreateEvasionScoreRequest):
    """Record a new evasion score for a respondent."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    score_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_disclosure.evasion_scores (id, tenant_id, respondent_id, score, reason)
        VALUES (:id, :tenant_id, :respondent_id, :score, :reason)
        """,
        {
            "id": score_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "respondent_id": request.respondent_id,
            "score": request.score,
            "reason": request.reason,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "disclosure.evasion.scored", {"respondent_id": request.respondent_id, "score": request.score}
        )

    return {"score_id": score_id}


@router.get("/compliance")
async def get_compliance_dashboard():
    """Get disclosure compliance summary per respondent."""
    if not _db:
        raise HTTPException(status_code=503, detail="Disclosure service not initialized")

    query = """
        SELECT
            respondent_id,
            COUNT(*) as total_requests,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_requests,
            SUM(CASE WHEN deadline < CURRENT_TIMESTAMP AND status != 'completed' THEN 1 ELSE 0 END) as overdue_requests
        FROM arkham_disclosure.requests
        GROUP BY respondent_id
    """
    rows = await _db.fetch_all(query)
    return {"respondents": [dict(r) for r in rows]}
