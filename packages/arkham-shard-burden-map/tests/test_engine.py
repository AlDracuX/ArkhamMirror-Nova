"""
BurdenMap Shard - Engine Tests

Tests for BurdenEngine domain logic:
- populate_from_claims for s.13, s.26, s.27
- traffic-light computation
- burden shift detection under s.136 EA 2010
- gap analysis
- dashboard aggregation
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_burden_map.engine import CLAIM_ELEMENTS, BurdenEngine

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
    return events


@pytest.fixture
def engine(mock_db, mock_events):
    return BurdenEngine(db=mock_db, event_bus=mock_events)


@pytest.fixture
def engine_no_db(mock_events):
    return BurdenEngine(db=None, event_bus=mock_events)


# ---------------------------------------------------------------------------
# Populate Tests
# ---------------------------------------------------------------------------


class TestPopulateFromClaims:
    """Test auto-population of burden elements from claim types."""

    @pytest.mark.asyncio
    async def test_populate_s13_creates_4_elements(self, engine, mock_db):
        """s.13 direct discrimination creates exactly 4 elements."""
        elements = await engine.populate_from_claims("case-1", "s.13")

        assert len(elements) == 4
        element_names = {e["element"] for e in elements}
        assert element_names == {
            "protected_characteristic",
            "less_favourable_treatment",
            "comparable_circumstances",
            "reason_why",
        }

        # All should be unmet initially
        for e in elements:
            assert e["status"] == "unmet"
            assert e["burden_party"] == "claimant"
            assert e["claim"] == "s.13"
            assert e["case_id"] == "case-1"

        # DB insert called 4 times
        assert mock_db.execute.call_count == 4

    @pytest.mark.asyncio
    async def test_populate_s26_creates_5_elements(self, engine, mock_db):
        """s.26 harassment creates exactly 5 elements."""
        elements = await engine.populate_from_claims("case-2", "s.26")

        assert len(elements) == 5
        element_names = {e["element"] for e in elements}
        assert element_names == {
            "unwanted_conduct",
            "related_to_protected_characteristic",
            "purpose_or_effect",
            "violating_dignity",
            "creating_hostile_environment",
        }

    @pytest.mark.asyncio
    async def test_populate_s27_creates_3_elements(self, engine, mock_db):
        """s.27 victimisation creates exactly 3 elements."""
        elements = await engine.populate_from_claims("case-3", "s.27")

        assert len(elements) == 3
        element_names = {e["element"] for e in elements}
        assert element_names == {
            "protected_act",
            "detriment",
            "reason_for_detriment",
        }

    @pytest.mark.asyncio
    async def test_populate_unknown_claim_raises(self, engine):
        """Unknown claim type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown claim type"):
            await engine.populate_from_claims("case-1", "s.99")

    @pytest.mark.asyncio
    async def test_populate_emits_event(self, engine, mock_events):
        """Populating elements emits burden.status.updated event."""
        await engine.populate_from_claims("case-1", "s.13")

        mock_events.emit.assert_called_once()
        event_name = mock_events.emit.call_args[0][0]
        assert event_name == "burden.status.updated"

    @pytest.mark.asyncio
    async def test_populate_each_element_has_legal_standard(self, engine):
        """Each populated element includes a non-empty legal_standard."""
        elements = await engine.populate_from_claims("case-1", "s.13")
        for e in elements:
            assert e["legal_standard"], f"Element {e['element']} missing legal_standard"
            assert "EA 2010" in e["legal_standard"]

    @pytest.mark.asyncio
    async def test_populate_without_db(self, engine_no_db):
        """Populate works without DB -- returns elements but doesn't persist."""
        elements = await engine_no_db.populate_from_claims("case-1", "s.13")
        assert len(elements) == 4


# ---------------------------------------------------------------------------
# Traffic Light Tests
# ---------------------------------------------------------------------------


