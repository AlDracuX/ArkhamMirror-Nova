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
    async def test_predict_arguments_no_llm_fallback(self, engine_no_llm):
        """Without LLM, predict_arguments returns empty list gracefully."""
        results = await engine_no_llm.predict_arguments(project_id="proj-1")

        assert isinstance(results, list)
        assert len(results) == 0

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
    async def test_swot_no_llm_fallback(self, engine_no_llm):
        """Without LLM, SWOT returns empty quadrants."""
        result = await engine_no_llm.build_swot(project_id="proj-1")

        assert isinstance(result, dict)
        assert result["strengths"] == []
        assert result["weaknesses"] == []
        assert result["opportunities"] == []
        assert result["threats"] == []


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
    async def test_red_team_no_llm_fallback(self, engine_no_llm):
        """Without LLM, red team returns empty result."""
        result = await engine_no_llm.red_team(project_id="proj-1", target_id="target-1")

        assert isinstance(result, dict)
        assert result["weaknesses"] == []
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
