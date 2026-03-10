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

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = CrossExamShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0


# ---------------------------------------------------------------------------
# API Logic Tests
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
