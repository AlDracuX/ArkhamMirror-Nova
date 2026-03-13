"""Strategist Shard API endpoints."""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .models import CounterArgument, RedTeamReport, StrategicPrediction, Strategy, TacticalModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategist", tags=["strategist"])

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


# ---------------------------------------------------------------------------
# Legacy prediction/report endpoints (unchanged)
# ---------------------------------------------------------------------------


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
        await _event_bus.emit("strategist.prediction.generated", {"prediction_id": pred_id}, source="strategist")

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


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_strategist.predictions")
    return {"count": result["count"] if result else 0}


# ---------------------------------------------------------------------------
# Strategy CRUD endpoints
# ---------------------------------------------------------------------------


class CreateStrategyRequest(BaseModel):
    case_id: str
    name: str
    approach: str
    summary: Optional[str] = None
    strengths: List[str] = []
    weaknesses: List[str] = []
    risks: List[str] = []
    opportunities: List[str] = []
    recommended: bool = False
    confidence_score: Optional[float] = None


class UpdateStrategyRequest(BaseModel):
    name: Optional[str] = None
    approach: Optional[str] = None
    summary: Optional[str] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    risks: Optional[List[str]] = None
    opportunities: Optional[List[str]] = None
    recommended: Optional[bool] = None
    confidence_score: Optional[float] = None


class EvaluateRequest(BaseModel):
    strategy_id: str


@router.get("/")
async def list_strategies(
    case_id: Optional[str] = Query(None),
    recommended: Optional[bool] = Query(None),
):
    """List strategies, optionally filtered by case_id and/or recommended flag."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    query = "SELECT * FROM arkham_strategist.strategies WHERE 1=1"
    params: Dict[str, Any] = {}

    if case_id is not None:
        query += " AND case_id = :case_id"
        params["case_id"] = case_id

    if recommended is not None:
        query += " AND recommended = :recommended"
        params["recommended"] = recommended

    query += " ORDER BY created_at DESC"

    rows = await _db.fetch_all(query, params)
    return [dict(r) for r in rows]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get a single strategy by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_strategist.strategies WHERE id = :id",
        {"id": strategy_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return dict(row)


@router.post("/")
async def create_strategy(request: CreateStrategyRequest):
    """Create a new strategy."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    strategy_id = str(uuid.uuid4())

    await _db.execute(
        """
        INSERT INTO arkham_strategist.strategies
        (id, case_id, name, approach, summary, strengths, weaknesses, risks, opportunities, recommended, confidence_score)
        VALUES (:id, :case_id, :name, :approach, :summary, :strengths, :weaknesses, :risks, :opportunities, :recommended, :confidence_score)
        """,
        {
            "id": strategy_id,
            "case_id": request.case_id,
            "name": request.name,
            "approach": request.approach,
            "summary": request.summary,
            "strengths": json.dumps(request.strengths),
            "weaknesses": json.dumps(request.weaknesses),
            "risks": json.dumps(request.risks),
            "opportunities": json.dumps(request.opportunities),
            "recommended": request.recommended,
            "confidence_score": request.confidence_score,
        },
    )

    if _event_bus:
        await _event_bus.emit("strategist.strategy.created", {"strategy_id": strategy_id}, source="strategist")

    return {"id": strategy_id}


