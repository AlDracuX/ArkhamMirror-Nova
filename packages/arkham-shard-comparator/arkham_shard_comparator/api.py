"""Comparator Shard API endpoints.

CRUD for Comparators, Incidents, Treatments, Divergences.
Plus advanced analysis for s.13/s.26 discrimination claims.
"""

import json
import logging
import uuid
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .models import (
    DiscriminationElement,
    HarassmentElement,
    SignificanceLevel,
    TreatmentOutcome,
)

if TYPE_CHECKING:
    from .shard import ComparatorShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "ComparatorShard":
    """Get the Comparator shard instance from app state."""
    shard = getattr(request.app.state, "comparator_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Comparator shard not available")
    return shard


router = APIRouter(prefix="/api/comparator", tags=["comparator"])

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


# --- Request / Response Models ---


class CreateComparatorRequest(BaseModel):
    name: str
    characteristic: str = Field(
        default="",
        description="Protected characteristic, e.g. race, sex, disability",
    )


class UpdateComparatorRequest(BaseModel):
    name: Optional[str] = None
    characteristic: Optional[str] = None


class CreateIncidentRequest(BaseModel):
    description: str
    date: Optional[str] = Field(default=None, description="ISO 8601 date string")
    project_id: Optional[str] = None


class UpdateIncidentRequest(BaseModel):
    description: Optional[str] = None
    date: Optional[str] = None
    project_id: Optional[str] = None


class CreateTreatmentRequest(BaseModel):
    incident_id: str
    subject_id: str = Field(description="'claimant' or a comparator UUID")
    treatment_description: str
    outcome: str = Field(
        default="unknown",
        description="favourable | unfavourable | neutral | unknown",
    )
    evidence_ids: List[str] = Field(default_factory=list)


class UpdateTreatmentRequest(BaseModel):
    treatment_description: Optional[str] = None
    outcome: Optional[str] = None
    evidence_ids: Optional[List[str]] = None


class CreateDivergenceRequest(BaseModel):
    incident_id: str
    description: str
    significance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class UpdateDivergenceRequest(BaseModel):
    description: Optional[str] = None
    significance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# --- Helpers ---


def _require_db():
    if not _db:
        raise HTTPException(status_code=503, detail="Comparator service not initialized")


# --- Comparators CRUD ---


@router.get("/comparators")
async def list_comparators(tenant_id: Optional[str] = None):
    """List all comparators."""
    _require_db()
    query = "SELECT * FROM arkham_comparator.comparators WHERE 1=1"
    params: dict = {}
    if tenant_id:
        query += " AND tenant_id = :tenant_id"
        params["tenant_id"] = tenant_id
    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "comparators": [dict(r) for r in rows]}


