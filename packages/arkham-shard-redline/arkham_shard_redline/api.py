"""Redline Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .models import DocumentChange, DocumentComparison, VersionChain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/redline", tags=["redline"])

_db = None
_event_bus = None
_llm_service = None
_shard = None


def init_api(db, event_bus, llm_service=None, shard=None):
    global _db, _event_bus, _llm_service, _shard
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard


class CreateComparisonRequest(BaseModel):
    project_id: str
    base_document_id: str
    target_document_id: str
    metadata: Dict[str, Any] = {}


@router.post("/comparisons", response_model=Dict[str, str])
async def create_comparison(request: CreateComparisonRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    comp_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_redline.comparisons
        (id, tenant_id, project_id, base_document_id, target_document_id, diff_summary)
        VALUES (:id, :tenant_id, :project_id, :base, :target, :summary)
        """,
        {
            "id": comp_id,
            "tenant_id": tenant_id,
            "project_id": request.project_id,
            "base": request.base_document_id,
            "target": request.target_document_id,
            "summary": "Comparison pending...",
        },
    )

    if _event_bus:
        await _event_bus.emit("redline.comparison.created", {"comparison_id": comp_id})

    return {"id": comp_id}


@router.get("/comparisons/{comp_id}")
async def get_comparison(comp_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_redline.comparisons WHERE id = :id", {"id": comp_id})
    if not row:
        raise HTTPException(status_code=404, detail="Comparison not found")

    comp = dict(row)
    changes = await _db.fetch_all("SELECT * FROM arkham_redline.changes WHERE comparison_id = :id", {"id": comp_id})
    comp["changes"] = [dict(c) for c in changes]

    return comp


@router.get("/project/{project_id}/chains")
async def list_chains(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_redline.version_chains WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_redline.comparisons")
    return {"count": result["count"] if result else 0}
