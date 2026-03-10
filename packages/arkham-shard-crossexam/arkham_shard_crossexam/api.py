"""CrossExam Shard API endpoints.

CRUD for Question Trees, Nodes, Impeachment Sequences, and Damage Scores.
"""

import json
import logging
import uuid
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import CrossExamShard

logger = logging.getLogger(__name__)


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


# --- Endpoints ---


@router.get("/trees")
async def list_trees(
    witness_id: Optional[str] = None,
    project_id: Optional[str] = None,
):
    """List question trees."""
    if not _db:
        raise HTTPException(status_code=503, detail="CrossExam service not initialized")

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
    if not _db:
        raise HTTPException(status_code=503, detail="CrossExam service not initialized")

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


@router.get("/impeachments")
async def list_impeachments(witness_id: Optional[str] = None):
    """List impeachment sequences."""
    if not _db:
        raise HTTPException(status_code=503, detail="CrossExam service not initialized")

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


# --- AI Generation ---


@router.post("/generate/question-tree")
async def generate_question_tree(witness_id: str, project_id: str):
    """
    AI-powered generation of cross-examination trees.

    Analyzes witness statements against documentary evidence to find conflicts.
    """
    if not _llm_service:
        raise HTTPException(status_code=503, detail="LLM service not available")

    # This would involve complex prompting and context assembly
    return {
        "status": "triggered",
        "witness_id": witness_id,
        "message": "AI generation started (simulated)",
    }


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_crossexam.question_trees")
    return {"count": result["count"] if result else 0}
