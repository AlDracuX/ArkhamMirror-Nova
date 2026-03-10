"""Authority search and analysis engine for Oracle shard.

Provides:
- Keyword and vector search across legal authorities
- Case summarization with LLM fallback and DB caching
- Relevance scoring (LLM or keyword overlap)
- Citation chain mapping (both directions)
- Binding/persuasive classification by court hierarchy
"""

import logging
import uuid
from typing import Any

from .llm import OracleLLM

logger = logging.getLogger(__name__)

# UK court hierarchy for binding/persuasive classification.
# Higher rank = more authoritative. Courts at a higher level bind those below.
UK_COURT_HIERARCHY: dict[str, int] = {
    "Supreme Court": 5,
    "House of Lords": 5,  # Pre-2009 equivalent of Supreme Court
    "Court of Appeal": 4,
    "Employment Appeal Tribunal": 3,
    "EAT": 3,
    "High Court": 3,
    "Employment Tribunal": 1,
    "ET": 1,
}

# Courts at rank >= BINDING_THRESHOLD are binding on the Employment Tribunal
BINDING_THRESHOLD = 3


class AuthoritySearch:
    """Search, analyse and classify legal authorities.

    Combines SQL/vector search with LLM-assisted analysis. All LLM-dependent
    methods include a deterministic fallback so the shard works without an LLM.
    """

    def __init__(
        self,
        db,
        vectors_service=None,
        event_bus=None,
        llm_service=None,
    ):
        self._db = db
        self._vectors = vectors_service
        self._events = event_bus
        self._llm = OracleLLM(llm_service)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        jurisdiction: str | None = None,
        claim_types: list[str] | None = None,
    ) -> list[dict]:
        """Search authorities by keyword, jurisdiction, and claim_type.

        Uses vector search if vectors service is available, otherwise falls
        back to SQL ILIKE on title, summary, and citation.
        """
        if self._vectors:
            return await self._search_vectors(query, jurisdiction, claim_types)
        return await self._search_sql(query, jurisdiction, claim_types)

    async def _search_vectors(
        self,
        query: str,
        jurisdiction: str | None,
        claim_types: list[str] | None,
    ) -> list[dict]:
        """Vector-based semantic search with optional SQL filters."""
        try:
            results = await self._vectors.search(query, collection="oracle_authorities", limit=20)
            if results:
                # Vector search returns IDs; fetch full records and apply filters
                ids = [r.get("id") or r.get("metadata", {}).get("id") for r in results if r]
                ids = [i for i in ids if i]
                if ids:
                    return await self._fetch_by_ids(ids, jurisdiction, claim_types)
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to SQL: {e}")

        # Fallback to SQL
        return await self._search_sql(query, jurisdiction, claim_types)

    async def _search_sql(
        self,
        query: str,
        jurisdiction: str | None,
        claim_types: list[str] | None,
    ) -> list[dict]:
        """SQL ILIKE keyword search."""
        conditions = ["(title ILIKE :query OR summary ILIKE :query OR citation ILIKE :query)"]
        params: dict[str, Any] = {"query": f"%{query}%"}

        if jurisdiction:
            conditions.append("jurisdiction = :jurisdiction")
            params["jurisdiction"] = jurisdiction

        if claim_types:
            conditions.append("claim_types && :claim_types")
            params["claim_types"] = claim_types

        where = "WHERE " + " AND ".join(conditions)
        sql = f"SELECT * FROM arkham_oracle.legal_authorities {where} ORDER BY created_at DESC"

        rows = await self._db.fetch_all(sql, params)
        return [dict(r) for r in rows]

    async def _fetch_by_ids(
        self,
        ids: list[str],
        jurisdiction: str | None,
        claim_types: list[str] | None,
    ) -> list[dict]:
        """Fetch authorities by IDs with optional filters."""
        conditions = ["id = ANY(:ids)"]
        params: dict[str, Any] = {"ids": ids}

        if jurisdiction:
            conditions.append("jurisdiction = :jurisdiction")
            params["jurisdiction"] = jurisdiction

        if claim_types:
            conditions.append("claim_types && :claim_types")
            params["claim_types"] = claim_types

        where = "WHERE " + " AND ".join(conditions)
        sql = f"SELECT * FROM arkham_oracle.legal_authorities {where}"

        rows = await self._db.fetch_all(sql, params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Summarize
    # ------------------------------------------------------------------

    async def summarize_case(self, authority_id: str) -> dict:
        """Generate or retrieve a case summary.

        Checks the case_summaries cache first. If no cached summary exists
        and an LLM is available, generates one and stores it.
        """
        # Check cache
        cached = await self._db.fetch_one(
            "SELECT * FROM arkham_oracle.case_summaries WHERE authority_id = :authority_id",
            {"authority_id": authority_id},
        )
        if cached:
            row = dict(cached)
            return {
                "facts": row.get("facts", ""),
                "decision": row.get("decision", ""),
                "legal_principles": row.get("legal_principles", []),
            }

        # Cache miss - try LLM generation
        if not self._llm.available:
            return {"facts": "", "decision": "", "legal_principles": []}

        authority = await self._db.fetch_one(
            "SELECT * FROM arkham_oracle.legal_authorities WHERE id = :id",
            {"id": authority_id},
        )
        if not authority:
            return {"facts": "", "decision": "", "legal_principles": []}

        auth = dict(authority)
        result = await self._llm.summarize_case(
            title=auth.get("title", ""),
            court=auth.get("court", ""),
            citation=auth.get("citation", ""),
            text=auth.get("full_text") or auth.get("summary", ""),
        )

        summary_dict = {
            "facts": result.facts,
            "decision": result.decision,
            "legal_principles": result.legal_principles,
        }

        # Store in cache
        if result.facts or result.decision:
            summary_id = str(uuid.uuid4())
            try:
                await self._db.execute(
                    """
                    INSERT INTO arkham_oracle.case_summaries (id, authority_id, facts, decision, legal_principles)
                    VALUES (:id, :authority_id, :facts, :decision, :legal_principles)
                    """,
                    {
                        "id": summary_id,
                        "authority_id": authority_id,
                        "facts": result.facts,
                        "decision": result.decision,
                        "legal_principles": result.legal_principles,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to cache case summary: {e}")

        return summary_dict

    # ------------------------------------------------------------------
    # Relevance Scoring
    # ------------------------------------------------------------------

    async def score_relevance(self, authority_id: str, case_facts: str) -> float:
        """Score how relevant an authority is to current case facts.

        Returns 0.0-1.0. Uses LLM if available, otherwise keyword overlap.
        """
        authority = await self._db.fetch_one(
            "SELECT * FROM arkham_oracle.legal_authorities WHERE id = :id",
            {"id": authority_id},
        )
        if not authority:
            return 0.0

        auth = dict(authority)

        # Try LLM scoring first
        if self._llm.available:
            result = await self._llm.score_relevance(
                title=auth.get("title", ""),
                summary=auth.get("summary", ""),
                court=auth.get("court", ""),
                claim_types=auth.get("claim_types", []),
                case_facts=case_facts,
            )
            if result.score > 0.0:
                return result.score

        # Fallback: keyword overlap scoring
        return self._keyword_overlap_score(auth, case_facts)

    def _keyword_overlap_score(self, authority: dict, case_facts: str) -> float:
        """Score relevance by keyword overlap between authority and case facts."""
        # Build authority text from available fields
        auth_text_parts = [
            authority.get("title", ""),
            authority.get("summary", ""),
        ]
        # Include claim_types and relevance_tags as keywords
        claim_types = authority.get("claim_types", []) or []
        relevance_tags = authority.get("relevance_tags", []) or []
        auth_text_parts.extend(claim_types)
        auth_text_parts.extend(relevance_tags)

        auth_text = " ".join(auth_text_parts).lower()
        facts_text = case_facts.lower()

        # Tokenize (simple word splitting, remove very short words)
        auth_words = {w for w in auth_text.split() if len(w) > 2}
        facts_words = {w for w in facts_text.split() if len(w) > 2}

        if not auth_words or not facts_words:
            return 0.0

        intersection = auth_words & facts_words
        # Jaccard similarity
        union = auth_words | facts_words
        jaccard = len(intersection) / len(union) if union else 0.0

        # Also compute overlap ratio relative to facts (how much of the query is covered)
        coverage = len(intersection) / len(facts_words) if facts_words else 0.0

        # Weighted combination: coverage matters more than pure Jaccard
        score = 0.4 * jaccard + 0.6 * coverage
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Citation Chain
    # ------------------------------------------------------------------

    async def map_citation_chain(self, authority_id: str) -> list[dict]:
        """Build citation chain: which authorities this one cites and which cite it.

        Queries the authority_chains table in both directions.
        """
        chain: list[dict] = []

        # Direction 1: authorities this one cites
        cites_rows = await self._db.fetch_all(
            "SELECT * FROM arkham_oracle.authority_chains WHERE source_authority_id = :id",
            {"id": authority_id},
        )
        for row in cites_rows:
            r = dict(row)
            chain.append(
                {
                    "chain_id": r.get("id"),
                    "authority_id": r.get("cited_authority_id"),
                    "relationship_type": r.get("relationship_type", "cites"),
                    "direction": "cites",
                }
            )

        # Direction 2: authorities that cite this one
        cited_by_rows = await self._db.fetch_all(
            "SELECT * FROM arkham_oracle.authority_chains WHERE cited_authority_id = :id",
            {"id": authority_id},
        )
        for row in cited_by_rows:
            r = dict(row)
            chain.append(
                {
                    "chain_id": r.get("id"),
                    "authority_id": r.get("source_authority_id"),
                    "relationship_type": r.get("relationship_type", "cites"),
                    "direction": "cited_by",
                }
            )

        return chain

    # ------------------------------------------------------------------
    # Binding / Persuasive Classification
    # ------------------------------------------------------------------

    async def classify_binding_persuasive(self, authority_id: str) -> dict:
        """Classify authority as binding or persuasive based on UK court hierarchy.

        Supreme Court / House of Lords > Court of Appeal > EAT / High Court > ET.
        Authorities from courts at EAT level and above are binding on the ET.
        ET decisions are persuasive only.

        Returns:
            dict with classification, court, and reasoning.
        """
        authority = await self._db.fetch_one(
            "SELECT * FROM arkham_oracle.legal_authorities WHERE id = :id",
            {"id": authority_id},
        )
        if not authority:
            return {"classification": "unknown", "court": "Unknown", "reasoning": "Authority not found"}

        auth = dict(authority)
        court = auth.get("court", "Unknown") or "Unknown"

        rank = UK_COURT_HIERARCHY.get(court, 0)

        if rank >= BINDING_THRESHOLD:
            classification = "binding"
            reasoning = f"{court} decisions are binding on the Employment Tribunal. Court hierarchy rank: {rank}/5."
        elif rank > 0:
            classification = "persuasive"
            reasoning = (
                f"{court} decisions are persuasive but not binding on the Employment Tribunal. "
                f"Court hierarchy rank: {rank}/5."
            )
        else:
            classification = "persuasive"
            reasoning = (
                f"{court} is not in the standard UK employment court hierarchy. Treated as persuasive authority."
            )

        return {
            "classification": classification,
            "court": court,
            "reasoning": reasoning,
        }

    # ------------------------------------------------------------------
    # Research (LLM-powered comprehensive query)
    # ------------------------------------------------------------------

    async def research(self, query: str, context: str = "") -> dict:
        """Conduct comprehensive legal research using LLM.

        Falls back to a search-based response if LLM is unavailable.
        """
        if self._llm.available:
            result = await self._llm.research(query=query, context=context)
            research_dict = {
                "analysis": result.analysis,
                "key_authorities": result.key_authorities,
                "legal_principles": result.legal_principles,
                "recommendations": result.recommendations,
            }

            # Emit event
            if self._events:
                try:
                    await self._events.emit(
                        "oracle.research.completed",
                        {"query": query, "has_results": bool(result.analysis)},
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit research event: {e}")

            return research_dict

        # Fallback: search-based response
        search_results = await self.search(query=query)
        return {
            "analysis": f"Found {len(search_results)} authorities matching query (LLM unavailable for deeper analysis)",
            "key_authorities": [r.get("citation", r.get("title", "")) for r in search_results[:5]],
            "legal_principles": [],
            "recommendations": ["Enable LLM service for comprehensive legal research"],
        }
