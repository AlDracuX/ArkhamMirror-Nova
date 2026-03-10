"""Strategist Engine - Core domain logic for adversarial modelling.

Orchestrates LLM-powered analysis with database persistence and event emission.
All methods gracefully degrade when LLM is unavailable.
"""

import json
import logging
import uuid
from typing import Any

from .llm import StrategistLLM

logger = logging.getLogger(__name__)


class StrategistEngine:
    """
    Core engine for the Strategist shard.

    Coordinates LLM analysis, database persistence, and event emission
    for adversarial modelling and red-teaming operations.
    """

    def __init__(self, db=None, event_bus=None, llm_service=None):
        self._db = db
        self._event_bus = event_bus
        self._llm = StrategistLLM(llm_service=llm_service)

    # -------------------------------------------------------------------------
    # Predict Arguments
    # -------------------------------------------------------------------------

    async def predict_arguments(self, project_id: str, claim_id: str | None = None) -> list[dict]:
        """Generate predicted respondent arguments using LLM + case context.

        Returns list of dicts: [{argument, confidence, reasoning, likely_evidence}].
        Returns empty list if LLM is unavailable.
        """
        if not self._llm.is_available:
            logger.warning("LLM not available — skipping argument prediction")
            return []

        # Gather context from existing predictions if available
        context = ""
        if self._db:
            try:
                existing = await self._db.fetch_all(
                    "SELECT predicted_argument FROM arkham_strategist.predictions WHERE project_id = :project_id",
                    {"project_id": project_id},
                )
                if existing:
                    context = "Existing predictions:\n" + "\n".join(
                        f"- {row['predicted_argument']}" for row in existing
                    )
            except Exception as e:
                logger.debug(f"Could not fetch existing predictions: {e}")

        try:
            predictions = await self._llm.predict_arguments(
                project_id=project_id,
                claim_id=claim_id,
                context=context,
            )
        except Exception as e:
            logger.error(f"LLM prediction failed: {e}")
            return []

        # Persist each prediction
        for pred in predictions:
            pred_id = str(uuid.uuid4())
            pred["id"] = pred_id
            if self._db:
                try:
                    await self._db.execute(
                        """
                        INSERT INTO arkham_strategist.predictions
                        (id, project_id, claim_id, predicted_argument, confidence, reasoning, metadata)
                        VALUES (:id, :project_id, :claim_id, :argument, :confidence, :reasoning, :metadata)
                        """,
                        {
                            "id": pred_id,
                            "project_id": project_id,
                            "claim_id": claim_id,
                            "argument": pred.get("argument", ""),
                            "confidence": pred.get("confidence", 0.0),
                            "reasoning": pred.get("reasoning", ""),
                            "metadata": json.dumps({"likely_evidence": pred.get("likely_evidence", [])}),
                        },
                    )
                except Exception as e:
                    logger.error(f"Failed to persist prediction: {e}")

        # Emit event
        if self._event_bus and predictions:
            try:
                await self._event_bus.emit(
                    "strategist.prediction.created",
                    {"project_id": project_id, "count": len(predictions)},
                    source="strategist-shard",
                )
            except Exception as e:
                logger.error(f"Failed to emit prediction event: {e}")

        return predictions

    # -------------------------------------------------------------------------
    # Counterarguments
    # -------------------------------------------------------------------------

    async def generate_counterarguments(self, prediction_id: str) -> list[dict]:
        """Generate counterarguments for a predicted argument.

        Returns list of dicts: [{counterargument, evidence_refs, strength}].
        Returns empty list if LLM is unavailable.
        """
        if not self._llm.is_available:
            logger.warning("LLM not available — skipping counterargument generation")
            return []

        # Fetch the prediction
        prediction = None
        if self._db:
            try:
                prediction = await self._db.fetch_one(
                    "SELECT * FROM arkham_strategist.predictions WHERE id = :id",
                    {"id": prediction_id},
                )
            except Exception as e:
                logger.error(f"Failed to fetch prediction: {e}")

        if not prediction:
            logger.warning(f"Prediction {prediction_id} not found")
            return []

        pred_dict = dict(prediction) if not isinstance(prediction, dict) else prediction

        try:
            counters = await self._llm.generate_counterarguments(pred_dict)
        except Exception as e:
            logger.error(f"LLM counterargument generation failed: {e}")
            return []

        # Persist counterarguments
        for counter in counters:
            counter_id = str(uuid.uuid4())
            counter["id"] = counter_id
            if self._db:
                try:
                    await self._db.execute(
                        """
                        INSERT INTO arkham_strategist.counterarguments
                        (id, prediction_id, argument, rebuttal_strategy, evidence_ids)
                        VALUES (:id, :prediction_id, :argument, :rebuttal, :evidence_ids)
                        """,
                        {
                            "id": counter_id,
                            "prediction_id": prediction_id,
                            "argument": counter.get("counterargument", ""),
                            "rebuttal": counter.get("counterargument", ""),
                            "evidence_ids": json.dumps(counter.get("evidence_refs", [])),
                        },
                    )
                except Exception as e:
                    logger.error(f"Failed to persist counterargument: {e}")

        return counters

    # -------------------------------------------------------------------------
    # SWOT Analysis
    # -------------------------------------------------------------------------

    async def build_swot(self, project_id: str) -> dict:
        """Build SWOT analysis for current litigation position.

        Returns dict: {strengths: [...], weaknesses: [...], opportunities: [...], threats: [...]}.
        Returns empty quadrants if LLM is unavailable.
        """
        empty_swot = {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}

        if not self._llm.is_available:
            logger.warning("LLM not available — returning empty SWOT")
            return empty_swot

        # Gather context from existing data
        context = ""
        if self._db:
            try:
                preds = await self._db.fetch_all(
                    "SELECT predicted_argument, confidence FROM arkham_strategist.predictions "
                    "WHERE project_id = :project_id ORDER BY confidence DESC LIMIT 10",
                    {"project_id": project_id},
                )
                if preds:
                    context = "Known respondent arguments:\n" + "\n".join(
                        f"- {row['predicted_argument']} (confidence: {row['confidence']})" for row in preds
                    )
            except Exception as e:
                logger.debug(f"Could not fetch context for SWOT: {e}")

        try:
            return await self._llm.build_swot(project_id=project_id, context=context)
        except Exception as e:
            logger.error(f"LLM SWOT analysis failed: {e}")
            return empty_swot

    # -------------------------------------------------------------------------
    # Red Team
    # -------------------------------------------------------------------------

    async def red_team(self, project_id: str, target_id: str) -> dict:
        """Attack own case from respondent's perspective.

        Returns dict: {weaknesses: [{area, vulnerability, exploitation_method}], overall_risk: 0.0-1.0}.
        Returns empty result if LLM is unavailable.
        """
        empty_result = {"weaknesses": [], "overall_risk": 0.0}

        if not self._llm.is_available:
            logger.warning("LLM not available — returning empty red team result")
            return empty_result

        # Gather context
        context = ""
        if self._db:
            try:
                preds = await self._db.fetch_all(
                    "SELECT predicted_argument, confidence FROM arkham_strategist.predictions "
                    "WHERE project_id = :project_id",
                    {"project_id": project_id},
                )
                if preds:
                    context = "Predicted respondent arguments:\n" + "\n".join(
                        f"- {row['predicted_argument']}" for row in preds
                    )
            except Exception as e:
                logger.debug(f"Could not fetch context for red team: {e}")

        try:
            result = await self._llm.red_team(
                project_id=project_id,
                target_id=target_id,
                context=context,
            )
        except Exception as e:
            logger.error(f"LLM red team failed: {e}")
            return empty_result

        # Persist report
        report_id = str(uuid.uuid4())
        if self._db:
            try:
                await self._db.execute(
                    """
                    INSERT INTO arkham_strategist.red_team_reports
                    (id, project_id, target_id, weaknesses, recommendations, overall_risk_score)
                    VALUES (:id, :project_id, :target_id, :weaknesses, :recommendations, :risk_score)
                    """,
                    {
                        "id": report_id,
                        "project_id": project_id,
                        "target_id": target_id,
                        "weaknesses": json.dumps(result.get("weaknesses", [])),
                        "recommendations": json.dumps([]),
                        "risk_score": result.get("overall_risk", 0.0),
                    },
                )
            except Exception as e:
                logger.error(f"Failed to persist red team report: {e}")

        # Emit event
        if self._event_bus:
            try:
                await self._event_bus.emit(
                    "strategist.redteam.completed",
                    {"project_id": project_id, "target_id": target_id, "report_id": report_id},
                    source="strategist-shard",
                )
            except Exception as e:
                logger.error(f"Failed to emit red team event: {e}")

        return result

    # -------------------------------------------------------------------------
    # Tactical Model
    # -------------------------------------------------------------------------

    async def build_tactical_model(self, project_id: str, respondent_id: str) -> dict:
        """Model respondent's likely tactics based on behaviour patterns.

        Returns dict: {tactics: [{tactic, likelihood, counter_strategy}], profile_summary: str}.
        Returns empty result if LLM is unavailable.
        """
        empty_result = {"tactics": [], "profile_summary": ""}

        if not self._llm.is_available:
            logger.warning("LLM not available — returning empty tactical model")
            return empty_result

        # Gather context from existing tactical models
        context = ""
        if self._db:
            try:
                existing = await self._db.fetch_all(
                    "SELECT likely_tactics, metadata FROM arkham_strategist.tactical_models "
                    "WHERE project_id = :project_id AND respondent_id = :respondent_id "
                    "ORDER BY created_at DESC LIMIT 1",
                    {"project_id": project_id, "respondent_id": respondent_id},
                )
                if existing:
                    context = f"Previous tactical assessment: {existing[0].get('likely_tactics', '')}"
            except Exception as e:
                logger.debug(f"Could not fetch context for tactical model: {e}")

        try:
            result = await self._llm.build_tactical_model(
                project_id=project_id,
                respondent_id=respondent_id,
                context=context,
            )
        except Exception as e:
            logger.error(f"LLM tactical model failed: {e}")
            return empty_result

        # Persist
        model_id = str(uuid.uuid4())
        if self._db:
            try:
                await self._db.execute(
                    """
                    INSERT INTO arkham_strategist.tactical_models
                    (id, project_id, respondent_id, likely_tactics, counter_measures, metadata)
                    VALUES (:id, :project_id, :respondent_id, :tactics, :counters, :metadata)
                    """,
                    {
                        "id": model_id,
                        "project_id": project_id,
                        "respondent_id": respondent_id,
                        "tactics": json.dumps(result.get("tactics", [])),
                        "counters": json.dumps([t.get("counter_strategy", "") for t in result.get("tactics", [])]),
                        "metadata": json.dumps({"profile_summary": result.get("profile_summary", "")}),
                    },
                )
            except Exception as e:
                logger.error(f"Failed to persist tactical model: {e}")

        return result
