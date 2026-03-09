"""Witnesses Shard API endpoints."""

import logging
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from .shard import WitnessesShard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/witnesses", tags=["witnesses"])

_shard: Optional["WitnessesShard"] = None
_event_bus = None


def init_api(shard=None, event_bus=None):
    global _shard, _event_bus
    _shard = shard
    _event_bus = event_bus


def get_shard(request: Request) -> "WitnessesShard":
    shard = _shard or getattr(request.app.state, "witnesses_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Witnesses shard not available")
    return shard


# === Request Models ===


class WitnessCreate(BaseModel):
    name: str
    role: str = "claimant"
    party: str = "claimant"
    status: str = "identified"
    organization: Optional[str] = None
    position: Optional[str] = None
    contact_info: dict = {}
    notes: str = ""
    credibility_level: str = "unknown"
    credibility_notes: str = ""
    linked_entity_id: Optional[str] = None
    linked_document_ids: list = []
    metadata: dict = {}


class WitnessUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    party: Optional[str] = None
    status: Optional[str] = None
    organization: Optional[str] = None
    position: Optional[str] = None
    contact_info: Optional[dict] = None
    notes: Optional[str] = None
    credibility_level: Optional[str] = None
    credibility_notes: Optional[str] = None
    linked_entity_id: Optional[str] = None
    linked_document_ids: Optional[list] = None
    metadata: Optional[dict] = None


class StatementCreate(BaseModel):
    title: str = ""
    content: str = ""
    status: str = "draft"
    key_points: list = []
    contradictions_found: list = []
    filed_date: Optional[str] = None


class StatementUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    key_points: Optional[list] = None
    contradictions_found: Optional[list] = None
    filed_date: Optional[str] = None


class CrossExamCreate(BaseModel):
    statement_id: Optional[str] = None
    topic: str = ""
    question: str = ""
    expected_answer: str = ""
    actual_answer: str = ""
    effectiveness: str = ""
    notes: str = ""


class EntityLink(BaseModel):
    entity_id: str


# === Endpoints ===


