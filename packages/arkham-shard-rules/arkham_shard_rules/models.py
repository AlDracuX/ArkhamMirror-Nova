"""Data models for the Rules Shard.

Encodes Employment Tribunal Rules of Procedure (SI 2013/1237 as amended)
and related Practice Directions as structured data.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

# ============================================================
# Enums
# ============================================================


class RuleCategory(str, Enum):
    """Category of ET procedural rule."""

    INITIAL_CONSIDERATION = "initial_consideration"
    CASE_MANAGEMENT = "case_management"
    DISCLOSURE = "disclosure"
    WITNESSES = "witnesses"
    HEARING = "hearing"
    JUDGMENT = "judgment"
    APPEAL = "appeal"
    COSTS = "costs"
    UNLESS_ORDER = "unless_order"
    STRIKE_OUT = "strike_out"
    DEPOSIT_ORDER = "deposit_order"
    DEFAULT_JUDGMENT = "default_judgment"


class DeadlineType(str, Enum):
    """How the deadline period is calculated."""

    CALENDAR_DAYS = "calendar_days"
    WORKING_DAYS = "working_days"
    MONTHS = "months"
    WEEKS = "weeks"


class TriggerType(str, Enum):
    """What event triggers the deadline clock."""

    DATE_OF_ORDER = "date_of_order"
    DATE_OF_JUDGMENT = "date_of_judgment"
    DATE_OF_HEARING = "date_of_hearing"
    DATE_OF_CLAIM = "date_of_claim"
    DATE_OF_RESPONSE = "date_of_response"
    DATE_OF_DISMISSAL = "date_of_dismissal"
    DATE_OF_DISCLOSURE_REQUEST = "date_of_disclosure_request"
    DATE_OF_NOTIFICATION = "date_of_notification"
    CUSTOM = "custom"


class BreachSeverity(str, Enum):
    """Severity classification of a procedural breach."""

    MINOR = "minor"
    MODERATE = "moderate"
    SERIOUS = "serious"
    EGREGIOUS = "egregious"


class BreachStatus(str, Enum):
    """Current status of a logged breach."""

    DETECTED = "detected"
    NOTIFIED = "notified"
    APPLICATION_DRAFTED = "application_drafted"
    APPLICATION_FILED = "application_filed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ComplianceResult(str, Enum):
    """Outcome of a compliance check."""

    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    BORDERLINE = "borderline"
    UNABLE_TO_ASSESS = "unable_to_assess"


# ============================================================
# Core Rule model
# ============================================================


@dataclass
class Rule:
    """A single Employment Tribunal procedural rule.

    Encodes a specific rule from the ET Rules of Procedure 2013
    (or Practice Direction) as structured, queryable data.
    """

    id: str
    rule_number: str  # e.g. "Rule 29", "Rule 47", "PD 2.3"
    title: str
    description: str
    category: RuleCategory
    trigger_type: TriggerType
    tenant_id: Optional[str] = None
    deadline_days: Optional[int] = None  # Number of days/weeks/months
    deadline_type: DeadlineType = DeadlineType.CALENDAR_DAYS
    statutory_source: str = "ET Rules of Procedure 2013 (SI 2013/1237)"
    applies_to: str = "both"  # claimant | respondent | both | tribunal
    is_mandatory: bool = True  # False = discretionary
    consequence_of_breach: str = ""
    strike_out_risk: bool = False
    unless_order_applicable: bool = False
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# Deadline Calculation
# ============================================================


@dataclass
class Calculation:
    """A computed deadline from a trigger event and a rule.

    Stores the inputs and output of one deadline calculation
    so it can be audited and surfaced in the UI.
    """

    id: str
    rule_id: str
    rule_number: str
    rule_title: str
    trigger_date: date
    trigger_type: TriggerType
    deadline_date: date
    deadline_days: int
    deadline_type: DeadlineType
    description: str  # Human-readable summary, e.g. "ET3 due 28 days from claim"
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    document_id: Optional[str] = None  # Source order/judgment document
    respondent: Optional[str] = None  # Named respondent if applicable
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


# ============================================================
# Breach
# ============================================================


@dataclass
class Breach:
    """A logged procedural breach by a party.

    Records when a respondent (or claimant) has failed to comply
    with a specific rule or order, supporting costs and
    strike-out/unless order applications.
    """

    id: str
    rule_id: str
    rule_number: str
    rule_title: str
    breaching_party: str  # Name of the respondent or 'Claimant'
    breach_date: date  # Date the breach occurred / was detected
    deadline_date: Optional[date]  # The deadline that was missed (if applicable)
    description: str  # Factual description of the breach
    tenant_id: Optional[str] = None
    severity: BreachSeverity = BreachSeverity.MODERATE
    status: BreachStatus = BreachStatus.DETECTED
    document_evidence: list[str] = field(default_factory=list)  # Document IDs
    suggested_remedy: str = ""  # e.g. "Apply for Unless Order under Rule 38"
    application_text: Optional[str] = None  # Draft application if generated
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


# ============================================================
# Compliance Check
# ============================================================


@dataclass
class ComplianceCheck:
    """A compliance assessment of a submission or document against ET Rules.

    Validates whether a filing or action meets procedural requirements
    before it is submitted to the Tribunal.
    """

    id: str
    document_id: Optional[str]  # Document being checked (if any)
    submission_type: str  # e.g. "ET3 Response", "Witness Statement", "Skeleton"
    rules_checked: list[str]  # Rule IDs checked
    result: ComplianceResult
    tenant_id: Optional[str] = None
    issues_found: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    score: float = 0.0  # 0.0 - 1.0 compliance score
    project_id: Optional[str] = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
