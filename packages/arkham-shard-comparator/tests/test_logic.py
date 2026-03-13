"""
Comparator Shard - Logic Tests

Tests for models, API handler logic, and the comparison matrix aggregation.
All external dependencies are mocked.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from arkham_shard_comparator.models import (
    Comparator,
    Divergence,
    Incident,
    SignificanceLevel,
    Treatment,
    TreatmentOutcome,
)
from arkham_shard_comparator.shard import ComparatorShard

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

    def test_comparator_defaults(self):
        c = Comparator(id="c1")
        assert c.id == "c1"
        assert c.name == ""
        assert c.characteristic == ""
        assert c.tenant_id is None

    def test_comparator_with_values(self):
        c = Comparator(id="c1", name="Jane Smith", characteristic="race")
        assert c.name == "Jane Smith"
        assert c.characteristic == "race"

    def test_incident_defaults(self):
        i = Incident(id="i1")
        assert i.id == "i1"
        assert i.description == ""
        assert i.project_id is None
        assert i.date is None

    def test_treatment_defaults(self):
        t = Treatment(id="t1")
        assert t.outcome == TreatmentOutcome.UNKNOWN
        assert t.evidence_ids == []
        assert t.subject_id == ""

    def test_treatment_outcome_enum(self):
        assert TreatmentOutcome.FAVOURABLE == "favourable"
        assert TreatmentOutcome.UNFAVOURABLE == "unfavourable"
        assert TreatmentOutcome.NEUTRAL == "neutral"
        assert TreatmentOutcome.UNKNOWN == "unknown"

    def test_divergence_defaults(self):
        d = Divergence(id="d1")
        assert d.significance_score == 0.0
        assert d.description == ""
        assert d.incident_id == ""

    def test_significance_level_enum(self):
        assert SignificanceLevel.LOW == "low"
        assert SignificanceLevel.MEDIUM == "medium"
        assert SignificanceLevel.HIGH == "high"
        assert SignificanceLevel.CRITICAL == "critical"

    def test_treatment_with_evidence_ids(self):
        t = Treatment(id="t1", evidence_ids=["doc-1", "doc-2"])
        assert len(t.evidence_ids) == 2
        assert "doc-1" in t.evidence_ids


# ---------------------------------------------------------------------------
# Schema Creation Tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    """Verify all four tables are created during initialize()."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, mock_frame, mock_db):
        shard = ComparatorShard()
        await shard.initialize(mock_frame)

        executed_sql = " ".join(str(c.args[0]) for c in mock_db.execute.call_args_list)

        assert "CREATE SCHEMA IF NOT EXISTS arkham_comparator" in executed_sql
        assert "arkham_comparator.comparators" in executed_sql
        assert "arkham_comparator.incidents" in executed_sql
        assert "arkham_comparator.treatments" in executed_sql
        assert "arkham_comparator.divergences" in executed_sql

    @pytest.mark.asyncio
    async def test_comparators_table_columns(self, mock_frame, mock_db):
        shard = ComparatorShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        comparators_ddl = next((s for s in ddl_calls if "comparators" in s and "CREATE TABLE" in s), None)
        assert comparators_ddl is not None
        assert "tenant_id" in comparators_ddl
        assert "name" in comparators_ddl
        assert "characteristic" in comparators_ddl
        assert "created_at" in comparators_ddl

    @pytest.mark.asyncio
    async def test_treatments_table_has_evidence_ids(self, mock_frame, mock_db):
        shard = ComparatorShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        treatments_ddl = next((s for s in ddl_calls if "treatments" in s and "CREATE TABLE" in s), None)
        assert treatments_ddl is not None
        assert "evidence_ids" in treatments_ddl
        assert "subject_id" in treatments_ddl
        assert "outcome" in treatments_ddl

    @pytest.mark.asyncio
    async def test_divergences_table_has_score(self, mock_frame, mock_db):
        shard = ComparatorShard()
        await shard.initialize(mock_frame)

        ddl_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list]
        div_ddl = next((s for s in ddl_calls if "divergences" in s and "CREATE TABLE" in s), None)
        assert div_ddl is not None
        assert "significance_score" in div_ddl
        assert "incident_id" in div_ddl

    @pytest.mark.asyncio
    async def test_indexes_created(self, mock_frame, mock_db):
        shard = ComparatorShard()
        await shard.initialize(mock_frame)

        index_calls = [str(c.args[0]) for c in mock_db.execute.call_args_list if "CREATE INDEX" in str(c.args[0])]
        assert len(index_calls) > 0, "No indexes were created"


