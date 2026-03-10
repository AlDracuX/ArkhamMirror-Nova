"""
CrossExam Shard - QuestionTreeBuilder Tests

Tests for domain logic: tree building, damage scoring,
impeachment sequences, and follow-up routing.
All external dependencies are mocked.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_crossexam.builder import QuestionTreeBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    return events


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def builder(mock_db, mock_events, mock_llm):
    return QuestionTreeBuilder(db=mock_db, event_bus=mock_events, llm_service=mock_llm)


@pytest.fixture
def builder_no_llm(mock_db, mock_events):
    return QuestionTreeBuilder(db=mock_db, event_bus=mock_events, llm_service=None)


# ---------------------------------------------------------------------------
# Test: damage score for material contradiction
# ---------------------------------------------------------------------------


class TestDamageScore:
    """test_damage_score_material_contradiction -- high score for material fact conflict."""

    @pytest.mark.asyncio
    async def test_damage_score_material_contradiction(self, builder, mock_db, mock_llm):
        """A question contradicting a material fact scores high (>= 0.7)."""
        node_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": node_id,
            "tree_id": "tree-1",
            "question_text": "You stated you never received the email, correct?",
            "expected_answer": "Yes, I never received it.",
            "alternative_answer": "Well, I may have seen it.",
            "damage_potential": 0.0,
            "metadata": json.dumps({"contradicts_document": "email-exhibit-3"}),
        }

        mock_llm.generate = AsyncMock(
            return_value=MagicMock(
                text=json.dumps(
                    {
                        "score": 0.85,
                        "reasoning": "Contradicts documentary evidence of email receipt confirmation.",
                        "factors": {
                            "material_fact": True,
                            "undermines_credibility": True,
                            "supports_case_theory": True,
                        },
                    }
                )
            )
        )

        result = await builder.score_damage(node_id)

        assert result["score"] >= 0.7
        assert "reasoning" in result
        assert len(result["reasoning"]) > 0

    @pytest.mark.asyncio
    async def test_damage_score_no_llm_fallback(self, builder_no_llm, mock_db):
        """Without LLM, score_damage uses heuristic and returns valid result."""
        node_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": node_id,
            "tree_id": "tree-1",
            "question_text": "Did you attend the meeting on 5 March?",
            "expected_answer": "No",
            "alternative_answer": "Yes",
            "damage_potential": 0.5,
            "metadata": "{}",
        }

        result = await builder_no_llm.score_damage(node_id)

        assert 0.0 <= result["score"] <= 1.0
        assert "reasoning" in result


# ---------------------------------------------------------------------------
# Test: impeachment sequence has 3 steps
# ---------------------------------------------------------------------------


class TestImpeachmentSequence:
    """test_impeachment_sequence_three_steps -- verify 3-step structure."""

    @pytest.mark.asyncio
    async def test_impeachment_sequence_three_steps(self, builder, mock_db, mock_llm, mock_events):
        """Impeachment sequence has exactly 3 steps: commit, introduce, confront."""
        contradiction_id = str(uuid.uuid4())
        mock_db.fetch_one.side_effect = [
            # First call: fetch contradiction info
            {
                "id": contradiction_id,
                "witness_id": "w-1",
                "claim_a": "I was not present at the meeting on 5 March.",
                "claim_b": "Minutes show attendee: John Smith.",
                "doc_a_id": "statement-1",
                "doc_b_id": "minutes-exhibit-2",
            },
            # Second call: fetch inserted impeachment row (not used but may be called)
            None,
        ]

        mock_llm.generate = AsyncMock(
            return_value=MagicMock(
                text=json.dumps(
                    {
                        "steps": [
                            {
                                "step": 1,
                                "type": "commit",
                                "question": "You have told the tribunal you were not at the meeting on 5 March, is that correct?",
                            },
                            {
                                "step": 2,
                                "type": "introduce",
                                "question": "I would like to refer you to the minutes at page 42. Do you see your name listed as an attendee?",
                            },
                            {
                                "step": 3,
                                "type": "confront",
                                "question": "How do you explain your name appearing in the minutes if you were not present?",
                            },
                        ]
                    }
                )
            )
        )

        seq_id = await builder.generate_impeachment_sequence(contradiction_id)

        assert seq_id is not None
        assert isinstance(seq_id, str)
        # Verify DB insert was called with 3 steps
        insert_call = mock_db.execute.call_args_list[-1]
        call_params = insert_call.args[1] if len(insert_call.args) > 1 else insert_call.kwargs.get("values", {})
        steps = json.loads(call_params.get("steps", "[]"))
        assert len(steps) == 3
        assert steps[0]["type"] == "commit"
        assert steps[1]["type"] == "introduce"
        assert steps[2]["type"] == "confront"

    @pytest.mark.asyncio
    async def test_impeachment_no_llm_generates_template(self, builder_no_llm, mock_db, mock_events):
        """Without LLM, generates template 3-step impeachment."""
        contradiction_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {
            "id": contradiction_id,
            "witness_id": "w-1",
            "claim_a": "I never signed the document.",
            "claim_b": "Signature on exhibit 5 matches witness.",
            "doc_a_id": "statement-1",
            "doc_b_id": "exhibit-5",
        }

        seq_id = await builder_no_llm.generate_impeachment_sequence(contradiction_id)

        assert seq_id is not None
        insert_call = mock_db.execute.call_args_list[-1]
        call_params = insert_call.args[1] if len(insert_call.args) > 1 else insert_call.kwargs.get("values", {})
        steps = json.loads(call_params.get("steps", "[]"))
        assert len(steps) == 3


# ---------------------------------------------------------------------------
# Test: follow-up routing
# ---------------------------------------------------------------------------


class TestFollowupRouting:
    """Follow-up routing based on actual witness answer."""

    @pytest.mark.asyncio
    async def test_followup_routing_expected_path(self, builder, mock_db):
        """Expected answer routes to the expected follow-up node."""
        node_id = str(uuid.uuid4())
        expected_follow_up = str(uuid.uuid4())
        alt_follow_up = str(uuid.uuid4())

        mock_db.fetch_one.return_value = {
            "id": node_id,
            "tree_id": "tree-1",
            "question_text": "Were you present on 5 March?",
            "expected_answer": "No, I was not present.",
            "alternative_answer": "Yes, I was there.",
            "follow_up_expected_id": expected_follow_up,
            "follow_up_alternative_id": alt_follow_up,
            "metadata": "{}",
        }

        result = await builder.route_followup(node_id, actual_answer="No, I was not there that day.")

        assert result == expected_follow_up

    @pytest.mark.asyncio
    async def test_followup_routing_alternative_path(self, builder, mock_db):
        """Unexpected/alternative answer routes to the alternative follow-up node."""
        node_id = str(uuid.uuid4())
        expected_follow_up = str(uuid.uuid4())
        alt_follow_up = str(uuid.uuid4())

        mock_db.fetch_one.return_value = {
            "id": node_id,
            "tree_id": "tree-1",
            "question_text": "Were you present on 5 March?",
            "expected_answer": "No, I was not present.",
            "alternative_answer": "Yes, I was there.",
            "follow_up_expected_id": expected_follow_up,
            "follow_up_alternative_id": alt_follow_up,
            "metadata": "{}",
        }

        result = await builder.route_followup(node_id, actual_answer="Yes, I attended that meeting.")

        assert result == alt_follow_up

    @pytest.mark.asyncio
    async def test_followup_routing_terminal(self, builder, mock_db):
        """Terminal node (no follow-ups) returns None."""
        node_id = str(uuid.uuid4())

        mock_db.fetch_one.return_value = {
            "id": node_id,
            "tree_id": "tree-1",
            "question_text": "No further questions.",
            "expected_answer": "",
            "alternative_answer": "",
            "follow_up_expected_id": None,
            "follow_up_alternative_id": None,
            "metadata": "{}",
        }

        result = await builder.route_followup(node_id, actual_answer="Whatever the answer.")

        assert result is None


# ---------------------------------------------------------------------------
# Test: build tree stores nodes
# ---------------------------------------------------------------------------


class TestBuildTree:
    """test_build_tree_stores_nodes -- verify DB persistence."""

    @pytest.mark.asyncio
    async def test_build_tree_stores_nodes(self, builder, mock_db, mock_llm, mock_events):
        """Building a tree from a statement stores the tree and nodes in DB."""
        witness_id = "w-1"
        statement_text = (
            "I started working at Bylor Ltd in January 2020. "
            "My manager was Sarah Jones. "
            "I was never told about the redundancy process. "
            "I did not receive any written warnings."
        )

        mock_llm.generate = AsyncMock(
            return_value=MagicMock(
                text=json.dumps(
                    {
                        "questions": [
                            {
                                "question": "You say you started in January 2020 - can you confirm the exact date?",
                                "expected_answer": "It was around the 6th of January.",
                                "alternative_answer": "I am not sure of the exact date.",
                                "damage_potential": 0.3,
                            },
                            {
                                "question": "You state you were never told about redundancy - did you receive any emails about restructuring?",
                                "expected_answer": "No, I did not.",
                                "alternative_answer": "There may have been some emails.",
                                "damage_potential": 0.8,
                            },
                            {
                                "question": "You claim no written warnings - I refer you to exhibit 7. Is that your signature?",
                                "expected_answer": "That is not my signature.",
                                "alternative_answer": "It looks like it could be.",
                                "damage_potential": 0.9,
                            },
                        ]
                    }
                )
            )
        )

        tree_id = await builder.build_from_statement(witness_id, statement_text)

        assert tree_id is not None
        assert isinstance(tree_id, str)

        # Verify tree insert + node inserts happened
        # At minimum: 1 tree insert + 3 node inserts = 4 execute calls
        execute_calls = mock_db.execute.call_args_list
        assert len(execute_calls) >= 4, f"Expected >= 4 DB calls, got {len(execute_calls)}"

        # Verify the tree insert
        tree_insert = str(execute_calls[0].args[0])
        assert "arkham_crossexam.question_trees" in tree_insert

        # Verify node inserts
        node_inserts = [c for c in execute_calls if "question_nodes" in str(c.args[0])]
        assert len(node_inserts) == 3

    @pytest.mark.asyncio
    async def test_build_tree_no_llm_skeleton(self, builder_no_llm, mock_db, mock_events):
        """Without LLM, build_from_statement creates a skeleton tree with placeholder nodes."""
        witness_id = "w-2"
        statement_text = "I worked there for three years and was never given a contract."

        tree_id = await builder_no_llm.build_from_statement(witness_id, statement_text)

        assert tree_id is not None
        execute_calls = mock_db.execute.call_args_list
        # Should still create tree + at least 1 placeholder node
        assert len(execute_calls) >= 2

    @pytest.mark.asyncio
    async def test_build_tree_emits_event(self, builder, mock_db, mock_llm, mock_events):
        """After building a tree, emits crossexam.plan.generated event."""
        mock_llm.generate = AsyncMock(
            return_value=MagicMock(
                text=json.dumps(
                    {
                        "questions": [
                            {
                                "question": "Test question?",
                                "expected_answer": "Yes",
                                "alternative_answer": "No",
                                "damage_potential": 0.5,
                            },
                        ]
                    }
                )
            )
        )

        await builder.build_from_statement("w-1", "Test statement text here.")

        mock_events.emit.assert_called_once()
        event_name = mock_events.emit.call_args.args[0]
        assert event_name == "crossexam.plan.generated"
