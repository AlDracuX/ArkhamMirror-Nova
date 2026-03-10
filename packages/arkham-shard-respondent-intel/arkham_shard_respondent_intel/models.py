"""Data models for the RespondentIntel Shard."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RespondentProfile(BaseModel):
    """A respondent profile for litigation intelligence."""

    id: str
    case_id: str
    name: str
    role: str
    organization: str
    title: Optional[str] = None
    background: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    known_positions: List[str] = Field(default_factory=list)
    credibility_notes: Optional[str] = None
    document_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
