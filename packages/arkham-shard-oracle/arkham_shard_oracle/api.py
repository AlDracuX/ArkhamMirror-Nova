"""Oracle Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .models import CaseSummary, LegalAuthority, ResearchSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oracle", tags=["oracle"])

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


class ResearchRequest(BaseModel):
    project_id: str
    query: str
    metadata: Dict[str, Any] = {}


@router.post("/research", response_model=Dict[str, str])
async def start_research(request: ResearchRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    session_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_oracle.research_sessions
        (id, project_id, query)
        VALUES (:id, :project_id, :query)
        """,
        {
            "id": session_id,
            "project_id": request.project_id,
            "query": request.query,
        },
    )

    if _event_bus:
        await _event_bus.emit("oracle.research.started", {"session_id": session_id})

    return {"id": session_id}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_oracle.research_sessions WHERE id = :id", {"id": session_id})
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    return dict(row)


@router.get("/authorities/{auth_id}")
async def get_authority(auth_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_oracle.authorities WHERE id = :id", {"id": auth_id})
    if not row:
        raise HTTPException(status_code=404, detail="Authority not found")

    auth = dict(row)
    summary = await _db.fetch_one(
        "SELECT * FROM arkham_oracle.case_summaries WHERE authority_id = :id", {"id": auth_id}
    )
    if summary:
        auth["summary_details"] = dict(summary)

    return auth


@router.get("/project/{project_id}/authorities")
async def list_authorities(project_id: str):
    """List authorities linked to a project via research sessions."""
    sessions = await _db.fetch_all(
        "SELECT authority_ids FROM arkham_oracle.research_sessions WHERE project_id = :project_id",
        {"project_id": project_id},
    )
    all_ids = set()
    for session in sessions:
        ids = session["authority_ids"] if session["authority_ids"] else []
        if isinstance(ids, str):
            import json

            ids = json.loads(ids)
        all_ids.update(ids)

    if not all_ids:
        return []

    id_list = list(all_ids)
    placeholders = ", ".join(f":id_{i}" for i in range(len(id_list)))
    params = {f"id_{i}": aid for i, aid in enumerate(id_list)}
    rows = await _db.fetch_all(
        f"SELECT * FROM arkham_oracle.authorities WHERE id IN ({placeholders})",
        params,
    )
    return [dict(r) for r in rows]


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_oracle.authorities")
    return {"count": result["count"] if result else 0}
