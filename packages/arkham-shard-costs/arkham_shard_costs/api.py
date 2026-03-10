"""Costs Shard API endpoints."""

import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

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
_engine = None
_costs_llm = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    engine=None,
    costs_llm=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _engine, _costs_llm
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _engine = engine
    _costs_llm = costs_llm


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


class CostItemCreate(BaseModel):
    case_id: str
    category: str
    description: str
    amount: Decimal
    currency: str = "GBP"
    date: date
    claimant: str
    evidence_doc_id: Optional[str] = None
    status: str = "claimed"

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v


class CostItemUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    date: Optional[date] = None
    claimant: Optional[str] = None
    evidence_doc_id: Optional[str] = None
    status: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be positive")
        return v


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


# --- Domain Endpoints (Engine + LLM) ---


class AggregateTimeRequest(BaseModel):
    project_id: str
    hourly_rate: float = 0.0


class RollupExpensesRequest(BaseModel):
    project_id: str


class ScoreConductRequest(BaseModel):
    project_id: str


class BuildApplicationRequest(BaseModel):
    application_id: str


@router.post("/time/aggregate")
async def aggregate_time(request: AggregateTimeRequest):
    """Aggregate time entries for a project."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Costs engine not initialized")
    return await _engine.aggregate_time(request.project_id, request.hourly_rate)


@router.post("/expenses/rollup")
async def rollup_expenses(request: RollupExpensesRequest):
    """Rollup expenses for a project."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Costs engine not initialized")
    return await _engine.rollup_expenses(request.project_id)


@router.post("/conduct/score")
async def score_conduct(request: ScoreConductRequest):
    """Score conduct log for Rule 76 costs basis."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Costs engine not initialized")
    return await _engine.score_conduct(request.project_id)


@router.post("/application/build")
async def build_application(request: BuildApplicationRequest):
    """Build a costs application from linked records."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Costs engine not initialized")
    return await _engine.build_application(request.application_id)


@router.post("/application/{application_id}/schedule")
async def generate_schedule(application_id: str):
    """Generate a Schedule of Costs document."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Costs engine not initialized")
    text = await _engine.generate_schedule(application_id)
    return {"schedule": text}


@router.post("/application/{application_id}/draft")
async def draft_application(application_id: str):
    """LLM: Draft a costs application text."""
    if not _engine or not _costs_llm:
        raise HTTPException(status_code=503, detail="Costs engine or LLM not initialized")

    # Build application data first
    app_data = await _engine.build_application(application_id)
    if "error" in app_data:
        raise HTTPException(status_code=404, detail=app_data["error"])

    # Get conduct summary
    project_id = app_data.get("project_id", "")
    conduct_score = await _engine.score_conduct(project_id) if project_id else {}
    conduct_summary = json.dumps(conduct_score.get("by_type", {}), indent=2)

    result = await _costs_llm.draft_application(
        conduct_summary=conduct_summary,
        time_total=app_data.get("time_cost", 0.0),
        expense_total=app_data.get("expense_total", 0.0),
        total_claimed=app_data.get("total_amount_claimed", 0.0),
    )

    if result.success and result.text:
        # Store draft text on the application
        await _db.execute(
            "UPDATE arkham_costs.applications SET application_text = :text, updated_at = :now WHERE id = :id",
            {"text": result.text, "now": datetime.utcnow(), "id": application_id},
        )

        if _event_bus:
            await _event_bus.emit(
                "costs.application.drafted",
                {"application_id": application_id, "project_id": project_id},
                source="costs-shard",
            )

    return {
        "application_id": application_id,
        "text": result.text,
        "rule_references": result.rule_references,
        "success": result.success,
        "error": result.error,
    }


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


# --- Cost Items Endpoints ---


@router.get("/summary")
async def get_cost_items_summary(case_id: Optional[str] = None):
    """Return totals grouped by category."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    query = "SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM arkham_costs.cost_items"
    params: dict[str, Any] = {}
    if case_id:
        query += " WHERE case_id = :case_id"
        params["case_id"] = case_id
    query += " GROUP BY category ORDER BY category"

    rows = await _db.fetch_all(query, params)
    categories = [{"category": row["category"], "total": float(row["total"]), "count": row["count"]} for row in rows]
    grand_total = sum(c["total"] for c in categories)
    return {"categories": categories, "grand_total": grand_total}


@router.get("/{item_id}")
async def get_cost_item(item_id: str):
    """Get a single cost item by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    row = await _db.fetch_one("SELECT * FROM arkham_costs.cost_items WHERE id = :id", {"id": item_id})
    if not row:
        raise HTTPException(status_code=404, detail="Cost item not found")
    return dict(row)


@router.get("/")
async def list_cost_items(
    case_id: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
):
    """List cost items with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    query = "SELECT * FROM arkham_costs.cost_items WHERE 1=1"
    params: dict[str, Any] = {}
    if case_id:
        query += " AND case_id = :case_id"
        params["case_id"] = case_id
    if category:
        query += " AND category = :category"
        params["category"] = category
    if status:
        query += " AND status = :status"
        params["status"] = status
    query += " ORDER BY date DESC"

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/")
async def create_cost_item(request: CostItemCreate):
    """Create a new cost item."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    item_id = str(uuid.uuid4())

    await _db.execute(
        """
        INSERT INTO arkham_costs.cost_items
        (id, case_id, category, description, amount, currency, date, claimant, evidence_doc_id, status)
        VALUES (:id, :case_id, :category, :description, :amount, :currency, :date, :claimant, :evidence_doc_id, :status)
        """,
        {
            "id": item_id,
            "case_id": request.case_id,
            "category": request.category,
            "description": request.description,
            "amount": float(request.amount),
            "currency": request.currency,
            "date": request.date,
            "claimant": request.claimant,
            "evidence_doc_id": request.evidence_doc_id,
            "status": request.status,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "costs.item.created",
            {"item_id": item_id, "case_id": request.case_id, "amount": float(request.amount)},
            source="costs-shard",
        )

    return {"id": item_id, "status": "created"}


@router.put("/{item_id}")
async def update_cost_item(item_id: str, request: CostItemUpdate):
    """Update an existing cost item."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    existing = await _db.fetch_one("SELECT id FROM arkham_costs.cost_items WHERE id = :id", {"id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Cost item not found")

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        return {"id": item_id, "status": "no_changes"}

    if "amount" in updates:
        updates["amount"] = float(updates["amount"])

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = item_id
    updates["_updated_at"] = datetime.utcnow()
    set_clauses += ", updated_at = :_updated_at"

    await _db.execute(
        f"UPDATE arkham_costs.cost_items SET {set_clauses} WHERE id = :id",
        updates,
    )

    return {"id": item_id, "status": "updated"}


@router.delete("/{item_id}")
async def delete_cost_item(item_id: str):
    """Delete a cost item."""
    if not _db:
        raise HTTPException(status_code=503, detail="Costs service not initialized")

    existing = await _db.fetch_one("SELECT id FROM arkham_costs.cost_items WHERE id = :id", {"id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Cost item not found")

    await _db.execute("DELETE FROM arkham_costs.cost_items WHERE id = :id", {"id": item_id})

    return {"id": item_id, "status": "deleted"}
