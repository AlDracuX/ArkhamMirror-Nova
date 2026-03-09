"""Data models for the Oracle Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LegalAuthority(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    title: str
    citation: str
    type: str  # statute, case_law, regulation
    jurisdiction: str
    binding_status: str  # binding, persuasive
    summary: str
    ratio_decidendi: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchSession(BaseModel):
    id: str
    project_id: str
    query: str
    findings: List[str] = Field(default_factory=list)
    authority_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CaseSummary(BaseModel):
    id: str
    authority_id: str
    facts: str
    decision: str
    legal_principles: List[str] = Field(default_factory=list)


class AuthorityChain(BaseModel):
    id: str
    source_authority_id: str
    cited_authority_id: str
    relationship_type: str  # follows, distinguishes, overrules, etc.
