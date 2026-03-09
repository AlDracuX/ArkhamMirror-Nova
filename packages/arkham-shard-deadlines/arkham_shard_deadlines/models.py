"""Deadlines Shard - Data Models."""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional


class DeadlineType(str, Enum):
    TRIBUNAL_ORDER = "tribunal_order"
    FILING = "filing"
    RESPONSE = "response"
    HEARING = "hearing"
    APPEAL = "appeal"
    DISCLOSURE = "disclosure"
    WITNESS_STATEMENT = "witness_statement"
    COSTS = "costs"
    COMPLIANCE = "compliance"
    CUSTOM = "custom"


class DeadlineStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BREACHED = "breached"
    WAIVED = "waived"
    EXTENDED = "extended"


class UrgencyLevel(str, Enum):
    CRITICAL = "critical"       # 0-2 days
    HIGH = "high"               # 3-7 days
    MEDIUM = "medium"           # 8-14 days
    LOW = "low"                 # 15-30 days
    FUTURE = "future"           # 31+ days
    OVERDUE = "overdue"         # Past due


class CaseType(str, Enum):
    ET = "et"                   # Employment Tribunal
    EAT = "eat"                 # Employment Appeal Tribunal
    HOUSING = "housing"
    JR = "jr"                   # Judicial Review
    OTHER = "other"


@dataclass
class Deadline:
    id: str
    title: str
    deadline_date: date
    deadline_type: DeadlineType = DeadlineType.CUSTOM
    status: DeadlineStatus = DeadlineStatus.PENDING
    urgency: UrgencyLevel = UrgencyLevel.FUTURE
    description: str = ""
    deadline_time: Optional[time] = None
    case_type: CaseType = CaseType.ET
    case_reference: str = ""
    source_document: str = ""
    source_order_date: Optional[date] = None
    rule_reference: str = ""
    auto_calculated: bool = False
    calculation_base_date: Optional[date] = None
    calculation_days: Optional[int] = None
    notes: str = ""
    completed_at: Optional[datetime] = None
    completed_by: str = ""
    linked_document_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeadlineRule:
    id: str
    name: str
    description: str = ""
    case_type: CaseType = CaseType.ET
    deadline_type: DeadlineType = DeadlineType.CUSTOM
    days_from_trigger: int = 14
    trigger_event: str = ""
    working_days_only: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DeadlineFilter:
    status: Optional[DeadlineStatus] = None
    deadline_type: Optional[DeadlineType] = None
    case_type: Optional[CaseType] = None
    urgency: Optional[UrgencyLevel] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    search_text: Optional[str] = None
    show_completed: bool = False


@dataclass
class DeadlineStats:
    total: int = 0
    pending: int = 0
    breached: int = 0
    completed: int = 0
    by_urgency: Dict[str, int] = field(default_factory=dict)
    by_case_type: Dict[str, int] = field(default_factory=dict)
    next_deadline: Optional[Dict[str, Any]] = None
