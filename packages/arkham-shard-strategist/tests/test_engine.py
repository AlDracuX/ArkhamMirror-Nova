"""
Strategist Shard - Engine Tests

Tests for StrategistEngine domain logic with mocked dependencies.
TDD: These tests define the contract before implementation.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from arkham_shard_strategist.engine import StrategistEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock database service."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetch_all = AsyncMock(return_value=[])
    db.fetch_one = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def mock_llm():
    """Create a mock LLM service that returns structured JSON."""
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_event_bus, mock_llm):
    """Create a StrategistEngine with all dependencies."""
    return StrategistEngine(db=mock_db, event_bus=mock_event_bus, llm_service=mock_llm)


@pytest.fixture
def engine_no_llm(mock_db, mock_event_bus):
    """Create a StrategistEngine without LLM (fallback path)."""
    return StrategistEngine(db=mock_db, event_bus=mock_event_bus, llm_service=None)


def _make_llm_response(text: str):
    """Create a mock LLM response with .text attribute."""
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Predict Arguments
# ---------------------------------------------------------------------------


class TestPredictArguments:
    """Tests for predict_arguments method."""

    @pytest.mark.asyncio
    async def test_predict_arguments_returns_list(self, engine, mock_llm):
        """Mocked LLM returns predictions as a list of dicts."""
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {
                        "argument": "The claimant was dismissed for performance reasons",
                        "confidence": 0.85,
                        "reasoning": "Standard defence tactic in unfair dismissal claims",
                        "likely_evidence": ["Performance review documents", "Warning letters"],
                    },
                    {
                        "argument": "The claimant failed to follow grievance procedure",
                        "confidence": 0.7,
                        "reasoning": "Procedural defence often raised by respondent solicitors",
                        "likely_evidence": ["HR policy handbook", "Grievance procedure logs"],
                    },
                ]
            )
        )

        results = await engine.predict_arguments(project_id="proj-1", claim_id="claim-1")

        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0]["argument"] == "The claimant was dismissed for performance reasons"
        assert results[0]["confidence"] == 0.85
        assert "reasoning" in results[0]
        assert "likely_evidence" in results[0]

    @pytest.mark.asyncio
    async def test_predict_arguments_no_llm_fallback_with_claim_type(self, engine_no_llm):
        """Without LLM, predict_arguments returns template arguments for known claim types."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1", claim_id="s13_discrimination")

        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert "argument" in r
            assert "confidence" in r
            assert "reasoning" in r
            assert "likely_evidence" in r
            assert r["confidence"] > 0.0
            assert "[heuristic]" in r.get("reasoning", "").lower() or r.get("source") == "heuristic"

    @pytest.mark.asyncio
    async def test_predict_arguments_no_llm_fallback_s26_harassment(self, engine_no_llm):
        """Without LLM, s26 harassment returns specific template arguments."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1", claim_id="s26_harassment")

        assert isinstance(results, list)
        assert len(results) > 0
        arguments_text = " ".join(r["argument"].lower() for r in results)
        # Should mention typical harassment defences
        assert any(
            keyword in arguments_text for keyword in ["reasonable steps", "not related to", "banter", "proportionate"]
        )

    @pytest.mark.asyncio
    async def test_predict_arguments_no_llm_fallback_s27_victimisation(self, engine_no_llm):
        """Without LLM, s27 victimisation returns template arguments."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1", claim_id="s27_victimisation")

        assert isinstance(results, list)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_predict_arguments_no_llm_fallback_unfair_dismissal(self, engine_no_llm):
        """Without LLM, unfair dismissal returns template arguments."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1", claim_id="unfair_dismissal")

        assert isinstance(results, list)
        assert len(results) > 0
        arguments_text = " ".join(r["argument"].lower() for r in results)
        assert any(keyword in arguments_text for keyword in ["fair procedure", "reasonable", "capability", "conduct"])

    @pytest.mark.asyncio
    async def test_predict_arguments_no_llm_fallback_unknown_claim(self, engine_no_llm):
        """Without LLM and unknown claim type, returns general fallback arguments."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1", claim_id="unknown_type_xyz")

        assert isinstance(results, list)
        assert len(results) > 0  # Should still return general arguments

    @pytest.mark.asyncio
    async def test_predict_arguments_no_llm_no_claim_id(self, engine_no_llm):
        """Without LLM and no claim_id, returns general fallback arguments."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1")

        assert isinstance(results, list)
        assert len(results) > 0  # General arguments returned

    @pytest.mark.asyncio
    async def test_predict_arguments_llm_exception_uses_fallback(self, engine, mock_llm):
        """When LLM raises exception, fallback heuristics are used instead of empty list."""
        mock_llm.generate.side_effect = Exception("LLM service timeout")

        results = await engine.predict_arguments(project_id="proj-1", claim_id="s13_discrimination")

        assert isinstance(results, list)
        assert len(results) > 0  # Fallback instead of empty

    @pytest.mark.asyncio
    async def test_predict_arguments_stores_to_db(self, engine, mock_llm, mock_db):
        """Predictions are persisted to the database."""
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {
                        "argument": "Time limitation defence",
                        "confidence": 0.6,
                        "reasoning": "Common in ET cases",
                        "likely_evidence": ["ACAS certificate dates"],
                    },
                ]
            )
        )

        results = await engine.predict_arguments(project_id="proj-1")

        assert len(results) == 1
        # Verify DB execute was called for storage
        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_predict_arguments_emits_event(self, engine, mock_llm, mock_event_bus):
        """Prediction creation emits strategist.prediction.created event."""
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {
                        "argument": "Test argument",
                        "confidence": 0.5,
                        "reasoning": "Test",
                        "likely_evidence": [],
                    },
                ]
            )
        )

        await engine.predict_arguments(project_id="proj-1")

        mock_event_bus.emit.assert_called()
        call_args = mock_event_bus.emit.call_args_list
        event_names = [c[0][0] for c in call_args]
        assert "strategist.prediction.created" in event_names

    @pytest.mark.asyncio
    async def test_predict_arguments_handles_malformed_llm_response(self, engine, mock_llm):
        """Malformed LLM response returns empty list instead of crashing."""
        mock_llm.generate.return_value = _make_llm_response("This is not JSON at all")

        results = await engine.predict_arguments(project_id="proj-1")

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_predict_arguments_empty_llm_array(self, engine, mock_llm):
        """LLM returning empty JSON array yields empty results without error."""
        mock_llm.generate.return_value = _make_llm_response("[]")

        results = await engine.predict_arguments(project_id="proj-1")

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_predict_arguments_db_error_still_returns_results(self, engine, mock_llm, mock_db):
        """DB persistence failure does not prevent returning LLM results."""
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {
                        "argument": "Test argument",
                        "confidence": 0.5,
                        "reasoning": "Test",
                        "likely_evidence": [],
                    },
                ]
            )
        )
        mock_db.execute.side_effect = Exception("DB connection lost")

        results = await engine.predict_arguments(project_id="proj-1")

        assert len(results) == 1
        assert results[0]["argument"] == "Test argument"

    @pytest.mark.asyncio
    async def test_predict_arguments_no_event_when_empty(self, engine, mock_llm, mock_event_bus):
        """No event emitted when LLM returns no predictions."""
        mock_llm.generate.return_value = _make_llm_response("[]")

        await engine.predict_arguments(project_id="proj-1")

        mock_event_bus.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_predict_arguments_each_gets_unique_id(self, engine, mock_llm, mock_db):
        """Each prediction in a batch receives a unique id."""
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {"argument": "Arg A", "confidence": 0.5, "reasoning": "R", "likely_evidence": []},
                    {"argument": "Arg B", "confidence": 0.6, "reasoning": "R", "likely_evidence": []},
                ]
            )
        )

        results = await engine.predict_arguments(project_id="proj-1")

        ids = [r["id"] for r in results]
        assert len(set(ids)) == 2, "Each prediction must have a unique id"

    @pytest.mark.asyncio
    async def test_predict_arguments_without_db(self, mock_event_bus, mock_llm):
        """Engine operates without a database (db=None)."""
        engine_no_db = StrategistEngine(db=None, event_bus=mock_event_bus, llm_service=mock_llm)
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps([{"argument": "Arg", "confidence": 0.5, "reasoning": "R", "likely_evidence": []}])
        )

        results = await engine_no_db.predict_arguments(project_id="proj-1")

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_predict_arguments_llm_exception_returns_fallback(self, engine, mock_llm):
        """If LLM.generate raises an exception, returns heuristic fallback arguments."""
        mock_llm.generate.side_effect = Exception("LLM service timeout")

        results = await engine.predict_arguments(project_id="proj-1")

        assert isinstance(results, list)
        assert len(results) > 0  # Fallback general arguments


# ---------------------------------------------------------------------------
# Counterarguments
# ---------------------------------------------------------------------------


class TestCounterarguments:
    """Tests for generate_counterarguments method."""

    @pytest.mark.asyncio
    async def test_counterarguments_reference_evidence(self, engine, mock_llm, mock_db):
        """Counterarguments include evidence_refs."""
        # Set up a prediction in the DB
        mock_db.fetch_one.return_value = {
            "id": "pred-1",
            "project_id": "proj-1",
            "predicted_argument": "Claimant was underperforming",
            "confidence": 0.8,
            "reasoning": "Standard defence",
        }

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {
                        "counterargument": "Performance reviews show consistent 'meets expectations' ratings",
                        "evidence_refs": ["doc-annual-review-2024", "doc-bonus-letter-2024"],
                        "strength": 0.9,
                    },
                    {
                        "counterargument": "No formal performance improvement plan was ever issued",
                        "evidence_refs": ["doc-hr-records"],
                        "strength": 0.85,
                    },
                ]
            )
        )

        results = await engine.generate_counterarguments(prediction_id="pred-1")

        assert isinstance(results, list)
        assert len(results) == 2
        assert "evidence_refs" in results[0]
        assert len(results[0]["evidence_refs"]) > 0
        assert "strength" in results[0]

    @pytest.mark.asyncio
    async def test_counterarguments_no_llm_fallback(self, engine_no_llm, mock_db):
        """Without LLM, counterarguments returns empty list."""
        mock_db.fetch_one.return_value = {
            "id": "pred-1",
            "project_id": "proj-1",
            "predicted_argument": "Test",
            "confidence": 0.5,
            "reasoning": "Test",
        }

        results = await engine_no_llm.generate_counterarguments(prediction_id="pred-1")

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_counterarguments_prediction_not_found(self, engine, mock_db):
        """Returns empty list when prediction_id does not exist in DB."""
        mock_db.fetch_one.return_value = None

        results = await engine.generate_counterarguments(prediction_id="nonexistent")

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_counterarguments_malformed_llm_response(self, engine, mock_llm, mock_db):
        """Malformed LLM response returns empty list without crashing."""
        mock_db.fetch_one.return_value = {
            "id": "pred-1",
            "project_id": "proj-1",
            "predicted_argument": "Test",
            "confidence": 0.5,
            "reasoning": "Test",
        }
        mock_llm.generate.return_value = _make_llm_response("Not valid JSON")

        results = await engine.generate_counterarguments(prediction_id="pred-1")

        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_counterarguments_persisted_to_db(self, engine, mock_llm, mock_db):
        """Counterarguments are stored in the database."""
        mock_db.fetch_one.return_value = {
            "id": "pred-1",
            "project_id": "proj-1",
            "predicted_argument": "Test argument",
            "confidence": 0.8,
            "reasoning": "Test",
        }
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {
                        "counterargument": "Rebuttal one",
                        "evidence_refs": ["doc-1"],
                        "strength": 0.9,
                    },
                ]
            )
        )

        results = await engine.generate_counterarguments(prediction_id="pred-1")

        assert len(results) == 1
        # fetch_one for the prediction + execute for the insert
        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_counterarguments_each_gets_unique_id(self, engine, mock_llm, mock_db):
        """Each counterargument receives a unique id."""
        mock_db.fetch_one.return_value = {
            "id": "pred-1",
            "project_id": "proj-1",
            "predicted_argument": "Test",
            "confidence": 0.5,
            "reasoning": "Test",
        }
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                [
                    {"counterargument": "A", "evidence_refs": [], "strength": 0.5},
                    {"counterargument": "B", "evidence_refs": [], "strength": 0.6},
                ]
            )
        )

        results = await engine.generate_counterarguments(prediction_id="pred-1")

        ids = [r["id"] for r in results]
        assert len(set(ids)) == 2


# ---------------------------------------------------------------------------
# SWOT Analysis
# ---------------------------------------------------------------------------


class TestSWOT:
    """Tests for build_swot method."""

    @pytest.mark.asyncio
    async def test_swot_all_quadrants_populated(self, engine, mock_llm, mock_db):
        """SWOT analysis has all 4 sections present and non-empty."""
        mock_db.fetch_all.return_value = [
            {"id": "pred-1", "predicted_argument": "Performance defence", "confidence": 0.8},
        ]

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "strengths": [
                        {
                            "item": "Strong documentary evidence trail",
                            "detail": "Emails and meeting notes support timeline",
                        },
                    ],
                    "weaknesses": [
                        {"item": "Limited witness corroboration", "detail": "Key witnesses no longer employed"},
                    ],
                    "opportunities": [
                        {
                            "item": "Respondent's inconsistent ET3 response",
                            "detail": "Multiple contradictions identified",
                        },
                    ],
                    "threats": [
                        {"item": "Time limitation argument", "detail": "Some claims may be out of time"},
                    ],
                }
            )
        )

        result = await engine.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        assert "strengths" in result
        assert "weaknesses" in result
        assert "opportunities" in result
        assert "threats" in result
        assert len(result["strengths"]) > 0
        assert len(result["weaknesses"]) > 0
        assert len(result["opportunities"]) > 0
        assert len(result["threats"]) > 0

    @pytest.mark.asyncio
    async def test_swot_no_llm_fallback_generates_heuristic(self, engine_no_llm, mock_db):
        """Without LLM, SWOT generates heuristic analysis from DB context."""
        mock_db.fetch_all.return_value = [
            {"predicted_argument": "Performance defence", "confidence": 0.8},
            {"predicted_argument": "Time limitation", "confidence": 0.6},
            {"predicted_argument": "No knowledge of protected characteristic", "confidence": 0.7},
        ]

        result = await engine_no_llm.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        assert "strengths" in result
        assert "weaknesses" in result
        assert "opportunities" in result
        assert "threats" in result
        # At least some quadrants should be populated from heuristics
        total_items = sum(len(result[k]) for k in ["strengths", "weaknesses", "opportunities", "threats"])
        assert total_items > 0, "Heuristic SWOT should produce at least some items"

    @pytest.mark.asyncio
    async def test_swot_no_llm_fallback_no_db_data(self, engine_no_llm, mock_db):
        """Without LLM and no DB data, SWOT still produces generic heuristic items."""
        mock_db.fetch_all.return_value = []

        result = await engine_no_llm.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        total_items = sum(len(result[k]) for k in ["strengths", "weaknesses", "opportunities", "threats"])
        assert total_items > 0, "Generic heuristic SWOT should still have items"

    @pytest.mark.asyncio
    async def test_swot_llm_exception_uses_fallback(self, engine, mock_llm, mock_db):
        """When LLM raises exception, SWOT uses heuristic fallback."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.side_effect = Exception("LLM timeout")

        result = await engine.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        total_items = sum(len(result[k]) for k in ["strengths", "weaknesses", "opportunities", "threats"])
        assert total_items > 0, "Fallback SWOT should produce items on LLM failure"

    @pytest.mark.asyncio
    async def test_swot_heuristic_items_have_correct_structure(self, engine_no_llm, mock_db):
        """Heuristic SWOT items have 'item' and 'detail' fields matching LLM format."""
        mock_db.fetch_all.return_value = []

        result = await engine_no_llm.build_swot(project_id="proj-1")

        for quadrant in ["strengths", "weaknesses", "opportunities", "threats"]:
            for entry in result[quadrant]:
                assert "item" in entry, f"Missing 'item' key in {quadrant}"
                assert "detail" in entry, f"Missing 'detail' key in {quadrant}"

    @pytest.mark.asyncio
    async def test_swot_malformed_llm_response(self, engine, mock_llm, mock_db):
        """Malformed LLM response returns empty SWOT quadrants."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response("Not JSON")

        result = await engine.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        assert result["strengths"] == []
        assert result["weaknesses"] == []
        assert result["opportunities"] == []
        assert result["threats"] == []

    @pytest.mark.asyncio
    async def test_swot_partial_llm_response(self, engine, mock_llm, mock_db):
        """LLM response with only some quadrants still returns all four keys."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response(json.dumps({"strengths": [{"item": "S1", "detail": "D1"}]}))

        result = await engine.build_swot(project_id="proj-1")

        assert "strengths" in result
        assert "weaknesses" in result
        assert "opportunities" in result
        assert "threats" in result
        assert len(result["strengths"]) == 1
        assert result["weaknesses"] == []

    @pytest.mark.asyncio
    async def test_swot_llm_exception_returns_heuristic(self, engine, mock_llm, mock_db):
        """LLM exception returns heuristic SWOT without crashing."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.side_effect = Exception("LLM timeout")

        result = await engine.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        assert "strengths" in result
        assert "weaknesses" in result
        assert "opportunities" in result
        assert "threats" in result
        # Heuristic fallback should produce items
        total_items = sum(len(result[k]) for k in ["strengths", "weaknesses", "opportunities", "threats"])
        assert total_items > 0


# ---------------------------------------------------------------------------
# Red Team
# ---------------------------------------------------------------------------


class TestRedTeam:
    """Tests for red_team method."""

    @pytest.mark.asyncio
    async def test_red_team_identifies_weaknesses(self, engine, mock_llm, mock_db):
        """Red team assessment returns non-empty weakness list."""
        mock_db.fetch_all.return_value = [
            {"id": "pred-1", "predicted_argument": "Performance defence", "confidence": 0.8},
        ]

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "weaknesses": [
                        {
                            "area": "Witness credibility",
                            "vulnerability": "Primary witness has personal relationship with claimant",
                            "exploitation_method": "Cross-examination on bias and partiality",
                        },
                        {
                            "area": "Document gaps",
                            "vulnerability": "No contemporaneous notes for key meeting",
                            "exploitation_method": "Argue fabrication or unreliable recollection",
                        },
                    ],
                    "overall_risk": 0.65,
                }
            )
        )

        result = await engine.red_team(project_id="proj-1", target_id="submission-1")

        assert isinstance(result, dict)
        assert "weaknesses" in result
        assert len(result["weaknesses"]) > 0
        assert "area" in result["weaknesses"][0]
        assert "vulnerability" in result["weaknesses"][0]
        assert "exploitation_method" in result["weaknesses"][0]

    @pytest.mark.asyncio
    async def test_red_team_overall_risk_bounded(self, engine, mock_llm, mock_db):
        """Overall risk score is between 0.0 and 1.0."""
        mock_db.fetch_all.return_value = []

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "weaknesses": [
                        {"area": "Test", "vulnerability": "Test", "exploitation_method": "Test"},
                    ],
                    "overall_risk": 0.45,
                }
            )
        )

        result = await engine.red_team(project_id="proj-1", target_id="target-1")

        assert "overall_risk" in result
        assert 0.0 <= result["overall_risk"] <= 1.0

    @pytest.mark.asyncio
    async def test_red_team_emits_event(self, engine, mock_llm, mock_db, mock_event_bus):
        """Red team completion emits strategist.redteam.completed event."""
        mock_db.fetch_all.return_value = []

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "weaknesses": [],
                    "overall_risk": 0.1,
                }
            )
        )

        await engine.red_team(project_id="proj-1", target_id="target-1")

        mock_event_bus.emit.assert_called()
        call_args = mock_event_bus.emit.call_args_list
        event_names = [c[0][0] for c in call_args]
        assert "strategist.redteam.completed" in event_names

    @pytest.mark.asyncio
    async def test_red_team_clamps_risk_score(self, engine, mock_llm, mock_db):
        """Risk scores outside 0-1 range are clamped."""
        mock_db.fetch_all.return_value = []

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "weaknesses": [],
                    "overall_risk": 1.5,
                }
            )
        )

        result = await engine.red_team(project_id="proj-1", target_id="target-1")

        assert result["overall_risk"] <= 1.0

    @pytest.mark.asyncio
    async def test_red_team_no_llm_fallback_returns_template_weaknesses(self, engine_no_llm):
        """Without LLM, red team returns template vulnerability patterns."""
        result = await engine_no_llm.red_team(project_id="proj-1", target_id="target-1")

        assert isinstance(result, dict)
        assert len(result["weaknesses"]) > 0, "Heuristic red team should identify template weaknesses"
        assert 0.0 <= result["overall_risk"] <= 1.0
        for w in result["weaknesses"]:
            assert "area" in w
            assert "vulnerability" in w
            assert "exploitation_method" in w

    @pytest.mark.asyncio
    async def test_red_team_llm_exception_uses_fallback(self, engine, mock_llm, mock_db):
        """When LLM raises exception, red team uses heuristic fallback."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.side_effect = Exception("LLM error")

        result = await engine.red_team(project_id="proj-1", target_id="target-1")

        assert isinstance(result, dict)
        assert len(result["weaknesses"]) > 0, "Fallback should produce template weaknesses"

    @pytest.mark.asyncio
    async def test_red_team_fallback_covers_key_areas(self, engine_no_llm):
        """Heuristic red team covers burden of proof, hearsay, and timeline areas."""
        result = await engine_no_llm.red_team(project_id="proj-1", target_id="target-1")

        areas = [w["area"].lower() for w in result["weaknesses"]]
        areas_text = " ".join(areas)
        # Should cover at least two of: burden of proof, hearsay, timeline
        covered = sum(
            1 for keyword in ["burden", "hearsay", "timeline", "witness", "evidence"] if keyword in areas_text
        )
        assert covered >= 2, f"Expected coverage of key vulnerability areas, got: {areas}"

    @pytest.mark.asyncio
    async def test_red_team_malformed_llm_response(self, engine, mock_llm, mock_db):
        """Malformed LLM response returns empty red team result."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response("Not valid JSON")

        result = await engine.red_team(project_id="proj-1", target_id="target-1")

        assert isinstance(result, dict)
        # When LLM response is malformed, the LLM layer returns default
        assert "weaknesses" in result
        assert "overall_risk" in result

    @pytest.mark.asyncio
    async def test_red_team_clamps_negative_risk_score(self, engine, mock_llm, mock_db):
        """Negative risk scores are clamped to 0.0."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response(json.dumps({"weaknesses": [], "overall_risk": -0.5}))

        result = await engine.red_team(project_id="proj-1", target_id="target-1")

        assert result["overall_risk"] >= 0.0

    @pytest.mark.asyncio
    async def test_red_team_persists_report(self, engine, mock_llm, mock_db):
        """Red team report is persisted to database."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "weaknesses": [{"area": "Test", "vulnerability": "V", "exploitation_method": "E"}],
                    "overall_risk": 0.5,
                }
            )
        )

        await engine.red_team(project_id="proj-1", target_id="target-1")

        # Should have at least one INSERT call for the report
        insert_calls = [
            c
            for c in mock_db.execute.call_args_list
            if "INSERT" in str(c.args[0]) and "red_team_reports" in str(c.args[0])
        ]
        assert len(insert_calls) == 1

    @pytest.mark.asyncio
    async def test_red_team_llm_exception_returns_heuristic(self, engine, mock_llm, mock_db):
        """LLM exception returns heuristic red team result without crashing."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.side_effect = Exception("LLM error")

        result = await engine.red_team(project_id="proj-1", target_id="target-1")

        assert isinstance(result, dict)
        assert len(result["weaknesses"]) > 0  # Heuristic fallback
        assert 0.0 <= result["overall_risk"] <= 1.0


