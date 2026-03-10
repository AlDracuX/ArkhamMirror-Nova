"""Costs Shard API endpoints."""

import json
import logging
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import CostsShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "CostsShard":
    """Get the Costs shard instance from app state."""
    shard = getattr(request.app.state, "costs_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Costs shard not available")
    return shard


router = APIRouter(prefix="/api/costs", tags=["costs"])

# Module-level references set during initialization
_db = None
_event_bus = None
_llm_service = None
_shard = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard


# --- Request/Response Models ---


class TimeEntryCreate(BaseModel):
    activity: str
    duration_minutes: int
    activity_date: date
    project_id: Optional[str] = None
    hourly_rate: Optional[float] = None
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None


class ExpenseCreate(BaseModel):
    description: str
    amount: float
    currency: str = "GBP"
    expense_date: date
    receipt_document_id: Optional[str] = None
    project_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConductLogCreate(BaseModel):
    party_name: str
    conduct_type: str
    description: str = ""
    occurred_at: datetime
    supporting_evidence: list[str] = Field(default_factory=list)
    significance: str = "medium"
    legal_reference: str = "Rule 76(1)(a)"
    project_id: Optional[str] = None
    created_by: Optional[str] = None


# --- Time Entries Endpoints ---


@router.get("/time-entries")
async def list_time_entries(project_id: Optional[str] = None):
    """List time entries."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    query = "SELECT * FROM arkham_costs.time_entries WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/time-entries")
async def create_time_entry(request: TimeEntryCreate):
    """Log a new time entry."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    entry_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_costs.time_entries
        (id, tenant_id, activity, duration_minutes, activity_date, project_id, hourly_rate, notes, metadata, created_by)
        VALUES (:id, :tenant_id, :activity, :duration_minutes, :activity_date, :project_id, :hourly_rate, :notes, :metadata, :created_by)
        """,
        {
            "id": entry_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "activity": request.activity,
            "duration_minutes": request.duration_minutes,
            "activity_date": request.activity_date,
            "project_id": request.project_id,
            "hourly_rate": request.hourly_rate,
            "notes": request.notes,
            "metadata": json.dumps(request.metadata),
            "created_by": request.created_by,
        },
    )

    return {"id": entry_id, "status": "created"}


# --- Expenses Endpoints ---


@router.get("/expenses")
async def list_expenses(project_id: Optional[str] = None):
    """List expenses."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    query = "SELECT * FROM arkham_costs.expenses WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/expenses")
async def create_expense(request: ExpenseCreate):
    """Log a new expense."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    expense_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_costs.expenses
        (id, tenant_id, description, amount, currency, expense_date, receipt_document_id, project_id, metadata)
        VALUES (:id, :tenant_id, :description, :amount, :currency, :expense_date, :receipt_document_id, :project_id, :metadata)
        """,
        {
            "id": expense_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "description": request.description,
            "amount": request.amount,
            "currency": request.currency,
            "expense_date": request.expense_date,
            "receipt_document_id": request.receipt_document_id,
            "project_id": request.project_id,
            "metadata": json.dumps(request.metadata),
        },
    )

    return {"id": expense_id, "status": "created"}


# --- Conduct Log Endpoints ---


@router.get("/conduct-log")
async def list_conduct_log(project_id: Optional[str] = None):
    """List conduct log entries."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    query = "SELECT * FROM arkham_costs.conduct_log WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/conduct-log")
async def create_conduct_log(request: ConductLogCreate):
    """Log an instance of unreasonable conduct."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    log_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_costs.conduct_log
        (id, tenant_id, party_name, conduct_type, description, occurred_at, supporting_evidence, significance, legal_reference, project_id, created_by)
        VALUES (:id, :tenant_id, :party_name, :conduct_type, :description, :occurred_at, :supporting_evidence, :significance, :legal_reference, :project_id, :created_by)
        """,
        {
            "id": log_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "party_name": request.party_name,
            "conduct_type": request.conduct_type,
            "description": request.description,
            "occurred_at": request.occurred_at,
            "supporting_evidence": json.dumps(request.supporting_evidence),
            "significance": request.significance,
            "legal_reference": request.legal_reference,
            "project_id": request.project_id,
            "created_by": request.created_by,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "costs.conduct.logged",
            {"log_id": log_id, "party": request.party_name},
            source="costs-shard",
        )

    return {"id": log_id, "status": "created"}


# --- Applications Endpoints ---


@router.get("/applications")
async def list_applications(project_id: Optional[str] = None):
    """List costs applications."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    query = "SELECT * FROM arkham_costs.applications WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_costs.time_entries")
    return {"count": result["count"] if result else 0}
