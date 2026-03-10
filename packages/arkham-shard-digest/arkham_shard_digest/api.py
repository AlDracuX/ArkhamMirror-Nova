"""Digest Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .models import CaseBriefing, ChangeLogEntry, DigestSubscription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/digest", tags=["digest"])

_db = None
_event_bus = None
_llm_service = None
_shard = None
_engine = None


def init_api(db, event_bus, llm_service=None, shard=None, engine=None):
    global _db, _event_bus, _llm_service, _shard, _engine
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _engine = engine


# =============================================================================
# Request Models
# =============================================================================


class GenerateBriefingRequest(BaseModel):
    project_id: str
    type: str = "daily"  # daily, weekly, sitrep
    metadata: Dict[str, Any] = {}


class SubscriptionRequest(BaseModel):
    user_id: str
    project_id: str
    frequency: str = "daily"


class ActionItemsRequest(BaseModel):
    project_id: str
    limit: int = 50


# =============================================================================
# Briefing Endpoints
# =============================================================================


@router.post("/briefing/generate")
async def generate_briefing_endpoint(request: GenerateBriefingRequest):
    """Generate a new briefing for a project."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Digest engine not available")

    result = await _engine.generate_briefing(
        project_id=request.project_id,
        briefing_type=request.type,
    )
    return result


@router.get("/briefing/{project_id}")
async def get_latest_briefing(project_id: str):
    """Get the latest briefing for a project."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one(
        """
        SELECT * FROM arkham_digest.briefings
        WHERE project_id = :project_id
        ORDER BY created_at DESC
        LIMIT 1
        """,
        {"project_id": project_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="No briefing found for this project")
    return dict(row)


@router.post("/briefings", response_model=Dict[str, str])
async def generate_briefing(request: GenerateBriefingRequest):
    """Legacy endpoint - generate briefing."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    # If engine available, use it
    if _engine:
        result = await _engine.generate_briefing(
            project_id=request.project_id,
            briefing_type=request.type,
        )
        return {"id": result["briefing_id"]}

    # Fallback to simple insert
    brief_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_digest.briefings
        (id, tenant_id, project_id, type, content)
        VALUES (:id, :tenant_id, :project_id, :type, :content)
        """,
        {
            "id": brief_id,
            "tenant_id": tenant_id,
            "project_id": request.project_id,
            "type": request.type,
            "content": "Generating briefing...",
        },
    )

    if _event_bus:
        await _event_bus.emit("digest.briefing.generated", {"briefing_id": brief_id})

    return {"id": brief_id}


@router.get("/briefings/{brief_id}")
async def get_briefing(brief_id: str):
    """Get a specific briefing by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one("SELECT * FROM arkham_digest.briefings WHERE id = :id", {"id": brief_id})
    if not row:
        raise HTTPException(status_code=404, detail="Briefing not found")

    return dict(row)


# =============================================================================
# Subscription Endpoints
# =============================================================================


@router.post("/subscription")
async def manage_subscription_endpoint(request: SubscriptionRequest):
    """Create or update a briefing subscription."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Digest engine not available")

    result = await _engine.manage_subscription(
        user_id=request.user_id,
        project_id=request.project_id,
        frequency=request.frequency,
    )
    return result


# =============================================================================
# Change Log Endpoints
# =============================================================================


@router.get("/changes/{project_id}")
async def get_changes(project_id: str, limit: int = 50):
    """List recent changes for a project."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    rows = await _db.fetch_all(
        """
        SELECT * FROM arkham_digest.change_log
        WHERE project_id = :project_id
        ORDER BY timestamp DESC
        LIMIT :limit
        """,
        {"project_id": project_id, "limit": limit},
    )
    return [dict(r) for r in rows]


# =============================================================================
# Action Items Endpoints
# =============================================================================


@router.post("/action-items")
async def extract_action_items_endpoint(request: ActionItemsRequest):
    """Extract action items from recent changes."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Digest engine not available")
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    rows = await _db.fetch_all(
        """
        SELECT * FROM arkham_digest.change_log
        WHERE project_id = :project_id
        ORDER BY timestamp DESC
        LIMIT :limit
        """,
        {"project_id": request.project_id, "limit": request.limit},
    )
    changes = [dict(r) for r in rows] if rows else []

    action_items = await _engine.extract_action_items(changes)
    return {"action_items": action_items, "change_count": len(changes)}


# =============================================================================
# Legacy Endpoints (backward compat)
# =============================================================================


@router.get("/project/{project_id}/briefings")
async def list_briefings(project_id: str):
    """List all briefings for a project."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_digest.briefings WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]


@router.get("/project/{project_id}/changes")
async def get_changelog(project_id: str, limit: int = 50):
    """Legacy endpoint - get changelog."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_digest.change_log WHERE project_id = :project_id ORDER BY timestamp DESC LIMIT :limit",
        {"project_id": project_id, "limit": limit},
    )
    return [dict(r) for r in rows]


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_digest.briefings")
    return {"count": result["count"] if result else 0}
