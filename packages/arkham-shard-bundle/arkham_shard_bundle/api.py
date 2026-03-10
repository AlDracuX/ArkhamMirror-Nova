"""Bundle Shard API endpoints.

CRUD for Bundles, Versions, Pages, and Indices.
Plus the core bundle compilation logic and LLM-assisted ordering.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .models import (
    BundleIndex,
    BundleIndexEntry,
    BundleStatus,
    DocumentStatus,
    IndexEntryType,
)

if TYPE_CHECKING:
    from .compiler import BundleCompiler
    from .llm import BundleLLMIntegration
    from .shard import BundleShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "BundleShard":
    """Get the Bundle shard instance from app state."""
    shard = getattr(request.app.state, "bundle_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Bundle shard not available")
    return shard


router = APIRouter(prefix="/api/bundle", tags=["bundle"])

# Module-level references set during initialization
_db = None
_event_bus = None
_llm_service = None
_shard = None
_compiler = None
_llm_integration = None


def init_api(
    db,
    event_bus,
    llm_service=None,
    shard=None,
    compiler=None,
    llm_integration=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _llm_service, _shard, _compiler, _llm_integration
    _db = db
    _event_bus = event_bus
    _llm_service = llm_service
    _shard = shard
    _compiler = compiler
    _llm_integration = llm_integration


# --- Request/Response Models ---


class CreateBundleRequest(BaseModel):
    title: str
    description: str = ""
    project_id: str | None = None
    created_by: str | None = None


class UpdateBundleRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: BundleStatus | None = None


class CompileRequest(BaseModel):
    document_ids: List[str]
    document_overrides: dict = Field(default_factory=dict)
    section_headers: dict = Field(default_factory=dict)
    change_notes: str = ""
    compiled_by: str | None = None


class AddDocumentRequest(BaseModel):
    document_id: str
    position: int | None = None
    title: str = ""
    filename: str = ""
    page_count: int = 1
    status: str = "unknown"
    section_label: str = ""
    notes: str = ""


class SuggestOrderRequest(BaseModel):
    documents: list[dict] = Field(default_factory=list)


# --- Bundle CRUD Endpoints ---


@router.get("/bundles")
async def list_bundles(
    project_id: str | None = None,
    status: str | None = None,
):
    """List bundles with optional filtering."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    query = "SELECT * FROM arkham_bundle.bundles WHERE 1=1"
    params: dict = {}

    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id
    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC"

    rows = await _db.fetch_all(query, params)
    return {
        "count": len(rows),
        "bundles": [dict(row) for row in rows],
    }


@router.get("/bundles/{bundle_id}")
async def get_bundle(bundle_id: str):
    """Get a bundle by ID."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_bundle.bundles WHERE id = :id",
        {"id": bundle_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Bundle not found: {bundle_id}")

    return dict(row)


@router.post("/bundles")
async def create_bundle(request: CreateBundleRequest):
    """Create a new bundle."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    bundle_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_bundle.bundles
        (id, tenant_id, title, description, project_id, created_by)
        VALUES (:id, :tenant_id, :title, :description, :project_id, :created_by)
        """,
        {
            "id": bundle_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "title": request.title,
            "description": request.description,
            "project_id": request.project_id,
            "created_by": request.created_by,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "bundle.bundle.created",
            {"bundle_id": bundle_id, "title": request.title},
            source="bundle-shard",
        )

    return {"bundle_id": bundle_id, "title": request.title, "status": "draft"}


@router.put("/bundles/{bundle_id}")
async def update_bundle(bundle_id: str, request: UpdateBundleRequest):
    """Update a bundle."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    sets = []
    params: dict = {"id": bundle_id}
    if request.title is not None:
        sets.append("title = :title")
        params["title"] = request.title
    if request.description is not None:
        sets.append("description = :description")
        params["description"] = request.description
    if request.status is not None:
        sets.append("status = :status")
        params["status"] = request.status

    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets.append("updated_at = CURRENT_TIMESTAMP")
    await _db.execute(
        f"UPDATE arkham_bundle.bundles SET {', '.join(sets)} WHERE id = :id",
        params,
    )

    if _event_bus:
        await _event_bus.emit("bundle.bundle.updated", {"bundle_id": bundle_id}, source="bundle-shard")

    return {"bundle_id": bundle_id, "status": "updated"}


