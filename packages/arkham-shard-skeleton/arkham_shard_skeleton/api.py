"""Skeleton Shard API endpoints."""

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .builder import SkeletonBuilder
    from .llm import SkeletonLLMIntegration
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
_builder: "SkeletonBuilder | None" = None
_llm_integration: "SkeletonLLMIntegration | None" = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    builder=None,
    llm_integration=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _builder, _llm_integration
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _builder = builder
    _llm_integration = llm_integration


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


class TreeBuildRequest(BaseModel):
    """Request to build an argument tree from a claim."""

    claim_id: str


class AuthorityLinkRequest(BaseModel):
    """Request to link authorities to a tree."""

    tree_id: str
    authority_ids: list[str]


class BundleRefRequest(BaseModel):
    """Request to add bundle page references to a submission."""

    submission_id: str
    bundle_id: str


class DraftRequest(BaseModel):
    """Request to draft an argument section via LLM."""

    heading: str
    claim_summary: str
    legal_test: str = ""
    evidence_summaries: list[str] = Field(default_factory=list)
    authority_citations: list[str] = Field(default_factory=list)
    bundle_refs: dict[str, int] = Field(default_factory=dict)


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


# --- Domain Endpoints ---


@router.post("/tree/build")
async def build_argument_tree(request: TreeBuildRequest):
    """Build argument tree from a claim.

    Fetches claim data and linked evidence/authorities, builds structured
    argument tree, persists it, and emits skeleton.argument.structured event.
    """
    if not _builder:
        raise HTTPException(status_code=503, detail="Skeleton builder not initialized")

    result = await _builder.build_argument_tree(request.claim_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Claim {request.claim_id} not found")

    return result


@router.post("/render/{submission_id}")
async def render_submission(submission_id: str):
    """Render submission as structured legal text.

    Produces numbered paragraphs with bundle page references and authority citations.
    """
    if not _builder:
        raise HTTPException(status_code=503, detail="Skeleton builder not initialized")

    text = await _builder.render_submission(submission_id)
    if text is None:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")

    # Emit event
    if _event_bus:
        await _event_bus.emit(
            "skeleton.submission.drafted",
            {"submission_id": submission_id},
            source="skeleton-shard",
        )

    return {"submission_id": submission_id, "rendered_text": text}


@router.post("/authorities/link")
async def link_authorities(request: AuthorityLinkRequest):
    """Link authorities to an argument tree.

    Merges new authority IDs with existing ones on the tree (deduplicates).
    """
    if not _builder:
        raise HTTPException(status_code=503, detail="Skeleton builder not initialized")

    try:
        await _builder.link_authorities(request.tree_id, request.authority_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"tree_id": request.tree_id, "status": "linked"}


@router.post("/bundle-refs")
async def add_bundle_references(request: BundleRefRequest):
    """Add bundle page references to a submission.

    Cross-references bundle page numbers for all document citations
    by querying the arkham_bundle schema.
    """
    if not _builder:
        raise HTTPException(status_code=503, detail="Skeleton builder not initialized")

    try:
        await _builder.add_bundle_references(request.submission_id, request.bundle_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"submission_id": request.submission_id, "status": "updated"}


@router.post("/draft")
async def draft_section(request: DraftRequest):
    """Draft an argument section using LLM.

    Uses UK Employment Tribunal legal drafter persona to produce
    numbered paragraphs with neutral citations and bundle page references.
    """
    if not _llm_integration or not _llm_integration.is_available:
        raise HTTPException(status_code=503, detail="LLM service not available")

    result = await _llm_integration.draft_section(
        heading=request.heading,
        claim_summary=request.claim_summary,
        legal_test=request.legal_test,
        evidence_summaries=request.evidence_summaries,
        authority_citations=request.authority_citations,
        bundle_refs=request.bundle_refs,
    )

    return {
        "heading": result.heading,
        "paragraphs": result.paragraphs,
        "authority_citations": result.authority_citations,
    }


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


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_skeleton.argument_trees")
    return {"count": result["count"] if result else 0}
