"""Data models for the Burden Map Shard.

Burden of proof element tracker with s.136 Equality Act burden shift support.
Traffic-light status: Green (burden met), Amber (borderline), Red (gap).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# === Enums ===


class BurdenHolder(str, Enum):
    """Who holds the burden of proof for this element."""

    CLAIMANT = "claimant"
    RESPONDENT = "respondent"
    SHARED = "shared"
    REVERSE = "reverse"  # s.136 EA 2010 — burden shifts to respondent once prima facie shown


class TrafficLight(str, Enum):
    """Traffic-light status for evidence weight on a claim element."""

    GREEN = "green"  # Burden met — sufficient weight of evidence
    AMBER = "amber"  # Borderline — evidence present but not conclusive
    RED = "red"  # Gap — insufficient or no evidence


class EvidenceWeightValue(str, Enum):
    """Assessed weight of a single piece of evidence."""

    STRONG = "strong"  # Definitively supports/undermines element (score: 3)
    MODERATE = "moderate"  # Reasonably supports/undermines element  (score: 2)
    WEAK = "weak"  # Marginal contribution to element         (score: 1)
    NEUTRAL = "neutral"  # No material contribution                 (score: 0)
    ADVERSE = "adverse"  # Actively harms the burden holder         (score: -2)


class EvidenceSource(str, Enum):
    """Origin of the evidence item."""

    DOCUMENT = "document"  # From ingested document corpus
    CLAIM = "claim"  # From the claims shard
    WITNESS = "witness"  # Witness statement
    CASEMAP = "casemap"  # Theory/element from casemap shard
    EXTERNAL = "external"  # External source or URL
    MANUAL = "manual"  # Analyst-entered note


class ElementStatus(str, Enum):
    """Lifecycle status of a claim element record."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# === Numeric weight map ===

WEIGHT_SCORES: Dict[str, int] = {
    EvidenceWeightValue.STRONG: 3,
    EvidenceWeightValue.MODERATE: 2,
    EvidenceWeightValue.WEAK: 1,
    EvidenceWeightValue.NEUTRAL: 0,
    EvidenceWeightValue.ADVERSE: -2,
}

# Traffic-light thresholds (net score from summed EvidenceWeight rows)
# Net score >= GREEN_THRESHOLD  → GREEN
# Net score >= AMBER_THRESHOLD  → AMBER
# Otherwise                      → RED
GREEN_THRESHOLD = 4
AMBER_THRESHOLD = 1


# === Dataclasses ===


@dataclass
class ClaimElement:
    """
    A single element (sub-issue) that must be established for a legal claim.

    Maps to a row in arkham_burden_map.claim_elements.

    Links to the casemap shard via theory_id / element_id, and optionally
    to a claims shard claim via linked_claim_id.

    For s.136 EA 2010 discrimination claims the burden is REVERSE — the
    claimant must establish a prima facie case, then the burden shifts to
    the respondent to prove non-discrimination.
    """

    id: str
    title: str
    claim_type: str  # e.g. "discrimination", "unfair_dismissal"
    statutory_reference: str = ""  # e.g. "EA 2010 s.136"
    description: str = ""
    burden_holder: BurdenHolder = BurdenHolder.CLAIMANT
    required: bool = True  # Optional elements do not gate overall status
    display_order: int = 0

    # Cross-shard linkage (EventBus — no direct import)
    theory_id: Optional[str] = None  # casemap.legal_theories.id
    casemap_element_id: Optional[str] = None  # casemap.legal_elements.id
    linked_claim_id: Optional[str] = None  # claims.claims.id

    # s.136 EA 2010 reverse burden tracking
    prima_facie_established: bool = False  # Claimant's initial hurdle cleared
    burden_shifted: bool = False  # True once prima facie shown & shift triggered

    project_id: Optional[str] = None
    status: ElementStatus = ElementStatus.ACTIVE
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class EvidenceWeight:
    """
    A single piece of evidence assessed against a ClaimElement.

    Maps to a row in arkham_burden_map.evidence_weights.

    The net score across all EvidenceWeight rows for an element drives
    the traffic-light calculation for that element's BurdenAssignment.
    """

    id: str
    element_id: str  # FK → claim_elements.id
    weight: EvidenceWeightValue = EvidenceWeightValue.NEUTRAL
    source_type: EvidenceSource = EvidenceSource.DOCUMENT
    source_id: Optional[str] = None  # ID in the originating shard / table
    source_title: Optional[str] = None  # Display label
    excerpt: Optional[str] = None  # Relevant excerpt or quote
    supports_burden_holder: bool = True  # False = evidence favours opposing party
    analyst_notes: str = ""
    added_by: str = "system"
    added_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def numeric_score(self) -> int:
        """Return signed numeric score for this weight entry."""
        raw = WEIGHT_SCORES.get(self.weight, 0)
        return raw if self.supports_burden_holder else -abs(raw)


