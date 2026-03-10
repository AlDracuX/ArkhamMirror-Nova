"""Data models for the Costs Shard.

Costs & Wasted Costs Tracker - tracks time, expenses, and respondent conduct
for potential costs applications in the Employment Tribunal.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

# ============================================================
# Enums
# ============================================================


class ConductType(str, Enum):
    """Type of unreasonable conduct by a party."""

    DELAY = "delay"
    EVASION = "evasion"
    VEXATIOUS = "vexatious"
    ABUSIVE = "abusive"
    DISRUPTIVE = "disruptive"
    BREACH_OF_ORDER = "breach_of_order"
    OTHER = "other"


class ApplicationStatus(str, Enum):
    """Status of a costs application."""

    DRAFT = "draft"
    FILED = "filed"
    GRANTED = "granted"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"


# ============================================================
# Core models
# ============================================================


@dataclass
class TimeEntry:
    """A record of time spent on a litigation activity."""

    id: str
    activity: str
    duration_minutes: int
    activity_date: date
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    hourly_rate: Optional[float] = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class Expense:
    """A record of a litigation-related expense."""

    id: str
    description: str
    amount: float
    expense_date: date
    tenant_id: Optional[str] = None
    currency: str = "GBP"
    receipt_document_id: Optional[str] = None
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConductLog:
    """A log of unreasonable respondent conduct.

    Essential for Rule 76 costs applications where 'unreasonable conduct'
    is the primary threshold.
    """

    id: str
    party_name: str  # The respondent who engaged in the conduct
    conduct_type: ConductType
    description: str
    occurred_at: datetime
    tenant_id: Optional[str] = None
    supporting_evidence: list[str] = field(default_factory=list)  # Document IDs
    significance: str = "medium"  # low | medium | high | critical
    legal_reference: str = "Rule 76(1)(a)"
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class CostItem:
    """A single cost item for a case (expense claim line item)."""

    id: str
    case_id: str
    category: str
    description: str
    amount: Decimal
    date: date
    claimant: str
    currency: str = "GBP"
    evidence_doc_id: Optional[str] = None
    status: str = "claimed"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CostApplication:
    """A draft or filed application for costs."""

    id: str
    tenant_id: Optional[str] = None
    title: str = ""
    project_id: Optional[str] = None
    total_amount_claimed: float = 0.0
    status: ApplicationStatus = ApplicationStatus.DRAFT
    conduct_ids: list[str] = field(default_factory=list)
    time_entry_ids: list[str] = field(default_factory=list)
    expense_ids: list[str] = field(default_factory=list)
    application_text: Optional[str] = None
    schedule_document_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
