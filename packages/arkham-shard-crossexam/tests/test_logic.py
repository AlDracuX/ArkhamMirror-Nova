"""
CrossExam Shard - Logic Tests

Tests for models, API handler logic, and schema creation.
All external dependencies are mocked.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_crossexam.models import (
    DamageScore,
    ExamApproach,
    ExamPlan,
    ExamPlanStatus,
    ImpeachmentSequence,
    ItemStatus,
    NodeStatus,
    QuestionNode,
    QuestionTree,
)
from arkham_shard_crossexam.shard import CrossExamShard

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    events.subscribe = AsyncMock()
    events.unsubscribe = AsyncMock()
    return events


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_frame(mock_events, mock_db):
    frame = MagicMock()
    frame.database = mock_db
    frame.get_service = MagicMock(
        side_effect=lambda name: {
            "events": mock_events,
            "llm": None,
            "database": mock_db,
            "vectors": None,
            "documents": None,
        }.get(name)
    )
    return frame


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify dataclass construction and enum values."""

    def test_item_status_enum(self):
        assert ItemStatus.ACTIVE == "active"
        assert ItemStatus.ARCHIVED == "archived"
        assert ItemStatus.DELETED == "deleted"

    def test_node_status_enum(self):
        assert NodeStatus.PENDING == "pending"
        assert NodeStatus.ASKED == "asked"
        assert NodeStatus.SKIPPED == "skipped"

    def test_exam_approach_enum(self):
        assert ExamApproach.STANDARD == "standard"
        assert ExamApproach.HOSTILE == "hostile"
        assert ExamApproach.FRIENDLY == "friendly"
        assert ExamApproach.EXPERT == "expert"

    def test_exam_plan_status_enum(self):
        assert ExamPlanStatus.DRAFT == "draft"
        assert ExamPlanStatus.PREPARED == "prepared"
        assert ExamPlanStatus.IN_PROGRESS == "in_progress"
        assert ExamPlanStatus.COMPLETED == "completed"

    def test_question_node_defaults(self):
        n = QuestionNode(id="n1", tree_id="t1", question_text="?")
        assert n.id == "n1"
        assert n.status == NodeStatus.PENDING

    def test_question_tree_defaults(self):
        t = QuestionTree(id="t1", witness_id="w1", title="T")
        assert t.id == "t1"
        assert t.status == ItemStatus.ACTIVE

    def test_impeachment_sequence_defaults(self):
        s = ImpeachmentSequence(id="s1", witness_id="w1", title="S")
        assert s.id == "s1"
        assert s.status == ItemStatus.ACTIVE

    def test_damage_score_defaults(self):
        d = DamageScore(id="d1", target_id="n1")
        assert d.id == "d1"
        assert d.score == 0.0

    def test_exam_plan_defaults(self):
        p = ExamPlan(id="p1", witness_name="John Doe")
        assert p.id == "p1"
        assert p.approach == ExamApproach.STANDARD
        assert p.status == ExamPlanStatus.DRAFT
        assert p.topics == []
        assert p.questions == []
        assert p.impeachment_points == []
        assert p.witness_id is None
        assert p.case_id is None
        assert p.objectives is None


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = CrossExamShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_crossexam" in executed_sql
        assert "arkham_crossexam.question_trees" in executed_sql
        assert "arkham_crossexam.question_nodes" in executed_sql
        assert "arkham_crossexam.impeachment_sequences" in executed_sql
        assert "arkham_crossexam.damage_scores" in executed_sql
        assert "arkham_crossexam.exam_plans" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = CrossExamShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0

    @pytest.mark.asyncio
    async def test_exam_plans_indexes_created(self, mock_frame, mock_db):
        shard = CrossExamShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        index_sql = " ".join(index_calls)
        assert "idx_crossexam_plans_case" in index_sql
        assert "idx_crossexam_plans_status" in index_sql


