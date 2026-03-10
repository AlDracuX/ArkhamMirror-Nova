"""Playbook Shard API endpoints."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .models import VALID_PRIORITIES, VALID_STATUSES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playbook", tags=["playbook"])

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


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert a database row to a dict with parsed JSONB fields."""
    d = dict(row)
    for field in ("steps", "triggers", "expected_outcomes", "contingencies"):
        if field in d:
            d[field] = _parse_json_field(d[field])
    return d


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class CreatePlayRequest(BaseModel):
    case_id: Optional[str] = None
    name: str
    scenario: str = ""
    description: str = ""
    steps: List[Dict[str, Any]] = []
    triggers: List[Dict[str, Any]] = []
    expected_outcomes: List[Dict[str, Any]] = []
    contingencies: List[Dict[str, Any]] = []
    priority: str = "medium"
    status: str = "draft"


class UpdatePlayRequest(BaseModel):
    case_id: Optional[str] = None
    name: Optional[str] = None
    scenario: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    triggers: Optional[List[Dict[str, Any]]] = None
    expected_outcomes: Optional[List[Dict[str, Any]]] = None
    contingencies: Optional[List[Dict[str, Any]]] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class SimulateRequest(BaseModel):
    play_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_plays(
    case_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    """List plays with optional filters."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    query = "SELECT * FROM arkham_playbook.plays WHERE 1=1"
    params: Dict[str, Any] = {}

    if case_id:
        query += " AND case_id = :case_id"
        params["case_id"] = case_id
    if status:
        query += " AND status = :status"
        params["status"] = status
    if priority:
        query += " AND priority = :priority"
        params["priority"] = priority

    query += " ORDER BY created_at DESC"

    rows = await _db.fetch_all(query, params)
    return [_row_to_dict(r) for r in rows]


@router.get("/{play_id}")
async def get_play(play_id: str):
    """Get a single play by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one("SELECT * FROM arkham_playbook.plays WHERE id = :id", {"id": play_id})
    if not row:
        raise HTTPException(status_code=404, detail="Play not found")

    return _row_to_dict(row)


@router.post("/")
async def create_play(request: CreatePlayRequest):
    """Create a new play."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    if request.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority: {request.priority}")
    if request.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {request.status}")

    play_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await _db.execute(
        """
        INSERT INTO arkham_playbook.plays
        (id, case_id, name, scenario, description, steps, triggers,
         expected_outcomes, contingencies, priority, status, created_at, updated_at)
        VALUES (:id, :case_id, :name, :scenario, :description, :steps, :triggers,
                :expected_outcomes, :contingencies, :priority, :status, :created_at, :updated_at)
        """,
        {
            "id": play_id,
            "case_id": request.case_id,
            "name": request.name,
            "scenario": request.scenario,
            "description": request.description,
            "steps": json.dumps(request.steps),
            "triggers": json.dumps(request.triggers),
            "expected_outcomes": json.dumps(request.expected_outcomes),
            "contingencies": json.dumps(request.contingencies),
            "priority": request.priority,
            "status": request.status,
            "created_at": now,
            "updated_at": now,
        },
    )

    if _event_bus:
        await _event_bus.emit("playbook.strategy.updated", {"play_id": play_id})

    return {"id": play_id}


@router.put("/{play_id}")
async def update_play(play_id: str, request: UpdatePlayRequest):
    """Update an existing play."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = await _db.fetch_one("SELECT * FROM arkham_playbook.plays WHERE id = :id", {"id": play_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Play not found")

    if request.priority is not None and request.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority: {request.priority}")
    if request.status is not None and request.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {request.status}")

    updates = {}
    update_fields = request.model_dump(exclude_none=True)

    if not update_fields:
        return _row_to_dict(existing)

    set_clauses = []
    for field, value in update_fields.items():
        if field in ("steps", "triggers", "expected_outcomes", "contingencies"):
            value = json.dumps(value)
        set_clauses.append(f"{field} = :{field}")
        updates[field] = value

    updates["updated_at"] = datetime.now(timezone.utc)
    set_clauses.append("updated_at = :updated_at")
    updates["id"] = play_id

    query = f"UPDATE arkham_playbook.plays SET {', '.join(set_clauses)} WHERE id = :id"
    await _db.execute(query, updates)

    if _event_bus:
        await _event_bus.emit("playbook.strategy.updated", {"play_id": play_id})

    updated = await _db.fetch_one("SELECT * FROM arkham_playbook.plays WHERE id = :id", {"id": play_id})
    return _row_to_dict(updated)


@router.delete("/{play_id}")
async def delete_play(play_id: str):
    """Delete a play."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    existing = await _db.fetch_one("SELECT * FROM arkham_playbook.plays WHERE id = :id", {"id": play_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Play not found")

    await _db.execute("DELETE FROM arkham_playbook.plays WHERE id = :id", {"id": play_id})

    return {"deleted": True, "id": play_id}


@router.post("/simulate")
async def simulate_play(request: SimulateRequest):
    """Simulate a play and return risk assessment."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await _db.fetch_one("SELECT * FROM arkham_playbook.plays WHERE id = :id", {"id": request.play_id})
    if not row:
        raise HTTPException(status_code=404, detail="Play not found")

    play = _row_to_dict(row)

    # Sort steps by order field if present
    steps = play.get("steps", [])
    steps_sorted = sorted(steps, key=lambda s: s.get("order", 0))

    # Determine risk based on priority and step count
    priority = play.get("priority", "medium")
    contingencies = play.get("contingencies", [])
    step_count = len(steps_sorted)

    if priority in ("critical", "high") and len(contingencies) == 0:
        risk = "high"
    elif priority in ("critical", "high") and len(contingencies) > 0:
        risk = "medium"
    elif step_count > 5 and len(contingencies) == 0:
        risk = "medium"
    else:
        risk = "low"

    estimated_outcomes = play.get("expected_outcomes", [])

    return {
        "play_id": play["id"],
        "scenario": play.get("scenario", ""),
        "steps": steps_sorted,
        "risk_assessment": risk,
        "estimated_outcomes": estimated_outcomes,
    }


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_playbook.plays")
    return {"count": result["count"] if result else 0}