@router.get("/")
async def list_witnesses(
    request: Request,
    role: Optional[str] = None,
    status: Optional[str] = None,
    party: Optional[str] = None,
    credibility: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    shard = get_shard(request)
    from .models import CredibilityLevel, Party, WitnessFilter, WitnessRole, WitnessStatus

    filters = WitnessFilter(
        role=WitnessRole(role) if role else None,
        status=WitnessStatus(status) if status else None,
        party=Party(party) if party else None,
        credibility_level=CredibilityLevel(credibility) if credibility else None,
        search_text=search,
    )
    witnesses = await shard.list_witnesses(filters=filters, limit=limit, offset=offset)
    return {"witnesses": [_witness_to_dict(w) for w in witnesses], "total": len(witnesses)}


@router.get("/count")
async def count_witnesses(request: Request):
    shard = get_shard(request)
    count = await shard.count_witnesses()
    return {"count": count}


@router.post("/")
async def create_witness(request: Request, body: WitnessCreate):
    shard = get_shard(request)
    witness = await shard.create_witness(body.model_dump(exclude_none=True))
    return _witness_to_dict(witness)


@router.get("/stats")
async def get_stats(request: Request):
    shard = get_shard(request)
    stats = await shard.get_stats()
    return {
        "total_witnesses": stats.total_witnesses,
        "by_role": stats.by_role,
        "by_status": stats.by_status,
        "by_party": stats.by_party,
        "total_statements": stats.total_statements,
        "total_cross_exam_notes": stats.total_cross_exam_notes,
    }


@router.get("/{witness_id}")
async def get_witness(request: Request, witness_id: str):
    shard = get_shard(request)
    witness = await shard.get_witness(witness_id)
    if not witness:
        raise HTTPException(status_code=404, detail="Witness not found")
    result = _witness_to_dict(witness)
    result["statements"] = [_stmt_to_dict(s) for s in await shard.list_statements(witness_id)]
    result["cross_exam_notes"] = [_note_to_dict(n) for n in await shard.list_cross_exam_notes(witness_id)]
    return result


@router.put("/{witness_id}")
async def update_witness(request: Request, witness_id: str, body: WitnessUpdate):
    shard = get_shard(request)
    witness = await shard.update_witness(witness_id, body.model_dump(exclude_none=True))
    if not witness:
        raise HTTPException(status_code=404, detail="Witness not found")
    return _witness_to_dict(witness)


@router.delete("/{witness_id}")
async def delete_witness(request: Request, witness_id: str):
    shard = get_shard(request)
    await shard.delete_witness(witness_id)
    return {"deleted": True}


@router.post("/{witness_id}/statements")
async def add_statement(request: Request, witness_id: str, body: StatementCreate):
    shard = get_shard(request)
    stmt = await shard.add_statement(witness_id, body.model_dump(exclude_none=True))
    return _stmt_to_dict(stmt)


@router.get("/{witness_id}/statements")
async def list_statements(request: Request, witness_id: str):
    shard = get_shard(request)
    stmts = await shard.list_statements(witness_id)
    return {"statements": [_stmt_to_dict(s) for s in stmts]}


@router.put("/{witness_id}/statements/{statement_id}")
async def update_statement(request: Request, witness_id: str, statement_id: str, body: StatementUpdate):
    shard = get_shard(request)
    stmt = await shard.update_statement(statement_id, body.model_dump(exclude_none=True))
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    return _stmt_to_dict(stmt)


@router.post("/{witness_id}/cross-exam")
async def add_cross_exam(request: Request, witness_id: str, body: CrossExamCreate):
    shard = get_shard(request)
    note = await shard.add_cross_exam_note(witness_id, body.model_dump(exclude_none=True))
    return _note_to_dict(note)


@router.get("/{witness_id}/cross-exam")
async def list_cross_exam(request: Request, witness_id: str):
    shard = get_shard(request)
    notes = await shard.list_cross_exam_notes(witness_id)
    return {"notes": [_note_to_dict(n) for n in notes]}


@router.get("/{witness_id}/summary")
async def get_summary(request: Request, witness_id: str):
    shard = get_shard(request)
    return await shard.get_witness_summary(witness_id)


@router.post("/{witness_id}/link-entity")
async def link_entity(request: Request, witness_id: str, body: EntityLink):
    shard = get_shard(request)
    witness = await shard.link_entity(witness_id, body.entity_id)
    if not witness:
        raise HTTPException(status_code=404, detail="Witness not found")
    return _witness_to_dict(witness)


# === Serializers ===


def _witness_to_dict(w) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "role": w.role,
        "status": w.status,
        "party": w.party,
        "organization": w.organization,
        "position": w.position,
        "contact_info": w.contact_info,
        "notes": w.notes,
        "credibility_level": w.credibility_level,
        "credibility_notes": w.credibility_notes,
        "linked_entity_id": w.linked_entity_id,
        "linked_document_ids": w.linked_document_ids,
        "created_at": str(w.created_at),
        "updated_at": str(w.updated_at),
        "metadata": w.metadata,
    }


def _stmt_to_dict(s) -> dict:
    return {
        "id": s.id,
        "witness_id": s.witness_id,
        "version": s.version,
        "title": s.title,
        "content": s.content,
        "status": s.status,
        "key_points": s.key_points,
        "contradictions_found": s.contradictions_found,
        "filed_date": str(s.filed_date) if s.filed_date else None,
        "created_at": str(s.created_at),
        "updated_at": str(s.updated_at),
    }


def _note_to_dict(n) -> dict:
    return {
        "id": n.id,
        "witness_id": n.witness_id,
        "statement_id": n.statement_id,
        "topic": n.topic,
        "question": n.question,
        "expected_answer": n.expected_answer,
        "actual_answer": n.actual_answer,
        "effectiveness": n.effectiveness,
        "notes": n.notes,
        "created_at": str(n.created_at),
    }
