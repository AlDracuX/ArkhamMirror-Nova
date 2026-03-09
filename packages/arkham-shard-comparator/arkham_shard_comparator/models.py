"""Data models for the Comparator Shard.

Equality Act s.13/s.26 treatment comparison matrix.
Tracks claimant vs comparator treatment per incident.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class SignificanceLevel(str, Enum):
    """Significance level for divergences."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TreatmentOutcome(str, Enum):
    """Outcome classification for a treatment record."""

    FAVOURABLE = "favourable"
    UNFAVOURABLE = "unfavourable"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class DiscriminationElement(str, Enum):
    """s.13 Direct Discrimination legal elements."""

    PROTECTED_CHARACTERISTIC = "protected_characteristic"
    LESS_FAVOURABLE_TREATMENT = "less_favourable_treatment"
    COMPARATIVE_SITUATION = "comparative_situation"
    CAUSATION_REASON_WHY = "causation_reason_why"


class HarassmentElement(str, Enum):
    """s.26 Harassment legal elements."""

    UNWANTED_CONDUCT = "unwanted_conduct"
    RELATED_TO_CHARACTERISTIC = "related_to_characteristic"
    PURPOSE_OR_EFFECT = "purpose_or_effect"
    VIOLATING_DIGNITY = "violating_dignity"
    INTIMIDATING_ENVIRONMENT = "intimidating_environment"


@dataclass
class Comparator:
    """A named comparator (actual or hypothetical) for discrimination analysis.

    Represents a colleague or hypothetical person used as a reference point
    for direct discrimination claims under s.13 Equality Act 2010.
    """

    id: str
    tenant_id: Optional[str] = None
    name: str = ""
    characteristic: str = ""  # e.g., race, sex, disability, age
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Incident:
    """A workplace incident or situation where differential treatment may have occurred.

    Captures a discrete event or policy application that can be compared
    across the claimant and named comparators.
    """

    id: str
    tenant_id: Optional[str] = None
    date: Optional[datetime] = None
    description: str = ""
    project_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Treatment:
    """How a specific subject (claimant or comparator) was treated in an incident.

    subject_id is either the literal string 'claimant' (for the claimant)
    or a comparator UUID (for a named comparator).
    """

    id: str
    tenant_id: Optional[str] = None
    incident_id: str = ""
    subject_id: str = ""  # 'claimant' or comparator UUID
    treatment_description: str = ""
    outcome: TreatmentOutcome = TreatmentOutcome.UNKNOWN
    evidence_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Divergence:
    """A recorded divergence in treatment between claimant and a comparator.

    Represents a finding of less favourable treatment relevant to
    s.13 direct discrimination or s.26 harassment claims.
    """

    id: str
    tenant_id: Optional[str] = None
    incident_id: str = ""
    description: str = ""
    significance_score: float = 0.0  # 0.0 - 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
