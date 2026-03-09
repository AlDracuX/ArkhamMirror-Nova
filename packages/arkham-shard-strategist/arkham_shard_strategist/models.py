"""Data models for the Strategist Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StrategicPrediction(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    project_id: str
    claim_id: Optional[str] = None
    respondent_id: Optional[str] = None
    predicted_argument: str
    confidence: float
    reasoning: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CounterArgument(BaseModel):
    id: str
    prediction_id: str
    argument: str
    rebuttal_strategy: str
    evidence_ids: List[str] = Field(default_factory=list)


class RedTeamReport(BaseModel):
    id: str
    project_id: str
    target_id: str  # document_id or submission_id
    weaknesses: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    overall_risk_score: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TacticalModel(BaseModel):
    id: str
    project_id: str
    respondent_id: str
    likely_tactics: List[str] = Field(default_factory=list)
    counter_measures: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
