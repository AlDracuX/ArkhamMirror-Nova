"""Deadlines Shard API endpoints."""

import logging
from datetime import date
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from .shard import DeadlinesShard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deadlines", tags=["deadlines"])

_shard: Optional["DeadlinesShard"] = None
_event_bus = None


def init_api(shard=None, event_bus=None):
    global _shard, _event_bus
    _shard = shard
    _event_bus = event_bus


def get_shard(request: Request) -> "DeadlinesShard":
    shard = _shard or getattr(request.app.state, "deadlines_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Deadlines shard not available")
    return shard


# === Request Models ===


class DeadlineCreate(BaseModel):
    title: str
    deadline_date: str
    description: str = ""
    deadline_time: Optional[str] = None
    deadline_type: str = "custom"
    case_type: str = "et"
    case_reference: str = ""
    source_document: str = ""
    source_order_date: Optional[str] = None
    rule_reference: str = ""
    notes: str = ""
    linked_document_ids: list = []
    metadata: dict = {}


class DeadlineUpdate(BaseModel):
    title: Optional[str] = None
    deadline_date: Optional[str] = None
    description: Optional[str] = None
    deadline_type: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    case_reference: Optional[str] = None
    rule_reference: Optional[str] = None
    notes: Optional[str] = None
    linked_document_ids: Optional[list] = None
    metadata: Optional[dict] = None


class DeadlineComplete(BaseModel):
    completed_by: str = ""


class DeadlineExtend(BaseModel):
    new_date: str
    reason: str = ""


class CalculateRequest(BaseModel):
    rule_id: str
    base_date: str


class RuleCreate(BaseModel):
    name: str
    description: str = ""
    case_type: str = "et"
    deadline_type: str = "custom"
    days_from_trigger: int = 14
    trigger_event: str = ""
    working_days_only: bool = True


# === Endpoints ===


