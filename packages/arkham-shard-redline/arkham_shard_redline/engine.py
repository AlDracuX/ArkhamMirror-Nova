"""Redline Engine - Core diff computation and change classification logic."""

import difflib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Legal-significance patterns for UK Employment Tribunal documents
_DATE_PATTERN = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+\d{4})?\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    re.IGNORECASE,
)

_AMOUNT_PATTERN = re.compile(
    r"\bGBP\s*[\d,]+(?:\.\d{2})?\b"
    r"|\b\xa3[\d,]+(?:\.\d{2})?\b"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b"
    r"|\b\d+(?:\.\d{2})?\s*(?:pounds?|GBP)\b",
    re.IGNORECASE,
)

_NAME_PATTERN = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Claimant|Respondent|Appellant|Judge)\b"
    r"|\b[A-Z][a-z]+\s+(?:Ltd|Limited|LLP|PLC|plc)\b",
    re.IGNORECASE,
)

_OBLIGATION_PATTERN = re.compile(
    r"\b(?:shall|must|obliged|required|directed|ordered|unless)\b"
    r"|\b(?:disclosure|hearing|witness statement|bundle|schedule)\b",
    re.IGNORECASE,
)

_WHITESPACE_ONLY = re.compile(r"^\s*$")


class RedlineEngine:
    """
    Core engine for document version comparison.

    Provides line-by-line diff computation, legal-aware change classification,
    full document comparison with DB persistence, and LLM-powered semantic diff.
    """

    def __init__(self, db=None, event_bus=None, llm_service=None):
        self._db = db
        self._event_bus = event_bus
        self._llm_service = llm_service

    # ------------------------------------------------------------------
    # compute_diff
    # ------------------------------------------------------------------

    def compute_diff(self, text_a: str, text_b: str) -> list[dict]:
        """
        Line-by-line diff using difflib.unified_diff.

        Returns a list of change dicts:
            [{type: 'add'|'delete'|'modify', line_number: int, content: str}]
        """
        lines_a = text_a.splitlines(keepends=False)
        lines_b = text_b.splitlines(keepends=False)

        raw_diffs: list[dict] = []

        # Use SequenceMatcher for precise opcodes
        matcher = difflib.SequenceMatcher(None, lines_a, lines_b)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue

            if tag == "replace":
                # Lines changed — report as modifications
                deleted = lines_a[i1:i2]
                added = lines_b[j1:j2]
                # Pair up as modifications where possible
                pairs = min(len(deleted), len(added))
                for k in range(pairs):
                    raw_diffs.append(
                        {
                            "type": "modify",
                            "line_number": i1 + k + 1,
                            "content": f"{deleted[k]} -> {added[k]}",
                        }
                    )
                # Remaining deletes
                for k in range(pairs, len(deleted)):
                    raw_diffs.append(
                        {
                            "type": "delete",
                            "line_number": i1 + k + 1,
                            "content": deleted[k],
                        }
                    )
                # Remaining adds
                for k in range(pairs, len(added)):
                    raw_diffs.append(
                        {
                            "type": "add",
                            "line_number": j1 + k + 1,
                            "content": added[k],
                        }
                    )

            elif tag == "delete":
                for k in range(i1, i2):
                    raw_diffs.append(
                        {
                            "type": "delete",
                            "line_number": k + 1,
                            "content": lines_a[k],
                        }
                    )

            elif tag == "insert":
                for k in range(j1, j2):
                    raw_diffs.append(
                        {
                            "type": "add",
                            "line_number": k + 1,
                            "content": lines_b[k],
                        }
                    )

        return raw_diffs

    # ------------------------------------------------------------------
    # classify_changes
    # ------------------------------------------------------------------

    def classify_changes(self, diffs: list[dict]) -> list[dict]:
        """
        Classify each change and add significance score (0.0-1.0).

        Legal-relevant changes (dates, amounts, names, obligations) score higher.
        Returns list of dicts with added 'significance' and 'category' fields.
        """
        classified = []
        for diff in diffs:
            content = diff.get("content", "")
            category, significance = self._classify_content(content)

            classified.append(
                {
                    **diff,
                    "significance": significance,
                    "category": category,
                }
            )

        return classified

    def _classify_content(self, content: str) -> tuple[str, float]:
        """Classify content and return (category, significance)."""
        if not content or _WHITESPACE_ONLY.match(content):
            return "formatting", 0.05

        # Check if this is a whitespace/indentation-only change
        # (content that is just extra spaces around existing text)
        stripped = content.strip()
        if not stripped or len(stripped) <= 3:
            return "formatting", 0.05

        # Detect content with significant leading/trailing whitespace
        # This indicates a whitespace/indentation formatting change
        leading = len(content) - len(content.lstrip())
        trailing = len(content) - len(content.rstrip())
        if leading >= 3 or trailing >= 3:
            return "formatting", 0.10

        # Check patterns in order of legal significance
        if _AMOUNT_PATTERN.search(content):
            return "amount", 0.85

        if _DATE_PATTERN.search(content):
            return "date", 0.75

        if _OBLIGATION_PATTERN.search(content):
            return "obligation", 0.70

        if _NAME_PATTERN.search(content):
            return "entity", 0.65

        # Default: general text change
        return "text", 0.40

    # ------------------------------------------------------------------
    # compare_documents
    # ------------------------------------------------------------------

    async def compare_documents(self, doc_a_id: str, doc_b_id: str) -> dict:
        """
        Full comparison: fetch texts from DB, compute diff, classify, store Comparison.

        Returns:
            {comparison_id, additions, deletions, modifications,
             total_changes, significant_changes}
        """
        # Fetch document texts
        text_a = await self._fetch_document_text(doc_a_id)
        text_b = await self._fetch_document_text(doc_b_id)

        # Compute diff
        diffs = self.compute_diff(text_a, text_b)

        # Classify changes
        classified = self.classify_changes(diffs)

        # Count by type
        additions = sum(1 for d in classified if d["type"] == "add")
        deletions = sum(1 for d in classified if d["type"] == "delete")
        modifications = sum(1 for d in classified if d["type"] == "modify")
        total_changes = len(classified)
        significant_changes = [d for d in classified if d.get("significance", 0) >= 0.6]

        # Store in DB
        comparison_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        if self._db:
            await self._db.execute(
                """
                INSERT INTO arkham_redline.comparisons
                (id, doc_a_id, doc_b_id, status, diff_count,
                 additions, deletions, modifications, diffs, created_at, updated_at)
                VALUES (:id, :doc_a_id, :doc_b_id, :status, :diff_count,
                        :additions, :deletions, :modifications, :diffs,
                        :created_at, :updated_at)
                """,
                {
                    "id": comparison_id,
                    "doc_a_id": doc_a_id,
                    "doc_b_id": doc_b_id,
                    "status": "complete",
                    "diff_count": total_changes,
                    "additions": additions,
                    "deletions": deletions,
                    "modifications": modifications,
                    "diffs": json.dumps(classified),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        # Emit completion event
        if self._event_bus:
            await self._event_bus.emit(
                "redline.comparison.completed",
                {
                    "comparison_id": comparison_id,
                    "doc_a_id": doc_a_id,
                    "doc_b_id": doc_b_id,
                    "total_changes": total_changes,
                },
                source="redline-engine",
            )

            # Emit significant change event if any
            if significant_changes:
                await self._event_bus.emit(
                    "redline.significant_change.detected",
                    {
                        "comparison_id": comparison_id,
                        "significant_count": len(significant_changes),
                        "changes": significant_changes,
                    },
                    source="redline-engine",
                )

        return {
            "comparison_id": comparison_id,
            "additions": additions,
            "deletions": deletions,
            "modifications": modifications,
            "total_changes": total_changes,
            "significant_changes": len(significant_changes),
        }

    # ------------------------------------------------------------------
    # semantic_diff
    # ------------------------------------------------------------------

    async def semantic_diff(self, doc_a_id: str, doc_b_id: str) -> list[dict]:
        """
        LLM-powered semantic diff: detect meaning changes vs formatting changes.

        Returns:
            [{change_type: 'substantive'|'formatting'|'clarification',
              description: str, significance: float}]
        """
        text_a = await self._fetch_document_text(doc_a_id)
        text_b = await self._fetch_document_text(doc_b_id)

        if not self._llm_service:
            logger.warning("LLM service not available, falling back to basic diff classification")
            return self._fallback_semantic_diff(text_a, text_b)

        # Build prompt for LLM
        from .llm import build_semantic_diff_prompt

        prompt = build_semantic_diff_prompt(text_a, text_b)

        try:
            response = await self._llm_service.generate(prompt)
            response_text = response.text if hasattr(response, "text") else str(response)

            # Parse JSON response
            results = json.loads(response_text) if response_text else []
            if not isinstance(results, list):
                results = [results]

            # Validate and normalize
            validated = []
            for item in results:
                validated.append(
                    {
                        "change_type": item.get("change_type", "substantive"),
                        "description": item.get("description", ""),
                        "significance": float(item.get("significance", 0.5)),
                    }
                )

            return validated

        except Exception as e:
            logger.error(f"LLM semantic diff failed: {e}")
            return self._fallback_semantic_diff(text_a, text_b)

    def _fallback_semantic_diff(self, text_a: str, text_b: str) -> list[dict]:
        """Fallback semantic diff using rule-based classification."""
        diffs = self.compute_diff(text_a, text_b)
        classified = self.classify_changes(diffs)

        results = []
        for d in classified:
            sig = d.get("significance", 0.5)
            cat = d.get("category", "text")

            if sig >= 0.6:
                change_type = "substantive"
            elif cat == "formatting":
                change_type = "formatting"
            else:
                change_type = "clarification"

            results.append(
                {
                    "change_type": change_type,
                    "description": d.get("content", ""),
                    "significance": sig,
                }
            )

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fetch_document_text(self, doc_id: str) -> str:
        """Fetch document text from the database."""
        if not self._db:
            return ""

        row = await self._db.fetch_one(
            "SELECT content FROM arkham_documents WHERE id = :id",
            {"id": doc_id},
        )

        if row:
            return row.get("content", "") if isinstance(row, dict) else ""

        return ""
