"""Skeleton Shard API endpoints."""

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import SkeletonShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "SkeletonShard":
    """Get the Skeleton shard instance from app state."""
    shard = getattr(request.app.state, "skeleton_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Skeleton shard not available")
    return shard


router = APIRouter(prefix="/api/skeleton", tags=["skeleton"])

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


class ArgumentTreeCreate(BaseModel):
    title: str
    project_id: Optional[str] = None
    claim_id: Optional[str] = None
    legal_test: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    authority_ids: list[str] = Field(default_factory=list)
    logic_summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None


class AuthorityCreate(BaseModel):
    citation: str
    title: str = ""
    authority_type: str = "case_law"
    ratio_decidendi: str = ""
    key_quotes: list[str] = Field(default_factory=list)
    bundle_page: Optional[int] = None
    is_binding: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubmissionCreate(BaseModel):
    title: str
    project_id: Optional[str] = None
    submission_type: str = "skeleton_argument"
    status: str = "draft"
    content_structure: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None


# --- Argument Trees Endpoints ---


@router.get("/argument-trees")
async def list_argument_trees(project_id: Optional[str] = None):
    """List argument trees with optional project filter."""
    if not _db:
        raise HTTPException(status_code=503, detail="Skeleton service not initialized")

    query = "SELECT * FROM arkham_skeleton.argument_trees WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/argument-trees")
async def create_argument_tree(request: ArgumentTreeCreate):
    """Create a new argument tree."""
    if not _db:
        raise HTTPException(status_code=503, detail="Skeleton service not initialized")

    tree_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_skeleton.argument_trees
        (id, tenant_id, title, project_id, claim_id, legal_test, evidence_refs, authority_ids, logic_summary, metadata, created_by)
        VALUES (:id, :tenant_id, :title, :project_id, :claim_id, :legal_test, :evidence_refs, :authority_ids, :logic_summary, :metadata, :created_by)
        """,
        {
            "id": tree_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "title": request.title,
            "project_id": request.project_id,
            "claim_id": request.claim_id,
            "legal_test": request.legal_test,
            "evidence_refs": json.dumps(request.evidence_refs),
            "authority_ids": json.dumps(request.authority_ids),
            "logic_summary": request.logic_summary,
            "metadata": json.dumps(request.metadata),
            "created_by": request.created_by,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "skeleton.argument.structured",
            {"tree_id": tree_id, "title": request.title},
            source="skeleton-shard",
        )

    return {"id": tree_id, "status": "created"}


# --- Authorities Endpoints ---


@router.get("/authorities")
async def list_authorities():
    """List all legal authorities."""
    if not _db:
        raise HTTPException(status_code=503, detail="Skeleton service not initialized")

    rows = await _db.fetch_all("SELECT * FROM arkham_skeleton.authorities")
    return [dict(row) for row in rows]


@router.post("/authorities")
async def create_authority(request: AuthorityCreate):
    """Create a new legal authority."""
    if not _db:
        raise HTTPException(status_code=503, detail="Skeleton service not initialized")

    auth_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_skeleton.authorities
        (id, tenant_id, citation, title, authority_type, ratio_decidendi, key_quotes, bundle_page, is_binding, metadata)
        VALUES (:id, :tenant_id, :citation, :title, :authority_type, :ratio_decidendi, :key_quotes, :bundle_page, :is_binding, :metadata)
        """,
        {
            "id": auth_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "citation": request.citation,
            "title": request.title,
            "authority_type": request.authority_type,
            "ratio_decidendi": request.ratio_decidendi,
            "key_quotes": json.dumps(request.key_quotes),
            "bundle_page": request.bundle_page,
            "is_binding": request.is_binding,
            "metadata": json.dumps(request.metadata),
        },
    )

    return {"id": auth_id, "status": "created"}


# --- Submissions Endpoints ---


@router.get("/submissions")
async def list_submissions(project_id: Optional[str] = None):
    """List submissions with optional project filter."""
    if not _db:
        raise HTTPException(status_code=503, detail="Skeleton service not initialized")

    query = "SELECT * FROM arkham_skeleton.submissions WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/submissions")
async def create_submission(request: SubmissionCreate):
    """Create a new legal submission."""
    if not _db:
        raise HTTPException(status_code=503, detail="Skeleton service not initialized")

    sub_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_skeleton.submissions
        (id, tenant_id, title, project_id, submission_type, status, content_structure, metadata, created_by)
        VALUES (:id, :tenant_id, :title, :project_id, :submission_type, :status, :content_structure, :metadata, :created_by)
        """,
        {
            "id": sub_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "title": request.title,
            "project_id": request.project_id,
            "submission_type": request.submission_type,
            "status": request.status,
            "content_structure": json.dumps(request.content_structure),
            "metadata": json.dumps(request.metadata),
            "created_by": request.created_by,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "skeleton.submission.generated",
            {"submission_id": sub_id, "title": request.title},
            source="skeleton-shard",
        )

    return {"id": sub_id, "status": "created"}
