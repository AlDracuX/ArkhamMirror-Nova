"""Strategist Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .models import CounterArgument, RedTeamReport, StrategicPrediction, TacticalModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategist", tags=["strategist"])

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


class CreatePredictionRequest(BaseModel):
    project_id: str
    claim_id: Optional[str] = None
    respondent_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


@router.post("/predictions", response_model=Dict[str, str])
async def create_prediction(request: CreatePredictionRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    pred_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_strategist.predictions
        (id, tenant_id, project_id, claim_id, respondent_id, predicted_argument, confidence, reasoning)
        VALUES (:id, :tenant_id, :project_id, :claim_id, :respondent_id, :argument, :confidence, :reasoning)
        """,
        {
            "id": pred_id,
            "tenant_id": tenant_id,
            "project_id": request.project_id,
            "claim_id": request.claim_id,
            "respondent_id": request.respondent_id,
            "argument": "Prediction pending...",
            "confidence": 0.0,
            "reasoning": "Awaiting analysis",
        },
    )

    if _event_bus:
        await _event_bus.emit("strategist.prediction.generated", {"prediction_id": pred_id})

    return {"id": pred_id}


@router.get("/predictions/{pred_id}")
async def get_prediction(pred_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_strategist.predictions WHERE id = :id", {"id": pred_id})
    if not row:
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred = dict(row)
    counters = await _db.fetch_all(
        "SELECT * FROM arkham_strategist.counterarguments WHERE prediction_id = :id", {"id": pred_id}
    )
    pred["counter_arguments"] = [dict(c) for c in counters]

    return pred


@router.get("/project/{project_id}/reports")
async def list_reports(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_strategist.red_team_reports WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]


@router.get("/project/{project_id}/tactical-models")
async def list_tactical_models(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_strategist.tactical_models WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]
