"""RespondentIntel Shard API endpoints."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/respondent-intel", tags=["respondent-intel"])

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
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateProfileRequest(BaseModel):
    case_id: str
    name: str
    role: str
    organization: str
    title: Optional[str] = None
    background: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    known_positions: List[str] = Field(default_factory=list)
    credibility_notes: Optional[str] = None
    document_ids: List[str] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    organization: Optional[str] = None
    title: Optional[str] = None
    background: Optional[str] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    known_positions: Optional[List[str]] = None
    credibility_notes: Optional[str] = None
    document_ids: Optional[List[str]] = None


class BuildProfileRequest(BaseModel):
    case_id: str
    respondent_name: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_json_field(value: Any, default: Any = None) -> Any:
    """Parse a JSON field that may already be parsed by the database driver."""
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return default if default is not None else []


def _compute_assessment(strengths: list, weaknesses: list) -> str:
    """Compute assessment based on strength/weakness balance."""
    s = len(strengths)
    w = len(weaknesses)
    if s > w:
        return "strong"
    elif w > s:
        return "weak"
    return "moderate"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_profiles(
    case_id: Optional[str] = Query(None),
    organization: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """List respondent profiles with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    conditions = []
    params: Dict[str, Any] = {}

    if case_id:
        conditions.append("case_id = :case_id")
        params["case_id"] = case_id

    if organization:
        conditions.append("organization = :organization")
        params["organization"] = organization

    where = ""
    if conditions:
        where = " WHERE " + " AND ".join(conditions)

    query = f"SELECT * FROM arkham_respondent_intel.respondent_profiles{where} ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return [dict(r) for r in rows]


@router.get("/dossier/{profile_id}")
async def get_dossier(profile_id: str) -> Dict[str, Any]:
    """Return a full dossier for a respondent profile."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_respondent_intel.respondent_profiles WHERE id = :id",
        {"id": profile_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = dict(row)
    strengths = _parse_json_field(profile.get("strengths"), [])
    weaknesses = _parse_json_field(profile.get("weaknesses"), [])
    doc_ids = _parse_json_field(profile.get("document_ids"), [])

    return {
        "profile": profile,
        "strength_count": len(strengths),
        "weakness_count": len(weaknesses),
        "document_count": len(doc_ids),
        "assessment": _compute_assessment(strengths, weaknesses),
    }


@router.get("/{profile_id}")
async def get_profile(profile_id: str) -> Dict[str, Any]:
    """Get a single respondent profile."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_respondent_intel.respondent_profiles WHERE id = :id",
        {"id": profile_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return dict(row)


@router.post("/")
async def create_profile(request: CreateProfileRequest) -> Dict[str, str]:
    """Create a new respondent profile."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    profile_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await _db.execute(
        """
        INSERT INTO arkham_respondent_intel.respondent_profiles
        (id, case_id, name, role, organization, title, background,
         strengths, weaknesses, known_positions, credibility_notes,
         document_ids, created_at, updated_at)
        VALUES (:id, :case_id, :name, :role, :organization, :title, :background,
                :strengths, :weaknesses, :known_positions, :credibility_notes,
                :document_ids, :created_at, :updated_at)
        """,
        {
            "id": profile_id,
            "case_id": request.case_id,
            "name": request.name,
            "role": request.role,
            "organization": request.organization,
            "title": request.title,
            "background": request.background,
            "strengths": json.dumps(request.strengths),
            "weaknesses": json.dumps(request.weaknesses),
            "known_positions": json.dumps(request.known_positions),
            "credibility_notes": request.credibility_notes,
            "document_ids": request.document_ids if request.document_ids else [],
            "created_at": now,
            "updated_at": now,
        },
    )

    if _event_bus:
        await _event_bus.emit("respondent.profile.updated", {"profile_id": profile_id}, source="respondent-intel")

    return {"id": profile_id}


@router.put("/{profile_id}")
async def update_profile(profile_id: str, request: UpdateProfileRequest) -> Dict[str, Any]:
    """Update an existing respondent profile."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    # Check existence
    existing = await _db.fetch_one(
        "SELECT * FROM arkham_respondent_intel.respondent_profiles WHERE id = :id",
        {"id": profile_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Build SET clause from non-None fields
    updates = {}
    fields_to_update = request.model_dump(exclude_none=True)

    for field_name, value in fields_to_update.items():
        if isinstance(value, list) and field_name in ("strengths", "weaknesses", "known_positions"):
            updates[field_name] = json.dumps(value)
        else:
            updates[field_name] = value

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = profile_id
        await _db.execute(
            f"UPDATE arkham_respondent_intel.respondent_profiles SET {set_clause} WHERE id = :id",
            updates,
        )

    if _event_bus:
        await _event_bus.emit("respondent.profile.updated", {"profile_id": profile_id}, source="respondent-intel")

    return {"id": profile_id, "updated": True}


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str) -> Dict[str, Any]:
    """Delete a respondent profile."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = await _db.fetch_one(
        "SELECT id FROM arkham_respondent_intel.respondent_profiles WHERE id = :id",
        {"id": profile_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    await _db.execute(
        "DELETE FROM arkham_respondent_intel.respondent_profiles WHERE id = :id",
        {"id": profile_id},
    )

    return {"id": profile_id, "deleted": True}


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_respondent_intel.respondent_profiles")
    return {"count": result["count"] if result else 0}


# ---------------------------------------------------------------------------
# Domain Intelligence Endpoints
# ---------------------------------------------------------------------------


@router.post("/profile/build")
async def build_profile(request: BuildProfileRequest) -> Dict[str, Any]:
    """Build a respondent profile from entity mentions and documents."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    result = await _engine.build_profile(
        case_id=request.case_id,
        respondent_name=request.respondent_name,
    )
    return result


@router.get("/profile/{profile_id}/positions")
async def get_positions(profile_id: str) -> List[Dict[str, Any]]:
    """Track positions the respondent has taken across documents."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    return await _engine.track_positions(profile_id)


@router.post("/profile/{profile_id}/inconsistencies")
async def detect_inconsistencies(profile_id: str) -> List[Dict[str, Any]]:
    """Detect inconsistencies in the respondent's positions across documents."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    return await _engine.detect_inconsistencies(profile_id)


@router.post("/profile/{profile_id}/assess")
async def assess_strengths_weaknesses(profile_id: str) -> Dict[str, Any]:
    """Generate a strengths/weaknesses assessment of the respondent's case."""
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    return await _engine.assess_strengths_weaknesses(profile_id)
