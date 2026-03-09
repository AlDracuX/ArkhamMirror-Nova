"""Data models for the RespondentIntel Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RespondentProfile(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    name: str
    type: str  # individual, corporate
    corporate_structure: Dict[str, Any] = Field(default_factory=dict)
    key_personnel: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RespondentConnection(BaseModel):
    id: str
    source_respondent_id: str
    target_respondent_id: str
    relationship_type: str
    description: Optional[str] = None
    strength: float


class PublicRecord(BaseModel):
    id: str
    respondent_id: str
    record_type: str  # companies_house, news, filing
    title: str
    url: Optional[str] = None
    summary: str
    date: datetime


class RespondentVulnerability(BaseModel):
    id: str
    respondent_id: str
    category: str
    description: str
    severity: str  # low, medium, high, critical
    evidence_ids: List[str] = Field(default_factory=list)
