"""Data models for the Disclosure Shard."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

VALID_STATUSES = frozenset({"pending", "requested", "received", "partial", "refused", "overdue"})


class RequestStatus(str, Enum):
    """Status of a disclosure request."""

    PENDING = "pending"
    REQUESTED = "requested"
    RECEIVED = "received"
    PARTIAL = "partial"
    REFUSED = "refused"
    OVERDUE = "overdue"


class GapStatus(str, Enum):
    """Status of a disclosure gap."""

    OPEN = "open"
    CHASED = "chased"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class EvasionCategory(str, Enum):
    """Category of evasion behaviour."""

    PARTIAL_RESPONSE = "partial_response"
    REDACTION = "redaction"
    DELAY = "delay"
    REFUSAL = "refusal"
    IRRELEVANT_DOCUMENTS = "irrelevant_documents"
    NONE = "none"


@dataclass
class DisclosureRequest:
    """A disclosure request in the system."""

    id: str
    case_id: Optional[str] = None
    category: str = ""
    description: str = ""
    requesting_party: str = ""
    status: str = "pending"
    deadline: Optional[date] = None
    document_ids: List[str] = field(default_factory=list)
    response_text: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def validate_status(status: str) -> bool:
    """Validate that a status value is in the allowed set."""
    return status in VALID_STATUSES


def detect_overdue(requests: List[DisclosureRequest], as_of: Optional[date] = None) -> List[DisclosureRequest]:
    """Return requests that are past deadline and still pending/requested."""
    check_date = as_of or date.today()
    overdue = []
    for req in requests:
        if req.deadline and req.deadline < check_date and req.status in ("pending", "requested"):
            overdue.append(req)
    return overdue


def generate_timeline(requests: List[DisclosureRequest]) -> List[dict]:
    """Generate a disclosure timeline ordered by deadline (nulls last)."""
    with_deadline = [r for r in requests if r.deadline is not None]
    without_deadline = [r for r in requests if r.deadline is None]

    with_deadline.sort(key=lambda r: r.deadline)

    timeline = []
    for req in with_deadline + without_deadline:
        timeline.append(
            {
                "request_id": req.id,
                "category": req.category,
                "deadline": req.deadline.isoformat() if req.deadline else None,
                "status": req.status,
            }
        )
    return timeline
