"""Redline Shard API endpoints."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from .engine import RedlineEngine
    from .shard import RedlineShard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/redline", tags=["redline"])

_db = None
_event_bus = None
_llm_service = None
_shard: Optional["RedlineShard"] = None
_engine: Optional["RedlineEngine"] = None


def init_api(db, event_bus, llm_service=None, shard=None, engine=None):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _engine
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _engine = engine


def _get_shard() -> "RedlineShard":
    if not _shard:
        raise HTTPException(status_code=503, detail="Redline shard not available")
    return _shard


def _get_engine() -> "RedlineEngine":
    if not _engine:
        raise HTTPException(status_code=503, detail="Redline engine not available")
    return _engine


# --- Request/Response Models ---


class CreateComparisonRequest(BaseModel):
    doc_a_id: str
    doc_b_id: str
    title: str = ""
    case_id: Optional[str] = None


class UpdateComparisonRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    diff_count: Optional[int] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    modifications: Optional[int] = None
    diffs: Optional[List[Dict[str, Any]]] = None
    case_id: Optional[str] = None


class CompareRequest(BaseModel):
    doc_a_id: str
    doc_b_id: str
    title: str = ""
    case_id: Optional[str] = None


class DiffRequest(BaseModel):
    """Raw diff between two texts."""

    text_a: str
    text_b: str


class ClassifyRequest(BaseModel):
    """Classify a list of changes."""

    diffs: List[Dict[str, Any]]


class SemanticDiffRequest(BaseModel):
    """LLM semantic diff between two documents."""

    doc_a_id: str
    doc_b_id: str


# --- CRUD Endpoints ---


@router.get("/")
async def list_comparisons(
    case_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """List comparisons with optional filters."""
    shard = _get_shard()
    return await shard.list_comparisons(case_id=case_id, status=status)


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_redline.comparisons")
    return {"count": result["count"] if result else 0}


@router.get("/{comp_id}")
async def get_comparison(comp_id: str):
    """Get a single comparison with diffs."""
    shard = _get_shard()
    result = await shard.get_comparison(comp_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return result


@router.post("/")
async def create_comparison(request: CreateComparisonRequest):
    """Create a new comparison record."""
    shard = _get_shard()
    return await shard.create_comparison(
        doc_a_id=request.doc_a_id,
        doc_b_id=request.doc_b_id,
        title=request.title,
        case_id=request.case_id,
    )


@router.put("/{comp_id}")
async def update_comparison(comp_id: str, request: UpdateComparisonRequest):
    """Update a comparison record."""
    shard = _get_shard()

    # Check it exists first
    existing = await shard.get_comparison(comp_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Comparison not found")

    updates = request.model_dump(exclude_none=True)
    if not updates:
        return existing

    result = await shard.update_comparison(comp_id, updates)
    if result is None:
        raise HTTPException(status_code=400, detail="Invalid update")
    return result


@router.delete("/{comp_id}")
async def delete_comparison(comp_id: str):
    """Delete a comparison record."""
    shard = _get_shard()

    existing = await shard.get_comparison(comp_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Comparison not found")

    await shard.delete_comparison(comp_id)
    return {"deleted": True, "id": comp_id}


# --- Domain Endpoints ---


@router.post("/compare")
async def compare_documents(request: CompareRequest):
    """
    Compare two documents: compute diff, classify changes, store result.

    Uses the RedlineEngine for full document comparison.
    """
    engine = _get_engine()
    return await engine.compare_documents(
        doc_a_id=request.doc_a_id,
        doc_b_id=request.doc_b_id,
    )


@router.post("/diff")
async def raw_diff(request: DiffRequest):
    """
    Raw diff between two texts.

    Returns line-by-line diffs without classification or persistence.
    """
    engine = _get_engine()
    diffs = engine.compute_diff(request.text_a, request.text_b)
    return {"diffs": diffs, "total": len(diffs)}


@router.post("/classify")
async def classify_changes(request: ClassifyRequest):
    """
    Classify a list of changes with significance scores.

    Adds legal-relevance classification and significance (0.0-1.0).
    """
    engine = _get_engine()
    classified = engine.classify_changes(request.diffs)
    return {"classified": classified, "total": len(classified)}


@router.post("/semantic")
async def semantic_diff(request: SemanticDiffRequest):
    """
    LLM-powered semantic diff between two documents.

    Distinguishes substantive vs formatting vs clarification changes.
    """
    engine = _get_engine()
    results = await engine.semantic_diff(
        doc_a_id=request.doc_a_id,
        doc_b_id=request.doc_b_id,
    )
    return {"changes": results, "total": len(results)}
