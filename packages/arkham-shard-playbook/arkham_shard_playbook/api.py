"""Playbook Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .models import EvidenceObjective, LitigationStrategy, StrategyScenario

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playbook", tags=["playbook"])

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


class CreateStrategyRequest(BaseModel):
    project_id: str
    title: str
    description: str = ""
    metadata: Dict[str, Any] = {}


@router.post("/strategies", response_model=Dict[str, str])
async def create_strategy(request: CreateStrategyRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    strat_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_playbook.strategies
        (id, tenant_id, project_id, title, description)
        VALUES (:id, :tenant_id, :project_id, :title, :description)
        """,
        {
            "id": strat_id,
            "tenant_id": tenant_id,
            "project_id": request.project_id,
            "title": request.title,
            "description": request.description,
        },
    )

    if _event_bus:
        await _event_bus.emit("playbook.strategy.updated", {"strategy_id": strat_id})

    return {"id": strat_id}


@router.get("/strategies/{strat_id}")
async def get_strategy(strat_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_playbook.strategies WHERE id = :id", {"id": strat_id})
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    strat = dict(row)
    scenarios = await _db.fetch_all("SELECT * FROM arkham_playbook.scenarios WHERE strategy_id = :id", {"id": strat_id})
    strat["scenarios"] = [dict(s) for s in scenarios]

    return strat


@router.get("/project/{project_id}/objectives")
async def list_objectives(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_playbook.evidence_objectives WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_playbook.strategies")
    return {"count": result["count"] if result else 0}