class TestTrafficLight:
    """Test traffic-light status computation."""

    @pytest.mark.asyncio
    async def test_traffic_light_green_with_evidence(self, engine, mock_db):
        """status='met' + 2+ evidence_ids = GREEN."""
        mock_db.fetch_one.return_value = {
            "id": "e1",
            "status": "met",
            "evidence_ids": ["ev1", "ev2"],
        }

        colour = await engine.compute_traffic_light("e1")
        assert colour == "green"

    @pytest.mark.asyncio
    async def test_traffic_light_red_no_evidence(self, engine, mock_db):
        """status='unmet' + empty evidence_ids = RED."""
        mock_db.fetch_one.return_value = {
            "id": "e1",
            "status": "unmet",
            "evidence_ids": [],
        }

        colour = await engine.compute_traffic_light("e1")
        assert colour == "red"

    @pytest.mark.asyncio
    async def test_traffic_light_amber_partial(self, engine, mock_db):
        """status='partial' = AMBER regardless of evidence count."""
        mock_db.fetch_one.return_value = {
            "id": "e1",
            "status": "partial",
            "evidence_ids": [],
        }

        colour = await engine.compute_traffic_light("e1")
        assert colour == "amber"

    @pytest.mark.asyncio
    async def test_traffic_light_amber_one_evidence(self, engine, mock_db):
        """Any status + exactly 1 evidence_id = AMBER."""
        mock_db.fetch_one.return_value = {
            "id": "e1",
            "status": "unmet",
            "evidence_ids": ["ev1"],
        }

        colour = await engine.compute_traffic_light("e1")
        assert colour == "amber"

    @pytest.mark.asyncio
    async def test_traffic_light_not_found_raises(self, engine, mock_db):
        """Non-existent element raises ValueError."""
        mock_db.fetch_one.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await engine.compute_traffic_light("nonexistent")

    @pytest.mark.asyncio
    async def test_traffic_light_updates_db(self, engine, mock_db):
        """compute_traffic_light persists the new status."""
        mock_db.fetch_one.return_value = {
            "id": "e1",
            "status": "met",
            "evidence_ids": ["ev1", "ev2"],
        }

        await engine.compute_traffic_light("e1")

        # Should have called execute to UPDATE
        update_call = mock_db.execute.call_args
        assert update_call is not None
        sql = update_call[0][0]
        assert "UPDATE" in sql
        params = update_call[0][1]
        assert params["status"] == "green"


# ---------------------------------------------------------------------------
# Burden Shift Tests
# ---------------------------------------------------------------------------


class TestBurdenShift:
    """Test s.136 EA 2010 burden shift detection."""

    @pytest.mark.asyncio
    async def test_burden_shift_all_green(self, engine, mock_db, mock_events):
        """All elements met/green = burden shifted."""
        mock_db.fetch_all.return_value = [
            {"id": "e1", "claim": "s.13", "status": "met"},
            {"id": "e2", "claim": "s.13", "status": "green"},
            {"id": "e3", "claim": "s.13", "status": "amber"},
            {"id": "e4", "claim": "s.13", "status": "partial"},
        ]

        result = await engine.detect_burden_shift("case-1")

        assert result["shifted"] is True
        assert result["claim"] == "s.13"
        assert "s.136" in result["reasoning"]

        # Should emit burden.shifted event
        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "burden.shifted"

    @pytest.mark.asyncio
    async def test_burden_shift_with_red_not_shifted(self, engine, mock_db):
        """One RED/unmet element = burden NOT shifted."""
        mock_db.fetch_all.return_value = [
            {"id": "e1", "claim": "s.13", "status": "met"},
            {"id": "e2", "claim": "s.13", "status": "green"},
            {"id": "e3", "claim": "s.13", "status": "unmet"},  # RED
        ]

        result = await engine.detect_burden_shift("case-1")

        assert result["shifted"] is False

    @pytest.mark.asyncio
    async def test_burden_shift_no_elements(self, engine, mock_db):
        """No elements = not shifted with explanation."""
        mock_db.fetch_all.return_value = []

        result = await engine.detect_burden_shift("case-1")

        assert result["shifted"] is False
        assert "No elements" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_burden_shift_multiple_claims(self, engine, mock_db, mock_events):
        """If one claim is all GREEN/AMBER but another has RED, shifted for the first."""
        mock_db.fetch_all.return_value = [
            # s.13 -- all met
            {"id": "e1", "claim": "s.13", "status": "met"},
            {"id": "e2", "claim": "s.13", "status": "green"},
            # s.27 -- has unmet
            {"id": "e3", "claim": "s.27", "status": "met"},
            {"id": "e4", "claim": "s.27", "status": "unmet"},
        ]

        result = await engine.detect_burden_shift("case-1")

        assert result["shifted"] is True
        assert result["claim"] == "s.13"


# ---------------------------------------------------------------------------
# Gap Analysis Tests
# ---------------------------------------------------------------------------


