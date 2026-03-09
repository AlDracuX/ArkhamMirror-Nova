"""Data models for the Bundle Shard.

Implements ET Presidential Guidance-compliant tribunal bundle structures.
Bundle = paginated, indexed collection of documents for hearing submission.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

# ============================================
# Enums
# ============================================


class BundleStatus(str, Enum):
    """Lifecycle status of a bundle."""

    DRAFT = "draft"
    COMPILING = "compiling"
    COMPILED = "compiled"
    ARCHIVED = "archived"


class DocumentStatus(str, Enum):
    """Whether a document is agreed between parties (ET Presidential Guidance)."""

    AGREED = "agreed"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class IndexEntryType(str, Enum):
    """Type of entry in the bundle index."""

    DOCUMENT = "document"
    SECTION_HEADER = "section_header"
    DIVIDER = "divider"


# ============================================
# Core Domain Models
# ============================================


@dataclass
class Bundle:
    """
    A tribunal hearing bundle.

    Follows ET Presidential Guidance on bundle preparation:
    - Paginated continuously from page 1
    - Indexed with document titles and page ranges
    - Agreed/disputed markers per document
    - Versioned to track additions over time
    """

    id: str
    tenant_id: str | None = None
    title: str = ""
    description: str = ""
    project_id: str | None = None
    status: BundleStatus = BundleStatus.DRAFT
    # Total page count across all documents in this bundle
    total_pages: int = 0
    # Bundle version number, incremented on each recompile
    version: int = 1
    # Active version ID pointing to the BundleVersion record
    current_version_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str | None = None


@dataclass
class BundlePage:
    """
    Document-to-page mapping entry.

    Tracks how each source document maps onto the bundle's continuous
    page numbering. A document with 5 pages at bundle_page_start=10
    occupies bundle pages 10-14.

    This is the core of ET bundle pagination compliance: every document
    gets a fixed position so skeleton arguments can cite stable page numbers.
    """

    id: str
    bundle_id: str
    version_id: str
    # Source document from the documents shard
    document_id: str
    document_title: str = ""
    document_filename: str = ""
    # Position of this document within the bundle (1-indexed ordering)
    position: int = 0
    # Number of pages in the source document (extracted or estimated)
    document_page_count: int = 1
    # First bundle page number assigned to this document
    bundle_page_start: int = 1
    # Last bundle page number (inclusive): bundle_page_start + document_page_count - 1
    bundle_page_end: int = 1
    # Agreed/Disputed status per ET Presidential Guidance
    document_status: DocumentStatus = DocumentStatus.UNKNOWN
    # Optional section or tab label (e.g. "A", "B", "Claimant's Documents")
    section_label: str = ""
    # Free-text notes (e.g. "Redacted version", "Original produced at disclosure")
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def page_range(self) -> str:
        """Human-readable page range string, e.g. 'pp.1-5' or 'p.1'."""
        if self.bundle_page_start == self.bundle_page_end:
            return f"p.{self.bundle_page_start}"
        return f"pp.{self.bundle_page_start}-{self.bundle_page_end}"


@dataclass
class BundleIndexEntry:
    """A single row in the bundle index table."""

    entry_type: IndexEntryType
    position: int
    # Populated for DOCUMENT entries
    document_id: str | None = None
    document_title: str = ""
    document_filename: str = ""
    bundle_page_start: int | None = None
    bundle_page_end: int | None = None
    document_status: DocumentStatus = DocumentStatus.UNKNOWN
    section_label: str = ""
    notes: str = ""
    # Populated for SECTION_HEADER / DIVIDER entries
    header_text: str = ""

    @property
    def page_range(self) -> str:
        """Human-readable page range for index display."""
        if self.bundle_page_start is None:
            return ""
        if self.bundle_page_start == self.bundle_page_end:
            return f"p.{self.bundle_page_start}"
        return f"pp.{self.bundle_page_start}-{self.bundle_page_end}"


@dataclass
class BundleIndex:
    """
    The auto-generated index for a bundle version.

    The index is the table of contents: document title, page range,
    and agreed/disputed status. Per ET Presidential Guidance, each party
    is entitled to a paginated index they can use to locate documents.
    """

    id: str
    bundle_id: str
    version_id: str
    # Ordered list of index entries
    entries: list[BundleIndexEntry] = field(default_factory=list)
    # Total document count (excluding section headers)
    document_count: int = 0
    # Total page count across all documents
    total_pages: int = 0
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_text(self) -> str:
        """
        Render the index as plain text, suitable for prepending to a bundle PDF.

        Format follows ET Presidential Guidance bundle index conventions:
        Tab | Document | Pages | Status
        """
        lines = ["BUNDLE INDEX", "=" * 72, ""]
        lines.append(f"{'No.':<5} {'Document':<42} {'Pages':<14} {'Status'}")
        lines.append("-" * 72)
        doc_num = 0
        for entry in self.entries:
            if entry.entry_type == IndexEntryType.SECTION_HEADER:
                lines.append("")
                lines.append(f"  [{entry.header_text.upper()}]")
                lines.append("")
            elif entry.entry_type == IndexEntryType.DOCUMENT:
                doc_num += 1
                status_label = entry.document_status.value.capitalize()
                title = entry.document_title or entry.document_filename or "(untitled)"
                if len(title) > 40:
                    title = title[:37] + "..."
                lines.append(f"{doc_num:<5} {title:<42} {entry.page_range:<14} {status_label}")
        lines.append("-" * 72)
        lines.append(f"Total: {self.document_count} documents, {self.total_pages} pages")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for JSON API responses."""
        return {
            "id": self.id,
            "bundle_id": self.bundle_id,
            "version_id": self.version_id,
            "document_count": self.document_count,
            "total_pages": self.total_pages,
            "generated_at": self.generated_at.isoformat(),
            "entries": [
                {
                    "entry_type": e.entry_type.value,
                    "position": e.position,
                    "document_id": e.document_id,
                    "document_title": e.document_title,
                    "document_filename": e.document_filename,
                    "bundle_page_start": e.bundle_page_start,
                    "bundle_page_end": e.bundle_page_end,
                    "page_range": e.page_range,
                    "document_status": e.document_status.value,
                    "section_label": e.section_label,
                    "notes": e.notes,
                    "header_text": e.header_text,
                }
                for e in self.entries
            ],
        }