@router.delete("/bundles/{bundle_id}")
async def delete_bundle(bundle_id: str):
    """Delete a bundle."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    await _db.execute("DELETE FROM arkham_bundle.bundles WHERE id = :id", {"id": bundle_id})

    if _event_bus:
        await _event_bus.emit("bundle.bundle.deleted", {"bundle_id": bundle_id}, source="bundle-shard")

    return {"status": "deleted", "bundle_id": bundle_id}


# --- Compilation Endpoints ---


@router.post("/bundles/{bundle_id}/compile")
async def compile_bundle(bundle_id: str, request: CompileRequest):
    """
    Core bundle compilation logic.

    Assigns page numbers, generates index, and snapshots version.
    """
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    # 1. Fetch Bundle
    bundle_row = await _db.fetch_one("SELECT * FROM arkham_bundle.bundles WHERE id = :id", {"id": bundle_id})
    if not bundle_row:
        raise HTTPException(status_code=404, detail="Bundle not found")

    # 2. Assign Version
    version_id = str(uuid.uuid4())
    version_number = bundle_row["version"] + 1

    # 3. Compile Pages
    current_page = 1
    pages_to_insert = []
    index_entries = []

    for pos, doc_id in enumerate(request.document_ids):
        # Handle section header injection
        if str(pos) in request.section_headers:
            index_entries.append(
                BundleIndexEntry(
                    entry_type=IndexEntryType.SECTION_HEADER,
                    position=len(index_entries),
                    header_text=request.section_headers[str(pos)],
                )
            )

        # Get overrides
        override = request.document_overrides.get(doc_id, {})
        page_count = override.get("page_count", 1)
        status = override.get("status", "unknown")

        page_start = current_page
        page_end = current_page + page_count - 1
        current_page = page_end + 1

        page_id = str(uuid.uuid4())
        pages_to_insert.append(
            {
                "id": page_id,
                "bundle_id": bundle_id,
                "version_id": version_id,
                "document_id": doc_id,
                "document_title": override.get("title", f"Document {doc_id[:8]}"),
                "document_filename": override.get("filename", ""),
                "position": pos,
                "document_page_count": page_count,
                "bundle_page_start": page_start,
                "bundle_page_end": page_end,
                "document_status": status,
                "section_label": override.get("section_label", ""),
                "notes": override.get("notes", ""),
            }
        )

        index_entries.append(
            BundleIndexEntry(
                entry_type=IndexEntryType.DOCUMENT,
                position=len(index_entries),
                document_id=doc_id,
                document_title=override.get("title", f"Document {doc_id[:8]}"),
                document_filename=override.get("filename", ""),
                bundle_page_start=page_start,
                bundle_page_end=page_end,
                document_status=DocumentStatus(status),
                section_label=override.get("section_label", ""),
                notes=override.get("notes", ""),
            )
        )

    # 4. Generate Index
    index_id = str(uuid.uuid4())
    bundle_index = BundleIndex(
        id=index_id,
        bundle_id=bundle_id,
        version_id=version_id,
        entries=index_entries,
        document_count=len(request.document_ids),
        total_pages=current_page - 1,
    )

    # 5. Persist Everything (Transaction recommended)
    async with _db.transaction():
        # Insert Version
        await _db.execute(
            """
            INSERT INTO arkham_bundle.versions
            (id, bundle_id, version_number, total_pages, document_count, change_notes, index_id, compiled_by)
            VALUES (:id, :bundle_id, :vnum, :pages, :docs, :notes, :index_id, :by)
            """,
            {
                "id": version_id,
                "bundle_id": bundle_id,
                "vnum": version_number,
                "pages": bundle_index.total_pages,
                "docs": bundle_index.document_count,
                "notes": request.change_notes,
                "index_id": index_id,
                "by": request.compiled_by,
            },
        )

        # Insert Pages
        for p in pages_to_insert:
            await _db.execute(
                """
                INSERT INTO arkham_bundle.pages
                (id, bundle_id, version_id, document_id, document_title, document_filename,
                 position, document_page_count, bundle_page_start, bundle_page_end,
                 document_status, section_label, notes)
                VALUES
                (:id, :bundle_id, :version_id, :document_id, :document_title, :document_filename,
                 :position, :document_page_count, :bundle_page_start, :bundle_page_end,
                 :document_status, :section_label, :notes)
                """,
                p,
            )

        # Insert Index
        await _db.execute(
            """
            INSERT INTO arkham_bundle.indices
            (id, bundle_id, version_id, entries, document_count, total_pages)
            VALUES (:id, :bundle_id, :version_id, :entries, :docs, :pages)
            """,
            {
                "id": index_id,
                "bundle_id": bundle_id,
                "version_id": version_id,
                "entries": json.dumps(bundle_index.to_dict()["entries"]),
                "docs": bundle_index.document_count,
                "pages": bundle_index.total_pages,
            },
        )

        # Update Bundle
        await _db.execute(
            """
            UPDATE arkham_bundle.bundles SET
                version = :vnum,
                total_pages = :pages,
                current_version_id = :vid,
                status = 'compiled',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """,
            {"id": bundle_id, "vnum": version_number, "pages": bundle_index.total_pages, "vid": version_id},
        )

    if _event_bus:
        await _event_bus.emit(
            "bundle.bundle.compiled",
            {"bundle_id": bundle_id, "version_id": version_id, "pages": bundle_index.total_pages},
            source="bundle-shard",
        )

    return {
        "status": "compiled",
        "bundle_id": bundle_id,
        "version_id": version_id,
        "version_number": version_number,
        "total_pages": bundle_index.total_pages,
        "index": bundle_index.to_dict(),
    }


# --- Domain Endpoints (via BundleCompiler) ---


@router.post("/{bundle_id}/compile")
async def compile_bundle_via_compiler(bundle_id: str):
    """Compile bundle using the BundleCompiler (from existing pages)."""
    if not _compiler:
        raise HTTPException(status_code=503, detail="Compiler not initialized")

    try:
        result = await _compiler.compile(bundle_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{bundle_id}/documents/add")
async def add_document_to_bundle(bundle_id: str, request: AddDocumentRequest):
    """Add a document to the bundle at the specified position."""
    if not _compiler:
        raise HTTPException(status_code=503, detail="Compiler not initialized")

    try:
        result = await _compiler.add_document(
            bundle_id=bundle_id,
            document_id=request.document_id,
            position=request.position,
            title=request.title,
            filename=request.filename,
            page_count=request.page_count,
            status=request.status,
            section_label=request.section_label,
            notes=request.notes,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{bundle_id}/documents/{doc_id}")
async def remove_document_from_bundle(bundle_id: str, doc_id: str):
    """Remove a document from the bundle and renumber pages."""
    if not _compiler:
        raise HTTPException(status_code=503, detail="Compiler not initialized")

    try:
        await _compiler.remove_document(bundle_id=bundle_id, document_id=doc_id)
        return {"status": "removed", "bundle_id": bundle_id, "document_id": doc_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{bundle_id}/index")
async def get_bundle_index(bundle_id: str):
    """Get the current index for a bundle."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    bundle_row = await _db.fetch_one(
        "SELECT * FROM arkham_bundle.bundles WHERE id = :id",
        {"id": bundle_id},
    )
    if not bundle_row:
        raise HTTPException(status_code=404, detail="Bundle not found")

    version_id = bundle_row.get("current_version_id", "")
    if not version_id:
        raise HTTPException(status_code=404, detail="Bundle has no compiled version")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_bundle.indices WHERE bundle_id = :bundle_id AND version_id = :version_id",
        {"bundle_id": bundle_id, "version_id": version_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Index not found for current version")

    return dict(row)


@router.get("/{bundle_id}/index/text")
async def get_bundle_index_text(bundle_id: str):
    """Export the bundle index as formatted text (ET Presidential Guidance format)."""
    if not _compiler:
        raise HTTPException(status_code=503, detail="Compiler not initialized")

    try:
        text = await _compiler.export_index_text(bundle_id)
        return {"bundle_id": bundle_id, "text": text}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{bundle_id}/versions")
async def get_bundle_versions(bundle_id: str):
    """List all compiled versions of a bundle."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_bundle.versions WHERE bundle_id = :id ORDER BY version_number DESC",
        {"id": bundle_id},
    )
    return {"bundle_id": bundle_id, "versions": [dict(r) for r in rows]}


@router.get("/{bundle_id}/versions/compare")
async def compare_bundle_versions(
    bundle_id: str,
    version_a: str = Query(..., description="First version ID"),
    version_b: str = Query(..., description="Second version ID"),
):
    """Compare two bundle versions: added/removed/reordered docs, page count diff."""
    if not _compiler:
        raise HTTPException(status_code=503, detail="Compiler not initialized")

    result = await _compiler.compare_versions(version_a, version_b)
    return {"bundle_id": bundle_id, **result}


@router.post("/{bundle_id}/suggest-order")
async def suggest_document_order(bundle_id: str, request: SuggestOrderRequest):
    """LLM: suggest optimal document ordering per ET Presidential Guidance."""
    if not _llm_integration:
        raise HTTPException(status_code=503, detail="LLM integration not initialized")

    if not _llm_integration.is_available:
        raise HTTPException(status_code=503, detail="LLM service not available")

    result = await _llm_integration.suggest_ordering(request.documents)
    return {
        "bundle_id": bundle_id,
        "sections": [
            {"section": s.section, "document_ids": s.document_ids, "reasoning": s.reasoning} for s in result.sections
        ],
        "ordered_document_ids": result.ordered_document_ids,
        "reasoning": result.reasoning,
    }


# --- Legacy endpoints (kept for backwards compat with existing tests) ---


@router.get("/bundles/{bundle_id}/versions")
async def list_versions(bundle_id: str):
    """List all compiled versions of a bundle."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_bundle.versions WHERE bundle_id = :id ORDER BY version_number DESC",
        {"id": bundle_id},
    )
    return {"bundle_id": bundle_id, "versions": [dict(r) for r in rows]}


@router.get("/versions/{version_id}/pages")
async def get_version_pages(version_id: str):
    """Get the paginated document list for a specific bundle version."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_bundle.pages WHERE version_id = :id ORDER BY position ASC",
        {"id": version_id},
    )
    return {"version_id": version_id, "pages": [dict(r) for r in rows]}


@router.get("/versions/{version_id}/index")
async def get_version_index(version_id: str):
    """Get the generated index for a specific bundle version."""
    if not _db:
        raise HTTPException(status_code=503, detail="Bundle service not initialized")

    row = await _db.fetch_one(
        "SELECT * FROM arkham_bundle.indices WHERE version_id = :id",
        {"id": version_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Index not found for this version")

    return dict(row)


@router.get("/items/count")
async def count_items():
    """Return count for badge display."""
    if not _db:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await _db.fetch_one("SELECT COUNT(*) as count FROM arkham_bundle.bundles")
    return {"count": result["count"] if result else 0}
