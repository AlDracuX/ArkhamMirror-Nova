"""
Comparator Shard - Engine Logic Tests

Tests for ComparatorEngine: divergence scoring, treatment matrices,
s.13/s.26 element checklists, and aggregate significance.
All DB calls are mocked.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_comparator.engine import ComparatorEngine

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
    return ComparatorEngine(db=mock_db, event_bus=mock_events)


@pytest.fixture
def engine_no_db():
    return ComparatorEngine(db=None, event_bus=None)


# ---------------------------------------------------------------------------
# Divergence Scoring Tests
# ---------------------------------------------------------------------------


class TestDivergenceScoring:
    """Test divergence score calculations."""

    def test_opposite_outcomes_score_1(self, engine):
        """favourable vs unfavourable = 1.0 (maximum divergence)."""
        score = engine.score_divergence("favourable", "unfavourable")
        assert score == 1.0

    def test_opposite_outcomes_reversed(self, engine):
        """unfavourable vs favourable = 1.0 (symmetric)."""
        score = engine.score_divergence("unfavourable", "favourable")
        assert score == 1.0

    def test_same_outcome_favourable(self, engine):
        """Both favourable = 0.0 (no divergence)."""
        score = engine.score_divergence("favourable", "favourable")
        assert score == 0.0

    def test_same_outcome_unfavourable(self, engine):
        """Both unfavourable = 0.0."""
        score = engine.score_divergence("unfavourable", "unfavourable")
        assert score == 0.0

    def test_same_outcome_neutral(self, engine):
        """Both neutral = 0.0."""
        score = engine.score_divergence("neutral", "neutral")
        assert score == 0.0

    def test_favourable_vs_neutral(self, engine):
        """favourable vs neutral = 0.5."""
        score = engine.score_divergence("favourable", "neutral")
        assert score == 0.5

    def test_unfavourable_vs_neutral(self, engine):
        """unfavourable vs neutral = 0.5."""
        score = engine.score_divergence("unfavourable", "neutral")
        assert score == 0.5

    def test_unknown_treated_as_neutral(self, engine):
        """unknown outcome treated same as neutral (0.5 score)."""
        score = engine.score_divergence("favourable", "unknown")
        assert score == 0.5

    def test_unrecognised_outcome_treated_as_neutral(self, engine):
        """Unrecognised outcome string defaults to neutral."""
        score = engine.score_divergence("favourable", "something_else")
        assert score == 0.5


# ---------------------------------------------------------------------------
# s.13 Element Checklist Tests
# ---------------------------------------------------------------------------


class TestS13Elements:
    """Test s.13 direct discrimination element tracking."""

    @pytest.mark.asyncio
    async def test_s13_all_elements_met(self, engine, mock_db):
        """All 4 s.13 elements met when each has evidence."""
        mock_db.fetch_one = AsyncMock(return_value={"cnt": 2})

        result = await engine.check_s13_elements("case-001")

        assert result["complete"] is True
        assert len(result["elements"]) == 4
        for el in result["elements"]:
            assert el["status"] == "met"
            assert el["evidence_count"] == 2

    @pytest.mark.asyncio
    async def test_s13_missing_element(self, engine, mock_db):
        """Incomplete when one element has no evidence."""
        call_count = 0

        async def varying_count(query, params):
            nonlocal call_count
            call_count += 1
            # First 3 elements met, 4th unmet
            if call_count <= 3:
                return {"cnt": 1}
            return {"cnt": 0}

        mock_db.fetch_one = varying_count

        result = await engine.check_s13_elements("case-001")

        assert result["complete"] is False
        met_count = sum(1 for el in result["elements"] if el["status"] == "met")
        assert met_count == 3

    @pytest.mark.asyncio
    async def test_s13_no_db(self, engine_no_db):
        """Without DB, all elements are unmet."""
        result = await engine_no_db.check_s13_elements("case-001")

        assert result["complete"] is False
        assert len(result["elements"]) == 4
        for el in result["elements"]:
            assert el["status"] == "unmet"
            assert el["evidence_count"] == 0

    @pytest.mark.asyncio
    async def test_s13_element_names(self, engine, mock_db):
        """Verify correct s.13 element names."""
        mock_db.fetch_one = AsyncMock(return_value={"cnt": 0})

        result = await engine.check_s13_elements("case-001")
        names = [el["element"] for el in result["elements"]]

        assert "protected_characteristic" in names
        assert "less_favourable_treatment" in names
        assert "comparative_situation" in names
        assert "causation_reason_why" in names


# ---------------------------------------------------------------------------
# s.26 Element Checklist Tests
# ---------------------------------------------------------------------------


class TestS26Elements:
    """Test s.26 harassment element tracking."""

    @pytest.mark.asyncio
    async def test_s26_all_elements_met(self, engine, mock_db):
        """All 5 s.26 elements met."""
        mock_db.fetch_one = AsyncMock(return_value={"cnt": 1})

        result = await engine.check_s26_elements("case-001")

        assert result["complete"] is True
        assert len(result["elements"]) == 5

    @pytest.mark.asyncio
    async def test_s26_missing_one(self, engine, mock_db):
        """4 of 5 met = incomplete."""
        call_count = 0

        async def varying_count(query, params):
            nonlocal call_count
            call_count += 1
            # First 4 met, 5th unmet
            if call_count <= 4:
                return {"cnt": 3}
            return {"cnt": 0}

        mock_db.fetch_one = varying_count

        result = await engine.check_s26_elements("case-001")

        assert result["complete"] is False
        met_count = sum(1 for el in result["elements"] if el["status"] == "met")
        assert met_count == 4
        unmet_count = sum(1 for el in result["elements"] if el["status"] == "unmet")
        assert unmet_count == 1

    @pytest.mark.asyncio
    async def test_s26_element_names(self, engine, mock_db):
        """Verify correct s.26 element names."""
        mock_db.fetch_one = AsyncMock(return_value={"cnt": 0})

        result = await engine.check_s26_elements("case-001")
        names = [el["element"] for el in result["elements"]]

        assert "unwanted_conduct" in names
        assert "related_to_characteristic" in names
        assert "purpose_or_effect" in names
        assert "violating_dignity" in names
        assert "intimidating_environment" in names


# ---------------------------------------------------------------------------
# Treatment Matrix Tests
# ---------------------------------------------------------------------------


class TestTreatmentMatrix:
    """Test treatment matrix building."""

    @pytest.mark.asyncio
    async def test_empty_incident(self, engine, mock_db):
        """Matrix for non-existent incident returns empty treatments."""
        mock_db.fetch_one = AsyncMock(return_value=None)
        mock_db.fetch_all = AsyncMock(return_value=[])

        result = await engine.build_treatment_matrix("inc-999")

        assert result["incident_id"] == "inc-999"
        assert result["incident"] is None
        assert result["treatments"] == []
        assert result["divergences"] == []

    @pytest.mark.asyncio
    async def test_matrix_groups_by_subject(self, engine, mock_db):
        """Treatment matrix groups claimant vs 2 comparators."""
        mock_db.fetch_one = AsyncMock(return_value={"id": "inc-001", "description": "Test incident"})

        treatments = [
            _mock_treatment("t1", "inc-001", "claimant", "Excluded from meeting", "unfavourable"),
            _mock_treatment("t2", "inc-001", "comp-A", "Invited to meeting", "favourable"),
            _mock_treatment("t3", "inc-001", "comp-B", "Invited to meeting", "favourable"),
        ]
        mock_db.fetch_all = AsyncMock(return_value=treatments)

        result = await engine.build_treatment_matrix("inc-001")

        assert len(result["treatments"]) == 3
        subjects = [t["subject"] for t in result["treatments"]]
        assert "claimant" in subjects
        assert "comp-A" in subjects
        assert "comp-B" in subjects

    @pytest.mark.asyncio
    async def test_matrix_divergences_computed(self, engine, mock_db):
        """Divergences computed between claimant and each comparator."""
        mock_db.fetch_one = AsyncMock(return_value={"id": "inc-001", "description": "Test"})

        treatments = [
            _mock_treatment("t1", "inc-001", "claimant", "Penalised", "unfavourable"),
            _mock_treatment("t2", "inc-001", "comp-A", "Praised", "favourable"),
            _mock_treatment("t3", "inc-001", "comp-B", "No action", "neutral"),
        ]
        mock_db.fetch_all = AsyncMock(return_value=treatments)

        result = await engine.build_treatment_matrix("inc-001")

        assert len(result["divergences"]) == 2

        # comp-A divergence: unfavourable vs favourable = 1.0
        div_a = next(d for d in result["divergences"] if d["comparator_subject"] == "comp-A")
        assert div_a["score"] == 1.0

        # comp-B divergence: unfavourable vs neutral = 0.5
        div_b = next(d for d in result["divergences"] if d["comparator_subject"] == "comp-B")
        assert div_b["score"] == 0.5

    @pytest.mark.asyncio
    async def test_matrix_no_claimant_no_divergences(self, engine, mock_db):
        """No divergences if claimant treatment is missing."""
        mock_db.fetch_one = AsyncMock(return_value={"id": "inc-001", "description": "Test"})

        treatments = [
            _mock_treatment("t1", "inc-001", "comp-A", "Praised", "favourable"),
        ]
        mock_db.fetch_all = AsyncMock(return_value=treatments)

        result = await engine.build_treatment_matrix("inc-001")

        assert result["divergences"] == []

    @pytest.mark.asyncio
    async def test_matrix_no_db(self, engine_no_db):
        """Matrix without DB returns empty structure."""
        result = await engine_no_db.build_treatment_matrix("inc-001")

        assert result["incident"] is None
        assert result["treatments"] == []
        assert result["divergences"] == []


# ---------------------------------------------------------------------------
# Aggregate Significance Tests
# ---------------------------------------------------------------------------


class TestAggregateSignificance:
    """Test aggregate significance calculations."""

    @pytest.mark.asyncio
    async def test_aggregate_averaging(self, engine, mock_db):
        """3 incidents, verify average and max."""
        mock_db.fetch_all = AsyncMock(
            return_value=[
                {"significance_score": 0.9},
                {"significance_score": 0.6},
                {"significance_score": 0.3},
            ]
        )

        result = await engine.aggregate_significance("case-001")

        assert result["incident_count"] == 3
        assert result["avg_divergence"] == 0.6
        assert result["max_divergence"] == 0.9
        assert result["overall_significance"] == "high"

    @pytest.mark.asyncio
    async def test_aggregate_empty(self, engine, mock_db):
        """No divergences returns zero aggregation."""
        mock_db.fetch_all = AsyncMock(return_value=[])

        result = await engine.aggregate_significance("case-001")

        assert result["incident_count"] == 0
        assert result["avg_divergence"] == 0.0
        assert result["max_divergence"] == 0.0
        assert result["overall_significance"] == "low"

    @pytest.mark.asyncio
    async def test_aggregate_critical(self, engine, mock_db):
        """High average scores classify as critical."""
        mock_db.fetch_all = AsyncMock(
            return_value=[
                {"significance_score": 1.0},
                {"significance_score": 0.9},
                {"significance_score": 0.8},
            ]
        )

        result = await engine.aggregate_significance("case-001")

        assert result["avg_divergence"] == 0.9
        assert result["overall_significance"] == "critical"

    @pytest.mark.asyncio
    async def test_aggregate_low(self, engine, mock_db):
        """Low average scores classify as low."""
        mock_db.fetch_all = AsyncMock(
            return_value=[
                {"significance_score": 0.1},
                {"significance_score": 0.2},
            ]
        )

        result = await engine.aggregate_significance("case-001")

        assert result["avg_divergence"] == 0.15
        assert result["overall_significance"] == "low"

    @pytest.mark.asyncio
    async def test_aggregate_medium(self, engine, mock_db):
        """Medium average scores classify as medium."""
        mock_db.fetch_all = AsyncMock(
            return_value=[
                {"significance_score": 0.4},
                {"significance_score": 0.5},
            ]
        )

        result = await engine.aggregate_significance("case-001")

        assert result["avg_divergence"] == 0.45
        assert result["overall_significance"] == "medium"

    @pytest.mark.asyncio
    async def test_aggregate_no_db(self, engine_no_db):
        """Without DB, returns zero aggregation."""
        result = await engine_no_db.aggregate_significance("case-001")

        assert result["incident_count"] == 0
        assert result["overall_significance"] == "low"


# ---------------------------------------------------------------------------
# Divergence Scoring by ID Tests
# ---------------------------------------------------------------------------


class TestDivergenceByIds:
    """Test divergence scoring via treatment ID lookups."""

    @pytest.mark.asyncio
    async def test_score_by_ids(self, engine, mock_db):
        """Score divergence between two treatment IDs."""
        call_count = 0

        async def mock_fetch_one(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"outcome": "favourable"}
            return {"outcome": "unfavourable"}

        mock_db.fetch_one = mock_fetch_one

        score = await engine.score_divergence_by_ids("t1", "t2")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_score_by_ids_missing_treatment(self, engine, mock_db):
        """Missing treatment returns 0.0."""
        mock_db.fetch_one = AsyncMock(return_value=None)

        score = await engine.score_divergence_by_ids("t1", "t2")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_score_by_ids_no_db(self, engine_no_db):
        """No DB returns 0.0."""
        score = await engine_no_db.score_divergence_by_ids("t1", "t2")
        assert score == 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_treatment(tid, incident_id, subject_id, description, outcome):
    """Create a mock treatment row dict."""
    return MagicMock(
        __getitem__=lambda self, k: {
            "id": tid,
            "incident_id": incident_id,
            "subject_id": subject_id,
            "treatment_description": description,
            "outcome": outcome,
            "evidence_ids": [],
            "tenant_id": None,
            "created_at": None,
        }[k],
        get=lambda k, d=None: {
            "id": tid,
            "incident_id": incident_id,
            "subject_id": subject_id,
            "treatment_description": description,
            "outcome": outcome,
            "evidence_ids": [],
            "tenant_id": None,
            "created_at": None,
        }.get(k, d),
        keys=lambda: [
            "id",
            "incident_id",
            "subject_id",
            "treatment_description",
            "outcome",
            "evidence_ids",
            "tenant_id",
            "created_at",
        ],
        values=lambda: [tid, incident_id, subject_id, description, outcome, [], None, None],
        items=lambda: [
            ("id", tid),
            ("incident_id", incident_id),
            ("subject_id", subject_id),
            ("treatment_description", description),
            ("outcome", outcome),
            ("evidence_ids", []),
            ("tenant_id", None),
            ("created_at", None),
        ],
    )
