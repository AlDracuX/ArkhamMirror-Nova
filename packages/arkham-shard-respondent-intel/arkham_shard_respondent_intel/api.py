"""RespondentIntel Shard API endpoints."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .models import PublicRecord, RespondentConnection, RespondentProfile, RespondentVulnerability

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/respondent-intel", tags=["respondent-intel"])

_db = None
_event_bus = None
_llm_service = None
_shard = None


def init_api(db, event_bus, llm_service=None, shard=None):
    global _db, _event_bus, _llm_service, _shard
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard


class CreateProfileRequest(BaseModel):
    name: str
    type: str
    metadata: Dict[str, Any] = {}


@router.post("/profiles", response_model=Dict[str, str])
async def create_profile(request: CreateProfileRequest):
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    profile_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_respondent_intel.profiles
        (id, tenant_id, name, type)
        VALUES (:id, :tenant_id, :name, :type)
        """,
        {
            "id": profile_id,
            "tenant_id": tenant_id,
            "name": request.name,
            "type": request.type,
        },
    )

    if _event_bus:
        await _event_bus.emit("respondent.profile.updated", {"profile_id": profile_id})

    return {"id": profile_id}


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str):
    row = await _db.fetch_one("SELECT * FROM arkham_respondent_intel.profiles WHERE id = :id", {"id": profile_id})
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = dict(row)
    records = await _db.fetch_all(
        "SELECT * FROM arkham_respondent_intel.public_records WHERE respondent_id = :id", {"id": profile_id}
    )
    profile["public_records"] = [dict(r) for r in records]

    vulnerabilities = await _db.fetch_all(
        "SELECT * FROM arkham_respondent_intel.vulnerabilities WHERE respondent_id = :id", {"id": profile_id}
    )
    profile["vulnerabilities"] = [dict(v) for v in vulnerabilities]

    return profile


@router.get("/profiles")
async def list_profiles():
    rows = await _db.fetch_all("SELECT * FROM arkham_respondent_intel.profiles")
    return [dict(r) for r in rows]