class TestGapAnalysis:
    """Test gap analysis for evidence gaps."""

    @pytest.mark.asyncio
    async def test_gap_analysis_returns_unmet_elements(self, engine, mock_db):
        """Unmet/partial elements are returned as gaps."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "element": "protected_characteristic",
                "claim": "s.13",
                "status": "unmet",
                "legal_standard": "EA 2010 s.4",
            },
            {
                "id": "e2",
                "element": "less_favourable_treatment",
                "claim": "s.13",
                "status": "partial",
                "legal_standard": "EA 2010 s.13(1)",
            },
        ]

        gaps = await engine.gap_analysis("case-1")

        assert len(gaps) == 2
        assert gaps[0]["element"] == "protected_characteristic"
        assert gaps[0]["status"] == "unmet"
        assert gaps[1]["element"] == "less_favourable_treatment"
        assert gaps[1]["status"] == "partial"

    @pytest.mark.asyncio
    async def test_gap_analysis_includes_gap_description(self, engine, mock_db):
        """Each gap includes a human-readable description."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "element": "protected_act",
                "claim": "s.27",
                "status": "unmet",
                "legal_standard": "EA 2010 s.27(2)",
            },
        ]

        gaps = await engine.gap_analysis("case-1")

        assert len(gaps) == 1
        assert "protected_act" in gaps[0]["gap_description"]
        assert "s.27" in gaps[0]["gap_description"]

    @pytest.mark.asyncio
    async def test_gap_analysis_includes_suggested_evidence(self, engine, mock_db):
        """Each gap includes a suggested evidence description."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "element": "detriment",
                "claim": "s.27",
                "status": "unmet",
                "legal_standard": "EA 2010 s.27(1)",
            },
        ]

        gaps = await engine.gap_analysis("case-1")

        assert gaps[0]["suggested_evidence"]
        assert "detriment" in gaps[0]["suggested_evidence"]

    @pytest.mark.asyncio
    async def test_gap_analysis_empty_when_all_met(self, engine, mock_db):
        """No gaps returned when query returns no unmet/partial elements."""
        mock_db.fetch_all.return_value = []

        gaps = await engine.gap_analysis("case-1")
        assert gaps == []

    @pytest.mark.asyncio
    async def test_gap_analysis_emits_critical_event(self, engine, mock_db, mock_events):
        """Critical gap event emitted when unmet elements exist."""
        mock_db.fetch_all.return_value = [
            {
                "id": "e1",
                "element": "reason_why",
                "claim": "s.13",
                "status": "unmet",
                "legal_standard": "EA 2010 s.13(1)",
            },
        ]

        await engine.gap_analysis("case-1")

        mock_events.emit.assert_called_once()
        assert mock_events.emit.call_args[0][0] == "burden.gap.critical"


# ---------------------------------------------------------------------------
# Dashboard Aggregation Tests
# ---------------------------------------------------------------------------


class TestDashboard:
    """Test dashboard aggregation."""

    @pytest.mark.asyncio
    async def test_dashboard_aggregation_correct_counts(self, engine, mock_db):
        """Dashboard correctly counts green/amber/red elements."""
        # First call: compute_dashboard fetches all elements
        # Second call: detect_burden_shift fetches all elements
        mock_db.fetch_all.side_effect = [
            # Dashboard fetch
            [
                {"id": "e1", "claim": "s.13", "status": "met", "evidence_ids": ["ev1", "ev2"]},
                {"id": "e2", "claim": "s.13", "status": "green", "evidence_ids": ["ev3"]},
                {"id": "e3", "claim": "s.13", "status": "partial", "evidence_ids": []},
                {"id": "e4", "claim": "s.13", "status": "unmet", "evidence_ids": []},
            ],
            # Shift detection fetch
            [
                {"id": "e1", "claim": "s.13", "status": "met"},
                {"id": "e2", "claim": "s.13", "status": "green"},
                {"id": "e3", "claim": "s.13", "status": "partial"},
                {"id": "e4", "claim": "s.13", "status": "unmet"},
            ],
        ]

        dashboard = await engine.compute_dashboard("case-1")

        assert dashboard["total"] == 4
        assert dashboard["green_count"] == 2  # met + green
        assert dashboard["amber_count"] == 1  # partial
        assert dashboard["red_count"] == 1  # unmet
        assert dashboard["shift_detected"] is False  # has unmet element
        assert len(dashboard["claims"]) == 1
        assert dashboard["claims"][0]["claim"] == "s.13"

    @pytest.mark.asyncio
    async def test_dashboard_empty_case(self, engine, mock_db):
        """Empty case returns zero counts."""
        mock_db.fetch_all.return_value = []

        dashboard = await engine.compute_dashboard("empty-case")

        assert dashboard["total"] == 0
        assert dashboard["green_count"] == 0
        assert dashboard["amber_count"] == 0
        assert dashboard["red_count"] == 0
        assert dashboard["shift_detected"] is False

    @pytest.mark.asyncio
    async def test_dashboard_multiple_claims(self, engine, mock_db):
        """Dashboard groups elements by claim type."""
        mock_db.fetch_all.side_effect = [
            [
                {"id": "e1", "claim": "s.13", "status": "met"},
                {"id": "e2", "claim": "s.27", "status": "unmet"},
            ],
            [
                {"id": "e1", "claim": "s.13", "status": "met"},
                {"id": "e2", "claim": "s.27", "status": "unmet"},
            ],
        ]

        dashboard = await engine.compute_dashboard("case-1")

        assert len(dashboard["claims"]) == 2
        claim_names = {c["claim"] for c in dashboard["claims"]}
        assert claim_names == {"s.13", "s.27"}