@router.get("/")
async def list_deadlines(
    request: Request,
    status: Optional[str] = None,
    deadline_type: Optional[str] = None,
    case_type: Optional[str] = None,
    urgency: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    show_completed: bool = False,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    shard = get_shard(request)
    from .models import CaseType, DeadlineFilter, DeadlineStatus, DeadlineType, UrgencyLevel

    filters = DeadlineFilter(
        status=DeadlineStatus(status) if status else None,
        deadline_type=DeadlineType(deadline_type) if deadline_type else None,
        case_type=CaseType(case_type) if case_type else None,
        urgency=UrgencyLevel(urgency) if urgency else None,
        from_date=date.fromisoformat(from_date) if from_date else None,
        to_date=date.fromisoformat(to_date) if to_date else None,
        search_text=search,
        show_completed=show_completed,
    )
    deadlines = await shard.list_deadlines(filters=filters, limit=limit, offset=offset)
    return {"deadlines": [_dl_to_dict(d) for d in deadlines], "total": len(deadlines)}


@router.get("/upcoming/count")
async def count_upcoming(request: Request):
    shard = get_shard(request)
    count = await shard.count_upcoming()
    return {"count": count}


@router.get("/upcoming")
async def get_upcoming(request: Request, days: int = Query(default=30, le=365)):
    shard = get_shard(request)
    deadlines = await shard.get_upcoming(days=days)
    return {"deadlines": [_dl_to_dict(d) for d in deadlines]}


@router.post("/")
async def create_deadline(request: Request, body: DeadlineCreate):
    shard = get_shard(request)
    dl = await shard.create_deadline(body.model_dump(exclude_none=True))
    return _dl_to_dict(dl)


@router.get("/stats")
async def get_stats(request: Request):
    shard = get_shard(request)
    stats = await shard.get_stats()
    return {
        "total": stats.total,
        "pending": stats.pending,
        "breached": stats.breached,
        "completed": stats.completed,
        "by_urgency": stats.by_urgency,
        "by_case_type": stats.by_case_type,
        "next_deadline": stats.next_deadline,
    }


@router.get("/export/ics")
async def export_ics(request: Request, ids: Optional[str] = None):
    shard = get_shard(request)
    deadline_ids = ids.split(",") if ids else None
    ics = await shard.export_ics(deadline_ids)
    return PlainTextResponse(
        ics, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=deadlines.ics"}
    )


@router.get("/rules")
async def list_rules(request: Request):
    shard = get_shard(request)
    rules = await shard.list_rules()
    return {"rules": [_rule_to_dict(r) for r in rules]}


@router.post("/rules")
async def create_rule(request: Request, body: RuleCreate):
    shard = get_shard(request)
    rule = await shard.create_rule(body.model_dump())
    return _rule_to_dict(rule)


@router.post("/calculate")
async def calculate_from_rule(request: Request, body: CalculateRequest):
    shard = get_shard(request)
    base = date.fromisoformat(body.base_date)
    result = await shard.calculate_from_rule(body.rule_id, base)
    return result


@router.post("/check-breaches")
async def check_breaches(request: Request):
    shard = get_shard(request)
    breached = await shard.check_breaches()
    return {"breached_count": len(breached), "breached": [_dl_to_dict(d) for d in breached]}


@router.get("/{deadline_id}")
async def get_deadline(request: Request, deadline_id: str):
    shard = get_shard(request)
    dl = await shard.get_deadline(deadline_id)
    if not dl:
        raise HTTPException(status_code=404, detail="Deadline not found")
    return _dl_to_dict(dl)


@router.put("/{deadline_id}")
async def update_deadline(request: Request, deadline_id: str, body: DeadlineUpdate):
    shard = get_shard(request)
    dl = await shard.update_deadline(deadline_id, body.model_dump(exclude_none=True))
    if not dl:
        raise HTTPException(status_code=404, detail="Deadline not found")
    return _dl_to_dict(dl)


@router.delete("/{deadline_id}")
async def delete_deadline(request: Request, deadline_id: str):
    shard = get_shard(request)
    await shard.delete_deadline(deadline_id)
    return {"deleted": True}


@router.post("/{deadline_id}/complete")
async def complete_deadline(request: Request, deadline_id: str, body: DeadlineComplete):
    shard = get_shard(request)
    dl = await shard.complete_deadline(deadline_id, body.completed_by)
    if not dl:
        raise HTTPException(status_code=404, detail="Deadline not found")
    return _dl_to_dict(dl)


@router.post("/{deadline_id}/extend")
async def extend_deadline(request: Request, deadline_id: str, body: DeadlineExtend):
    shard = get_shard(request)
    new_date = date.fromisoformat(body.new_date)
    dl = await shard.extend_deadline(deadline_id, new_date, body.reason)
    if not dl:
        raise HTTPException(status_code=404, detail="Deadline not found")
    return _dl_to_dict(dl)


# === Serializers ===


def _dl_to_dict(d) -> dict:
    days_remaining = (d.deadline_date - date.today()).days if d.deadline_date else None
    return {
        "id": d.id,
        "title": d.title,
        "deadline_date": str(d.deadline_date),
        "deadline_time": str(d.deadline_time) if d.deadline_time else None,
        "deadline_type": d.deadline_type,
        "status": d.status,
        "urgency": d.urgency,
        "days_remaining": days_remaining,
        "case_type": d.case_type,
        "case_reference": d.case_reference,
        "source_document": d.source_document,
        "source_order_date": str(d.source_order_date) if d.source_order_date else None,
        "rule_reference": d.rule_reference,
        "auto_calculated": d.auto_calculated,
        "description": d.description,
        "notes": d.notes,
        "completed_at": str(d.completed_at) if d.completed_at else None,
        "completed_by": d.completed_by,
        "linked_document_ids": d.linked_document_ids,
        "created_at": str(d.created_at),
        "updated_at": str(d.updated_at),
        "metadata": d.metadata,
    }


def _rule_to_dict(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "case_type": r.case_type,
        "deadline_type": r.deadline_type,
        "days_from_trigger": r.days_from_trigger,
        "trigger_event": r.trigger_event,
        "working_days_only": r.working_days_only,
        "created_at": str(r.created_at),
    }
