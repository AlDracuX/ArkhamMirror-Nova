"""Witnesses Shard - Data Models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class WitnessRole(str, Enum):
    CLAIMANT = "claimant"
    RESPONDENT_WITNESS = "respondent_witness"
    INDEPENDENT = "independent"
    EXPERT = "expert"
    CHARACTER = "character"


class WitnessStatus(str, Enum):
    IDENTIFIED = "identified"
    CONTACTED = "contacted"
    CONFIRMED = "confirmed"
    STATEMENT_TAKEN = "statement_taken"
    UNAVAILABLE = "unavailable"


class StatementStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SIGNED = "signed"
    FILED = "filed"
    SUPERSEDED = "superseded"


class CredibilityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Party(str, Enum):
    CLAIMANT = "claimant"
    RESPONDENT = "respondent"
    THIRD_PARTY = "third_party"


@dataclass
class Witness:
    id: str
    name: str
    role: WitnessRole
    status: WitnessStatus = WitnessStatus.IDENTIFIED
    party: Party = Party.CLAIMANT
    organization: Optional[str] = None
    position: Optional[str] = None
    contact_info: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    credibility_level: CredibilityLevel = CredibilityLevel.UNKNOWN
    credibility_notes: str = ""
    linked_entity_id: Optional[str] = None
    linked_document_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WitnessStatement:
    id: str
    witness_id: str
    version: int = 1
    title: str = ""
    content: str = ""
    status: StatementStatus = StatementStatus.DRAFT
    key_points: List[str] = field(default_factory=list)
    contradictions_found: List[str] = field(default_factory=list)
    filed_date: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CrossExamNote:
    id: str
    witness_id: str
    statement_id: Optional[str] = None
    topic: str = ""
    question: str = ""
    expected_answer: str = ""
    actual_answer: str = ""
    effectiveness: str = ""
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WitnessFilter:
    role: Optional[WitnessRole] = None
    status: Optional[WitnessStatus] = None
    party: Optional[Party] = None
    credibility_level: Optional[CredibilityLevel] = None
    search_text: Optional[str] = None


@dataclass
class WitnessStats:
    total_witnesses: int = 0
    by_role: Dict[str, int] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)
    by_party: Dict[str, int] = field(default_factory=dict)
    total_statements: int = 0
    total_cross_exam_notes: int = 0
