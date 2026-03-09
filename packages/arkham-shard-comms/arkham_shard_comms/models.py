"""Data models for the Comms Shard.

Communication Thread Analyzer - reconstructs email/message threads,
detects BCC patterns, hidden coordination, and gaps in communication chains.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

# ============================================================
# Enums
# ============================================================


class ThreadStatus(str, Enum):
    """Status of a reconstructed thread."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    FLAGGED = "flagged"


class ParticipantRole(str, Enum):
    """Role of a participant in a thread."""

    SENDER = "sender"
    RECIPIENT = "recipient"
    CC = "cc"
    BCC = "bcc"
    UNKNOWN = "unknown"


class GapType(str, Enum):
    """Type of detected gap in communications."""

    MISSING_REPLY = "missing_reply"
    CONSPICUOUS_SILENCE = "conspicuous_silence"
    DELAYED_RESPONSE = "delayed_response"
    MISSING_FORWARD = "missing_forward"
    BCC_EXCLUDED = "bcc_excluded"


class CoordinationFlag(str, Enum):
    """Type of coordination pattern detected."""

    BCC_CHAIN = "bcc_chain"
    FORWARDING_CHAIN = "forwarding_chain"
    SIMULTANEOUS_SEND = "simultaneous_send"
    PRE_MEETING_COORDINATION = "pre_meeting_coordination"
    POST_MEETING_COORDINATION = "post_meeting_coordination"
    REPLY_ALL_SUPPRESSED = "reply_all_suppressed"


# ============================================================
# Core models
# ============================================================


@dataclass
class Thread:
    """A reconstructed email/message thread.

    Built from fragmented sources (disclosed documents, BYLOR emails etc.)
    to map who-knew-what-when across communication chains.
    """

    id: str
    tenant_id: Optional[str] = None
    subject: str = ""
    description: str = ""
    project_id: Optional[str] = None
    status: ThreadStatus = ThreadStatus.ACTIVE
    # Reconstructed date range
    first_message_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    message_count: int = 0
    participant_count: int = 0
    # Flags
    has_gaps: bool = False
    has_bcc_pattern: bool = False
    has_coordination_flags: bool = False
    # Source references
    source_document_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class Message:
    """A single message within a thread.

    Captures sender, recipients (To/CC/BCC), timestamps, and
    content references for thread reconstruction.
    """

    id: str
    thread_id: str
    tenant_id: Optional[str] = None
    # Message identity
    message_id_header: Optional[str] = None  # Email Message-ID header
    in_reply_to: Optional[str] = None  # Parent message_id_header
    subject: str = ""
    body_summary: str = ""  # Excerpt or summary, not full body
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    # Participants
    from_address: str = ""
    from_name: Optional[str] = None
    to_addresses: list[str] = field(default_factory=list)
    cc_addresses: list[str] = field(default_factory=list)
    bcc_addresses: list[str] = field(default_factory=list)  # Detected from other sources
    # Source
    source_document_id: Optional[str] = None
    page_reference: Optional[str] = None
    extraction_method: str = "manual"  # manual | ocr | parse
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Participant:
    """A participant identified across one or more threads."""

    id: str
    tenant_id: Optional[str] = None
    email_address: str = ""
    display_name: Optional[str] = None
    entity_id: Optional[str] = None  # Link to arkham_entities if known
    organisation: Optional[str] = None
    role_notes: str = ""  # e.g. "HR Director", "Respondent 3"
    thread_count: int = 0
    message_count: int = 0
    bcc_appearances: int = 0  # Times appeared as suspected BCC
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Gap:
    """A detected gap or silence in a communication chain.

    Flags missing replies, conspicuous silences, and other anomalies
    that may indicate deleted messages or hidden coordination.
    """

    id: str
    thread_id: str
    tenant_id: Optional[str] = None
    gap_type: GapType = GapType.MISSING_REPLY
    description: str = ""
    # Temporal context
    gap_start: Optional[datetime] = None
    gap_end: Optional[datetime] = None
    gap_duration_hours: Optional[float] = None
    # Context
    expected_sender: Optional[str] = None  # Who should have replied
    preceding_message_id: Optional[str] = None
    following_message_id: Optional[str] = None
    significance: str = "medium"  # low | medium | high | critical
    notes: str = ""
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class CoordinationFlagRecord:
    """A detected coordination pattern across threads.

    Highlights BCC patterns, forwarding chains, and other hidden
    coordination signals relevant to discrimination/conspiracy claims.
    """

    id: str
    thread_id: str
    tenant_id: Optional[str] = None
    flag_type: CoordinationFlag = CoordinationFlag.BCC_CHAIN
    description: str = ""
    # Participants involved
    participants_involved: list[str] = field(default_factory=list)  # email addresses
    # Supporting evidence
    supporting_message_ids: list[str] = field(default_factory=list)
    source_document_ids: list[str] = field(default_factory=list)
    # Assessment
    confidence: float = 0.5  # 0.0 - 1.0
    significance: str = "medium"  # low | medium | high | critical
    legal_relevance: str = ""  # Notes on legal relevance to claims
    project_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