# ---------------------------------------------------------------------------
# Tactical Model
# ---------------------------------------------------------------------------


class TestTacticalModel:
    """Tests for build_tactical_model method."""

    @pytest.mark.asyncio
    async def test_tactical_model_profiles_respondent(self, engine, mock_llm, mock_db):
        """Tactical model includes profile_summary."""
        mock_db.fetch_all.return_value = []

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "tactics": [
                        {
                            "tactic": "Delay and exhaust",
                            "likelihood": 0.8,
                            "counter_strategy": "Apply for unless orders on disclosure deadlines",
                        },
                        {
                            "tactic": "Minimise evidence scope",
                            "likelihood": 0.7,
                            "counter_strategy": "Specific disclosure application with relevance justification",
                        },
                    ],
                    "profile_summary": (
                        "TLT Solicitors acting for Bylor Ltd typically employ a strategy of procedural "
                        "delay combined with aggressive cost warnings. They favour narrowing issues at "
                        "preliminary hearings and resisting broad disclosure."
                    ),
                }
            )
        )

        result = await engine.build_tactical_model(project_id="proj-1", respondent_id="resp-1")

        assert isinstance(result, dict)
        assert "tactics" in result
        assert len(result["tactics"]) > 0
        assert "tactic" in result["tactics"][0]
        assert "likelihood" in result["tactics"][0]
        assert "counter_strategy" in result["tactics"][0]
        assert "profile_summary" in result
        assert len(result["profile_summary"]) > 0

    @pytest.mark.asyncio
    async def test_tactical_model_no_llm_fallback(self, engine_no_llm):
        """Without LLM, tactical model returns empty result."""
        result = await engine_no_llm.build_tactical_model(project_id="proj-1", respondent_id="resp-1")

        assert isinstance(result, dict)
        assert result["tactics"] == []
        assert "profile_summary" in result

    @pytest.mark.asyncio
    async def test_tactical_model_stores_to_db(self, engine, mock_llm, mock_db):
        """Tactical model is persisted to the database."""
        mock_db.fetch_all.return_value = []

        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "tactics": [
                        {"tactic": "Delay", "likelihood": 0.8, "counter_strategy": "Apply for orders"},
                    ],
                    "profile_summary": "Standard respondent behaviour pattern",
                }
            )
        )

        await engine.build_tactical_model(project_id="proj-1", respondent_id="resp-1")

        assert mock_db.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_tactical_model_malformed_llm_response(self, engine, mock_llm, mock_db):
        """Malformed LLM response returns empty tactical model."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response("Not JSON")

        result = await engine.build_tactical_model(project_id="proj-1", respondent_id="resp-1")

        assert isinstance(result, dict)
        assert result["tactics"] == []
        assert result["profile_summary"] == ""

    @pytest.mark.asyncio
    async def test_tactical_model_llm_exception_returns_empty(self, engine, mock_llm, mock_db):
        """LLM exception returns empty tactical model without crashing."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.side_effect = Exception("LLM timeout")

        result = await engine.build_tactical_model(project_id="proj-1", respondent_id="resp-1")

        assert result == {"tactics": [], "profile_summary": ""}

    @pytest.mark.asyncio
    async def test_tactical_model_partial_response(self, engine, mock_llm, mock_db):
        """LLM response with only tactics still returns profile_summary key."""
        mock_db.fetch_all.return_value = []
        mock_llm.generate.return_value = _make_llm_response(
            json.dumps(
                {
                    "tactics": [
                        {"tactic": "Delay", "likelihood": 0.7, "counter_strategy": "Push back"},
                    ],
                }
            )
        )

        result = await engine.build_tactical_model(project_id="proj-1", respondent_id="resp-1")

        assert "tactics" in result
        assert "profile_summary" in result
        assert len(result["tactics"]) == 1
        assert result["profile_summary"] == ""