@dataclass
class BundleVersion:
    """
    Snapshot of a bundle at a point in time.

    Every (re)compile creates a new BundleVersion. Old versions are retained
    so skeleton arguments that cite page numbers remain stable even if the
    bundle is later amended. Each version knows its page count so regressions
    in bundle size can be detected.
    """

    id: str
    bundle_id: str
    # Sequential version number within this bundle (1, 2, 3…)
    version_number: int = 1
    # Total pages in this version
    total_pages: int = 0
    # Number of documents compiled into this version
    document_count: int = 0
    # Free-text description of what changed in this version
    change_notes: str = ""
    # ID of the BundleIndex generated for this version
    index_id: str | None = None
    compiled_at: datetime = field(default_factory=datetime.utcnow)
    compiled_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================
# Request / Response helpers (used by api.py)
# ============================================


@dataclass
class CompileRequest:
    """
    Input for the bundle compilation endpoint.

    The caller provides an ordered list of document IDs. The compiler
    fetches metadata for each document (title, page count), assigns
    continuous bundle page numbers, and generates the index.
    """

    document_ids: list[str]
    # Optional per-document overrides keyed by document_id
    document_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Optional section headers injected before specific document positions
    # e.g. {0: "Claimant Documents", 5: "Respondent Documents"}
    section_headers: dict[int, str] = field(default_factory=dict)
    change_notes: str = ""
    compiled_by: str | None = None


@dataclass
class CompileResult:
    """Result returned after a successful compilation."""

    bundle_id: str
    version_id: str
    version_number: int
    total_pages: int
    document_count: int
    index: BundleIndex
    pages: list[BundlePage]
