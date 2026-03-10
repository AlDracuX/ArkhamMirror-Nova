"""Data models for the Playbook Shard."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

VALID_STATUSES = {"draft", "active", "executed", "archived"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}


class Play(BaseModel):
    id: str
    case_id: Optional[str] = None
    name: str
    scenario: str = ""
    description: str = ""
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    expected_outcomes: List[Dict[str, Any]] = Field(default_factory=list)
    contingencies: List[Dict[str, Any]] = Field(default_factory=list)
    priority: str = "medium"
    status: str = "draft"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SimulationResult(BaseModel):
    play_id: str
    scenario: str
    steps: List[Dict[str, Any]]
    risk_assessment: str
    estimated_outcomes: List[Dict[str, Any]]
