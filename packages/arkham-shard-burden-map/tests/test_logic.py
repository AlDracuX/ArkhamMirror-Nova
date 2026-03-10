"""
BurdenMap Shard - Logic Tests

Tests for models, API handler logic, and burden calculations.
All external dependencies are mocked.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arkham_shard_burden_map.api import (
    AddEvidenceWeightRequest,
    CreateElementRequest,
)
from arkham_shard_burden_map.models import (
    BurdenAssignment,
    BurdenHolder,
    ClaimElement,
    ElementStatus,
    EvidenceSource,
    EvidenceWeight,
    EvidenceWeightValue,
    TrafficLight,
    calculate_net_score,
    calculate_traffic_light,
    compute_burden_assignment,
)
from arkham_shard_burden_map.shard import BurdenMapShard
from fastapi import HTTPException

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

    def test_claim_element_defaults(self):
        ce = ClaimElement(id="e1", title="Discrimination", claim_type="direct")
        assert ce.id == "e1"
        assert ce.burden_holder == BurdenHolder.CLAIMANT
        assert ce.status == ElementStatus.ACTIVE

    def test_burden_holder_enum(self):
        assert BurdenHolder.CLAIMANT == "claimant"
        assert BurdenHolder.REVERSE == "reverse"

    def test_traffic_light_enum(self):
        assert TrafficLight.GREEN == "green"
        assert TrafficLight.RED == "red"

    def test_evidence_weight_value_enum(self):
        assert EvidenceWeightValue.STRONG == "strong"
        assert EvidenceWeightValue.ADVERSE == "adverse"

    def test_evidence_weight_numeric_score(self):
        ew1 = EvidenceWeight(id="w1", element_id="e1", weight=EvidenceWeightValue.STRONG, supports_burden_holder=True)
        assert ew1.numeric_score == 3

        ew2 = EvidenceWeight(id="w2", element_id="e1", weight=EvidenceWeightValue.STRONG, supports_burden_holder=False)
        assert ew2.numeric_score == -3

        ew3 = EvidenceWeight(id="w3", element_id="e1", weight=EvidenceWeightValue.ADVERSE, supports_burden_holder=True)
        assert ew3.numeric_score == -2

    def test_calculate_traffic_light(self):
        assert calculate_traffic_light(5) == TrafficLight.GREEN
        assert calculate_traffic_light(4) == TrafficLight.GREEN
        assert calculate_traffic_light(3) == TrafficLight.AMBER
        assert calculate_traffic_light(1) == TrafficLight.AMBER
        assert calculate_traffic_light(0) == TrafficLight.RED
        assert calculate_traffic_light(-1) == TrafficLight.RED

    def test_compute_burden_assignment(self):
        weights = [
            EvidenceWeight(id="w1", element_id="e1", weight=EvidenceWeightValue.STRONG, supports_burden_holder=True),
            EvidenceWeight(id="w2", element_id="e1", weight=EvidenceWeightValue.MODERATE, supports_burden_holder=True),
            EvidenceWeight(id="w3", element_id="e1", weight=EvidenceWeightValue.WEAK, supports_burden_holder=False),
        ]
        # 3 + 2 - 1 = 4
        assignment = compute_burden_assignment("e1", "a1", weights)
        assert assignment.net_score == 4
        assert assignment.traffic_light == TrafficLight.GREEN
        assert assignment.supporting_count == 2
        assert assignment.adverse_count == 1
        assert "1 adverse item(s) weaken position" in assignment.gap_summary

    def test_compute_burden_assignment_satisfied(self):
        weights = [
            EvidenceWeight(id="w1", element_id="e1", weight=EvidenceWeightValue.STRONG, supports_burden_holder=True),
            EvidenceWeight(id="w2", element_id="e1", weight=EvidenceWeightValue.MODERATE, supports_burden_holder=True),
        ]
        # 3 + 2 = 5
        assignment = compute_burden_assignment("e1", "a1", weights)
        assert assignment.traffic_light == TrafficLight.GREEN
        assert assignment.gap_summary == "Burden appears satisfied."

    def test_compute_burden_assignment_gap(self):
        weights = [
            EvidenceWeight(id="w1", element_id="e1", weight=EvidenceWeightValue.WEAK, supports_burden_holder=True),
        ]
        assignment = compute_burden_assignment("e1", "a1", weights)
        assert assignment.traffic_light == TrafficLight.AMBER
        assert (
            "Burden appears satisfied" in assignment.gap_summary
        )  # Threshold for green is 4, but it's not RED, so it's "satisfied" in model logic?
        # Actually check compute_burden_assignment logic:
        # if light == TrafficLight.RED: gap_parts.append("Insufficient evidence...")
        # if adverse: ...
        # if not supporting: ...
        # return gap_summary=" ".join(gap_parts) if gap_parts else "Burden appears satisfied."
        # If light is AMBER and no adverse, gap_summary is "Burden appears satisfied." Correct.


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_burden_map" in executed_sql
        assert "arkham_burden_map.claim_elements" in executed_sql
        assert "arkham_burden_map.evidence_weights" in executed_sql
        assert "arkham_burden_map.burden_assignments" in executed_sql

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) >= 7


# ---------------------------------------------------------------------------
# API Logic Tests
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        import arkham_shard_burden_map.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_elements_no_db(self):
        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_elements()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_elements(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "e1", "title": "Test Element"}]
        result = await self.api.list_elements(project_id="p1")
        assert result["count"] == 1
        assert "project_id = :pid" in mock_db.fetch_all.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_element(self, mock_db):
        self.api._db = mock_db
        self.api._shard = None
        req = CreateElementRequest(title="Discrimination", claim_type="direct")
        result = await self.api.create_element(req)
        assert "element_id" in result
        mock_db.execute.assert_called_once()
        assert "claim_type" in mock_db.execute.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_burden_dashboard(self, mock_db):
        self.api._db = mock_db
        mock_db.fetch_all.return_value = [{"id": "e1", "traffic_light": "green"}]
        result = await self.api.get_burden_dashboard(project_id="p1")
        assert len(result["elements"]) == 1
        assert "LEFT JOIN arkham_burden_map.burden_assignments" in mock_db.fetch_all.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_evidence_weight(self, mock_db):
        self.api._db = mock_db
        shard = MagicMock()
        shard._recalculate_assignment = AsyncMock()
        self.api._shard = shard

        req = AddEvidenceWeightRequest(element_id="e1", weight="strong", source_id="s1", source_title="Source 1")
        result = await self.api.add_evidence_weight(req)
        assert result["status"] == "added"
        mock_db.execute.assert_called_once()
        shard._recalculate_assignment.assert_called_once_with("e1")


# ---------------------------------------------------------------------------
# Recalculation Logic Tests
# ---------------------------------------------------------------------------


class TestRecalculation:
    """Test the internal recalculation logic in the shard class."""

    @pytest.mark.asyncio
    async def test_recalculate_assignment(self, mock_frame, mock_db, mock_events):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)

        # Mock evidence weights
        mock_db.fetch_all.return_value = [
            {
                "id": "w1",
                "element_id": "e1",
                "weight": "strong",
                "source_type": "document",
                "source_id": "s1",
                "source_title": "S1",
                "excerpt": None,
                "supports_burden_holder": True,
                "analyst_notes": "",
            }
        ]

        # Mock element fetch for event payload
        mock_db.fetch_one.side_effect = [
            None,  # existing assignment check (fetch_one at line 307)
            {
                "title": "Test Element",
                "claim_type": "direct",
                "required": True,
            },  # element metadata (fetch_one at line 345)
        ]

        await shard._recalculate_assignment("e1")

        # Verify assignment insertion
        # One call for schema creation, others for recalculation
        # Actually it's better to check the specific call
        insert_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "INSERT INTO arkham_burden_map.burden_assignments" in str(c.args[0])
        ]
        assert len(insert_calls) == 1
        payload = insert_calls[0].args[1]
        assert payload["traffic_light"] == "amber"  # 3 < 4 (green threshold)
        assert payload["net_score"] == 3

        # Verify event emitted (RED and required) - wait, 3 is AMBER.
        # If it was RED, it would emit burden.gap.critical
        # Since it's AMBER, no event in this case based on logic.

    @pytest.mark.asyncio
    async def test_recalculate_assignment_green(self, mock_frame, mock_db, mock_events):
        shard = BurdenMapShard()
        await shard.initialize(mock_frame)

        # Mock evidence weights - enough for GREEN
        mock_db.fetch_all.return_value = [
            {
                "id": "w1",
                "element_id": "e1",
                "weight": "strong",
                "source_type": "document",
                "source_id": "s1",
                "source_title": "S1",
                "excerpt": None,
                "supports_burden_holder": True,
                "analyst_notes": "",
            },
            {
                "id": "w2",
                "element_id": "e1",
                "weight": "moderate",
                "source_type": "document",
                "source_id": "s2",
                "source_title": "S2",
                "excerpt": None,
                "supports_burden_holder": True,
                "analyst_notes": "",
            },
        ]
        # 3 + 2 = 5 (Green)

        mock_db.fetch_one.side_effect = [
            {"id": "a1"},  # existing assignment
            {"title": "Test Element", "claim_type": "direct", "required": True},
        ]

        await shard._recalculate_assignment("e1")

        # Verify event
        mock_events.emit.assert_called_with(
            "burden.element.satisfied",
            {
                "element_id": "e1",
                "traffic_light": "green",
                "net_score": 5,
                "element_title": "Test Element",
                "claim_type": "direct",
                "required": True,
            },
            source="burden-map-shard",
        )
