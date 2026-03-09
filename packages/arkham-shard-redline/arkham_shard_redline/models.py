"""Data models for the Redline Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentComparison(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    project_id: str
    base_document_id: str
    target_document_id: str
    diff_summary: str
    change_count: int
    silent_edits: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VersionChain(BaseModel):
    id: str
    project_id: str
    document_ids: List[str]
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentChange(BaseModel):
    id: str
    comparison_id: str
    type: str  # semantic, formatting, structural
    location: str
    before: str
    after: str
    significance: float
    is_silent: bool = False
