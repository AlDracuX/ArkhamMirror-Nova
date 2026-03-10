"""Data models for the CrossExam Shard."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class ItemStatus(str, Enum):
    """Status of an item."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class NodeStatus(str, Enum):
    """Status of a question node."""

    PENDING = "pending"
    ASKED = "asked"
    SKIPPED = "skipped"


class ExamApproach(str, Enum):
    """Approach style for cross-examination."""

    STANDARD = "standard"
    HOSTILE = "hostile"
    FRIENDLY = "friendly"
    EXPERT = "expert"


class ExamPlanStatus(str, Enum):
    """Status of an exam plan."""

    DRAFT = "draft"
    PREPARED = "prepared"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class QuestionNode:
    """A node in a cross-examination question tree."""

    id: str
    tree_id: str
    parent_id: Optional[str] = None
    question_text: str = ""
    expected_answer: str = ""
    alternative_answer: str = ""
    follow_up_expected_id: Optional[str] = None
    follow_up_alternative_id: Optional[str] = None
    damage_potential: float = 0.0  # 0.0 to 1.0
    damage_reasoning: str = ""
    status: NodeStatus = NodeStatus.PENDING
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class QuestionTree:
    """A cross-examination question tree for a witness."""

    id: str
    tenant_id: Optional[str] = None
    witness_id: str = ""
    title: str = ""
    description: str = ""
    root_node_id: Optional[str] = None
    status: ItemStatus = ItemStatus.ACTIVE
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class ImpeachmentSequence:
    """A sequence of questions designed to impeach a witness."""

    id: str
    tenant_id: Optional[str] = None
    witness_id: str = ""
    title: str = ""
    conflict_description: str = ""
    statement_claim_id: Optional[str] = None
    document_evidence_id: Optional[str] = None
    steps: List[str] = field(default_factory=list)  # List of question texts or node IDs
    status: ItemStatus = ItemStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExamPlan:
    """A cross-examination plan for a witness."""

    id: str
    case_id: Optional[str] = None
    witness_id: Optional[str] = None
    witness_name: str = ""
    topics: List[dict] = field(default_factory=list)
    questions: List[dict] = field(default_factory=list)
    impeachment_points: List[dict] = field(default_factory=list)
    objectives: Optional[str] = None
    approach: ExamApproach = ExamApproach.STANDARD
    status: ExamPlanStatus = ExamPlanStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DamageScore:
    """Detailed damage scoring for a question or sequence."""

    id: str
    tenant_id: Optional[str] = None
    target_id: str = ""  # QuestionNode ID or ImpeachmentSequence ID
    target_type: str = "question"  # "question" or "sequence"
    score: float = 0.0
    reasoning: str = ""
    impacted_claims: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
