"""Sentiment Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .models import ComparatorDiff, SentimentAnalysis, SentimentPattern, ToneScore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])

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


class CreateAnalysisRequest(BaseModel):
    document_id: Optional[str] = None
    thread_id: Optional[str] = None
    project_id: str
    metadata: Dict[str, Any] = {}


@router.post("/analyses", response_model=Dict[str, str])
async def create_analysis(request: CreateAnalysisRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    analysis_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    # In a real implementation, we would trigger an LLM job here.
    # For now, we'll just create a placeholder record.
    await _db.execute(
        """
        INSERT INTO arkham_sentiment.analyses
        (id, tenant_id, document_id, thread_id, project_id, summary, overall_sentiment)
        VALUES (:id, :tenant_id, :document_id, :thread_id, :project_id, :summary, :sentiment)
        """,
        {
            "id": analysis_id,
            "tenant_id": tenant_id,
            "document_id": request.document_id,
            "thread_id": request.thread_id,
            "project_id": request.project_id,
            "summary": "Pending analysis...",
            "sentiment": 0.0,
        },
    )

    if _event_bus:
        await _event_bus.emit("sentiment.analysis.created", {"analysis_id": analysis_id})

    return {"id": analysis_id}


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_sentiment.analyses WHERE id = :id", {"id": analysis_id})
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")

    analysis = dict(row)
    scores = await _db.fetch_all(
        "SELECT * FROM arkham_sentiment.tone_scores WHERE analysis_id = :id", {"id": analysis_id}
    )
    analysis["tone_scores"] = [dict(s) for s in scores]

    return analysis


@router.get("/project/{project_id}/patterns")
async def list_patterns(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_sentiment.patterns WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]


@router.get("/project/{project_id}/comparator-diffs")
async def list_comparator_diffs(project_id: str):
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_sentiment.comparator_diffs WHERE project_id = :project_id", {"project_id": project_id}
    )
    return [dict(r) for r in rows]