# ---------------------------------------------------------------------------
# API Logic Tests (legacy endpoints)
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_crossexam.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_trees_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_trees()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_nodes_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.get_tree_nodes("t1")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_impeachments_no_db(self):
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_impeachments()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_generate_tree_no_llm(self):
        from fastapi import HTTPException

        self.api._llm_service = None
        with pytest.raises(HTTPException) as exc:
            await self.api.generate_question_tree("w1", "p1")
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_tree(self, mock_db):
        from arkham_shard_crossexam.api import CreateTreeRequest, create_tree

        self.api._db = mock_db
        self.api._shard = None
        req = CreateTreeRequest(witness_id="w1", title="Tree 1")
        result = await create_tree(req)
        assert "tree_id" in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_node(self, mock_db):
        from arkham_shard_crossexam.api import CreateNodeRequest, create_node

        self.api._db = mock_db
        req = CreateNodeRequest(tree_id="t1", question_text="How?")
        result = await create_node(req)
        assert "node_id" in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_impeachment(self, mock_db):
        from arkham_shard_crossexam.api import CreateImpeachmentRequest, create_impeachment

        self.api._db = mock_db
        self.api._shard = None
        req = CreateImpeachmentRequest(witness_id="w1", title="Imp 1", conflict_description="C")
        result = await create_impeachment(req)
        assert "impeachment_id" in result
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_trees(self, mock_db):
        from arkham_shard_crossexam.api import list_trees

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "t1"}]
        result = await list_trees(witness_id="w1")
        assert result["count"] == 1
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nodes(self, mock_db):
        from arkham_shard_crossexam.api import get_tree_nodes

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "n1"}]
        result = await get_tree_nodes("t1")
        assert result["count"] == 1
        mock_db.fetch_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_impeachments(self, mock_db):
        from arkham_shard_crossexam.api import list_impeachments

        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "i1"}]
        result = await list_impeachments(witness_id="w1")
        assert result["count"] == 1
        mock_db.fetch_all.assert_called_once()


# ---------------------------------------------------------------------------
# Exam Plan CRUD Tests
# ---------------------------------------------------------------------------


class TestExamPlanCreation:
    """Test creating exam plans with validation."""

    def setup_method(self):
        import arkham_shard_crossexam.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_create_exam_plan(self, mock_db):
        """Creating a plan returns an ID and persists via db.execute."""
        from arkham_shard_crossexam.api import CreateExamPlanRequest, create_exam_plan

        self.api._db = mock_db
        req = CreateExamPlanRequest(
            witness_name="Jane Smith",
            case_id=str(uuid.uuid4()),
            approach="standard",
        )
        result = await create_exam_plan(req)

        assert "id" in result
        assert result["witness_name"] == "Jane Smith"
        assert result["approach"] == "standard"
        assert result["status"] == "draft"
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_exam_plan_all_approaches(self, mock_db):
        """All four valid approaches are accepted."""
        from arkham_shard_crossexam.api import CreateExamPlanRequest, create_exam_plan

        self.api._db = mock_db
        for approach in ("standard", "hostile", "friendly", "expert"):
            mock_db.execute.reset_mock()
            req = CreateExamPlanRequest(witness_name="W", approach=approach)
            result = await create_exam_plan(req)
            assert result["approach"] == approach


class TestExamPlanApproachValidation:
    """Test that invalid approaches are rejected."""

    def setup_method(self):
        import arkham_shard_crossexam.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_invalid_approach_rejected(self, mock_db):
        """An invalid approach value raises 422."""
        from arkham_shard_crossexam.api import CreateExamPlanRequest, create_exam_plan
        from fastapi import HTTPException

        self.api._db = mock_db
        req = CreateExamPlanRequest(witness_name="W", approach="aggressive")
        with pytest.raises(HTTPException) as exc:
            await create_exam_plan(req)
        assert exc.value.status_code == 422
        assert "aggressive" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self, mock_db):
        """An invalid status value raises 422."""
        from arkham_shard_crossexam.api import CreateExamPlanRequest, create_exam_plan
        from fastapi import HTTPException

        self.api._db = mock_db
        req = CreateExamPlanRequest(witness_name="W", status="unknown")
        with pytest.raises(HTTPException) as exc:
            await create_exam_plan(req)
        assert exc.value.status_code == 422


