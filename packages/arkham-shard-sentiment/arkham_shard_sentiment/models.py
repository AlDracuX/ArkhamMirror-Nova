"""Data models for the Sentiment Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SentimentAnalysis(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    document_id: Optional[str] = None
    thread_id: Optional[str] = None
    project_id: str
    summary: str
    overall_sentiment: float
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToneScore(BaseModel):
    id: str
    analysis_id: str
    category: str
    score: float
    reasoning: str
    evidence_segments: List[str] = Field(default_factory=list)


class SentimentPattern(BaseModel):
    id: str
    project_id: str
    type: str
    description: str
    significance_score: float
    analysis_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ComparatorDiff(BaseModel):
    id: str
    project_id: str
    claimant_analysis_id: str
    comparator_analysis_id: str
    divergence_score: float
    description: str
    findings: List[str] = Field(default_factory=list)
