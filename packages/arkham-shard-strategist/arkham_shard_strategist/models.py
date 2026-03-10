"""Data models for the Strategist Shard."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TacticalModel(BaseModel):
    id: str
    project_id: str
    respondent_id: str
    likely_tactics: List[str] = Field(default_factory=list)
    counter_measures: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Strategy(BaseModel):
    """A litigation strategy with SWOT analysis fields."""

    id: str
    case_id: str
    name: str
    approach: str
    summary: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    recommended: bool = False
    confidence_score: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        return v
