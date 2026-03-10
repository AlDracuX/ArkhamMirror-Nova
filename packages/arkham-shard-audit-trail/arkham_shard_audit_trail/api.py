"""AuditTrail Shard API endpoints.

Search and retrieval for the immutable system action log.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from .shard import AuditTrailShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "AuditTrailShard":
    """Get the AuditTrail shard instance from app state."""
    shard = getattr(request.app.state, "audit_trail_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="AuditTrail shard not available")
    return shard


router = APIRouter(prefix="/api/audit-trail", tags=["audit-trail"])

# Module-level references set during initialization
_db = None
_event_bus = None
_llm_service = None
_shard = None
_engine = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    engine=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _engine
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _engine = engine


# --- Request/Response Models ---


class AuditSearchRequest(BaseModel):
    user_id: Optional[str] = None
    shard: Optional[str] = None
    action_type: Optional[str] = None
    entity_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class CreateExportRequest(BaseModel):
    user_id: Optional[str] = None
    export_format: str
    filters_applied: dict = {}
    row_count: int = 0


class SearchRequest(BaseModel):
    shard: Optional[str] = None
    user_id: Optional[str] = None
    entity_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class ExportRequest(BaseModel):
    shard: Optional[str] = None
    user_id: Optional[str] = None
    entity_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    format: str = "json"


class RetentionRequest(BaseModel):
    retention_days: int = 365


# --- Endpoints ---


@router.get("/actions")
async def list_actions(
    user_id: Optional[str] = None,
    shard: Optional[str] = None,
    action_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 100,
):
    """Search system audit log."""
    if not _db:
        raise HTTPException(status_code=503, detail="Audit service not initialized")

    query = "SELECT * FROM arkham_audit_trail.actions WHERE 1=1"
    params: dict = {"limit": limit}

    if user_id:
        query += " AND user_id = :user_id"
        params["user_id"] = user_id
    if shard:
        query += " AND shard = :shard"
        params["shard"] = shard
    if action_type:
        query += " AND action_type = :action_type"
        params["action_type"] = action_type
    if entity_id:
        query += " AND entity_id = :entity_id"
        params["entity_id"] = entity_id

    query += " ORDER BY timestamp DESC LIMIT :limit"

    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "actions": [dict(r) for r in rows]}


@router.get("/summary")
async def get_audit_summary():
    """Get high-level audit statistics."""
    if not _db:
        return {"total_actions": 0}

    row = await _db.fetch_one("SELECT COUNT(*) as cnt FROM arkham_audit_trail.actions")
    shard_rows = await _db.fetch_all("SELECT shard, COUNT(*) as cnt FROM arkham_audit_trail.actions GROUP BY shard")
    return {
        "total_actions": row["cnt"] if row else 0,
        "shards": {r["shard"]: r["cnt"] for r in shard_rows},
    }


@router.get("/sessions")
async def list_sessions(limit: int = 50):
    """List audit sessions."""
    if not _db:
        raise HTTPException(status_code=503, detail="Audit service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_audit_trail.sessions ORDER BY start_time DESC LIMIT :limit",
        {"limit": limit},
    )
    return {"count": len(rows), "sessions": [dict(r) for r in rows]}


@router.get("/exports")
async def list_exports(limit: int = 50):
    """List audit trail exports."""
    if not _db:
        raise HTTPException(status_code=503, detail="Audit service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_audit_trail.exports ORDER BY created_at DESC LIMIT :limit",
        {"limit": limit},
    )
    return {"count": len(rows), "exports": [dict(r) for r in rows]}


@router.post("/exports")
async def record_export(request: CreateExportRequest):
    """Record that an audit export was performed."""
    if not _db:
        raise HTTPException(status_code=503, detail="Audit service not initialized")

    export_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_audit_trail.exports
        (id, tenant_id, user_id, export_format, filters_applied, row_count)
        VALUES (:id, :tenant_id, :user_id, :format, :filters, :rows)
        """,
        {
            "id": export_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "user_id": request.user_id,
            "format": request.export_format,
            "filters": json.dumps(request.filters_applied),
            "rows": request.row_count,
        },
    )

    if _event_bus:
        await _event_bus.emit("audit.export.recorded", {"export_id": export_id}, source="audit-trail-shard")

    return {"export_id": export_id, "status": "recorded"}


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_audit_trail.actions")
    return {"count": result["count"] if result else 0}


# --- Engine-powered endpoints ---


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO datetime string to datetime object."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@router.post("/search")
async def search_actions(request: SearchRequest):
    """Search audit actions with filters via engine."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Audit engine not initialized")

    results = await _engine.search_actions(
        shard=request.shard,
        user_id=request.user_id,
        entity_id=request.entity_id,
        date_from=_parse_datetime(request.date_from),
        date_to=_parse_datetime(request.date_to),
    )
    return {"count": len(results), "actions": results}


@router.get("/session/{session_id}")
async def get_session_actions(session_id: str):
    """Get all actions for a session, ordered chronologically."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Audit engine not initialized")

    results = await _engine.get_session_actions(session_id)
    return {"count": len(results), "session_id": session_id, "actions": results}


@router.post("/export")
async def export_audit_log(request: ExportRequest):
    """Export audit log for tribunal submission."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Audit engine not initialized")

    filters = {}
    if request.shard:
        filters["shard"] = request.shard
    if request.user_id:
        filters["user_id"] = request.user_id
    if request.entity_id:
        filters["entity_id"] = request.entity_id
    if request.date_from:
        filters["date_from"] = _parse_datetime(request.date_from)
    if request.date_to:
        filters["date_to"] = _parse_datetime(request.date_to)

    result = await _engine.export_audit_log(filters=filters, format=request.format)
    return result


@router.post("/retention")
async def manage_retention(request: RetentionRequest):
    """Manage audit log retention policy."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Audit engine not initialized")

    deleted_count = await _engine.manage_retention(retention_days=request.retention_days)
    return {"deleted_count": deleted_count, "retention_days": request.retention_days}
