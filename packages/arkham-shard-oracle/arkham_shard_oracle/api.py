"""Oracle Shard API endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .models import AuthorityCreate, AuthoritySearchRequest, AuthorityUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oracle", tags=["oracle"])

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


def _ensure_db():
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_authorities(
    jurisdiction: Optional[str] = Query(None),
    authority_type: Optional[str] = Query(None),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
) -> List[Dict[str, Any]]:
    """List authorities with optional filters."""
    _ensure_db()

    conditions = []
    params: Dict[str, Any] = {}

    if jurisdiction:
        conditions.append("jurisdiction = :jurisdiction")
        params["jurisdiction"] = jurisdiction

    if authority_type:
        conditions.append("authority_type = :authority_type")
        params["authority_type"] = authority_type

    if year_from is not None:
        conditions.append("year >= :year_from")
        params["year_from"] = year_from

    if year_to is not None:
        conditions.append("year <= :year_to")
        params["year_to"] = year_to

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT * FROM arkham_oracle.legal_authorities {where} ORDER BY created_at DESC"
    rows = await _db.fetch_all(sql, params)
    return [dict(r) for r in rows]


@router.get("/{authority_id}")
async def get_authority(authority_id: str) -> Dict[str, Any]:
    """Get a single authority by ID."""
    _ensure_db()

    row = await _db.fetch_one(
        "SELECT * FROM arkham_oracle.legal_authorities WHERE id = :id",
        {"id": authority_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Authority not found")

    return dict(row)


@router.post("/")
async def create_authority(body: AuthorityCreate) -> Dict[str, Any]:
    """Create a new legal authority. Citation must be unique."""
    _ensure_db()

    # Check citation uniqueness
    existing = await _db.fetch_one(
        "SELECT id FROM arkham_oracle.legal_authorities WHERE citation = :citation",
        {"citation": body.citation},
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Authority with citation '{body.citation}' already exists")

    authority_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)

    await _db.execute(
        """
        INSERT INTO arkham_oracle.legal_authorities
        (id, citation, jurisdiction, court, title, year, summary, full_text,
         relevance_tags, claim_types, authority_type, created_at, updated_at)
        VALUES (:id, :citation, :jurisdiction, :court, :title, :year, :summary, :full_text,
                :relevance_tags, :claim_types, :authority_type, :created_at, :updated_at)
        """,
        {
            "id": authority_id,
            "citation": body.citation,
            "jurisdiction": body.jurisdiction,
            "court": body.court,
            "title": body.title,
            "year": body.year,
            "summary": body.summary,
            "full_text": body.full_text,
            "relevance_tags": body.relevance_tags,
            "claim_types": body.claim_types,
            "authority_type": body.authority_type.value,
            "created_at": now,
            "updated_at": now,
        },
    )

    if _event_bus:
        await _event_bus.emit("oracle.authority.found", {"authority_id": authority_id})

    return {
        "id": authority_id,
        "citation": body.citation,
        "jurisdiction": body.jurisdiction,
        "court": body.court,
        "title": body.title,
        "year": body.year,
        "summary": body.summary,
        "full_text": body.full_text,
        "relevance_tags": body.relevance_tags,
        "claim_types": body.claim_types,
        "authority_type": body.authority_type.value,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@router.put("/{authority_id}")
async def update_authority(authority_id: str, body: AuthorityUpdate) -> Dict[str, Any]:
    """Update an existing authority."""
    _ensure_db()

    # Fetch current record
    existing = await _db.fetch_one(
        "SELECT * FROM arkham_oracle.legal_authorities WHERE id = :id",
        {"id": authority_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Authority not found")

    existing_dict = dict(existing)

    # Build update fields from non-None values
    update_fields = {}
    for field_name, value in body.model_dump(exclude_unset=True).items():
        if field_name == "authority_type" and value is not None:
            update_fields[field_name] = value.value if hasattr(value, "value") else value
        else:
            update_fields[field_name] = value

    if not update_fields:
        return existing_dict

    update_fields["updated_at"] = datetime.now(tz=timezone.utc)

    set_clauses = [f"{k} = :{k}" for k in update_fields]
    update_fields["id"] = authority_id

    await _db.execute(
        f"UPDATE arkham_oracle.legal_authorities SET {', '.join(set_clauses)} WHERE id = :id",
        update_fields,
    )

    # Merge updates into existing record for response
    for k, v in update_fields.items():
        if k != "id":
            existing_dict[k] = v

    return existing_dict


@router.delete("/{authority_id}")
async def delete_authority(authority_id: str) -> Dict[str, Any]:
    """Delete an authority by ID."""
    _ensure_db()

    existing = await _db.fetch_one(
        "SELECT id FROM arkham_oracle.legal_authorities WHERE id = :id",
        {"id": authority_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Authority not found")

    await _db.execute(
        "DELETE FROM arkham_oracle.legal_authorities WHERE id = :id",
        {"id": authority_id},
    )

    return {"deleted": True, "id": authority_id}


# ---------------------------------------------------------------------------
# Domain Endpoint: Search
# ---------------------------------------------------------------------------


@router.post("/search")
async def search_authorities(body: AuthoritySearchRequest) -> List[Dict[str, Any]]:
    """Search authorities by text match on title, summary, citation.

    Uses ILIKE for case-insensitive partial matching. Optionally filters
    by jurisdiction and claim_types.
    """
    _ensure_db()

    conditions = ["(title ILIKE :query OR summary ILIKE :query OR citation ILIKE :query)"]
    params: Dict[str, Any] = {"query": f"%{body.query}%"}

    if body.jurisdiction:
        conditions.append("jurisdiction = :jurisdiction")
        params["jurisdiction"] = body.jurisdiction

    if body.claim_types:
        conditions.append("claim_types && :claim_types")
        params["claim_types"] = body.claim_types

    where = "WHERE " + " AND ".join(conditions)
    sql = f"SELECT * FROM arkham_oracle.legal_authorities {where} ORDER BY created_at DESC"

    rows = await _db.fetch_all(sql, params)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Badge / Count Endpoint
# ---------------------------------------------------------------------------


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    _ensure_db()
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_oracle.legal_authorities")
    return {"count": result["count"] if result else 0}
