"""Bundle Compiler - Core domain logic for tribunal hearing bundle compilation.

Handles continuous page numbering, version management, index generation,
and document add/remove operations per ET Presidential Guidance.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from .models import (
    BundleIndex,
    BundleIndexEntry,
    BundlePage,
    BundleVersion,
    DocumentStatus,
    IndexEntryType,
)

logger = logging.getLogger(__name__)


# Standard ET Presidential Guidance section ordering
ET_STANDARD_SECTIONS = [
    "Claim and Response",
    "Case management orders",
    "Claimant's documents",
    "Respondent's documents",
    "Witness statements",
    "Authorities",
]


class BundleCompiler:
    """
    Compiles documents into ordered, paginated tribunal hearing bundles.

    Implements ET Presidential Guidance requirements:
    - Continuous page numbering across all documents
    - Version snapshots for stable page references
    - Auto-generated table of contents / index
    - Standard section ordering
    """

    def __init__(self, db, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Pure Functions
    # ------------------------------------------------------------------

    def assign_page_numbers(self, documents: list[dict]) -> list[dict]:
        """
        Assign continuous page numbers to an ordered list of documents.

        Each document dict must have 'page_count' (int). Returns a new list
        with 'bundle_page_start' and 'bundle_page_end' added.

        Pure function -- no database access.

        Args:
            documents: List of dicts with at least 'page_count' key.

        Returns:
            New list of dicts with page assignments added.
        """
        result = []
        current_page = 1
        for doc in documents:
            page_count = doc.get("page_count", 1)
            if page_count < 1:
                page_count = 1
            numbered = {
                **doc,
                "bundle_page_start": current_page,
                "bundle_page_end": current_page + page_count - 1,
            }
            result.append(numbered)
            current_page += page_count
        return result

    # ------------------------------------------------------------------
    # Compile
    # ------------------------------------------------------------------

    async def compile(self, bundle_id: str) -> dict:
        """
        Compile documents into an ordered bundle with continuous page numbering.

        Fetches all current pages for the bundle, assigns page numbers,
        creates a new BundleVersion and BundlePage records, and generates
        the BundleIndex.

        Args:
            bundle_id: The bundle to compile.

        Returns:
            Dict with version details including version_id, version_number,
            total_pages, document_count, and index.
        """
        # 1. Fetch bundle
        bundle_row = await self._db.fetch_one(
            "SELECT * FROM arkham_bundle.bundles WHERE id = :id",
            {"id": bundle_id},
        )
        if not bundle_row:
            raise ValueError(f"Bundle not found: {bundle_id}")

        # 2. Fetch current document list (from most recent version's pages, or bundle_documents)
        existing_pages = await self._db.fetch_all(
            """SELECT document_id, document_title, document_filename,
                      document_page_count, document_status, section_label, notes, position
               FROM arkham_bundle.pages
               WHERE bundle_id = :bundle_id
                 AND version_id = :version_id
               ORDER BY position ASC""",
            {"bundle_id": bundle_id, "version_id": bundle_row.get("current_version_id", "")},
        )

        # Build document list from existing pages
        documents = []
        for row in existing_pages:
            documents.append(
                {
                    "document_id": row["document_id"],
                    "title": row.get("document_title", ""),
                    "filename": row.get("document_filename", ""),
                    "page_count": row.get("document_page_count", 1),
                    "status": row.get("document_status", "unknown"),
                    "section_label": row.get("section_label", ""),
                    "notes": row.get("notes", ""),
                }
            )

        # 3. Assign page numbers
        numbered_docs = self.assign_page_numbers(documents)

        # 4. Create version
        version_id = str(uuid.uuid4())
        version_number = (bundle_row.get("version", 0) or 0) + 1
        total_pages = numbered_docs[-1]["bundle_page_end"] if numbered_docs else 0

        # 5. Persist version + pages + index in transaction
        index_id = str(uuid.uuid4())

        async with self._db.transaction():
            # Insert version
            await self._db.execute(
                """INSERT INTO arkham_bundle.versions
                   (id, bundle_id, version_number, total_pages, document_count, index_id, compiled_at)
                   VALUES (:id, :bundle_id, :vnum, :pages, :docs, :index_id, :compiled_at)""",
                {
                    "id": version_id,
                    "bundle_id": bundle_id,
                    "vnum": version_number,
                    "pages": total_pages,
                    "docs": len(numbered_docs),
                    "index_id": index_id,
                    "compiled_at": datetime.utcnow().isoformat(),
                },
            )

            # Insert pages
            index_entries = []
            for pos, doc in enumerate(numbered_docs):
                page_id = str(uuid.uuid4())
                await self._db.execute(
                    """INSERT INTO arkham_bundle.pages
                       (id, bundle_id, version_id, document_id, document_title, document_filename,
                        position, document_page_count, bundle_page_start, bundle_page_end,
                        document_status, section_label, notes)
                       VALUES (:id, :bundle_id, :version_id, :document_id, :title, :filename,
                               :position, :page_count, :page_start, :page_end,
                               :status, :section_label, :notes)""",
                    {
                        "id": page_id,
                        "bundle_id": bundle_id,
                        "version_id": version_id,
                        "document_id": doc["document_id"],
                        "title": doc.get("title", ""),
                        "filename": doc.get("filename", ""),
                        "position": pos,
                        "page_count": doc.get("page_count", 1),
                        "page_start": doc["bundle_page_start"],
                        "page_end": doc["bundle_page_end"],
                        "status": doc.get("status", "unknown"),
                        "section_label": doc.get("section_label", ""),
                        "notes": doc.get("notes", ""),
                    },
                )

                index_entries.append(
                    BundleIndexEntry(
                        entry_type=IndexEntryType.DOCUMENT,
                        position=pos,
                        document_id=doc["document_id"],
                        document_title=doc.get("title", ""),
                        document_filename=doc.get("filename", ""),
                        bundle_page_start=doc["bundle_page_start"],
                        bundle_page_end=doc["bundle_page_end"],
                        document_status=DocumentStatus(doc.get("status", "unknown")),
                        section_label=doc.get("section_label", ""),
                        notes=doc.get("notes", ""),
                    )
                )

            # Build and persist index
            bundle_index = BundleIndex(
                id=index_id,
                bundle_id=bundle_id,
                version_id=version_id,
                entries=index_entries,
                document_count=len(numbered_docs),
                total_pages=total_pages,
            )

            await self._db.execute(
                """INSERT INTO arkham_bundle.indices
                   (id, bundle_id, version_id, entries, document_count, total_pages)
                   VALUES (:id, :bundle_id, :version_id, :entries, :docs, :pages)""",
                {
                    "id": index_id,
                    "bundle_id": bundle_id,
                    "version_id": version_id,
                    "entries": json.dumps(bundle_index.to_dict()["entries"]),
                    "docs": len(numbered_docs),
                    "pages": total_pages,
                },
            )

            # Update bundle
            await self._db.execute(
                """UPDATE arkham_bundle.bundles SET
                      version = :vnum, total_pages = :pages,
                      current_version_id = :vid, status = 'compiled',
                      updated_at = CURRENT_TIMESTAMP
                   WHERE id = :id""",
                {"id": bundle_id, "vnum": version_number, "pages": total_pages, "vid": version_id},
            )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "bundle.compiled",
                {
                    "bundle_id": bundle_id,
                    "version_id": version_id,
                    "version_number": version_number,
                    "total_pages": total_pages,
                },
                source="bundle-shard",
            )

        return {
            "bundle_id": bundle_id,
            "version_id": version_id,
            "version_number": version_number,
            "total_pages": total_pages,
            "document_count": len(numbered_docs),
            "index": bundle_index.to_dict(),
        }

    # ------------------------------------------------------------------
    # Generate Index
    # ------------------------------------------------------------------

    async def generate_index(self, bundle_id: str, version_id: str) -> dict:
        """
        Generate a table of contents from BundlePage records.

        Args:
            bundle_id: The bundle ID.
            version_id: The version ID to generate index for.

        Returns:
            Dict representation of the BundleIndex.
        """
        pages = await self._db.fetch_all(
            """SELECT * FROM arkham_bundle.pages
               WHERE bundle_id = :bundle_id AND version_id = :version_id
               ORDER BY position ASC""",
            {"bundle_id": bundle_id, "version_id": version_id},
        )

        entries = []
        for row in pages:
            entries.append(
                BundleIndexEntry(
                    entry_type=IndexEntryType.DOCUMENT,
                    position=row["position"],
                    document_id=row["document_id"],
                    document_title=row.get("document_title", ""),
                    document_filename=row.get("document_filename", ""),
                    bundle_page_start=row["bundle_page_start"],
                    bundle_page_end=row["bundle_page_end"],
                    document_status=DocumentStatus(row.get("document_status", "unknown")),
                    section_label=row.get("section_label", ""),
                    notes=row.get("notes", ""),
                )
            )

        total_pages = pages[-1]["bundle_page_end"] if pages else 0

        index = BundleIndex(
            id=str(uuid.uuid4()),
            bundle_id=bundle_id,
            version_id=version_id,
            entries=entries,
            document_count=len(pages),
            total_pages=total_pages,
        )

        # Persist index
        await self._db.execute(
            """INSERT INTO arkham_bundle.indices
               (id, bundle_id, version_id, entries, document_count, total_pages)
               VALUES (:id, :bundle_id, :version_id, :entries, :docs, :pages)""",
            {
                "id": index.id,
                "bundle_id": bundle_id,
                "version_id": version_id,
                "entries": json.dumps(index.to_dict()["entries"]),
                "docs": index.document_count,
                "pages": index.total_pages,
            },
        )

        if self._event_bus:
            await self._event_bus.emit(
                "bundle.index.generated",
                {"bundle_id": bundle_id, "version_id": version_id, "document_count": len(pages)},
                source="bundle-shard",
            )

        return index.to_dict()

    # ------------------------------------------------------------------
    # Add / Remove Documents
    # ------------------------------------------------------------------

    async def add_document(self, bundle_id: str, document_id: str, position: int | None = None, **doc_meta) -> dict:
        """
        Add a single document to a bundle at the given position.

        If position is None, appends to end. After insertion, renumbers
        all subsequent pages for continuous pagination.

        Args:
            bundle_id: The bundle to add to.
            document_id: The document to add.
            position: Insert position (0-indexed). None = append.
            **doc_meta: Optional metadata: title, filename, page_count, status, section_label, notes.

        Returns:
            Dict with the new page entry details.
        """
        bundle_row = await self._db.fetch_one(
            "SELECT * FROM arkham_bundle.bundles WHERE id = :id",
            {"id": bundle_id},
        )
        if not bundle_row:
            raise ValueError(f"Bundle not found: {bundle_id}")

        current_version_id = bundle_row.get("current_version_id", "")

        # Fetch existing pages
        existing = await self._db.fetch_all(
            """SELECT * FROM arkham_bundle.pages
               WHERE bundle_id = :bundle_id AND version_id = :version_id
               ORDER BY position ASC""",
            {"bundle_id": bundle_id, "version_id": current_version_id},
        )

        docs = [dict(row) for row in existing]

        # Determine insert position
        if position is None or position >= len(docs):
            position = len(docs)

        # Build new doc entry
        page_count = doc_meta.get("page_count", 1)
        new_doc = {
            "id": str(uuid.uuid4()),
            "bundle_id": bundle_id,
            "version_id": current_version_id,
            "document_id": document_id,
            "document_title": doc_meta.get("title", ""),
            "document_filename": doc_meta.get("filename", ""),
            "position": position,
            "document_page_count": page_count,
            "bundle_page_start": 0,  # will be recalculated
            "bundle_page_end": 0,
            "document_status": doc_meta.get("status", "unknown"),
            "section_label": doc_meta.get("section_label", ""),
            "notes": doc_meta.get("notes", ""),
        }

        # Insert into list
        docs.insert(position, new_doc)

        # Renumber all pages
        current_page = 1
        for i, d in enumerate(docs):
            d["position"] = i
            pc = d.get("document_page_count", 1) or 1
            d["bundle_page_start"] = current_page
            d["bundle_page_end"] = current_page + pc - 1
            current_page += pc

        # Persist the new document
        await self._db.execute(
            """INSERT INTO arkham_bundle.pages
               (id, bundle_id, version_id, document_id, document_title, document_filename,
                position, document_page_count, bundle_page_start, bundle_page_end,
                document_status, section_label, notes)
               VALUES (:id, :bundle_id, :version_id, :document_id, :document_title,
                       :document_filename, :position, :document_page_count,
                       :bundle_page_start, :bundle_page_end,
                       :document_status, :section_label, :notes)""",
            new_doc,
        )

        # Update positions and page numbers for shifted docs
        for d in docs:
            if d["id"] != new_doc["id"]:
                await self._db.execute(
                    """UPDATE arkham_bundle.pages SET
                          position = :position,
                          bundle_page_start = :bundle_page_start,
                          bundle_page_end = :bundle_page_end
                       WHERE id = :id""",
                    {
                        "id": d["id"],
                        "position": d["position"],
                        "bundle_page_start": d["bundle_page_start"],
                        "bundle_page_end": d["bundle_page_end"],
                    },
                )

        # Update bundle total pages
        total_pages = docs[-1]["bundle_page_end"] if docs else 0
        await self._db.execute(
            "UPDATE arkham_bundle.bundles SET total_pages = :pages, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": bundle_id, "pages": total_pages},
        )

        return {
            "document_id": document_id,
            "position": position,
            "bundle_page_start": new_doc["bundle_page_start"],
            "bundle_page_end": new_doc["bundle_page_end"],
            "total_pages": total_pages,
        }

    async def remove_document(self, bundle_id: str, document_id: str) -> None:
        """
        Remove a document from the bundle and renumber remaining pages.

        Args:
            bundle_id: The bundle to remove from.
            document_id: The document to remove.
        """
        bundle_row = await self._db.fetch_one(
            "SELECT * FROM arkham_bundle.bundles WHERE id = :id",
            {"id": bundle_id},
        )
        if not bundle_row:
            raise ValueError(f"Bundle not found: {bundle_id}")

        current_version_id = bundle_row.get("current_version_id", "")

        # Delete the page record
        await self._db.execute(
            """DELETE FROM arkham_bundle.pages
               WHERE bundle_id = :bundle_id AND version_id = :version_id AND document_id = :document_id""",
            {"bundle_id": bundle_id, "version_id": current_version_id, "document_id": document_id},
        )

        # Fetch remaining pages
        remaining = await self._db.fetch_all(
            """SELECT * FROM arkham_bundle.pages
               WHERE bundle_id = :bundle_id AND version_id = :version_id
               ORDER BY position ASC""",
            {"bundle_id": bundle_id, "version_id": current_version_id},
        )

        # Renumber
        current_page = 1
        for i, row in enumerate(remaining):
            pc = row.get("document_page_count", 1) or 1
            await self._db.execute(
                """UPDATE arkham_bundle.pages SET
                      position = :position,
                      bundle_page_start = :page_start,
                      bundle_page_end = :page_end
                   WHERE id = :id""",
                {
                    "id": row["id"],
                    "position": i,
                    "page_start": current_page,
                    "page_end": current_page + pc - 1,
                },
            )
            current_page += pc

        # Update bundle total
        total_pages = (current_page - 1) if remaining else 0
        await self._db.execute(
            "UPDATE arkham_bundle.bundles SET total_pages = :pages, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": bundle_id, "pages": total_pages},
        )

    # ------------------------------------------------------------------
    # Compare Versions
    # ------------------------------------------------------------------

    async def compare_versions(self, version_a_id: str, version_b_id: str) -> dict:
        """
        Compare two bundle versions.

        Returns:
            Dict with added_docs, removed_docs, reordered_docs, page_count_diff.
        """
        pages_a = await self._db.fetch_all(
            "SELECT * FROM arkham_bundle.pages WHERE version_id = :id ORDER BY position ASC",
            {"id": version_a_id},
        )
        pages_b = await self._db.fetch_all(
            "SELECT * FROM arkham_bundle.pages WHERE version_id = :id ORDER BY position ASC",
            {"id": version_b_id},
        )

        docs_a = {row["document_id"]: row for row in pages_a}
        docs_b = {row["document_id"]: row for row in pages_b}

        ids_a = set(docs_a.keys())
        ids_b = set(docs_b.keys())

        added = ids_b - ids_a
        removed = ids_a - ids_b

        # Check reordering for docs present in both
        common = ids_a & ids_b
        order_a = [row["document_id"] for row in pages_a if row["document_id"] in common]
        order_b = [row["document_id"] for row in pages_b if row["document_id"] in common]
        reordered = [doc_id for i, doc_id in enumerate(order_b) if i < len(order_a) and order_a[i] != doc_id]

        total_a = pages_a[-1]["bundle_page_end"] if pages_a else 0
        total_b = pages_b[-1]["bundle_page_end"] if pages_b else 0

        return {
            "added_docs": list(added),
            "removed_docs": list(removed),
            "reordered_docs": reordered,
            "page_count_a": total_a,
            "page_count_b": total_b,
            "page_count_diff": total_b - total_a,
        }

    # ------------------------------------------------------------------
    # Export Index as Text
    # ------------------------------------------------------------------

    async def export_index_text(self, bundle_id: str) -> str:
        """
        Export the current bundle index as formatted text following
        ET Presidential Guidance format.

        Args:
            bundle_id: The bundle to export.

        Returns:
            Formatted text string of the index.
        """
        bundle_row = await self._db.fetch_one(
            "SELECT * FROM arkham_bundle.bundles WHERE id = :id",
            {"id": bundle_id},
        )
        if not bundle_row:
            raise ValueError(f"Bundle not found: {bundle_id}")

        current_version_id = bundle_row.get("current_version_id", "")

        # Try to get existing index
        index_row = await self._db.fetch_one(
            "SELECT * FROM arkham_bundle.indices WHERE bundle_id = :bundle_id AND version_id = :version_id",
            {"bundle_id": bundle_id, "version_id": current_version_id},
        )

        if index_row:
            entries_raw = index_row.get("entries", "[]")
            if isinstance(entries_raw, str):
                entries_data = json.loads(entries_raw)
            else:
                entries_data = entries_raw

            entries = []
            for e in entries_data:
                entries.append(
                    BundleIndexEntry(
                        entry_type=IndexEntryType(e.get("entry_type", "document")),
                        position=e.get("position", 0),
                        document_id=e.get("document_id"),
                        document_title=e.get("document_title", ""),
                        document_filename=e.get("document_filename", ""),
                        bundle_page_start=e.get("bundle_page_start"),
                        bundle_page_end=e.get("bundle_page_end"),
                        document_status=DocumentStatus(e.get("document_status", "unknown")),
                        section_label=e.get("section_label", ""),
                        notes=e.get("notes", ""),
                        header_text=e.get("header_text", ""),
                    )
                )

            index = BundleIndex(
                id=index_row.get("id", ""),
                bundle_id=bundle_id,
                version_id=current_version_id,
                entries=entries,
                document_count=index_row.get("document_count", 0),
                total_pages=index_row.get("total_pages", 0),
            )

            return index.to_text()

        # Fallback: build from pages
        pages = await self._db.fetch_all(
            """SELECT * FROM arkham_bundle.pages
               WHERE bundle_id = :bundle_id AND version_id = :version_id
               ORDER BY position ASC""",
            {"bundle_id": bundle_id, "version_id": current_version_id},
        )

        entries = []
        for row in pages:
            entries.append(
                BundleIndexEntry(
                    entry_type=IndexEntryType.DOCUMENT,
                    position=row["position"],
                    document_id=row["document_id"],
                    document_title=row.get("document_title", ""),
                    document_filename=row.get("document_filename", ""),
                    bundle_page_start=row["bundle_page_start"],
                    bundle_page_end=row["bundle_page_end"],
                    document_status=DocumentStatus(row.get("document_status", "unknown")),
                    section_label=row.get("section_label", ""),
                )
            )

        total_pages = pages[-1]["bundle_page_end"] if pages else 0
        index = BundleIndex(
            id="",
            bundle_id=bundle_id,
            version_id=current_version_id,
            entries=entries,
            document_count=len(pages),
            total_pages=total_pages,
        )

        return index.to_text()
