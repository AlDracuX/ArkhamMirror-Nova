"""Data models for the Skeleton Shard.

Legal Argument Builder - structures skeleton arguments and legal submissions
in ET-compliant format.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

# ============================================================
# Enums
# ============================================================


class SubmissionStatus(str, Enum):
    """Status of a legal submission."""

    DRAFT = "draft"
    REVIEW = "review"
    FINAL = "final"
    FILED = "filed"


class AuthorityType(str, Enum):
    """Type of legal authority."""

    CASE_LAW = "case_law"
    STATUTE = "statute"
    REGULATION = "regulation"
    PRACTICE_DIRECTION = "practice_direction"
    OTHER = "other"


# ============================================================
# Core models
# ============================================================


@dataclass
class ArgumentTree:
    """A structured legal argument tree.

    Maps claim -> legal test -> evidence -> authority.
    """

    id: str
    tenant_id: Optional[str] = None
    title: str = ""
    project_id: Optional[str] = None
    claim_id: Optional[str] = None  # Link to arkham_claims
    legal_test: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    authority_ids: list[str] = field(default_factory=list)
    logic_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


@dataclass
class Authority:
    """A reusable legal authority or principle."""

    id: str
    tenant_id: Optional[str] = None
    citation: str = ""
    title: str = ""
    authority_type: AuthorityType = AuthorityType.CASE_LAW
    ratio_decidendi: str = ""
    key_quotes: list[str] = field(default_factory=list)
    bundle_page: Optional[int] = None
    is_binding: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Submission:
    """A complete legal submission or skeleton argument."""

    id: str
    tenant_id: Optional[str] = None
    title: str = ""
    project_id: Optional[str] = None
    submission_type: str = "skeleton_argument"  # skeleton_argument | full_submission
    status: SubmissionStatus = SubmissionStatus.DRAFT
    content_structure: dict[str, Any] = field(default_factory=dict)  # Tree of argument_ids
    rendered_text: Optional[str] = None
    bundle_references: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
