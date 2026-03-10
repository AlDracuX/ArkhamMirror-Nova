"""CrossExam Shard API endpoints.

CRUD for Question Trees, Nodes, Impeachment Sequences, Damage Scores, and Exam Plans.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import CrossExamShard

logger = logging.getLogger(__name__)

VALID_APPROACHES = {"standard", "hostile", "friendly", "expert"}
VALID_STATUSES = {"draft", "prepared", "in_progress", "completed"}


def get_shard(request: Request) -> "CrossExamShard":
    """Get the CrossExam shard instance from app state."""
    shard = getattr(request.app.state, "crossexam_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="CrossExam shard not available")
    return shard


router = APIRouter(prefix="/api/crossexam", tags=["crossexam"])

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


class CreateTreeRequest(BaseModel):
    witness_id: str
    title: str
    description: Optional[str] = ""
    project_id: Optional[str] = None
    created_by: Optional[str] = None


class CreateNodeRequest(BaseModel):
    tree_id: str
    parent_id: Optional[str] = None
    question_text: str
    expected_answer: Optional[str] = None
    alternative_answer: Optional[str] = None
    damage_potential: float = 0.0


class CreateImpeachmentRequest(BaseModel):
    witness_id: str
    title: str
    conflict_description: str
    statement_claim_id: Optional[str] = None
    document_evidence_id: Optional[str] = None
    steps: List[dict] = []


class CreateExamPlanRequest(BaseModel):
    case_id: Optional[str] = None
    witness_id: Optional[str] = None
    witness_name: str
    topics: List[dict] = []
    questions: List[dict] = []
    impeachment_points: List[dict] = []
    objectives: Optional[str] = None
    approach: str = "standard"
    status: str = "draft"


class UpdateExamPlanRequest(BaseModel):
    witness_name: Optional[str] = None
    topics: Optional[List[dict]] = None
    questions: Optional[List[dict]] = None
    impeachment_points: Optional[List[dict]] = None
    objectives: Optional[str] = None
    approach: Optional[str] = None
    status: Optional[str] = None


class GenerateExamPlanRequest(BaseModel):
    witness_name: str
    case_id: str
    topics: List[str]


# --- Helper ---


def _ensure_db():
    if not _db:
        raise HTTPException(status_code=503, detail="CrossExam service not initialized")


def _parse_json_field(value, default=None):
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


def _plan_row_to_dict(row) -> dict:
    """Convert a database row to a plan dictionary with parsed JSON fields."""
    d = dict(row)
    for field_name in ("topics", "questions", "impeachment_points"):
        if field_name in d:
            d[field_name] = _parse_json_field(d[field_name], [])
    # Convert UUID/datetime to strings for JSON serialization
    for field_name in ("id", "case_id", "witness_id"):
        if field_name in d and d[field_name] is not None:
            d[field_name] = str(d[field_name])
    for field_name in ("created_at", "updated_at"):
        if field_name in d and d[field_name] is not None:
            d[field_name] = d[field_name].isoformat() if hasattr(d[field_name], "isoformat") else str(d[field_name])
    return d


# --- Question Tree Endpoints ---


@router.get("/trees")
async def list_trees(
    witness_id: Optional[str] = None,
    project_id: Optional[str] = None,
):
    """List question trees."""
    _ensure_db()

    query = "SELECT * FROM arkham_crossexam.question_trees WHERE 1=1"
    params: dict = {}
    if witness_id:
        query += " AND witness_id = :wid"
        params["wid"] = witness_id
    if project_id:
        query += " AND project_id = :pid"
        params["pid"] = project_id

    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "trees": [dict(r) for r in rows]}


@router.get("/trees/{tree_id}/nodes")
async def get_tree_nodes(tree_id: str):
    """Get all nodes for a question tree."""
    _ensure_db()

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_crossexam.question_nodes WHERE tree_id = :tid ORDER BY created_at ASC",
        {"tid": tree_id},
    )
    return {"count": len(rows), "nodes": [dict(r) for r in rows]}


@router.post("/trees")
async def create_tree(request: CreateTreeRequest):
    """Create a new question tree."""
    tid = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_crossexam.question_trees
        (id, tenant_id, witness_id, title, description, project_id, created_by)
        VALUES (:id, :tenant_id, :wid, :title, :desc, :pid, :by)
        """,
        {
            "id": tid,
            "tenant_id": tenant_id,
            "wid": request.witness_id,
            "title": request.title,
            "desc": request.description,
            "pid": request.project_id,
            "by": request.created_by,
        },
    )
    return {"tree_id": tid}


