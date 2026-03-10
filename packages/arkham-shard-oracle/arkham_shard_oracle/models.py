"""Data models for the Oracle Shard."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AuthorityType(str, Enum):
    """Valid authority types."""

    case_law = "case_law"
    statute = "statute"
    regulation = "regulation"
    guidance = "guidance"
    commentary = "commentary"


class LegalAuthority(BaseModel):
    """A legal authority record."""

    id: UUID
    citation: str
    jurisdiction: str
    court: Optional[str] = None
    title: str
    year: Optional[int] = None
    summary: Optional[str] = None
    full_text: Optional[str] = None
    relevance_tags: List[str] = Field(default_factory=list)
    claim_types: List[str] = Field(default_factory=list)
    authority_type: AuthorityType = AuthorityType.case_law
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuthorityCreate(BaseModel):
    """Request model for creating an authority."""

    citation: str
    jurisdiction: str
    court: Optional[str] = None
    title: str
    year: Optional[int] = None
    summary: Optional[str] = None
    full_text: Optional[str] = None
    relevance_tags: List[str] = Field(default_factory=list)
    claim_types: List[str] = Field(default_factory=list)
    authority_type: AuthorityType = AuthorityType.case_law


class AuthorityUpdate(BaseModel):
    """Request model for updating an authority."""

    citation: Optional[str] = None
    jurisdiction: Optional[str] = None
    court: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    summary: Optional[str] = None
    full_text: Optional[str] = None
    relevance_tags: Optional[List[str]] = None
    claim_types: Optional[List[str]] = None
    authority_type: Optional[AuthorityType] = None


class AuthoritySearchRequest(BaseModel):
    """Request model for searching authorities."""

    query: str
    jurisdiction: Optional[str] = None
    claim_types: Optional[List[str]] = None


class RelevanceRequest(BaseModel):
    """Request model for scoring authority relevance."""

    authority_id: str
    case_facts: str


class ResearchRequest(BaseModel):
    """Request model for comprehensive legal research."""

    query: str
    context: Optional[str] = None


# Keep legacy models for backward compat with existing research_sessions table
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
    relationship_type: str
