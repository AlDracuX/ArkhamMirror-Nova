"""Casemap Shard - Data Models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ClaimType(str, Enum):
    UNFAIR_DISMISSAL = "unfair_dismissal"
    CONSTRUCTIVE_DISMISSAL = "constructive_dismissal"
    DISCRIMINATION = "discrimination"
    HARASSMENT = "harassment"
    VICTIMISATION = "victimisation"
    WHISTLEBLOWING = "whistleblowing"
    BREACH_OF_CONTRACT = "breach_of_contract"
    UNPAID_WAGES = "unpaid_wages"
    REDUNDANCY = "redundancy"
    TUPE = "tupe"
    HEALTH_AND_SAFETY = "health_and_safety"
    CUSTOM = "custom"


class BurdenOfProof(str, Enum):
    CLAIMANT = "claimant"
    RESPONDENT = "respondent"
    SHARED = "shared"
    REVERSE = "reverse"         # Statutory reverse (e.g. discrimination EA 2010 s.136)


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NEUTRAL = "neutral"
    ADVERSE = "adverse"         # Evidence hurts this element


class ElementStatus(str, Enum):
    PROVEN = "proven"
    LIKELY = "likely"
    CONTESTED = "contested"
    WEAK = "weak"
    UNPROVEN = "unproven"
    CONCEDED = "conceded"


class TheoryStatus(str, Enum):
    ACTIVE = "active"
    ABANDONED = "abandoned"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SETTLED = "settled"


@dataclass
class LegalTheory:
    id: str
    title: str
    claim_type: ClaimType
    description: str = ""
    statutory_basis: str = ""
    respondent_ids: List[str] = field(default_factory=list)
    status: TheoryStatus = TheoryStatus.ACTIVE
    overall_strength: int = 0   # 0-100 calculated
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LegalElement:
    id: str
    theory_id: str
    title: str
    description: str = ""
    burden: BurdenOfProof = BurdenOfProof.CLAIMANT
    status: ElementStatus = ElementStatus.UNPROVEN
    required: bool = True
    statutory_reference: str = ""
    notes: str = ""
    display_order: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EvidenceLink:
    id: str
    element_id: str
    document_id: Optional[str] = None
    witness_id: Optional[str] = None
    description: str = ""
    strength: EvidenceStrength = EvidenceStrength.NEUTRAL
    source_reference: str = ""
    supports_element: bool = True
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StrengthAssessment:
    theory_id: str
    total_elements: int = 0
    proven_count: int = 0
    contested_count: int = 0
    unproven_count: int = 0
    overall_score: int = 0      # 0-100
    gaps: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)


@dataclass
class TheoryFilter:
    claim_type: Optional[ClaimType] = None
    status: Optional[TheoryStatus] = None
    search_text: Optional[str] = None
    min_strength: Optional[int] = None
    respondent_id: Optional[str] = None


# Pre-defined element templates for common UK employment claims
CLAIM_ELEMENT_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "unfair_dismissal": [
        {"title": "Employee with 2+ years continuous service", "burden": "claimant", "statutory_reference": "ERA 1996 s.108", "required": True},
        {"title": "Dismissal occurred", "burden": "claimant", "statutory_reference": "ERA 1996 s.95", "required": True},
        {"title": "Reason for dismissal identified", "burden": "respondent", "statutory_reference": "ERA 1996 s.98(1)", "required": True},
        {"title": "Reason is potentially fair", "burden": "respondent", "statutory_reference": "ERA 1996 s.98(2)", "required": True},
        {"title": "Fair procedure followed", "burden": "shared", "statutory_reference": "ERA 1996 s.98(4) / ACAS Code", "required": True},
        {"title": "Decision within range of reasonable responses", "burden": "shared", "statutory_reference": "ERA 1996 s.98(4)", "required": True},
    ],
    "constructive_dismissal": [
        {"title": "Fundamental breach of contract by employer", "burden": "claimant", "statutory_reference": "ERA 1996 s.95(1)(c)", "required": True},
        {"title": "Breach was sufficiently serious", "burden": "claimant", "statutory_reference": "Western Excavating v Sharp", "required": True},
        {"title": "Employee resigned in response to breach", "burden": "claimant", "statutory_reference": "ERA 1996 s.95(1)(c)", "required": True},
        {"title": "Employee did not delay or affirm contract", "burden": "claimant", "statutory_reference": "WE Cox Toner v Crook", "required": True},
        {"title": "Last straw (if series of acts)", "burden": "claimant", "statutory_reference": "Omilaju v Waltham Forest", "required": False},
    ],
    "discrimination": [
        {"title": "Protected characteristic exists", "burden": "claimant", "statutory_reference": "EA 2010 s.4", "required": True},
        {"title": "Less favourable treatment occurred", "burden": "claimant", "statutory_reference": "EA 2010 s.13", "required": True},
        {"title": "Comparator identified (actual or hypothetical)", "burden": "claimant", "statutory_reference": "EA 2010 s.23", "required": True},
        {"title": "Treatment because of protected characteristic", "burden": "reverse", "statutory_reference": "EA 2010 s.136", "required": True},
        {"title": "No legitimate justification", "burden": "respondent", "statutory_reference": "EA 2010 s.13(2)", "required": True},
    ],
    "whistleblowing": [
        {"title": "Qualifying disclosure made", "burden": "claimant", "statutory_reference": "ERA 1996 s.43B", "required": True},
        {"title": "Disclosure of information (not opinion)", "burden": "claimant", "statutory_reference": "Cavendish Munro v Geduld", "required": True},
        {"title": "Reasonable belief in truth of disclosure", "burden": "claimant", "statutory_reference": "ERA 1996 s.43B(1)", "required": True},
        {"title": "Disclosure in public interest", "burden": "claimant", "statutory_reference": "ERA 1996 s.43B(1)", "required": True},
        {"title": "Detriment suffered", "burden": "claimant", "statutory_reference": "ERA 1996 s.47B", "required": True},
        {"title": "Causal connection (done on ground of disclosure)", "burden": "reverse", "statutory_reference": "ERA 1996 s.48(2)", "required": True},
    ],
    "harassment": [
        {"title": "Unwanted conduct occurred", "burden": "claimant", "statutory_reference": "EA 2010 s.26(1)", "required": True},
        {"title": "Related to protected characteristic", "burden": "claimant", "statutory_reference": "EA 2010 s.26(1)(a)", "required": True},
        {"title": "Purpose or effect of violating dignity", "burden": "shared", "statutory_reference": "EA 2010 s.26(1)(b)", "required": True},
        {"title": "Reasonable for conduct to have that effect", "burden": "shared", "statutory_reference": "EA 2010 s.26(4)", "required": True},
    ],
    "victimisation": [
        {"title": "Protected act done", "burden": "claimant", "statutory_reference": "EA 2010 s.27(2)", "required": True},
        {"title": "Detriment suffered", "burden": "claimant", "statutory_reference": "EA 2010 s.27(1)", "required": True},
        {"title": "Detriment because of the protected act", "burden": "reverse", "statutory_reference": "EA 2010 s.136", "required": True},
    ],
}
