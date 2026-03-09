"""Data models for the Playbook Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LitigationStrategy(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    project_id: str
    title: str
    description: str
    status: str
    main_claims: List[str] = Field(default_factory=list)
    fallback_positions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StrategyScenario(BaseModel):
    id: str
    strategy_id: str
    name: str
    description: str
    probability: float
    impact: str
    consequences: List[str] = Field(default_factory=list)


class EvidenceObjective(BaseModel):
    id: str
    project_id: str
    evidence_id: str
    objective_id: str
    relevance_score: float
    notes: Optional[str] = None
