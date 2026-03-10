"""Data models for the Redline Shard."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ComparisonStatus:
    """Valid status values for comparisons."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"

    ALL = {PENDING, PROCESSING, COMPLETE, FAILED}


class Comparison(BaseModel):
    """A document comparison record."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: Optional[str] = None
    doc_a_id: str
    doc_b_id: str
    title: str = ""
    status: str = ComparisonStatus.PENDING
    diff_count: int = 0
    additions: int = 0
    deletions: int = 0
    modifications: int = 0
    diffs: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Keep legacy models for backward compat with existing tests until fully migrated
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VersionChain(BaseModel):
    id: str
    project_id: str
    document_ids: List[str]
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentChange(BaseModel):
    id: str
    comparison_id: str
    type: str  # semantic, formatting, structural
    location: str
    before: str
    after: str
    significance: float
    is_silent: bool = False
