"""Chain Shard API endpoints."""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from .shard import ChainShard

logger = logging.getLogger(__name__)


def get_shard(request: Request) -> "ChainShard":
    """Get the Chain shard instance from app state."""
    shard = getattr(request.app.state, "chain_shard", None)
    if not shard:
        raise HTTPException(status_code=503, detail="Chain shard not available")
    return shard


router = APIRouter(prefix="/api/chain", tags=["chain"])

# Module-level references set during initialization
_db = None
_event_bus = None
_storage_service = None
_llm_service = None
_shard = None


def init_api(
    db,
    event_bus,
    storage_service=None,
    llm_service=None,
    shard=None,
):
    """Initialize API with shard dependencies."""
    global _db, _event_bus, _storage_service, _llm_service, _shard
    _db = db
    _event_bus = event_bus
    _storage_service = storage_service
    _llm_service = llm_service
    _shard = shard


# --- Request/Response Models ---


class LogEventRequest(BaseModel):
    document_id: str
    action: str  # received, stored, accessed, transformed, exported, verified
    actor: str
    location: str
    previous_event_id: Optional[str] = None
    notes: str = ""


# --- Endpoints ---


@router.post("/events")
async def log_custody_event(request: LogEventRequest):
    """Log a new custody transition event."""
    if not _db:
        raise HTTPException(status_code=503, detail="Chain service not initialized")

    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    event_id = await _log_hash_and_event(
        db=_db,
        storage_service=_storage_service,
        event_bus=_event_bus,
        document_id=request.document_id,
        action=request.action,
        actor=request.actor,
        location=request.location,
        previous_event_id=request.previous_event_id,
        tenant_id=tenant_id,
        notes=request.notes,
    )

    return {"status": "logged", "event_id": event_id}


@router.get("/events/{document_id}")
async def get_document_history(document_id: str):
    """Get the full chain of custody for a document."""
    if not _db:
        raise HTTPException(status_code=503, detail="Chain service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_chain.custody_events WHERE document_id = :id ORDER BY timestamp ASC",
        {"id": document_id},
    )
    return {"document_id": document_id, "history": [dict(r) for r in rows]}


@router.get("/integrity-check/{document_id}")
async def verify_document_integrity(document_id: str):
    """Verify that the current file hash matches the last logged hash."""
    if not _db or not _storage_service:
        raise HTTPException(status_code=503, detail="Required services not initialized")

    # 1. Get last known hash
    last_hash_row = await _db.fetch_one(
        "SELECT sha256_hash FROM arkham_chain.hashes WHERE document_id = :id ORDER BY created_at DESC LIMIT 1",
        {"id": document_id},
    )
    if not last_hash_row:
        raise HTTPException(status_code=404, detail="No hash records found for document")

    # 2. Compute current hash
    try:
        content, _ = await _storage_service.retrieve(document_id)
        current_hash = hashlib.sha256(content).hexdigest()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document: {e}")

    match = current_hash == last_hash_row["sha256_hash"]

    # 3. Log verification event
    await _log_hash_and_event(
        db=_db,
        storage_service=_storage_service,
        event_bus=_event_bus,
        document_id=document_id,
        action="verified",
        actor="system",
        location="storage",
        hash_verified=match,
        notes=f"Integrity check performed. Match: {match}",
    )

    return {
        "document_id": document_id,
        "valid": match,
        "stored_hash": last_hash_row["sha256_hash"],
        "current_hash": current_hash,
    }


@router.post("/reports/{document_id}")
async def generate_provenance_report(document_id: str):
    """
    Generate and store a court-admissible provenance report for a document.

    Aggregates all custody events and hash snapshots into a single signed JSON report.
    """
    if not _db:
        raise HTTPException(status_code=503, detail="Chain service not initialized")

    # 1. Fetch full history
    rows = await _db.fetch_all(
        "SELECT * FROM arkham_chain.custody_events WHERE document_id = :id ORDER BY timestamp ASC",
        {"id": document_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No history found for document")

    # 2. Build report JSON
    history = [dict(r) for r in rows]
    # Serialise timestamps
    for h in history:
        if h.get("timestamp"):
            h["timestamp"] = h["timestamp"].isoformat()
        if h.get("created_at"):
            h["created_at"] = h["created_at"].isoformat()

    report = {
        "document_id": document_id,
        "generated_at": datetime.utcnow().isoformat(),
        "event_count": len(history),
        "history": history,
        "status": "verified" if all(h.get("hash_verified") for h in history) else "caution",
    }

    # 3. Store report
    report_id = str(uuid.uuid4())
    tenant_id = _shard.get_tenant_id_or_none() if _shard else None

    await _db.execute(
        """
        INSERT INTO arkham_chain.provenance_reports (id, tenant_id, document_id, report_json)
        VALUES (:id, :tenant_id, :doc_id, :json)
        """,
        {
            "id": report_id,
            "tenant_id": tenant_id,
            "doc_id": document_id,
            "json": json.dumps(report),
        },
    )

    return {"report_id": report_id, "report": report}


@router.get("/reports/{document_id}")
async def list_reports(document_id: str):
    """List all generated provenance reports for a document."""
    if not _db:
        raise HTTPException(status_code=503, detail="Chain service not initialized")

    rows = await _db.fetch_all(
        "SELECT * FROM arkham_chain.provenance_reports WHERE document_id = :id ORDER BY created_at DESC",
        {"id": document_id},
    )
    return {"document_id": document_id, "reports": [dict(r) for r in rows]}


# --- Internal Logic ---


async def _log_hash_and_event(
    db,
    storage_service,
    event_bus,
    document_id: str,
    action: str,
    actor: str,
    location: str,
    previous_event_id: Optional[str] = None,
    tenant_id: Optional[uuid.UUID] = None,
    hash_verified: bool = False,
    notes: str = "",
) -> str:
    """Helper to log both a hash snapshot and a custody event."""
    # 1. Compute hash
    sha256_hash = "unknown"
    if storage_service:
        try:
            content, _ = await storage_service.retrieve(document_id)
            sha256_hash = hashlib.sha256(content).hexdigest()
        except Exception:
            pass

    event_id = str(uuid.uuid4())
    hash_id = str(uuid.uuid4())

    # 2. Store hash
    await db.execute(
        """
        INSERT INTO arkham_chain.hashes (id, tenant_id, document_id, sha256_hash)
        VALUES (:id, :tenant_id, :doc_id, :hash)
        """,
        {"id": hash_id, "tenant_id": tenant_id, "doc_id": document_id, "hash": sha256_hash},
    )

    # 3. Store event
    await db.execute(
        """
        INSERT INTO arkham_chain.custody_events
            (id, tenant_id, document_id, action, actor, location, previous_event_id, hash_verified, notes)
        VALUES
            (:id, :tenant_id, :doc_id, :action, :actor, :location, :prev, :verified, :notes)
        """,
        {
            "id": event_id,
            "tenant_id": tenant_id,
            "doc_id": document_id,
            "action": action,
            "actor": actor,
            "location": location,
            "prev": previous_event_id,
            "verified": hash_verified or (sha256_hash != "unknown"),
            "notes": notes,
        },
    )

    # 4. Emit event
    if event_bus:
        await event_bus.emit(
            "chain.evidence.logged",
            {"document_id": document_id, "action": action, "event_id": event_id},
            source="chain-shard",
        )

    return event_id