@dataclass
class BurdenAssignment:
    """
    Computed burden status for a ClaimElement — the traffic-light output.

    Maps to a row in arkham_burden_map.burden_assignments.

    Recalculated whenever EvidenceWeight rows are added/updated, or when
    casemap.theory.updated / claims.status.changed events are received.
    """

    id: str
    element_id: str  # FK → claim_elements.id
    traffic_light: TrafficLight = TrafficLight.RED
    net_score: int = 0  # Sum of numeric_score across all EvidenceWeight rows
    supporting_count: int = 0  # Evidence items that support burden holder
    adverse_count: int = 0  # Evidence items adverse to burden holder
    gap_summary: str = ""  # Human-readable gap description
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


# === Calculation helpers ===


def calculate_traffic_light(net_score: int) -> TrafficLight:
    """
    Convert a net evidence score to a traffic-light status.

    Thresholds:
      net_score >= GREEN_THRESHOLD (4)  → GREEN  (burden met)
      net_score >= AMBER_THRESHOLD (1)  → AMBER  (borderline)
      otherwise                          → RED    (gap)
    """
    if net_score >= GREEN_THRESHOLD:
        return TrafficLight.GREEN
    if net_score >= AMBER_THRESHOLD:
        return TrafficLight.AMBER
    return TrafficLight.RED


def calculate_net_score(weights: List[EvidenceWeight]) -> int:
    """Sum all numeric scores for a set of EvidenceWeight records."""
    return sum(w.numeric_score for w in weights)


def compute_burden_assignment(
    element_id: str,
    assignment_id: str,
    weights: List[EvidenceWeight],
) -> BurdenAssignment:
    """
    Build a BurdenAssignment from a list of EvidenceWeight records.

    Called both in-process (after DB writes) and from event handlers that
    trigger recalculation when upstream shards update.
    """
    net = calculate_net_score(weights)
    light = calculate_traffic_light(net)

    supporting = [w for w in weights if w.supports_burden_holder and w.weight != EvidenceWeightValue.NEUTRAL]
    adverse = [w for w in weights if not w.supports_burden_holder]

    gap_parts: List[str] = []
    if light == TrafficLight.RED:
        gap_parts.append("Insufficient evidence to discharge burden.")
    if adverse:
        gap_parts.append(f"{len(adverse)} adverse item(s) weaken position.")
    if not supporting:
        gap_parts.append("No supporting evidence recorded.")

    return BurdenAssignment(
        id=assignment_id,
        element_id=element_id,
        traffic_light=light,
        net_score=net,
        supporting_count=len(supporting),
        adverse_count=len(adverse),
        gap_summary=" ".join(gap_parts) if gap_parts else "Burden appears satisfied.",
    )


# === Response / view models (Pydantic-free, used in API layer) ===


@dataclass
class ElementSummary:
    """Lightweight view of an element with its current burden assignment."""

    element: ClaimElement
    assignment: Optional[BurdenAssignment]
    evidence_count: int = 0


@dataclass
class BurdenMapOverview:
    """
    Top-level overview for the burden map dashboard.

    Aggregates all elements for a project/claim type showing
    which elements are green/amber/red at a glance.
    """

    project_id: Optional[str]
    claim_type: Optional[str]
    total_elements: int = 0
    green_count: int = 0
    amber_count: int = 0
    red_count: int = 0
    critical_gaps: List[str] = field(default_factory=list)  # RED + required
    elements: List[ElementSummary] = field(default_factory=list)
