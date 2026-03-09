"""Data models for the AuditTrail Shard."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ActionType(str, Enum):
    """Type of audited action."""

    # Document operations
    DOCUMENT_INGEST = "document.ingest"
    DOCUMENT_VIEW = "document.view"
    DOCUMENT_EDIT = "document.edit"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_EXPORT = "document.export"

    # Search operations
    SEARCH_QUERY = "search.query"
    SEARCH_SEMANTIC = "search.semantic"
    SEARCH_HYBRID = "search.hybrid"

    # Analysis operations
    ANALYSIS_ACH = "analysis.ach"
    ANALYSIS_CLAIM = "analysis.claim"
    ANALYSIS_PATTERN = "analysis.pattern"
    ANALYSIS_ANOMALY = "analysis.anomaly"
    ANALYSIS_CONTRADICTION = "analysis.contradiction"
    ANALYSIS_TIMELINE = "analysis.timeline"
    ANALYSIS_GRAPH = "analysis.graph"

    # Auth operations
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILED = "auth.failed"

    # Export operations
    EXPORT_CREATED = "export.created"
    EXPORT_DOWNLOADED = "export.downloaded"

    # System events (caught from EventBus)
    SYSTEM_EVENT = "system.event"

    # Generic fallback
    UNKNOWN = "unknown"


@dataclass
class AuditAction:
    """
    An immutable audit log entry recording a platform action.

    Append-only — never updated or deleted after insertion.
    """

    id: str
    tenant_id: str | None
    user_id: str | None
    action_type: str
    shard: str
    entity_id: str | None
    description: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "shard": self.shard,
            "entity_id": self.entity_id,
            "description": self.description,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class AuditSession:
    """
    A user session record for the audit trail.

    Tracks login periods, IP addresses, and user agents.
    """

    id: str
    tenant_id: str | None
    user_id: str | None
    start_time: datetime
    end_time: datetime | None
    ip_address: str | None
    user_agent: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


@dataclass
class AuditExport:
    """
    A record of an audit trail export (for forensic trail documentation).

    Tracks who exported the audit log, when, and what range was exported.
    """

    id: str
    tenant_id: str | None
    user_id: str | None
    export_format: str
    filters_applied: dict[str, Any]
    row_count: int
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "export_format": self.export_format,
            "filters_applied": self.filters_applied,
            "row_count": self.row_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
