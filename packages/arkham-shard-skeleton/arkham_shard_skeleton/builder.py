"""Skeleton Builder - domain logic for argument trees and submissions.

Builds structured legal argument trees (claim -> legal test -> evidence -> authority)
and renders them into ET-compliant skeleton arguments with numbered paragraphs,
neutral citations, and bundle page references.
"""

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _parse_json_field(value: Any, default: Any = None) -> Any:
    """Parse a JSON field that may already be parsed by the database driver."""
    if value is None:
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default if default is not None else []
    return default if default is not None else []


class SkeletonBuilder:
    """Builds argument trees and renders legal submissions.

    Responsible for:
    - Building argument trees from claims (claim -> legal test elements -> evidence -> authorities)
    - Rendering submissions as structured legal text with numbered paragraphs
    - Linking oracle authorities to argument tree nodes
    - Cross-referencing bundle page numbers for document citations
    """

    def __init__(self, db, event_bus=None, llm_service=None):
        self._db = db
        self._event_bus = event_bus
        self._llm_service = llm_service

    # -------------------------------------------------------------------------
    # build_argument_tree
    # -------------------------------------------------------------------------

    async def build_argument_tree(self, claim_id: str) -> dict | None:
        """Build argument tree: claim -> legal test elements -> evidence -> authorities.

        Returns:
            Dict with {tree_id, claim_id, claim_title, nodes: [{element, evidence_refs, authority_refs}]}
            or None if claim not found.
        """
        # Fetch claim from claims schema
        claim = await self._db.fetch_one(
            "SELECT id, title, legal_test FROM arkham_claims.claims WHERE id = :claim_id",
            {"claim_id": claim_id},
        )
        if not claim:
            logger.warning(f"Claim {claim_id} not found")
            return None

        # Check for existing tree
        existing = await self._db.fetch_one(
            "SELECT id FROM arkham_skeleton.argument_trees WHERE claim_id = :claim_id",
            {"claim_id": claim_id},
        )

        claim_title = claim["title"]
        legal_test = claim.get("legal_test", "")

        # Gather evidence refs linked to this claim
        evidence_rows = await self._db.fetch_all(
            "SELECT id, description, document_id FROM arkham_claims.evidence WHERE claim_id = :claim_id",
            {"claim_id": claim_id},
        )
        evidence_refs = [row["id"] for row in evidence_rows]

        # Gather authorities linked to this claim
        authority_rows = await self._db.fetch_all(
            "SELECT id, citation, title FROM arkham_skeleton.authorities WHERE id = ANY("
            "SELECT jsonb_array_elements_text(authority_ids) FROM arkham_skeleton.argument_trees "
            "WHERE claim_id = :claim_id)",
            {"claim_id": claim_id},
        )
        authority_refs = [row["id"] for row in authority_rows]

        # Build the node structure
        nodes = []
        if legal_test:
            nodes.append(
                {
                    "element": legal_test,
                    "evidence_refs": evidence_refs,
                    "authority_refs": authority_refs,
                }
            )
        else:
            # Even without a named legal test, create one node for the claim
            nodes.append(
                {
                    "element": claim_title,
                    "evidence_refs": evidence_refs,
                    "authority_refs": authority_refs,
                }
            )

        tree_id = str(uuid.uuid4())

        # Persist the tree
        await self._db.execute(
            """
            INSERT INTO arkham_skeleton.argument_trees
            (id, claim_id, title, legal_test, evidence_refs, authority_ids, logic_summary)
            VALUES (:id, :claim_id, :title, :legal_test, :evidence_refs, :authority_ids, :logic_summary)
            """,
            {
                "id": tree_id,
                "claim_id": claim_id,
                "title": claim_title,
                "legal_test": legal_test,
                "evidence_refs": json.dumps(evidence_refs),
                "authority_ids": json.dumps(authority_refs),
                "logic_summary": "",
            },
        )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "skeleton.argument.structured",
                {"tree_id": tree_id, "claim_id": claim_id, "title": claim_title},
                source="skeleton-shard",
            )

        return {
            "tree_id": tree_id,
            "claim_id": claim_id,
            "claim_title": claim_title,
            "legal_test": legal_test,
            "nodes": nodes,
        }

    # -------------------------------------------------------------------------
    # render_submission
    # -------------------------------------------------------------------------

    async def render_submission(self, submission_id: str) -> str | None:
        """Render submission as structured legal text with numbered paragraphs,
        bundle page references, and authority citations.

        Returns:
            Formatted text string, or None if submission not found.
        """
        submission = await self._db.fetch_one(
            "SELECT * FROM arkham_skeleton.submissions WHERE id = :id",
            {"id": submission_id},
        )
        if not submission:
            return None

        title = submission["title"]
        content_structure = _parse_json_field(submission.get("content_structure"), {})
        bundle_refs = _parse_json_field(submission.get("bundle_references"), {})
        sections = content_structure.get("sections", [])

        lines: list[str] = []
        para_num = 1

        lines.append(title.upper())
        lines.append("")

        # Collect all authority IDs we need
        all_authority_ids: list[str] = []

        for section in sections:
            heading = section.get("heading", "")
            tree_ids = section.get("tree_ids", [])

            lines.append(heading.upper())
            lines.append("")

            if not tree_ids:
                continue

            # Fetch trees for this section
            placeholders = ", ".join(f":tid_{i}" for i in range(len(tree_ids)))
            params = {f"tid_{i}": tid for i, tid in enumerate(tree_ids)}
            trees = await self._db.fetch_all(
                f"SELECT * FROM arkham_skeleton.argument_trees WHERE id IN ({placeholders})",
                params,
            )

            for tree in trees:
                logic = tree.get("logic_summary", "")
                tree_auth_ids = _parse_json_field(tree.get("authority_ids"), [])
                tree_ev_refs = _parse_json_field(tree.get("evidence_refs"), [])
                all_authority_ids.extend(tree_auth_ids)

                # Build paragraph text
                para_text = f"{para_num}. {logic}"

                # Add evidence bundle page refs if available
                if tree_ev_refs and bundle_refs:
                    # Fetch evidence details to get document_ids
                    ev_placeholders = ", ".join(f":ev_{i}" for i in range(len(tree_ev_refs)))
                    ev_params = {f"ev_{i}": eid for i, eid in enumerate(tree_ev_refs)}
                    evidence_rows = await self._db.fetch_all(
                        f"SELECT id, document_id, description FROM arkham_claims.evidence "
                        f"WHERE id IN ({ev_placeholders})",
                        ev_params,
                    )
                    for ev in evidence_rows:
                        doc_id = ev.get("document_id")
                        if doc_id and doc_id in bundle_refs:
                            page = bundle_refs[doc_id]
                            para_text += f" [p.{page}]"

                lines.append(para_text)
                para_num += 1

            lines.append("")

        # Append authority citations at the end if any
        if all_authority_ids:
            unique_auth_ids = list(dict.fromkeys(all_authority_ids))
            auth_placeholders = ", ".join(f":aid_{i}" for i in range(len(unique_auth_ids)))
            auth_params = {f"aid_{i}": aid for i, aid in enumerate(unique_auth_ids)}
            authorities = await self._db.fetch_all(
                f"SELECT * FROM arkham_skeleton.authorities WHERE id IN ({auth_placeholders})",
                auth_params,
            )

            for auth in authorities:
                citation = auth.get("citation", "")
                # Inline citation in relevant paragraph
                # Also add to authorities section
                lines.append(f"  - {citation}")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # link_authorities
    # -------------------------------------------------------------------------

    async def link_authorities(self, tree_id: str, authority_ids: list[str]) -> None:
        """Link oracle authorities to argument tree nodes.

        Merges new authority IDs with existing ones (deduplicates).

        Raises:
            ValueError: If tree not found.
        """
        tree = await self._db.fetch_one(
            "SELECT id, authority_ids FROM arkham_skeleton.argument_trees WHERE id = :id",
            {"id": tree_id},
        )
        if not tree:
            raise ValueError(f"Argument tree {tree_id} not found")

        existing_ids = _parse_json_field(tree.get("authority_ids"), [])

        # Validate that the authorities exist
        if authority_ids:
            placeholders = ", ".join(f":aid_{i}" for i in range(len(authority_ids)))
            params = {f"aid_{i}": aid for i, aid in enumerate(authority_ids)}
            found = await self._db.fetch_all(
                f"SELECT id, citation FROM arkham_skeleton.authorities WHERE id IN ({placeholders})",
                params,
            )
            found_ids = {row["id"] for row in found}
        else:
            found_ids = set()

        # Merge, deduplicating
        merged = list(dict.fromkeys(existing_ids + [aid for aid in authority_ids if aid in found_ids]))

        await self._db.execute(
            "UPDATE arkham_skeleton.argument_trees SET authority_ids = :authority_ids, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": tree_id, "authority_ids": json.dumps(merged)},
        )

    # -------------------------------------------------------------------------
    # add_bundle_references
    # -------------------------------------------------------------------------

    async def add_bundle_references(self, submission_id: str, bundle_id: str) -> None:
        """Cross-reference bundle page numbers for all document citations in submission.

        Queries the arkham_bundle schema for page numbers by document_id.

        Raises:
            ValueError: If submission not found.
        """
        submission = await self._db.fetch_one(
            "SELECT id, content_structure, bundle_references FROM arkham_skeleton.submissions WHERE id = :id",
            {"id": submission_id},
        )
        if not submission:
            raise ValueError(f"Submission {submission_id} not found")

        content_structure = _parse_json_field(submission.get("content_structure"), {})
        existing_refs = _parse_json_field(submission.get("bundle_references"), {})

        # Collect all tree_ids from content_structure
        all_tree_ids = []
        for section in content_structure.get("sections", []):
            all_tree_ids.extend(section.get("tree_ids", []))

        if not all_tree_ids:
            return

        # Fetch all trees to get evidence_refs
        tree_placeholders = ", ".join(f":tid_{i}" for i in range(len(all_tree_ids)))
        tree_params = {f"tid_{i}": tid for i, tid in enumerate(all_tree_ids)}
        trees = await self._db.fetch_all(
            f"SELECT id, evidence_refs FROM arkham_skeleton.argument_trees WHERE id IN ({tree_placeholders})",
            tree_params,
        )

        # Collect all evidence IDs
        all_evidence_ids = []
        for tree in trees:
            all_evidence_ids.extend(_parse_json_field(tree.get("evidence_refs"), []))

        if not all_evidence_ids:
            return

        # Fetch evidence to get document_ids
        ev_placeholders = ", ".join(f":ev_{i}" for i in range(len(all_evidence_ids)))
        ev_params = {f"ev_{i}": eid for i, eid in enumerate(all_evidence_ids)}
        evidence_rows = await self._db.fetch_all(
            f"SELECT id, document_id FROM arkham_claims.evidence WHERE id IN ({ev_placeholders})",
            ev_params,
        )

        document_ids = [row["document_id"] for row in evidence_rows if row.get("document_id")]

        if not document_ids:
            return

        # Query bundle schema for page numbers
        doc_placeholders = ", ".join(f":doc_{i}" for i in range(len(document_ids)))
        doc_params = {f"doc_{i}": did for i, did in enumerate(document_ids)}
        doc_params["bundle_id"] = bundle_id
        bundle_pages = await self._db.fetch_all(
            f"SELECT document_id, page_number FROM arkham_bundle.bundle_pages "
            f"WHERE bundle_id = :bundle_id AND document_id IN ({doc_placeholders})",
            doc_params,
        )

        # Build updated references map
        new_refs = dict(existing_refs)
        for bp in bundle_pages:
            new_refs[bp["document_id"]] = bp["page_number"]

        # Update submission
        await self._db.execute(
            "UPDATE arkham_skeleton.submissions SET bundle_references = :bundle_references, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"id": submission_id, "bundle_references": json.dumps(new_refs)},
        )