# ---------------------------------------------------------------------------
# API Logic Tests (unit-level, no HTTP layer)
# ---------------------------------------------------------------------------


class TestAPILogic:
    """Test the API module-level handler functions via direct import."""

    def setup_method(self):
        """Reset module-level _db before each test."""
        import arkham_shard_comparator.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_list_comparators_no_db(self):
        """list_comparators raises 503 when db is None."""
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_comparators()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_incidents_no_db(self):
        """list_incidents raises 503 when db is None."""
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_incidents()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_treatments_no_db(self):
        """list_treatments raises 503 when db is None."""
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_treatments()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_list_divergences_no_db(self):
        """list_divergences raises 503 when db is None."""
        from fastapi import HTTPException

        self.api._db = None
        with pytest.raises(HTTPException) as exc:
            await self.api.list_divergences()
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_comparator(self, mock_db, mock_events):
        """create_comparator writes to DB and emits event."""
        from arkham_shard_comparator.api import CreateComparatorRequest, create_comparator

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None  # no tenant

        req = CreateComparatorRequest(name="Jane Smith", characteristic="race")
        result = await create_comparator(req)

        assert "comparator_id" in result
        assert result["name"] == "Jane Smith"
        mock_db.execute.assert_called_once()
        mock_events.emit.assert_called_once()
        emit_args = mock_events.emit.call_args
        assert emit_args[0][0] == "comparator.comparator.created"

    @pytest.mark.asyncio
    async def test_create_incident(self, mock_db, mock_events):
        """create_incident writes to DB and emits event."""
        from arkham_shard_comparator.api import CreateIncidentRequest, create_incident

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateIncidentRequest(
            description="Claimant excluded from project meeting",
            date="2024-03-15",
            project_id="proj-001",
        )
        result = await create_incident(req)

        assert "incident_id" in result
        assert result["description"] == "Claimant excluded from project meeting"
        mock_db.execute.assert_called_once()
        emit_args = mock_events.emit.call_args
        assert emit_args[0][0] == "comparator.incident.created"

    @pytest.mark.asyncio
    async def test_create_treatment(self, mock_db, mock_events):
        """create_treatment writes to DB with correct subject_id."""
        from arkham_shard_comparator.api import CreateTreatmentRequest, create_treatment

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateTreatmentRequest(
            incident_id="inc-001",
            subject_id="claimant",
            treatment_description="Excluded from meeting",
            outcome="unfavourable",
            evidence_ids=["doc-1", "doc-2"],
        )
        result = await create_treatment(req)

        assert "treatment_id" in result
        assert result["incident_id"] == "inc-001"
        assert result["subject_id"] == "claimant"
        mock_db.execute.assert_called_once()

        # Check event payload
        emit_call = mock_events.emit.call_args
        assert emit_call[0][0] == "comparator.treatment.mapped"
        payload = emit_call[0][1]
        assert payload["incident_id"] == "inc-001"
        assert payload["subject_id"] == "claimant"

    @pytest.mark.asyncio
    async def test_create_divergence(self, mock_db, mock_events):
        """create_divergence writes score and emits event."""
        from arkham_shard_comparator.api import CreateDivergenceRequest, create_divergence

        self.api._db = mock_db
        self.api._event_bus = mock_events
        self.api._shard = None

        req = CreateDivergenceRequest(
            incident_id="inc-001",
            description="Claimant penalised; comparator rewarded for same action",
            significance_score=0.9,
        )
        result = await create_divergence(req)

        assert "divergence_id" in result
        assert result["incident_id"] == "inc-001"
        mock_db.execute.assert_called_once()

        emit_call = mock_events.emit.call_args
        assert emit_call[0][0] == "comparator.divergence.found"
        assert emit_call[0][1]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_get_comparator_not_found(self, mock_db):
        """get_comparator raises 404 when row is None."""
        from arkham_shard_comparator.api import get_comparator
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_comparator("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_incident_not_found(self, mock_db):
        """get_incident raises 404 when row is None."""
        from arkham_shard_comparator.api import get_incident
        from fastapi import HTTPException

        self.api._db = mock_db
        mock_db.fetch_one.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_incident("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_comparator_no_fields(self, mock_db):
        """update_comparator raises 400 when no fields provided."""
        from arkham_shard_comparator.api import UpdateComparatorRequest, update_comparator
        from fastapi import HTTPException

        self.api._db = mock_db
        req = UpdateComparatorRequest()
        with pytest.raises(HTTPException) as exc:
            await update_comparator("cid", req)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_divergence_no_fields(self, mock_db):
        """update_divergence raises 400 when no fields provided."""
        from arkham_shard_comparator.api import UpdateDivergenceRequest, update_divergence
        from fastapi import HTTPException

        self.api._db = mock_db
        req = UpdateDivergenceRequest()
        with pytest.raises(HTTPException) as exc:
            await update_divergence("did", req)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Comparison Matrix Tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Domain Logic Tests (required by spec)
# ---------------------------------------------------------------------------


class TestDomainLogic:
    """Required domain logic tests per shard specification."""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.fetch_all = AsyncMock(return_value=[])
        db.fetch_one = AsyncMock(return_value=None)
        return db

    @pytest.fixture
    def mock_events(self):
        events = AsyncMock()
        events.emit = AsyncMock()
        return events

    @pytest.fixture
    def engine(self, mock_db, mock_events):
        from arkham_shard_comparator.engine import ComparatorEngine

        return ComparatorEngine(db=mock_db, event_bus=mock_events)

    def test_divergence_score_opposite_outcomes(self, engine):
        """Opposite outcomes (favourable vs unfavourable) must score 1.0."""
        score = engine.score_divergence("favourable", "unfavourable")
        assert score == 1.0

    def test_divergence_score_same_outcome(self, engine):
        """Same outcomes must score 0.0."""
        assert engine.score_divergence("favourable", "favourable") == 0.0
        assert engine.score_divergence("unfavourable", "unfavourable") == 0.0
        assert engine.score_divergence("neutral", "neutral") == 0.0

    @pytest.mark.asyncio
    async def test_s13_elements_complete_when_all_met(self, engine, mock_db):
        """s.13 checklist is complete only when all 4 elements have evidence."""
        mock_db.fetch_one = AsyncMock(return_value={"cnt": 1})

        result = await engine.check_s13_elements("case-001")

        assert result["complete"] is True
        assert len(result["elements"]) == 4
        for el in result["elements"]:
            assert el["status"] == "met"

    @pytest.mark.asyncio
    async def test_s26_elements_missing_one(self, engine, mock_db):
        """s.26 checklist is incomplete when any element lacks evidence."""
        call_count = 0

        async def varying_count(query, params):
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                return {"cnt": 1}
            return {"cnt": 0}

        mock_db.fetch_one = varying_count

        result = await engine.check_s26_elements("case-001")

        assert result["complete"] is False
        met = sum(1 for el in result["elements"] if el["status"] == "met")
        unmet = sum(1 for el in result["elements"] if el["status"] == "unmet")
        assert met == 4
        assert unmet == 1

    @pytest.mark.asyncio
    async def test_treatment_matrix_groups_by_subject(self, engine, mock_db):
        """Treatment matrix groups treatments by subject_id."""
        mock_db.fetch_one = AsyncMock(return_value={"id": "inc-001", "description": "Test"})

        treatments = [
            _mock_treatment_row("t1", "inc-001", "claimant", "Excluded", "unfavourable"),
            _mock_treatment_row("t2", "inc-001", "comp-A", "Included", "favourable"),
            _mock_treatment_row("t3", "inc-001", "comp-B", "Included", "favourable"),
        ]
        mock_db.fetch_all = AsyncMock(return_value=treatments)

        result = await engine.build_treatment_matrix("inc-001")

        subjects = [t["subject"] for t in result["treatments"]]
        assert "claimant" in subjects
        assert "comp-A" in subjects
        assert "comp-B" in subjects
        assert len(result["treatments"]) == 3

    @pytest.mark.asyncio
    async def test_aggregate_significance_averaging(self, engine, mock_db):
        """Aggregate significance computes correct average across incidents."""
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


def _mock_treatment_row(tid, incident_id, subject_id, description, outcome):
    """Create a mock treatment row for domain logic tests.

    Must support dict(row) which the engine uses, so keys/values/items are needed.
    """
    data = {
        "id": tid,
        "incident_id": incident_id,
        "subject_id": subject_id,
        "treatment_description": description,
        "outcome": outcome,
        "evidence_ids": [],
        "tenant_id": None,
        "created_at": None,
    }
    return MagicMock(
        __getitem__=lambda self, k: data[k],
        get=lambda k, d=None: data.get(k, d),
        keys=lambda: data.keys(),
        values=lambda: data.values(),
        items=lambda: data.items(),
    )


class TestComparisonMatrix:
    """Test the matrix aggregation logic."""

    def setup_method(self):
        import arkham_shard_comparator.api as api_mod

        self.api = api_mod

    @pytest.mark.asyncio
    async def test_matrix_empty(self, mock_db):
        """Empty DB returns empty matrix structure."""
        from arkham_shard_comparator.api import get_comparison_matrix

        self.api._db = mock_db
        mock_db.fetch_all.return_value = []

        result = await get_comparison_matrix()

        assert result["incidents"] == []
        assert result["comparators"] == []
        assert result["matrix"] == {}
        assert result["divergences"] == {}

    @pytest.mark.asyncio
    async def test_matrix_with_data(self, mock_db):
        """Matrix aggregates treatments by incident and subject."""
        from arkham_shard_comparator.api import get_comparison_matrix

        self.api._db = mock_db

        inc_id = "inc-001"
        comp_id = "comp-abc"

        # Simulate fetch_all returning different results for different queries
        call_count = 0

        async def mock_fetch_all(query, params=None):
            nonlocal call_count
            call_count += 1
            if "incidents" in query:
                return [
                    MagicMock(
                        __getitem__=lambda self, k: {
                            "id": inc_id,
                            "description": "Incident 1",
                            "date": None,
                            "project_id": None,
                            "created_at": None,
                            "tenant_id": None,
                        }[k],
                        **{"id": inc_id, "description": "Incident 1"},
                    )
                ]
            elif "comparators" in query:
                return [
                    MagicMock(
                        __getitem__=lambda self, k: {
                            "id": comp_id,
                            "name": "Jane",
                            "characteristic": "race",
                            "created_at": None,
                            "tenant_id": None,
                        }[k],
                        **{"id": comp_id, "name": "Jane"},
                    )
                ]
            elif "treatments" in query:
                return [
                    MagicMock(
                        __getitem__=lambda self, k: {
                            "id": "t1",
                            "incident_id": inc_id,
                            "subject_id": "claimant",
                            "treatment_description": "Excluded",
                            "outcome": "unfavourable",
                            "evidence_ids": [],
                            "created_at": None,
                            "tenant_id": None,
                        }[k],
                    ),
                    MagicMock(
                        __getitem__=lambda self, k: {
                            "id": "t2",
                            "incident_id": inc_id,
                            "subject_id": comp_id,
                            "treatment_description": "Included",
                            "outcome": "favourable",
                            "evidence_ids": [],
                            "created_at": None,
                            "tenant_id": None,
                        }[k],
                    ),
                ]
            elif "divergences" in query:
                return []
            return []

        mock_db.fetch_all = mock_fetch_all

        result = await get_comparison_matrix()

        assert len(result["incidents"]) == 1
        assert len(result["comparators"]) == 1
        assert inc_id in result["matrix"]
        assert "claimant" in result["matrix"][inc_id]
        assert comp_id in result["matrix"][inc_id]

    @pytest.mark.asyncio
    async def test_matrix_project_filter_passed(self, mock_db):
        """project_id filter is passed through to incidents query."""
        from arkham_shard_comparator.api import get_comparison_matrix

        self.api._db = mock_db

        captured_queries = []
        captured_params = []

        async def mock_fetch_all(query, params=None):
            captured_queries.append(query)
            captured_params.append(params or {})
            return []

        mock_db.fetch_all = mock_fetch_all

        await get_comparison_matrix(project_id="proj-001")

        # First call should be incidents query with project_id filter
        inc_query = captured_queries[0]
        inc_params = captured_params[0]
        assert "project_id" in inc_query
        assert inc_params.get("project_id") == "proj-001"