# ---------------------------------------------------------------------------
# LLM JSON Parsing (markdown code blocks)
# ---------------------------------------------------------------------------


class TestLLMJsonParsing:
    """Tests for the LLM layer's JSON extraction from various response formats."""

    def test_parse_json_from_markdown_code_block(self):
        """LLM response wrapped in markdown code block is parsed correctly."""
        from arkham_shard_strategist.llm import StrategistLLM

        llm = StrategistLLM(llm_service=None)
        response = MagicMock()
        response.text = '```json\n{"strengths": ["s1"]}\n```'

        parsed = llm._parse_json(response)
        assert parsed == {"strengths": ["s1"]}

    def test_parse_json_direct(self):
        """Direct JSON is parsed without issue."""
        from arkham_shard_strategist.llm import StrategistLLM

        llm = StrategistLLM(llm_service=None)
        response = MagicMock()
        response.text = '[{"argument": "test"}]'

        parsed = llm._parse_json(response)
        assert isinstance(parsed, list)
        assert parsed[0]["argument"] == "test"

    def test_parse_json_empty_text(self):
        """Empty response text returns None."""
        from arkham_shard_strategist.llm import StrategistLLM

        llm = StrategistLLM(llm_service=None)
        response = MagicMock()
        response.text = ""

        parsed = llm._parse_json(response)
        assert parsed is None

    def test_parse_json_no_text_attribute(self):
        """Response without .text attribute returns None."""
        from arkham_shard_strategist.llm import StrategistLLM

        llm = StrategistLLM(llm_service=None)
        response = object()

        parsed = llm._parse_json(response)
        assert parsed is None