@router.post("/nodes")
async def create_node(request: CreateNodeRequest):
    """Add a node to a question tree."""
    nid = str(uuid.uuid4())
    await _db.execute(
        """
        INSERT INTO arkham_crossexam.question_nodes
        (id, tree_id, parent_id, question_text, expected_answer, alternative_answer, damage_potential)
        VALUES (:id, :tid, :pid, :text, :exp, :alt, :damage)
        """,
        {
            "id": nid,
            "tid": request.tree_id,
            "pid": request.parent_id,
            "text": request.question_text,
            "exp": request.expected_answer,
            "alt": request.alternative_answer,
            "damage": request.damage_potential,
        },
    )
    return {"node_id": nid}


# --- Impeachment Endpoints ---


@router.get("/impeachments")
async def list_impeachments(witness_id: Optional[str] = None):
    """List impeachment sequences."""
    _ensure_db()

    query = "SELECT * FROM arkham_crossexam.impeachment_sequences WHERE 1=1"
    params: dict = {}
    if witness_id:
        query += " AND witness_id = :wid"
        params["wid"] = witness_id

    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "impeachments": [dict(r) for r in rows]}


@router.post("/impeachments")
async def create_impeachment(request: CreateImpeachmentRequest):
    """Record an impeachment sequence."""
    iid = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_crossexam.impeachment_sequences
        (id, tenant_id, witness_id, title, conflict_description, statement_claim_id, document_evidence_id, steps)
        VALUES (:id, :tenant_id, :wid, :title, :desc, :sid, :did, :steps)
        """,
        {
            "id": iid,
            "tenant_id": tenant_id,
            "wid": request.witness_id,
            "title": request.title,
            "desc": request.conflict_description,
            "sid": request.statement_claim_id,
            "did": request.document_evidence_id,
            "steps": json.dumps(request.steps),
        },
    )
    return {"impeachment_id": iid}


# --- Exam Plan CRUD Endpoints ---


@router.get("/")
async def list_exam_plans(
    case_id: Optional[str] = None,
    witness_name: Optional[str] = None,
    status: Optional[str] = None,
):
    """List exam plans with optional filters."""
    _ensure_db()

    query = "SELECT * FROM arkham_crossexam.exam_plans WHERE 1=1"
    params: dict = {}
    if case_id:
        query += " AND case_id = :case_id"
        params["case_id"] = case_id
    if witness_name:
        query += " AND witness_name ILIKE :wname"
        params["wname"] = f"%{witness_name}%"
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}. Must be one of {VALID_STATUSES}")
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC"
    rows = await _db.fetch_all(query, params)
    return {"count": len(rows), "plans": [_plan_row_to_dict(r) for r in rows]}


@router.get("/{plan_id}")
async def get_exam_plan(plan_id: str):
    """Get a single exam plan by ID."""
    _ensure_db()

    row = await _db.fetch_one(
        "SELECT * FROM arkham_crossexam.exam_plans WHERE id = :id",
        {"id": plan_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Exam plan not found")
    return _plan_row_to_dict(row)


@router.post("/")
async def create_exam_plan(request: CreateExamPlanRequest):
    """Create a new exam plan."""
    _ensure_db()

    if request.approach not in VALID_APPROACHES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid approach: {request.approach}. Must be one of {VALID_APPROACHES}",
        )
    if request.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status: {request.status}. Must be one of {VALID_STATUSES}",
        )

    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await _db.execute(
        """
        INSERT INTO arkham_crossexam.exam_plans
        (id, case_id, witness_id, witness_name, topics, questions, impeachment_points,
         objectives, approach, status, created_at, updated_at)
        VALUES (:id, :case_id, :witness_id, :witness_name, :topics, :questions, :impeachment_points,
                :objectives, :approach, :status, :created_at, :updated_at)
        """,
        {
            "id": plan_id,
            "case_id": request.case_id,
            "witness_id": request.witness_id,
            "witness_name": request.witness_name,
            "topics": json.dumps(request.topics),
            "questions": json.dumps(request.questions),
            "impeachment_points": json.dumps(request.impeachment_points),
            "objectives": request.objectives,
            "approach": request.approach,
            "status": request.status,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    return {
        "id": plan_id,
        "witness_name": request.witness_name,
        "approach": request.approach,
        "status": request.status,
        "created_at": now.isoformat(),
    }


@router.put("/{plan_id}")
async def update_exam_plan(plan_id: str, request: UpdateExamPlanRequest):
    """Update an existing exam plan."""
    _ensure_db()

    # Verify plan exists
    existing = await _db.fetch_one(
        "SELECT * FROM arkham_crossexam.exam_plans WHERE id = :id",
        {"id": plan_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Exam plan not found")

    # Validate approach if provided
    if request.approach is not None and request.approach not in VALID_APPROACHES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid approach: {request.approach}. Must be one of {VALID_APPROACHES}",
        )
    if request.status is not None and request.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status: {request.status}. Must be one of {VALID_STATUSES}",
        )

    # Build dynamic SET clause
    updates = []
    params: dict = {"id": plan_id}
    now = datetime.now(timezone.utc)

    field_map = {
        "witness_name": request.witness_name,
        "objectives": request.objectives,
        "approach": request.approach,
        "status": request.status,
    }
    json_field_map = {
        "topics": request.topics,
        "questions": request.questions,
        "impeachment_points": request.impeachment_points,
    }

    for col, val in field_map.items():
        if val is not None:
            updates.append(f"{col} = :{col}")
            params[col] = val

    for col, val in json_field_map.items():
        if val is not None:
            updates.append(f"{col} = :{col}")
            params[col] = json.dumps(val)

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    updates.append("updated_at = :updated_at")
    params["updated_at"] = now.isoformat()

    query = f"UPDATE arkham_crossexam.exam_plans SET {', '.join(updates)} WHERE id = :id"
    await _db.execute(query, params)

    return {"id": plan_id, "updated": True, "updated_at": now.isoformat()}


@router.delete("/{plan_id}")
async def delete_exam_plan(plan_id: str):
    """Delete an exam plan."""
    _ensure_db()

    existing = await _db.fetch_one(
        "SELECT id FROM arkham_crossexam.exam_plans WHERE id = :id",
        {"id": plan_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Exam plan not found")

    await _db.execute(
        "DELETE FROM arkham_crossexam.exam_plans WHERE id = :id",
        {"id": plan_id},
    )
    return {"id": plan_id, "deleted": True}


# --- Generate Endpoint ---


def _generate_questions_for_topics(topics: List[str]) -> List[dict]:
    """Generate template questions for each topic.

    Each topic produces a structured question template with
    opening, probing, and closing question patterns.
    """
    questions = []
    for topic in topics:
        questions.append(
            {
                "topic": topic,
                "opening": f"Can you tell us about your involvement with {topic}?",
                "probing": f"What specific details can you provide regarding {topic}?",
                "closing": f"Is there anything else relevant to {topic} that you haven't mentioned?",
                "type": "template",
            }
        )
    return questions


@router.post("/generate")
async def generate_exam_plan(request: GenerateExamPlanRequest):
    """Generate a new exam plan with auto-generated question templates per topic.

    Takes a witness name, case ID, and list of topics. Creates a new plan
    with template questions generated for each topic.
    """
    _ensure_db()

    if not request.topics:
        raise HTTPException(status_code=422, detail="At least one topic is required")

    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    questions = _generate_questions_for_topics(request.topics)
    topics_as_dicts = [{"name": t, "status": "pending"} for t in request.topics]

    await _db.execute(
        """
        INSERT INTO arkham_crossexam.exam_plans
        (id, case_id, witness_name, topics, questions, impeachment_points,
         approach, status, created_at, updated_at)
        VALUES (:id, :case_id, :witness_name, :topics, :questions, :impeachment_points,
                :approach, :status, :created_at, :updated_at)
        """,
        {
            "id": plan_id,
            "case_id": request.case_id,
            "witness_name": request.witness_name,
            "topics": json.dumps(topics_as_dicts),
            "questions": json.dumps(questions),
            "impeachment_points": json.dumps([]),
            "approach": "standard",
            "status": "draft",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )

    return {
        "id": plan_id,
        "case_id": request.case_id,
        "witness_name": request.witness_name,
        "topics": topics_as_dicts,
        "questions": questions,
        "impeachment_points": [],
        "approach": "standard",
        "status": "draft",
        "created_at": now.isoformat(),
    }


# --- AI Generation (legacy) ---


@router.post("/generate/question-tree")
async def generate_question_tree(witness_id: str, project_id: str):
    """AI-powered generation of cross-examination trees."""
    if not _llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    return {
        "status": "triggered",
        "witness_id": witness_id,
        "message": "AI generation started (simulated)",
    }


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    _ensure_db()
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_crossexam.question_trees")
    count_trees = result["count"] if result else 0
    result2 = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_crossexam.exam_plans")
    count_plans = result2["count"] if result2 else 0
    return {"count": count_trees + count_plans}