@router.put("/{strategy_id}")
async def update_strategy(strategy_id: str, request: UpdateStrategyRequest):
    """Update an existing strategy."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = await _db.fetch_one(
        "SELECT * FROM arkham_strategist.strategies WHERE id = :id",
        {"id": strategy_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")

    updates = []
    params: Dict[str, Any] = {"id": strategy_id}

    for field_name in ["name", "approach", "summary", "recommended", "confidence_score"]:
        value = getattr(request, field_name)
        if value is not None:
            updates.append(f"{field_name} = :{field_name}")
            params[field_name] = value

    for json_field in ["strengths", "weaknesses", "risks", "opportunities"]:
        value = getattr(request, json_field)
        if value is not None:
            updates.append(f"{json_field} = :{json_field}")
            params[json_field] = json.dumps(value)

    if not updates:
        return dict(existing)

    updates.append("updated_at = NOW()")
    set_clause = ", ".join(updates)

    await _db.execute(
        f"UPDATE arkham_strategist.strategies SET {set_clause} WHERE id = :id",
        params,
    )

    updated = await _db.fetch_one(
        "SELECT * FROM arkham_strategist.strategies WHERE id = :id",
        {"id": strategy_id},
    )
    return dict(updated) if updated else {"id": strategy_id}


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: str):
    """Delete a strategy."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = await _db.fetch_one(
        "SELECT * FROM arkham_strategist.strategies WHERE id = :id",
        {"id": strategy_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")

    await _db.execute(
        "DELETE FROM arkham_strategist.strategies WHERE id = :id",
        {"id": strategy_id},
    )

    return {"deleted": True, "id": strategy_id}


@router.post("/evaluate")
async def evaluate_strategy(request: EvaluateRequest):
    """Evaluate a strategy and return SWOT analysis with recommendation."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_strategist.strategies WHERE id = :id",
        {"id": request.strategy_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found")

    data = dict(row)

    # Parse SWOT fields (may already be lists from JSONB driver)
    strengths = _parse_json_field(data.get("strengths", []))
    weaknesses = _parse_json_field(data.get("weaknesses", []))
    risks = _parse_json_field(data.get("risks", []))
    opportunities = _parse_json_field(data.get("opportunities", []))

    # Recommendation logic: compare strengths count vs weaknesses count
    s_count = len(strengths)
    w_count = len(weaknesses)

    if s_count > w_count:
        recommendation = "proceed"
    elif s_count < w_count:
        recommendation = "abandon"
    else:
        recommendation = "revise"

    # Confidence: ratio of strengths to total SWOT items, clamped to [0.0, 1.0]
    total = s_count + w_count + len(risks) + len(opportunities)
    if total > 0:
        confidence = min(1.0, max(0.0, s_count / total))
    else:
        confidence = 0.5  # No data, neutral confidence

    return {
        "strategy_id": request.strategy_id,
        "swot": {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "risks": risks,
            "opportunities": opportunities,
        },
        "recommendation": recommendation,
        "confidence": round(confidence, 4),
    }


def _parse_json_field(value: Any, default: Any = None) -> list:
    """Parse a JSON field that may already be parsed by the database driver."""
    if value is None:
        return default if default is not None else []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else []
    return default if default is not None else []


# ---------------------------------------------------------------------------
# Domain Analysis Endpoints (powered by StrategistEngine)
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    project_id: str
    claim_id: Optional[str] = None


class CounterRequest(BaseModel):
    pass  # prediction_id comes from path


class SWOTRequest(BaseModel):
    project_id: str


class RedTeamRequest(BaseModel):
    project_id: str
    target_id: str


class TacticalModelRequest(BaseModel):
    project_id: str
    respondent_id: str


@router.post("/predict")
async def predict_arguments(request: PredictRequest):
    """Predict respondent arguments using LLM and case context."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Strategist engine not available")

    results = await _engine.predict_arguments(
        project_id=request.project_id,
        claim_id=request.claim_id,
    )
    return {"predictions": results, "count": len(results)}


@router.post("/counter/{prediction_id}")
async def generate_counterarguments(prediction_id: str):
    """Generate counterarguments for a predicted respondent argument."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Strategist engine not available")

    results = await _engine.generate_counterarguments(prediction_id=prediction_id)
    return {"counterarguments": results, "count": len(results)}


@router.post("/swot")
async def build_swot(request: SWOTRequest):
    """Build SWOT analysis for the current litigation position."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Strategist engine not available")

    result = await _engine.build_swot(project_id=request.project_id)
    return result


@router.post("/red-team")
async def red_team(request: RedTeamRequest):
    """Red team assessment - attack own case from respondent's perspective."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Strategist engine not available")

    result = await _engine.red_team(
        project_id=request.project_id,
        target_id=request.target_id,
    )
    return result


@router.post("/tactical-model")
async def build_tactical_model(request: TacticalModelRequest):
    """Build tactical model of respondent's likely behaviour."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Strategist engine not available")

    result = await _engine.build_tactical_model(
        project_id=request.project_id,
        respondent_id=request.respondent_id,
    )
    return result