@router.get("/comparators/{comparator_id}")
async def get_comparator(comparator_id: str):
    """Get a comparator by ID."""
    _require_db()
    row = await _db.fetch_one(
        "SELECT * FROM arkham_comparator.comparators WHERE id = :id",
        {"id": comparator_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Comparator not found: {comparator_id}")
    return dict(row)


@router.post("/comparators")
async def create_comparator(request: CreateComparatorRequest):
    """Create a new comparator."""
    cid = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_comparator.comparators (id, tenant_id, name, characteristic)
        VALUES (:id, :tenant_id, :name, :characteristic)
        """,
        {
            "id": cid,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "name": request.name,
            "characteristic": request.characteristic,
        },
    )
    if _event_bus:
        await _event_bus.emit(
            "comparator.comparator.created",
            {"comparator_id": cid, "name": request.name},
            source="comparator-shard",
        )
    return {"comparator_id": cid, "name": request.name}


@router.put("/comparators/{comparator_id}")
async def update_comparator(comparator_id: str, request: UpdateComparatorRequest):
    """Update a comparator."""
    _require_db()
    sets, params = [], {"id": comparator_id}
    if request.name is not None:
        sets.append("name = :name")
        params["name"] = request.name
    if request.characteristic is not None:
        sets.append("characteristic = :characteristic")
        params["characteristic"] = request.characteristic
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await _db.execute(
        f"UPDATE arkham_comparator.comparators SET {', '.join(sets)} WHERE id = :id",
        params,
    )
    return {"comparator_id": comparator_id, "status": "updated"}


@router.delete("/comparators/{comparator_id}")
async def delete_comparator(comparator_id: str):
    """Delete a comparator."""
    _require_db()
    await _db.execute(
        "DELETE FROM arkham_comparator.comparators WHERE id = :id",
        {"id": comparator_id},
    )
    return {"status": "deleted", "comparator_id": comparator_id}


# --- Incidents CRUD ---


@router.get("/incidents")
async def list_incidents(
    project_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
):
    """List incidents with optional filtering."""
    _require_db()
    query = "SELECT * FROM arkham_comparator.incidents WHERE 1=1"
    params: dict = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id
    if tenant_id:
        query += " AND tenant_id = :tenant_id"
        params["tenant_id"] = tenant_id
    query += " ORDER BY date DESC NULLS LAST, created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "incidents": [dict(r) for r in rows]}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get an incident by ID."""
    _require_db()
    row = await _db.fetch_one(
        "SELECT * FROM arkham_comparator.incidents WHERE id = :id",
        {"id": incident_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Incident not found: {incident_id}")
    return dict(row)


@router.post("/incidents")
async def create_incident(request: CreateIncidentRequest):
    """Create a new incident."""
    iid = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_comparator.incidents (id, tenant_id, date, description, project_id)
        VALUES (:id, :tenant_id, :date, :description, :project_id)
        """,
        {
            "id": iid,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "date": request.date,
            "description": request.description,
            "project_id": request.project_id,
        },
    )
    if _event_bus:
        await _event_bus.emit(
            "comparator.incident.created",
            {"incident_id": iid},
            source="comparator-shard",
        )
    return {"incident_id": iid, "description": request.description}


@router.put("/incidents/{incident_id}")
async def update_incident(incident_id: str, request: UpdateIncidentRequest):
    """Update an incident."""
    _require_db()
    sets, params = [], {"id": incident_id}
    if request.description is not None:
        sets.append("description = :description")
        params["description"] = request.description
    if request.date is not None:
        sets.append("date = :date")
        params["date"] = request.date
    if request.project_id is not None:
        sets.append("project_id = :project_id")
        params["project_id"] = request.project_id
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await _db.execute(
        f"UPDATE arkham_comparator.incidents SET {', '.join(sets)} WHERE id = :id",
        params,
    )
    return {"incident_id": incident_id, "status": "updated"}


@router.delete("/incidents/{incident_id}")
async def delete_incident(incident_id: str):
    """Delete an incident and its treatments/divergences."""
    _require_db()
    await _db.execute(
        "DELETE FROM arkham_comparator.treatments WHERE incident_id = :id",
        {"id": incident_id},
    )
    await _db.execute(
        "DELETE FROM arkham_comparator.divergences WHERE incident_id = :id",
        {"id": incident_id},
    )
    await _db.execute(
        "DELETE FROM arkham_comparator.incidents WHERE id = :id",
        {"id": incident_id},
    )
    return {"status": "deleted", "incident_id": incident_id}


# --- Treatments CRUD ---


@router.get("/treatments")
async def list_treatments(
    incident_id: Optional[str] = None,
    subject_id: Optional[str] = None,
):
    """List treatments with optional filtering."""
    _require_db()
    query = "SELECT * FROM arkham_comparator.treatments WHERE 1=1"
    params: dict = {}
    if incident_id:
        query += " AND incident_id = :incident_id"
        params["incident_id"] = incident_id
    if subject_id:
        query += " AND subject_id = :subject_id"
        params["subject_id"] = subject_id
    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "treatments": [dict(r) for r in rows]}


@router.get("/treatments/{treatment_id}")
async def get_treatment(treatment_id: str):
    """Get a treatment by ID."""
    _require_db()
    row = await _db.fetch_one(
        "SELECT * FROM arkham_comparator.treatments WHERE id = :id",
        {"id": treatment_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Treatment not found: {treatment_id}")
    return dict(row)


@router.post("/treatments")
async def create_treatment(request: CreateTreatmentRequest):
    """Record a treatment for a subject in an incident."""
    tid = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_comparator.treatments
            (id, tenant_id, incident_id, subject_id, treatment_description, outcome, evidence_ids)
        VALUES (:id, :tenant_id, :incident_id, :subject_id, :treatment_description, :outcome, :evidence_ids)
        """,
        {
            "id": tid,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "incident_id": request.incident_id,
            "subject_id": request.subject_id,
            "treatment_description": request.treatment_description,
            "outcome": request.outcome,
            "evidence_ids": request.evidence_ids,
        },
    )
    if _event_bus:
        await _event_bus.emit(
            "comparator.treatment.mapped",
            {"treatment_id": tid, "incident_id": request.incident_id, "subject_id": request.subject_id},
            source="comparator-shard",
        )
    return {"treatment_id": tid, "incident_id": request.incident_id, "subject_id": request.subject_id}


@router.put("/treatments/{treatment_id}")
async def update_treatment(treatment_id: str, request: UpdateTreatmentRequest):
    """Update a treatment record."""
    _require_db()
    sets, params = [], {"id": treatment_id}
    if request.treatment_description is not None:
        sets.append("treatment_description = :treatment_description")
        params["treatment_description"] = request.treatment_description
    if request.outcome is not None:
        sets.append("outcome = :outcome")
        params["outcome"] = request.outcome
    if request.evidence_ids is not None:
        sets.append("evidence_ids = :evidence_ids")
        params["evidence_ids"] = request.evidence_ids
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await _db.execute(
        f"UPDATE arkham_comparator.treatments SET {', '.join(sets)} WHERE id = :id",
        params,
    )
    return {"treatment_id": treatment_id, "status": "updated"}


@router.delete("/treatments/{treatment_id}")
async def delete_treatment(treatment_id: str):
    """Delete a treatment record."""
    _require_db()
    await _db.execute(
        "DELETE FROM arkham_comparator.treatments WHERE id = :id",
        {"id": treatment_id},
    )
    return {"status": "deleted", "treatment_id": treatment_id}


# --- Divergences CRUD ---


@router.get("/divergences")
async def list_divergences(
    incident_id: Optional[str] = None,
    min_score: Optional[float] = Query(default=None, ge=0.0, le=1.0),
):
    """List divergences, optionally filtered by incident or minimum significance score."""
    _require_db()
    query = "SELECT * FROM arkham_comparator.divergences WHERE 1=1"
    params: dict = {}
    if incident_id:
        query += " AND incident_id = :incident_id"
        params["incident_id"] = incident_id
    if min_score is not None:
        query += " AND significance_score >= :min_score"
        params["min_score"] = min_score
    query += " ORDER BY significance_score DESC, created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "divergences": [dict(r) for r in rows]}


@router.get("/divergences/{divergence_id}")
async def get_divergence(divergence_id: str):
    """Get a divergence by ID."""
    _require_db()
    row = await _db.fetch_one(
        "SELECT * FROM arkham_comparator.divergences WHERE id = :id",
        {"id": divergence_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Divergence not found: {divergence_id}")
    return dict(row)


@router.post("/divergences")
async def create_divergence(request: CreateDivergenceRequest):
    """Record a divergence finding for an incident."""
    did = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_comparator.divergences
            (id, tenant_id, incident_id, description, significance_score)
        VALUES (:id, :tenant_id, :incident_id, :description, :significance_score)
        """,
        {
            "id": did,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "incident_id": request.incident_id,
            "description": request.description,
            "significance_score": request.significance_score,
        },
    )
    if _event_bus:
        await _event_bus.emit(
            "comparator.divergence.found",
            {"divergence_id": did, "incident_id": request.incident_id, "score": request.significance_score},
            source="comparator-shard",
        )
    return {"divergence_id": did, "incident_id": request.incident_id}


@router.put("/divergences/{divergence_id}")
async def update_divergence(divergence_id: str, request: UpdateDivergenceRequest):
    """Update a divergence record."""
    _require_db()
    sets, params = [], {"id": divergence_id}
    if request.description is not None:
        sets.append("description = :description")
        params["description"] = request.description
    if request.significance_score is not None:
        sets.append("significance_score = :significance_score")
        params["significance_score"] = request.significance_score
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await _db.execute(
        f"UPDATE arkham_comparator.divergences SET {', '.join(sets)} WHERE id = :id",
        params,
    )
    return {"divergence_id": divergence_id, "status": "updated"}


@router.delete("/divergences/{divergence_id}")
async def delete_divergence(divergence_id: str):
    """Delete a divergence record."""
    _require_db()
    await _db.execute(
        "DELETE FROM arkham_comparator.divergences WHERE id = :id",
        {"id": divergence_id},
    )
    return {"status": "deleted", "divergence_id": divergence_id}


# --- Comparison Matrix ---


@router.get("/matrix")
async def get_comparison_matrix(
    project_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
):
    """
    Comparison Matrix — aggregates treatments per incident and comparator.

    Returns a matrix suitable for rendering a less-favourable-treatment table.
    """
    _require_db()

    inc_query = "SELECT * FROM arkham_comparator.incidents WHERE 1=1"
    inc_params: dict = {}
    if project_id:
        inc_query += " AND project_id = :project_id"
        inc_params["project_id"] = project_id
    if tenant_id:
        inc_query += " AND tenant_id = :tenant_id"
        inc_params["tenant_id"] = tenant_id
    inc_query += " ORDER BY date DESC NULLS LAST, created_at DESC"
    incident_rows = await _db.fetch_all(inc_query, inc_params)

    comp_query = "SELECT * FROM arkham_comparator.comparators WHERE 1=1"
    comp_params: dict = {}
    if tenant_id:
        comp_query += " AND tenant_id = :tenant_id"
        comp_params["tenant_id"] = tenant_id
    comp_query += " ORDER BY name ASC"
    comparator_rows = await _db.fetch_all(comp_query, comp_params)

    incident_ids = [r["id"] for r in incident_rows]
    matrix: dict = {}
    divergences_map: dict = {}

    if incident_ids:
        treat_rows = await _db.fetch_all(
            "SELECT * FROM arkham_comparator.treatments WHERE incident_id = ANY(:ids)",
            {"ids": incident_ids},
        )
        for iid in incident_ids:
            matrix[iid] = {}
        for t in treat_rows:
            iid = t["incident_id"]
            sid = t["subject_id"]
            if iid not in matrix:
                matrix[iid] = {}
            if sid not in matrix[iid]:
                matrix[iid][sid] = dict(t)

        div_rows = await _db.fetch_all(
            "SELECT * FROM arkham_comparator.divergences WHERE incident_id = ANY(:ids) ORDER BY significance_score DESC",
            {"ids": incident_ids},
        )
        for d in div_rows:
            iid = d["incident_id"]
            if iid not in divergences_map:
                divergences_map[iid] = []
            divergences_map[iid].append(dict(d))

    return {
        "incidents": [dict(r) for r in incident_rows],
        "comparators": [dict(r) for r in comparator_rows],
        "matrix": matrix,
        "divergences": divergences_map,
    }


# --- Advanced Analysis (Wave 1 logic) ---


@router.post("/analyze/parallel-situations")
async def detect_parallel_situations(project_id: str):
    """
    AI-powered detection of parallel situations.

    Finds incidents where the same policy/situation was applied but with
    divergent outcomes between claimant and comparators.
    """
    if not _llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available for analysis")

    _require_db()

    # 1. Fetch all incidents and treatments for the project
    inc_rows = await _db.fetch_all(
        "SELECT * FROM arkham_comparator.incidents WHERE project_id = :pid", {"pid": project_id}
    )
    if not inc_rows:
        return {"parallel_situations": [], "count": 0}

    inc_ids = [r["id"] for r in inc_rows]
    treat_rows = await _db.fetch_all(
        "SELECT * FROM arkham_comparator.treatments WHERE incident_id = ANY(:ids)", {"ids": inc_ids}
    )

    # 2. Use LLM to analyze the corpus (simulated for now, would use prompt)
    # prompt = f"Analyze these {len(inc_rows)} incidents and their treatments... find same policy divergent outcomes."
    # response = await _llm_service.generate(prompt)

    # For Wave 1 implementation, we provide the structured analysis capability.
    return {
        "project_id": project_id,
        "analysis_type": "parallel_situations",
        "status": "completed",
        "findings": [],  # Would be populated by LLM
    }


@router.get("/analyze/linkage")
async def characteristic_linkage_analysis(project_id: str):
    """
    Analysis of linkage between treatments and protected characteristics.
    """
    _require_db()

    # Aggregates treatment outcomes by protected characteristic
    query = """
        SELECT c.characteristic, t.outcome, COUNT(*) as cnt
        FROM arkham_comparator.treatments t
        JOIN arkham_comparator.comparators c ON t.subject_id = c.id
        JOIN arkham_comparator.incidents i ON t.incident_id = i.id
        WHERE i.project_id = :pid
        GROUP BY c.characteristic, t.outcome
    """
    rows = await _db.fetch_all(query, {"pid": project_id})

    # Add claimant (assume claimant has a specific characteristic for this analysis)
    # This would normally pull from a profile shard
    return {
        "project_id": project_id,
        "linkage_data": [dict(r) for r in rows],
    }


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_comparator.comparators")
    return {"count": result["count"] if result else 0}
