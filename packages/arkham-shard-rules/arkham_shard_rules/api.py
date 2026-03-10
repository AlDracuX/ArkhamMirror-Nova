"""Rules Shard API endpoints."""

import json
import logging
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
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
_calculator = None
_seeder = None
_rules_llm = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    calculator=None,
    seeder=None,
    rules_llm=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _calculator, _seeder, _rules_llm
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _calculator = calculator
    _seeder = seeder
    _rules_llm = rules_llm


# --- Request/Response Models ---


class RuleCreate(BaseModel):
    rule_number: str = ""
    title: str
    jurisdiction: Optional[str] = None
    statute: Optional[str] = None
    section: Optional[str] = None
    description: str = ""
    text: Optional[str] = None
    category: str = ""
    trigger_type: str = ""
    deadline_days: Optional[int] = None
    deadline_type: str = "calendar_days"
    statutory_source: str = "ET Rules of Procedure 2013"
    applies_to: str = "both"
    is_mandatory: bool = True
    consequence_of_breach: str = ""
    strike_out_risk: bool = False
    unless_order_applicable: bool = False
    notes: str = ""
    applicability_notes: Optional[str] = None
    claim_types: list[str] = Field(default_factory=list)
    precedent_refs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RuleUpdate(BaseModel):
    rule_number: Optional[str] = None
    title: Optional[str] = None
    jurisdiction: Optional[str] = None
    statute: Optional[str] = None
    section: Optional[str] = None
    description: Optional[str] = None
    text: Optional[str] = None
    category: Optional[str] = None
    trigger_type: Optional[str] = None
    deadline_days: Optional[int] = None
    deadline_type: Optional[str] = None
    statutory_source: Optional[str] = None
    applies_to: Optional[str] = None
    is_mandatory: Optional[bool] = None
    consequence_of_breach: Optional[str] = None
    strike_out_risk: Optional[bool] = None
    unless_order_applicable: Optional[bool] = None
    notes: Optional[str] = None
    applicability_notes: Optional[str] = None
    claim_types: Optional[list[str]] = None
    precedent_refs: Optional[list[str]] = None
    tags: Optional[list[str]] = None


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


# --- Rules CRUD Endpoints ---


