"""QuestionTreeBuilder - Core domain logic for cross-examination planning.

Builds question trees from witness statements, scores damage potential,
generates impeachment sequences, and routes follow-up questions based
on actual witness answers.
"""

import json
import logging
import re
import uuid
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


class QuestionTreeBuilder:
    """
    Builds and manages cross-examination question trees.

    Integrates with LLM for intelligent question generation but falls back
    to heuristic/template approaches when LLM is unavailable.
    """

    def __init__(self, db=None, event_bus=None, llm_service=None):
        """
        Initialize the builder.

        Args:
            db: Database service (Frame's database)
            event_bus: EventBus for inter-shard communication
            llm_service: LLM service for AI-assisted generation
        """
        self._db = db
        self._event_bus = event_bus
        self._llm_service = llm_service

    # -------------------------------------------------------------------------
    # Build question tree from witness statement
    # -------------------------------------------------------------------------

    async def build_from_statement(self, witness_id: str, statement_text: str) -> str:
        """
        Build a question tree from a witness statement.

        Uses LLM to generate probing questions. If LLM is unavailable,
        creates a skeleton tree with placeholder questions extracted
        from statement sentences.

        Args:
            witness_id: ID of the witness
            statement_text: Full text of the witness statement

        Returns:
            tree_id: ID of the created question tree
        """
        tree_id = str(uuid.uuid4())

        # Insert the tree record
        await self._db.execute(
            """
            INSERT INTO arkham_crossexam.question_trees
            (id, witness_id, title, description, status)
            VALUES (:id, :witness_id, :title, :description, :status)
            """,
            {
                "id": tree_id,
                "witness_id": witness_id,
                "title": f"Cross-examination tree for witness {witness_id}",
                "description": f"Auto-generated from statement ({len(statement_text)} chars)",
                "status": "active",
            },
        )

        if self._llm_service:
            questions = await self._build_questions_llm(statement_text)
        else:
            questions = self._build_questions_skeleton(statement_text)

        # Insert question nodes
        root_node_id = None
        for i, q in enumerate(questions):
            node_id = str(uuid.uuid4())
            if i == 0:
                root_node_id = node_id

            await self._db.execute(
                """
                INSERT INTO arkham_crossexam.question_nodes
                (id, tree_id, parent_id, question_text, expected_answer,
                 alternative_answer, damage_potential, status)
                VALUES (:id, :tree_id, :parent_id, :question_text, :expected_answer,
                        :alternative_answer, :damage_potential, :status)
                """,
                {
                    "id": node_id,
                    "tree_id": tree_id,
                    "parent_id": root_node_id if i > 0 else None,
                    "question_text": q.get("question", ""),
                    "expected_answer": q.get("expected_answer", ""),
                    "alternative_answer": q.get("alternative_answer", ""),
                    "damage_potential": q.get("damage_potential", 0.0),
                    "status": "pending",
                },
            )

        # Update tree with root node
        if root_node_id:
            await self._db.execute(
                "UPDATE arkham_crossexam.question_trees SET root_node_id = :root WHERE id = :id",
                {"root": root_node_id, "id": tree_id},
            )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "crossexam.plan.generated",
                {"tree_id": tree_id, "witness_id": witness_id, "question_count": len(questions)},
                source="crossexam-shard",
            )

        logger.info(f"Built question tree {tree_id} with {len(questions)} nodes for witness {witness_id}")
        return tree_id

    async def _build_questions_llm(self, statement_text: str) -> list[dict]:
        """Generate questions using LLM."""
        try:
            from .llm import CrossExamLLM

            llm = CrossExamLLM(llm_service=self._llm_service)
            generated = await llm.generate_questions(statement_text)
            return [
                {
                    "question": q.question,
                    "expected_answer": q.expected_answer,
                    "alternative_answer": q.alternative_answer,
                    "damage_potential": q.damage_potential,
                }
                for q in generated
            ]
        except Exception as e:
            logger.error(f"LLM question generation failed, falling back to skeleton: {e}")
            return self._build_questions_skeleton(statement_text)

    def _build_questions_skeleton(self, statement_text: str) -> list[dict]:
        """Generate skeleton placeholder questions from statement sentences."""
        sentences = [s.strip() for s in re.split(r"[.!?]+", statement_text) if s.strip() and len(s.strip()) > 15]

        questions = []
        for sentence in sentences[:8]:  # Cap at 8 questions
            questions.append(
                {
                    "question": f"You state: '{sentence}' - can you provide more detail on this?",
                    "expected_answer": "The witness confirms or elaborates.",
                    "alternative_answer": "The witness equivocates or contradicts.",
                    "damage_potential": 0.3,
                }
            )

        # Always have at least one question
        if not questions:
            questions.append(
                {
                    "question": "Can you confirm the contents of your witness statement are true?",
                    "expected_answer": "Yes, the statement is true.",
                    "alternative_answer": "There are some corrections I need to make.",
                    "damage_potential": 0.2,
                }
            )

        return questions

    # -------------------------------------------------------------------------
    # Score damage potential
    # -------------------------------------------------------------------------

    async def score_damage(self, node_id: str) -> dict:
        """
        Score the damage potential of a question node.

        Factors:
        - Contradicts witness on a material fact
        - Undermines credibility
        - Supports case theory

        Args:
            node_id: ID of the question node

        Returns:
            Dict with score (0.0-1.0) and reasoning
        """
        row = await self._db.fetch_one(
            "SELECT * FROM arkham_crossexam.question_nodes WHERE id = :id",
            {"id": node_id},
        )

        if not row:
            return {"score": 0.0, "reasoning": "Node not found"}

        question_text = row.get("question_text", "")
        metadata_raw = row.get("metadata", "{}")
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                metadata = {}
        else:
            metadata = metadata_raw or {}

        if self._llm_service:
            return await self._score_damage_llm(question_text, metadata)
        else:
            return self._score_damage_heuristic(row, metadata)

    async def _score_damage_llm(self, question_text: str, metadata: dict) -> dict:
        """Score damage using LLM."""
        try:
            from .llm import CrossExamLLM

            llm = CrossExamLLM(llm_service=self._llm_service)
            context = json.dumps(metadata) if metadata else ""
            assessment = await llm.assess_damage(question_text, context=context)
            return {
                "score": max(0.0, min(1.0, assessment.score)),
                "reasoning": assessment.reasoning,
                "factors": assessment.factors,
            }
        except Exception as e:
            logger.error(f"LLM damage scoring failed: {e}")
            return {"score": 0.5, "reasoning": f"LLM scoring failed: {e}"}

    def _score_damage_heuristic(self, row: dict, metadata: dict) -> dict:
        """Heuristic damage scoring without LLM."""
        score = float(row.get("damage_potential", 0.3))

        # Boost if metadata indicates documentary contradiction
        if metadata.get("contradicts_document"):
            score = min(1.0, score + 0.3)

        reasoning_parts = []
        if metadata.get("contradicts_document"):
            reasoning_parts.append("Contradicts documentary evidence")
        if score >= 0.7:
            reasoning_parts.append("High damage potential based on question characteristics")
        else:
            reasoning_parts.append("Moderate damage potential")

        return {
            "score": max(0.0, min(1.0, score)),
            "reasoning": ". ".join(reasoning_parts) if reasoning_parts else "Heuristic assessment",
        }

    # -------------------------------------------------------------------------
    # Generate impeachment sequence
    # -------------------------------------------------------------------------

    async def generate_impeachment_sequence(self, contradiction_id: str) -> str:
        """
        Generate a 3-step impeachment sequence from a detected contradiction.

        Steps:
        1. COMMIT: Lock the witness into their position
        2. INTRODUCE: Present the contradicting document
        3. CONFRONT: Ask the witness to explain the contradiction

        Args:
            contradiction_id: ID of the detected contradiction

        Returns:
            impeachment_sequence_id
        """
        # Fetch contradiction details
        row = await self._db.fetch_one(
            "SELECT * FROM arkham_crossexam.impeachment_sequences WHERE id = :id "
            "UNION ALL "
            "SELECT id, NULL as tenant_id, '' as witness_id, '' as title, "
            "'' as conflict_description, NULL as statement_claim_id, "
            "NULL as document_evidence_id, '[]'::jsonb as steps, "
            "'active' as status, NULL as created_at, NULL as updated_at "
            "FROM (SELECT :id as id) t WHERE FALSE",
            {"id": contradiction_id},
        )

        # Try fetching from a generic contradiction source (cross-shard via event data)
        if not row:
            # The contradiction data should come from the contradictions shard event
            # We query our own local storage or use the ID to look up what we cached
            row = await self._db.fetch_one(
                "SELECT * FROM arkham_crossexam.question_nodes WHERE metadata::text LIKE :pattern",
                {"pattern": f"%{contradiction_id}%"},
            )

        # If we still have contradiction data passed (from event handler), use it directly
        # This handles the common case where contradiction data is fetched from the event payload
        if not row:
            logger.warning(f"Contradiction {contradiction_id} not found in local storage, using ID as reference")
            row = {
                "id": contradiction_id,
                "witness_id": "unknown",
                "claim_a": "Statement claim (see contradiction record)",
                "claim_b": "Documentary evidence (see contradiction record)",
                "doc_a_id": "statement",
                "doc_b_id": "document",
            }

        claim_a = row.get("claim_a", "")
        claim_b = row.get("claim_b", "")
        witness_id = row.get("witness_id", "unknown")
        doc_a_ref = row.get("doc_a_id", "statement")
        doc_b_ref = row.get("doc_b_id", "document")

        if self._llm_service:
            steps = await self._generate_impeachment_llm(claim_a, claim_b, doc_a_ref, doc_b_ref)
        else:
            steps = self._generate_impeachment_template(claim_a, claim_b, doc_a_ref, doc_b_ref)

        # Store the impeachment sequence
        seq_id = str(uuid.uuid4())
        await self._db.execute(
            """
            INSERT INTO arkham_crossexam.impeachment_sequences
            (id, witness_id, title, conflict_description, steps, status)
            VALUES (:id, :witness_id, :title, :conflict_description, :steps, :status)
            """,
            {
                "id": seq_id,
                "witness_id": witness_id,
                "title": f"Impeachment: {claim_a[:60]}..." if len(claim_a) > 60 else f"Impeachment: {claim_a}",
                "conflict_description": f"Statement: {claim_a} vs Document: {claim_b}",
                "steps": json.dumps(
                    [
                        {"step": s.get("step", i + 1), "type": s.get("type", ""), "question": s.get("question", "")}
                        for i, s in enumerate(steps)
                    ]
                ),
                "status": "active",
            },
        )

        # Emit event
        if self._event_bus:
            await self._event_bus.emit(
                "crossexam.impeachment.created",
                {"impeachment_id": seq_id, "contradiction_id": contradiction_id, "witness_id": witness_id},
                source="crossexam-shard",
            )

        logger.info(f"Generated impeachment sequence {seq_id} from contradiction {contradiction_id}")
        return seq_id

    async def _generate_impeachment_llm(self, claim_a: str, claim_b: str, doc_a_ref: str, doc_b_ref: str) -> list[dict]:
        """Generate impeachment steps using LLM."""
        try:
            from .llm import CrossExamLLM

            llm = CrossExamLLM(llm_service=self._llm_service)
            steps = await llm.suggest_impeachment(claim_a, claim_b, doc_a_ref, doc_b_ref)
            return [{"step": s.step, "type": s.type, "question": s.question} for s in steps]
        except Exception as e:
            logger.error(f"LLM impeachment generation failed: {e}")
            return self._generate_impeachment_template(claim_a, claim_b, doc_a_ref, doc_b_ref)

    def _generate_impeachment_template(self, claim_a: str, claim_b: str, doc_a_ref: str, doc_b_ref: str) -> list[dict]:
        """Generate template impeachment steps without LLM."""
        return [
            {
                "step": 1,
                "type": "commit",
                "question": f"You have stated in your witness statement that '{claim_a}'. Is that correct?",
            },
            {
                "step": 2,
                "type": "introduce",
                "question": f"I would like to refer you to {doc_b_ref}. This document indicates: '{claim_b}'. Do you see that?",
            },
            {
                "step": 3,
                "type": "confront",
                "question": "How do you reconcile your statement with what this document shows?",
            },
        ]

    # -------------------------------------------------------------------------
    # Route follow-up based on actual answer
    # -------------------------------------------------------------------------

    async def route_followup(self, node_id: str, actual_answer: str) -> str | None:
        """
        Given the actual answer to a question, select the appropriate follow-up path.

        Compares the actual answer against expected and alternative answers
        to determine which branch to follow.

        Args:
            node_id: ID of the question node that was answered
            actual_answer: The witness's actual answer

        Returns:
            Next node_id to follow, or None if this is a terminal node
        """
        row = await self._db.fetch_one(
            "SELECT * FROM arkham_crossexam.question_nodes WHERE id = :id",
            {"id": node_id},
        )

        if not row:
            logger.warning(f"Node {node_id} not found for follow-up routing")
            return None

        expected_id = row.get("follow_up_expected_id")
        alternative_id = row.get("follow_up_alternative_id")

        # Terminal node - no follow-ups
        if not expected_id and not alternative_id:
            return None

        expected_answer = row.get("expected_answer", "")
        alternative_answer = row.get("alternative_answer", "")

        # Calculate similarity to expected vs alternative
        expected_similarity = self._text_similarity(actual_answer, expected_answer)
        alternative_similarity = self._text_similarity(actual_answer, alternative_answer)

        if expected_similarity >= alternative_similarity:
            return expected_id
        else:
            return alternative_id

    def _text_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate text similarity using SequenceMatcher."""
        if not text_a or not text_b:
            return 0.0
        return SequenceMatcher(None, text_a.lower().strip(), text_b.lower().strip()).ratio()
