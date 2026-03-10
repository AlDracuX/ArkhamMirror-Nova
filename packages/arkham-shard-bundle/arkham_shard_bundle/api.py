"""Bundle Shard API endpoints.

CRUD for Bundles, Versions, Pages, and Indices.
Plus the core bundle compilation logic.
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


# --- Endpoints ---


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


# --- Compilation Logic ---


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

    # Fetch document metadata if possible (link to Documents shard would be here)
    # For now, we assume simple mapping provided by caller or default to 1 page
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
