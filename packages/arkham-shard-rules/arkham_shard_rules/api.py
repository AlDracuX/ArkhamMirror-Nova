"""Rules Shard API endpoints."""

import json
import logging
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import RulesShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "RulesShard":
    """Get the Rules shard instance from app state."""
    shard = getattr(request.app.state, "rules_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Rules shard not available")
    return shard


router = APIRouter(prefix="/api/rules", tags=["rules"])

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


class RuleCreate(BaseModel):
    rule_number: str
    title: str
    description: str = ""
    category: str
    trigger_type: str
    deadline_days: Optional[int] = None
    deadline_type: str = "calendar_days"
    statutory_source: str = "ET Rules of Procedure 2013"
    applies_to: str = "both"
    is_mandatory: bool = True
    consequence_of_breach: str = ""
    strike_out_risk: bool = False
    unless_order_applicable: bool = False
    notes: str = ""
    tags: list[str] = Field(default_factory=list)


class BreachCreate(BaseModel):
    rule_id: str
    breaching_party: str
    breach_date: date
    deadline_date: Optional[date] = None
    description: str
    severity: str = "moderate"
    status: str = "detected"
    document_evidence: list[str] = Field(default_factory=list)
    suggested_remedy: str = ""
    project_id: Optional[str] = None
    created_by: Optional[str] = None


# --- Rules Endpoints ---


@router.get("/rules")
async def list_rules(category: Optional[str] = None):
    """List procedural rules."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    query = "SELECT * FROM arkham_rules.rules WHERE 1=1"
    params = {}
    if category:
        query += " AND category = :category"
        params["category"] = category

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/rules")
async def create_rule(request: RuleCreate):
    """Register a new procedural rule."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    rule_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_rules.rules
        (id, tenant_id, rule_number, title, description, category, trigger_type, deadline_days, deadline_type, statutory_source, applies_to, is_mandatory, consequence_of_breach, strike_out_risk, unless_order_applicable, notes, tags)
        VALUES (:id, :tenant_id, :rule_number, :title, :description, :category, :trigger_type, :deadline_days, :deadline_type, :statutory_source, :applies_to, :is_mandatory, :consequence_of_breach, :strike_out_risk, :unless_order_applicable, :notes, :tags)
        """,
        {
            "id": rule_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "rule_number": request.rule_number,
            "title": request.title,
            "description": request.description,
            "category": request.category,
            "trigger_type": request.trigger_type,
            "deadline_days": request.deadline_days,
            "deadline_type": request.deadline_type,
            "statutory_source": request.statutory_source,
            "applies_to": request.applies_to,
            "is_mandatory": request.is_mandatory,
            "consequence_of_breach": request.consequence_of_breach,
            "strike_out_risk": request.strike_out_risk,
            "unless_order_applicable": request.unless_order_applicable,
            "notes": request.notes,
            "tags": json.dumps(request.tags),
        },
    )

    return {"id": rule_id, "status": "created"}


# --- Calculations Endpoints ---


@router.get("/calculations")
async def list_calculations(project_id: Optional[str] = None):
    """List computed deadlines."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    query = "SELECT * FROM arkham_rules.calculations WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


# --- Breaches Endpoints ---


@router.get("/breaches")
async def list_breaches(project_id: Optional[str] = None, party: Optional[str] = None):
    """List procedural breaches."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    query = "SELECT * FROM arkham_rules.breaches WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id
    if party:
        query += " AND breaching_party = :party"
        params["party"] = party

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/breaches")
async def create_breach(request: BreachCreate):
    """Log a new procedural breach."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    # Get rule details
    rule = await _db.fetch_one(
        "SELECT rule_number, title FROM arkham_rules.rules WHERE id = :id",
        {"id": request.rule_id},
    )
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule not found: {request.rule_id}")

    breach_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_rules.breaches
        (id, tenant_id, rule_id, rule_number, rule_title, breaching_party, breach_date, deadline_date, description, severity, status, document_evidence, suggested_remedy, project_id, created_by)
        VALUES (:id, :tenant_id, :rule_id, :rule_number, :rule_title, :breaching_party, :breach_date, :deadline_date, :description, :severity, :status, :document_evidence, :suggested_remedy, :project_id, :created_by)
        """,
        {
            "id": breach_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "rule_id": request.rule_id,
            "rule_number": rule["rule_number"],
            "rule_title": rule["title"],
            "breaching_party": request.breaching_party,
            "breach_date": request.breach_date,
            "deadline_date": request.deadline_date,
            "description": request.description,
            "severity": request.severity,
            "status": request.status,
            "document_evidence": json.dumps(request.document_evidence),
            "suggested_remedy": request.suggested_remedy,
            "project_id": request.project_id,
            "created_by": request.created_by,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "rules.breach.detected",
            {"breach_id": breach_id, "party": request.breaching_party},
            source="rules-shard",
        )

    return {"id": breach_id, "status": "created"}


# --- Compliance Checks Endpoints ---


@router.get("/compliance-checks")
async def list_compliance_checks(project_id: Optional[str] = None):
    """List compliance checks."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    query = "SELECT * FROM arkham_rules.compliance_checks WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]
