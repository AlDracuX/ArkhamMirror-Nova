"""Comms Shard API endpoints."""

import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .shard import CommsShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "CommsShard":
    """Get the Comms shard instance from app state."""
    shard = getattr(request.app.state, "comms_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Comms shard not available")
    return shard


router = APIRouter(prefix="/api/comms", tags=["comms"])

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


class ThreadCreate(BaseModel):
    subject: str
    description: str = ""
    project_id: Optional[str] = None
    created_by: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCreate(BaseModel):
    thread_id: str
    subject: str = ""
    body_summary: str = ""
    sent_at: Optional[datetime] = None
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    cc_addresses: list[str] = Field(default_factory=list)
    bcc_addresses: list[str] = Field(default_factory=list)
    source_document_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Threads Endpoints ---


@router.get("/threads")
async def list_threads(project_id: Optional[str] = None):
    """List threads with optional project filter."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    query = "SELECT * FROM arkham_comms.threads WHERE 1=1"
    params = {}
    if project_id:
        query += " AND project_id = :project_id"
        params["project_id"] = project_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/threads")
async def create_thread(request: ThreadCreate):
    """Create a new communication thread."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    thread_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_comms.threads
        (id, tenant_id, subject, description, project_id, metadata, created_by)
        VALUES (:id, :tenant_id, :subject, :description, :project_id, :metadata, :created_by)
        """,
        {
            "id": thread_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "subject": request.subject,
            "description": request.description,
            "project_id": request.project_id,
            "metadata": json.dumps(request.metadata),
            "created_by": request.created_by,
        },
    )

    if _event_bus:
        await _event_bus.emit(
            "comms.thread.created",
            {"thread_id": thread_id, "subject": request.subject},
            source="comms-shard",
        )

    return {"id": thread_id, "status": "created"}


# --- Messages Endpoints ---


@router.get("/messages")
async def list_messages(thread_id: Optional[str] = None):
    """List messages with optional thread filter."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    query = "SELECT * FROM arkham_comms.messages WHERE 1=1"
    params = {}
    if thread_id:
        query += " AND thread_id = :thread_id"
        params["thread_id"] = thread_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.post("/messages")
async def create_message(request: MessageCreate):
    """Create a new message in a thread."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    message_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_comms.messages
        (id, thread_id, tenant_id, subject, body_summary, sent_at, from_address, to_addresses, cc_addresses, bcc_addresses, source_document_id, metadata)
        VALUES (:id, :thread_id, :tenant_id, :subject, :body_summary, :sent_at, :from_address, :to_addresses, :cc_addresses, :bcc_addresses, :source_document_id, :metadata)
        """,
        {
            "id": message_id,
            "thread_id": request.thread_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "subject": request.subject,
            "body_summary": request.body_summary,
            "sent_at": request.sent_at,
            "from_address": request.from_address,
            "to_addresses": json.dumps(request.to_addresses),
            "cc_addresses": json.dumps(request.cc_addresses),
            "bcc_addresses": json.dumps(request.bcc_addresses),
            "source_document_id": request.source_document_id,
            "metadata": json.dumps(request.metadata),
        },
    )

    return {"id": message_id, "status": "created"}


# --- Participants Endpoints ---


@router.get("/participants")
async def list_participants():
    """List all communication participants."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    rows = await _db.fetch_all("SELECT * FROM arkham_comms.participants")
    return [dict(row) for row in rows]


# --- Gaps & Coordination Endpoints ---


@router.get("/gaps")
async def list_gaps(thread_id: Optional[str] = None):
    """List communication gaps."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    query = "SELECT * FROM arkham_comms.gaps WHERE 1=1"
    params = {}
    if thread_id:
        query += " AND thread_id = :thread_id"
        params["thread_id"] = thread_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]


@router.get("/coordination-flags")
async def list_coordination_flags(thread_id: Optional[str] = None):
    """List coordination flags."""
    if not _db:
        raise HTTPException(status_code=503, detail="Comms service not initialized")

    query = "SELECT * FROM arkham_comms.coordination_flags WHERE 1=1"
    params = {}
    if thread_id:
        query += " AND thread_id = :thread_id"
        params["thread_id"] = thread_id

    rows = await _db.fetch_all(query, params)
    return [dict(row) for row in rows]