class TestExamPlanGenerate:
    """Test the /generate endpoint that auto-creates question templates."""

    def setup_method(self):
        import arkham_shard_crossexam.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_generate_creates_plan(self, mock_db):
        """Generate endpoint creates a plan and returns it."""
        from arkham_shard_crossexam.api import GenerateExamPlanRequest, generate_exam_plan

        self.api._db = mock_db
        req = GenerateExamPlanRequest(
            witness_name="Bob",
            case_id=str(uuid.uuid4()),
            topics=["contract terms", "meeting dates"],
        )
        result = await generate_exam_plan(req)

        assert "id" in result
        assert result["witness_name"] == "Bob"
        assert result["status"] == "draft"
        assert result["approach"] == "standard"
        assert len(result["questions"]) == 2
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_topic_to_question_mapping(self, mock_db):
        """Each topic produces exactly one question template with expected fields."""
        from arkham_shard_crossexam.api import GenerateExamPlanRequest, generate_exam_plan

        self.api._db = mock_db
        topics = ["credibility", "timeline", "motive"]
        req = GenerateExamPlanRequest(
            witness_name="Alice",
            case_id=str(uuid.uuid4()),
            topics=topics,
        )
        result = await generate_exam_plan(req)

        assert len(result["questions"]) == len(topics)
        for i, q in enumerate(result["questions"]):
            assert q["topic"] == topics[i]
            assert "opening" in q
            assert "probing" in q
            assert "closing" in q
            assert q["type"] == "template"
            # Verify the topic name appears in the question text
            assert topics[i] in q["opening"]
            assert topics[i] in q["probing"]

    @pytest.mark.asyncio
    async def test_generate_empty_topics_rejected(self, mock_db):
        """Generate with empty topics list raises 422."""
        from arkham_shard_crossexam.api import GenerateExamPlanRequest, generate_exam_plan
        from fastapi import HTTPException

        self.api._db = mock_db
        req = GenerateExamPlanRequest(
            witness_name="Nobody",
            case_id=str(uuid.uuid4()),
            topics=[],
        )
        with pytest.raises(HTTPException) as exc:
            await generate_exam_plan(req)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_topics_stored_as_dicts(self, mock_db):
        """Topics are stored as structured dicts with name and status."""
        from arkham_shard_crossexam.api import GenerateExamPlanRequest, generate_exam_plan

        self.api._db = mock_db
        req = GenerateExamPlanRequest(
            witness_name="Carol",
            case_id=str(uuid.uuid4()),
            topics=["evidence handling"],
        )
        result = await generate_exam_plan(req)

        assert len(result["topics"]) == 1
        assert result["topics"][0]["name"] == "evidence handling"
        assert result["topics"][0]["status"] == "pending"


class TestExamPlanStatusTransitions:
    """Test status field transitions and update logic."""

    def setup_method(self):
        import arkham_shard_crossexam.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_update_status_draft_to_prepared(self, mock_db):
        """Updating status from draft to prepared succeeds."""
        from arkham_shard_crossexam.api import UpdateExamPlanRequest, update_exam_plan

        self.api._db = mock_db
        plan_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": plan_id, "status": "draft"}

        req = UpdateExamPlanRequest(status="prepared")
        result = await update_exam_plan(plan_id, req)
        assert result["updated"] is True
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_to_completed(self, mock_db):
        """Status can be set to completed."""
        from arkham_shard_crossexam.api import UpdateExamPlanRequest, update_exam_plan

        self.api._db = mock_db
        plan_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": plan_id, "status": "in_progress"}

        req = UpdateExamPlanRequest(status="completed")
        result = await update_exam_plan(plan_id, req)
        assert result["updated"] is True

    @pytest.mark.asyncio
    async def test_update_invalid_status_rejected(self, mock_db):
        """Updating to an invalid status raises 422."""
        from arkham_shard_crossexam.api import UpdateExamPlanRequest, update_exam_plan
        from fastapi import HTTPException

        self.api._db = mock_db
        plan_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": plan_id, "status": "draft"}

        req = UpdateExamPlanRequest(status="invalid_status")
        with pytest.raises(HTTPException) as exc:
            await update_exam_plan(plan_id, req)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_update_nonexistent_plan_404(self, mock_db):
        """Updating a non-existent plan raises 404."""
        from arkham_shard_crossexam.api import UpdateExamPlanRequest, update_exam_plan
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        req = UpdateExamPlanRequest(status="prepared")
        with pytest.raises(HTTPException) as exc:
            await update_exam_plan(str(uuid.uuid4()), req)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_plan(self, mock_db):
        """Deleting an existing plan succeeds."""
        from arkham_shard_crossexam.api import delete_exam_plan

        self.api._db = mock_db
        plan_id = str(uuid.uuid4())
        mock_db.fetch_one.return_value = {"id": plan_id}

        result = await delete_exam_plan(plan_id)
        assert result["deleted"] is True
        assert result["id"] == plan_id

    @pytest.mark.asyncio
    async def test_delete_nonexistent_plan_404(self, mock_db):
        """Deleting a non-existent plan raises 404."""
        from arkham_shard_crossexam.api import delete_exam_plan
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await delete_exam_plan(str(uuid.uuid4()))
        assert exc.value.status_code == 404
