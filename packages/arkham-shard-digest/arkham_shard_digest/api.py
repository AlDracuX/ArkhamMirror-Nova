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


def init_api(db, event_bus, llm_service=None, shard=None):
    global _db, _event_bus, _llm_service, _shard
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard


class GenerateBriefingRequest(BaseModel):
    project_id: str
    type: str = "daily"  # daily, weekly, sitrep
    metadata: Dict[str, Any] = {}


@router.post("/briefings", response_model=Dict[str, str])
async def generate_briefing(request: GenerateBriefingRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

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
    row = await _db.fetch_one("SELECT * FROM arkham_digest.briefings WHERE id = :id", {"id": brief_id})
    if not row:
        raise HTTPException(status_code=404, detail="Briefing not found")

    return dict(row)


@router.get("/project/{project_id}/briefings")
async def list_briefings(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_digest.briefings WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]


@router.get("/project/{project_id}/changes")
async def get_changelog(project_id: str, limit: int = 50):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_digest.change_log WHERE project_id = :project_id ORDER BY timestamp DESC LIMIT :limit",
        {"project_id": project_id, "limit": limit},
    )
    return [dict(r) for r in rows]