@router.get("/applicable")
async def get_applicable_rules(
    claim_type: str = Query(..., description="Claim type to match against claim_types array"),
):
    """Return rules where claim_type is in the claim_types array, sorted by jurisdiction then statute."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_rules.rules WHERE :claim_type = ANY(claim_types) ORDER BY jurisdiction, statute",
        {"claim_type": claim_type},
    )
    return [dict(row) for row in rows]


@router.get("/rules")
async def list_rules(
    category: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    statute: Optional[str] = None,
):
    """List procedural rules with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    query = "SELECT * FROM arkham_rules.rules WHERE 1=1"
    params: dict[str, Any] = {}
    if category:
        query += " AND category = :category"
        params["category"] = category
    if jurisdiction:
        query += " AND jurisdiction = :jurisdiction"
        params["jurisdiction"] = jurisdiction
    if statute:
        query += " AND statute = :statute"
        params["statute"] = statute

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str):
    """Get a single rule by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_rules.rules WHERE id = :id",
        {"id": rule_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return dict(row)


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
        (id, tenant_id, rule_number, title, jurisdiction, statute, section, description, text,
         category, trigger_type, deadline_days, deadline_type, statutory_source, applies_to,
         is_mandatory, consequence_of_breach, strike_out_risk, unless_order_applicable,
         notes, applicability_notes, claim_types, precedent_refs, tags)
        VALUES (:id, :tenant_id, :rule_number, :title, :jurisdiction, :statute, :section, :description, :text,
                :category, :trigger_type, :deadline_days, :deadline_type, :statutory_source, :applies_to,
                :is_mandatory, :consequence_of_breach, :strike_out_risk, :unless_order_applicable,
                :notes, :applicability_notes, :claim_types, :precedent_refs, :tags)
        """,
        {
            "id": rule_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "rule_number": request.rule_number,
            "title": request.title,
            "jurisdiction": request.jurisdiction,
            "statute": request.statute,
            "section": request.section,
            "description": request.description,
            "text": request.text,
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
            "applicability_notes": request.applicability_notes,
            "claim_types": request.claim_types,
            "precedent_refs": request.precedent_refs,
            "tags": json.dumps(request.tags),
        },
    )

    return {"id": rule_id, "status": "created"}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, request: RuleUpdate):
    """Update an existing rule. Only provided fields are updated."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    # Check rule exists
    existing = await _db.fetch_one(
        "SELECT * FROM arkham_rules.rules WHERE id = :id",
        {"id": rule_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    # Build dynamic SET clause from non-None fields
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return dict(existing)

    # Handle special serialization for array/json fields
    if "tags" in updates:
        updates["tags"] = json.dumps(updates["tags"])

    set_clauses = []
    params: dict[str, Any] = {"id": rule_id}
    for field_name, value in updates.items():
        set_clauses.append(f"{field_name} = :{field_name}")
        params[field_name] = value

    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    set_sql = ", ".join(set_clauses)

    await _db.execute(
        f"UPDATE arkham_rules.rules SET {set_sql} WHERE id = :id",
        params,
    )

    # Fetch and return updated row
    updated = await _db.fetch_one(
        "SELECT * FROM arkham_rules.rules WHERE id = :id",
        {"id": rule_id},
    )
    return dict(updated) if updated else {"id": rule_id, "status": "updated"}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a rule by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    existing = await _db.fetch_one(
        "SELECT id FROM arkham_rules.rules WHERE id = :id",
        {"id": rule_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    await _db.execute(
        "DELETE FROM arkham_rules.rules WHERE id = :id",
        {"id": rule_id},
    )
    return {"id": rule_id, "status": "deleted"}


# --- Calculations Endpoints ---


@router.get("/calculations")
async def list_calculations(project_id: Optional[str] = None):
    """List computed deadlines."""
    if not _db:
        raise HTTPException(status_code=503, detail="Rules service not initialized")

    query = "SELECT * FROM arkham_rules.calculations WHERE 1=1"
    params: dict[str, Any] = {}
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
    params: dict[str, Any] = {}
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
    params: dict[str, Any] = {}
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
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_rules.rules")
    return {"count": result["count"] if result else 0}


# --- Domain Endpoints ---


class CalculateRequest(BaseModel):
    rule_id: str
    trigger_date: date
    trigger_type: str = "custom"


class BreachDetectRequest(BaseModel):
    project_id: str


class ComplianceCheckRequest(BaseModel):
    document_id: str
    submission_type: str


class UnlessOrderRequest(BaseModel):
    breach_id: str


class ExtractDatesRequest(BaseModel):
    document_text: str


@router.post("/seed")
async def seed_rules():
    """Seed ET Rules 1-62 and Practice Directions."""
    if not _seeder or not _db:
        raise HTTPException(status_code=503, detail="Seeder not available")

    count = await _seeder.seed(_db)
    return {"status": "seeded", "count": count}


@router.post("/calculate")
async def calculate_deadline(request: CalculateRequest):
    """Calculate a deadline from a rule and trigger date."""
    if not _calculator:
        raise HTTPException(status_code=503, detail="Calculator not available")

    try:
        result = await _calculator.calculate(request.rule_id, request.trigger_date, request.trigger_type)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/breaches/detect")
async def detect_breaches(request: BreachDetectRequest):
    """Detect missed deadlines for a project."""
    if not _calculator:
        raise HTTPException(status_code=503, detail="Calculator not available")

    breaches = await _calculator.detect_breaches(request.project_id)
    return {"breaches": breaches, "count": len(breaches)}


@router.post("/compliance/check")
async def check_compliance(request: ComplianceCheckRequest):
    """Check document compliance against applicable rules."""
    if not _calculator:
        raise HTTPException(status_code=503, detail="Calculator not available")

    result = await _calculator.check_compliance(request.document_id, request.submission_type)
    return result


@router.post("/unless-order/assess")
async def assess_unless_order(request: UnlessOrderRequest):
    """Assess unless order risk for a breach."""
    if not _calculator:
        raise HTTPException(status_code=503, detail="Calculator not available")

    try:
        result = await _calculator.assess_unless_order_risk(request.breach_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/extract-dates")
async def extract_dates(request: ExtractDatesRequest):
    """Extract dates and legal significance from a document using LLM."""
    if not _rules_llm:
        raise HTTPException(status_code=503, detail="LLM service not available")

    dates = await _rules_llm.extract_dates(request.document_text)
    return {
        "dates": [
            {
                "date": d.date,
                "description": d.description,
                "rule_reference": d.rule_reference,
                "creates_deadline": d.creates_deadline,
                "deadline_for": d.deadline_for,
                "notes": d.notes,
            }
            for d in dates
        ],
        "count": len(dates),
    }
