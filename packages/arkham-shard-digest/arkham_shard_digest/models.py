"""Data models for the Digest Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CaseBriefing(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    project_id: str
    type: str  # daily, weekly, sitrep
    content: str
    priority_items: List[Dict[str, Any]] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChangeLogEntry(BaseModel):
    id: str
    project_id: str
    shard: str
    entity_type: str
    entity_id: str
    action: str
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DigestSubscription(BaseModel):
    id: str
    project_id: str
    user_id: str
    frequency: str  # daily, weekly
    format: str  # text, markdown, email
    last_sent: Optional[datetime] = None
