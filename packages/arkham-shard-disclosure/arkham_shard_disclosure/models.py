"""Data models for the Disclosure Shard."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class RequestStatus(str, Enum):
    """Status of a disclosure request."""

    PENDING = "pending"
    PARTIAL = "partial"
    FULFILLED = "fulfilled"
    OVERDUE = "overdue"
    REFUSED = "refused"


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
class Request:
    """A disclosure request sent to a respondent."""

    id: str
    tenant_id: Optional[str] = None
    respondent_id: str = ""
    request_text: str = ""
    deadline: Optional[datetime] = None
    status: RequestStatus = RequestStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Response:
    """A disclosure response received from a respondent."""

    id: str
    tenant_id: Optional[str] = None
    request_id: str = ""
    response_text: str = ""
    document_ids: List[str] = field(default_factory=list)
    received_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Gap:
    """A gap between what was requested and what was provided."""

    id: str
    tenant_id: Optional[str] = None
    request_id: str = ""
    missing_items_description: str = ""
    status: GapStatus = GapStatus.OPEN
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EvasionScore:
    """Evasion compliance score for a respondent."""

    id: str
    tenant_id: Optional[str] = None
    respondent_id: str = ""
    score: float = 0.0  # 0.0 = fully evasive, 1.0 = fully compliant
    reason: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
