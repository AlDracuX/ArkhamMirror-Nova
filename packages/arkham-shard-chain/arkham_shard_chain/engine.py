"""Chain Engine - Core algorithmic logic for chain-of-custody verification.

Purely algorithmic — no LLM needed. Handles hash verification, tampering
detection, provenance report generation, and integrity scoring.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ChainEngine:
    """
    Core engine for chain-of-custody integrity analysis.

    Provides hash verification, tampering detection, provenance reporting,
    and integrity scoring — all purely algorithmic, no LLM required.
    """

    def __init__(self, db=None, event_bus=None):
        self._db = db
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # verify_hash
    # ------------------------------------------------------------------

    async def verify_hash(self, document_id: str, current_hash: str) -> dict:
        """
        Compare current hash against the most recent stored hash.

        Returns:
            {verified: bool, stored_hash: str|None, current_hash: str, document_id: str}
        """
        stored_hash = None

        if self._db:
            row = await self._db.fetch_one(
                "SELECT sha256_hash FROM arkham_chain.hashes "
                "WHERE document_id = :doc_id ORDER BY created_at DESC LIMIT 1",
                {"doc_id": document_id},
            )
            if row:
                stored_hash = row["sha256_hash"]

        verified = stored_hash is not None and stored_hash == current_hash

        return {
            "verified": verified,
            "stored_hash": stored_hash,
            "current_hash": current_hash,
            "document_id": document_id,
        }

    # ------------------------------------------------------------------
    # detect_tampering
    # ------------------------------------------------------------------

    async def detect_tampering(self, document_id: str) -> dict:
        """
        Check all hashes for a document across custody events.
        Flag mismatches where consecutive hashes differ.

        Returns:
            {tampered: bool, document_id: str,
             mismatches: [{event_id, expected_hash, actual_hash}]}
        """
        rows = await self._fetch_chain_with_hashes(document_id)

        mismatches: list[dict] = []
        if len(rows) > 1:
            baseline_hash = rows[0]["sha256_hash"]
            for row in rows[1:]:
                if row["sha256_hash"] != baseline_hash:
                    mismatches.append(
                        {
                            "event_id": row["event_id"],
                            "expected_hash": baseline_hash,
                            "actual_hash": row["sha256_hash"],
                        }
                    )
                # Update baseline to current for next comparison
                baseline_hash = row["sha256_hash"]

        tampered = len(mismatches) > 0

        # Emit event if tampering detected
        if tampered and self._event_bus:
            await self._event_bus.emit(
                "chain.tampering.detected",
                {
                    "document_id": document_id,
                    "mismatch_count": len(mismatches),
                    "mismatches": mismatches,
                },
                source="chain-engine",
            )

        return {
            "tampered": tampered,
            "document_id": document_id,
            "mismatches": mismatches,
        }

    # ------------------------------------------------------------------
    # generate_provenance_report
    # ------------------------------------------------------------------

    async def generate_provenance_report(self, document_id: str) -> dict:
        """
        Generate a timeline of all custody events for a document.

        Returns:
            {report_id: str, document_id: str,
             events: [{timestamp, action, actor, hash}],
             integrity_score: float}
        """
        rows = []
        if self._db:
            rows = await self._db.fetch_all(
                "SELECT id, action, actor, sha256_hash, timestamp "
                "FROM arkham_chain.custody_events ce "
                "JOIN arkham_chain.hashes h ON h.document_id = ce.document_id "
                "WHERE ce.document_id = :doc_id "
                "ORDER BY ce.timestamp ASC",
                {"doc_id": document_id},
            )

        events = []
        for row in rows:
            ts = row.get("timestamp")
            events.append(
                {
                    "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "action": row.get("action", ""),
                    "actor": row.get("actor", ""),
                    "hash": row.get("sha256_hash", ""),
                }
            )

        # Compute integrity score for the report
        integrity_score = await self.score_integrity(document_id)

        # Generate report ID and persist
        report_id = str(uuid.uuid4())
        report_data = {
            "report_id": report_id,
            "document_id": document_id,
            "events": events,
            "integrity_score": integrity_score,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._db:
            await self._db.execute(
                "INSERT INTO arkham_chain.provenance_reports "
                "(id, document_id, report_json) VALUES (:id, :doc_id, :json)",
                {
                    "id": report_id,
                    "doc_id": document_id,
                    "json": json.dumps(report_data),
                },
            )

        return report_data

    # ------------------------------------------------------------------
    # score_integrity
    # ------------------------------------------------------------------

    async def score_integrity(self, document_id: str) -> float:
        """
        Score chain integrity: 1.0 = all hashes match, all custody events linked.

        Penalties:
            - Gap in custody chain (previous_event_id missing): -0.2 per gap
            - Hash mismatch vs previous event: -0.3 per mismatch

        Returns:
            float 0.0-1.0
        """
        rows = []
        if self._db:
            rows = await self._db.fetch_all(
                "SELECT id, sha256_hash, previous_event_id, timestamp "
                "FROM arkham_chain.custody_events ce "
                "JOIN arkham_chain.hashes h ON h.document_id = ce.document_id "
                "WHERE ce.document_id = :doc_id "
                "ORDER BY ce.timestamp ASC",
                {"doc_id": document_id},
            )

        if len(rows) <= 1:
            score = 1.0
        else:
            score = 1.0
            prev_id = rows[0]["id"]
            prev_hash = rows[0]["sha256_hash"]

            for row in rows[1:]:
                # Check for gap: second+ event should reference previous
                if row.get("previous_event_id") != prev_id:
                    score -= 0.2

                # Check for hash mismatch
                if row["sha256_hash"] != prev_hash:
                    score -= 0.3

                prev_id = row["id"]
                prev_hash = row["sha256_hash"]

            score = max(0.0, score)

        # Emit verification event
        if self._event_bus:
            await self._event_bus.emit(
                "chain.integrity.verified",
                {
                    "document_id": document_id,
                    "integrity_score": score,
                },
                source="chain-engine",
            )

        return score

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fetch_chain_with_hashes(self, document_id: str) -> list[dict]:
        """Fetch custody events with their associated hashes, ordered by time."""
        if not self._db:
            return []

        return await self._db.fetch_all(
            "SELECT ce.id as event_id, h.sha256_hash, ce.action, ce.timestamp "
            "FROM arkham_chain.custody_events ce "
            "JOIN arkham_chain.hashes h ON h.document_id = ce.document_id "
            "WHERE ce.document_id = :doc_id "
            "ORDER BY ce.timestamp ASC",
            {"doc_id": document_id},
        )
