"""Sentiment Shard API endpoints."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    ComparatorDiff,
    CreateResultRequest,
    SentimentAnalysis,
    SentimentPattern,
    ToneScore,
    UpdateResultRequest,
    analyze_sentiment,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])

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
# CRUD: sentiment_results
# ---------------------------------------------------------------------------


@router.get("/")
async def list_results(
    document_id: Optional[str] = Query(None),
    case_id: Optional[str] = Query(None),
    label: Optional[str] = Query(None),
):
    """List sentiment results with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    query = "SELECT * FROM arkham_sentiment.sentiment_results WHERE 1=1"
    params: Dict[str, Any] = {}

    if document_id:
        query += " AND document_id = :document_id"
        params["document_id"] = document_id
    if case_id:
        query += " AND case_id = :case_id"
        params["case_id"] = case_id
    if label:
        query += " AND label = :label"
        params["label"] = label

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    results = []
    for row in rows:
        r = dict(row)
        # Parse JSONB fields if they come back as strings
        for field in ("passages", "entity_sentiments"):
            if isinstance(r.get(field), str):
                try:
                    r[field] = json.loads(r[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        results.append(r)
    return results


@router.get("/{result_id}")
async def get_result(result_id: str):
    """Get a single sentiment result by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_sentiment.sentiment_results WHERE id = :id",
        {"id": result_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Sentiment result not found")

    r = dict(row)
    for field in ("passages", "entity_sentiments"):
        if isinstance(r.get(field), str):
            try:
                r[field] = json.loads(r[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return r


@router.post("/")
async def create_result(request: CreateResultRequest):
    """Create a new sentiment result."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    result_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await _db.execute(
        """
        INSERT INTO arkham_sentiment.sentiment_results
        (id, document_id, case_id, overall_score, label, confidence, passages, entity_sentiments, analyzed_at, created_at, updated_at)
        VALUES (:id, :document_id, :case_id, :overall_score, :label, :confidence, :passages, :entity_sentiments, :analyzed_at, :created_at, :updated_at)
        """,
        {
            "id": result_id,
            "document_id": request.document_id,
            "case_id": request.case_id,
            "overall_score": request.overall_score,
            "label": request.label,
            "confidence": request.confidence,
            "passages": json.dumps(request.passages),
            "entity_sentiments": json.dumps(request.entity_sentiments),
            "analyzed_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )

    if _event_bus:
        await _event_bus.emit("sentiment.analysis.created", {"result_id": result_id})

    return {"id": result_id}


@router.put("/{result_id}")
async def update_result(result_id: str, request: UpdateResultRequest):
    """Update an existing sentiment result."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    # Verify it exists
    existing = await _db.fetch_one(
        "SELECT id FROM arkham_sentiment.sentiment_results WHERE id = :id",
        {"id": result_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Sentiment result not found")

    updates = []
    params: Dict[str, Any] = {"id": result_id}

    if request.overall_score is not None:
        updates.append("overall_score = :overall_score")
        params["overall_score"] = request.overall_score
    if request.label is not None:
        updates.append("label = :label")
        params["label"] = request.label
    if request.confidence is not None:
        updates.append("confidence = :confidence")
        params["confidence"] = request.confidence
    if request.passages is not None:
        updates.append("passages = :passages")
        params["passages"] = json.dumps(request.passages)
    if request.entity_sentiments is not None:
        updates.append("entity_sentiments = :entity_sentiments")
        params["entity_sentiments"] = json.dumps(request.entity_sentiments)

    if updates:
        updates.append("updated_at = :updated_at")
        params["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(updates)
        await _db.execute(
            f"UPDATE arkham_sentiment.sentiment_results SET {set_clause} WHERE id = :id",
            params,
        )

    return {"id": result_id, "updated": True}


@router.delete("/{result_id}")
async def delete_result(result_id: str):
    """Delete a sentiment result."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = await _db.fetch_one(
        "SELECT id FROM arkham_sentiment.sentiment_results WHERE id = :id",
        {"id": result_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Sentiment result not found")

    await _db.execute(
        "DELETE FROM arkham_sentiment.sentiment_results WHERE id = :id",
        {"id": result_id},
    )

    return {"id": result_id, "deleted": True}


# ---------------------------------------------------------------------------
# Domain: analyze
# ---------------------------------------------------------------------------


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_text(request: AnalyzeRequest):
    """Analyze text for sentiment using keyword-based scoring + optional LLM."""
    if _engine:
        result = await _engine.analyze_document(
            document_id=str(request.document_id),
            text=request.text,
        )
        return AnalyzeResponse(
            document_id=str(request.document_id),
            score=result["overall_score"],
            label=result["label"],
            confidence=result["confidence"],
            key_passages=result["keywords_found"],
        )

    # Fallback: keyword-only when engine not initialised
    result = analyze_sentiment(request.text)
    return AnalyzeResponse(
        document_id=str(request.document_id),
        score=result["score"],
        label=result["label"],
        confidence=result["confidence"],
        key_passages=result["key_passages"],
    )


# ---------------------------------------------------------------------------
# Domain: temporal patterns
# ---------------------------------------------------------------------------


@router.get("/patterns/{case_id}")
async def get_temporal_patterns(case_id: str):
    """Detect tone changes over time for a case."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")
    patterns = await _engine.detect_temporal_patterns(case_id=case_id)
    return {"case_id": case_id, "patterns": patterns}


# ---------------------------------------------------------------------------
# Domain: party comparison
# ---------------------------------------------------------------------------


@router.get("/compare/{case_id}")
async def compare_parties(case_id: str):
    """Compare claimant vs respondent communication styles."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")
    result = await _engine.compare_parties(case_id=case_id)
    return {"case_id": case_id, **result}


# ---------------------------------------------------------------------------
# Domain: classify tone categories
# ---------------------------------------------------------------------------


class ClassifyRequest(BaseModel):
    """Request body for tone classification."""

    text: str


@router.post("/classify")
async def classify_tone(request: ClassifyRequest):
    """Classify communication tone into categories."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")
    categories = _engine.classify_tone_categories(request.text)
    return {"categories": categories}


# ---------------------------------------------------------------------------
# Legacy / badge endpoints
# ---------------------------------------------------------------------------


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


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_sentiment.sentiment_results")
    return {"count": result["count"] if result else 0}