# ---------------------------------------------------------------------------
# Event Handlers
# ---------------------------------------------------------------------------


class TestShardEventHandlers:
    """Tests for shard-level event handlers."""

    @pytest.fixture
    def mock_engine(self):
        engine = AsyncMock()
        engine.predict_arguments = AsyncMock(return_value=[])
        engine.build_tactical_model = AsyncMock(return_value={})
        engine.red_team = AsyncMock(return_value={})
        return engine

    @pytest.mark.asyncio
    async def test_handle_strategy_updated_calls_predict(self, mock_engine):
        """Strategy updated event triggers predict_arguments."""
        from arkham_shard_strategist.shard import StrategistShard

        shard = StrategistShard()
        shard.engine = mock_engine

        await shard.handle_strategy_updated({"project_id": "proj-1"})

        mock_engine.predict_arguments.assert_called_once_with(project_id="proj-1")

    @pytest.mark.asyncio
    async def test_handle_profile_updated_calls_tactical_model(self, mock_engine):
        """Profile updated event triggers build_tactical_model."""
        from arkham_shard_strategist.shard import StrategistShard

        shard = StrategistShard()
        shard.engine = mock_engine

        await shard.handle_profile_updated({"project_id": "proj-1", "respondent_id": "resp-1"})

        mock_engine.build_tactical_model.assert_called_once_with(project_id="proj-1", respondent_id="resp-1")

    @pytest.mark.asyncio
    async def test_handle_statement_created_calls_red_team(self, mock_engine):
        """Statement created event triggers red_team."""
        from arkham_shard_strategist.shard import StrategistShard

        shard = StrategistShard()
        shard.engine = mock_engine

        await shard.handle_statement_created({"project_id": "proj-1", "statement_id": "stmt-1"})

        mock_engine.red_team.assert_called_once_with(project_id="proj-1", target_id="stmt-1")

    @pytest.mark.asyncio
    async def test_handle_strategy_updated_no_project_id(self, mock_engine):
        """Missing project_id in event does not call engine."""
        from arkham_shard_strategist.shard import StrategistShard

        shard = StrategistShard()
        shard.engine = mock_engine

        await shard.handle_strategy_updated({})

        mock_engine.predict_arguments.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_strategy_updated_engine_error_no_crash(self, mock_engine):
        """Engine exception in event handler does not crash the shard."""
        from arkham_shard_strategist.shard import StrategistShard

        shard = StrategistShard()
        shard.engine = mock_engine
        mock_engine.predict_arguments.side_effect = Exception("Engine failure")

        # Should not raise
        await shard.handle_strategy_updated({"project_id": "proj-1"})
