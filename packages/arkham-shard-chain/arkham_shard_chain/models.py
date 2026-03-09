"""Data models for the Chain Shard - cryptographic evidence chain of custody."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class CustodyAction(str, Enum):
    """Actions that can occur in a document's custody chain."""

    RECEIVED = "received"
    STORED = "stored"
    ACCESSED = "accessed"
    TRANSFORMED = "transformed"
    EXPORTED = "exported"
    VERIFIED = "verified"


@dataclass
class EvidenceHash:
    """SHA-256 hash record for a document at a point in time."""

    id: str
    tenant_id: Optional[str]
    document_id: str
    sha256_hash: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CustodyEvent:
    """A single event in a document's chain of custody."""

    id: str
    tenant_id: Optional[str]
    document_id: str
    action: CustodyAction
    actor: str
    location: str
    timestamp: datetime
    previous_event_id: Optional[str]
    hash_verified: bool
    created_at: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""


@dataclass
class ProvenanceReport:
    """A generated provenance/chain-of-custody report for a document."""

    id: str
    tenant_id: Optional[str]
    document_id: str
    report_json: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
