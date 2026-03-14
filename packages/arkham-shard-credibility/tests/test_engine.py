"""
Tests for credibility scoring engine.

TDD: These tests define the contract for CredibilityEngine before implementation.
Covers consistency, corroboration, specificity scoring, and overall scoring.
"""

import pytest
from arkham_shard_credibility.engine import CredibilityEngine


@pytest.fixture
def engine():
    """Create a CredibilityEngine instance without dependencies."""
    return CredibilityEngine()


# =============================================================================
# CONSISTENCY SCORING
# =============================================================================


class TestConsistencyScoring:
    """Test consistency detection between witness statements."""

    def test_identical_statements_score_high(self, engine):
        """Repeated consistent statements should score high."""
        statements = [
            "The meeting took place on 14 March 2024 at 10am.",
            "I attended the meeting on 14 March 2024 at 10am.",
        ]
        result = engine.score_consistency(statements)
        assert result["score"] >= 70
        assert "evidence" in result

    def test_contradictory_statements_score_low(self, engine):
        """Directly contradictory statements should score low."""
        statements = [
            "I was not present at the meeting on 14 March.",
            "I attended the meeting on 14 March and took notes.",
        ]
        result = engine.score_consistency(statements)
        assert result["score"] <= 50
        assert len(result["evidence"]) > 0

    def test_single_statement_returns_neutral(self, engine):
        """A single statement cannot be assessed for consistency."""
        statements = ["I saw the incident on Tuesday."]
        result = engine.score_consistency(statements)
        assert result["score"] == 70  # neutral baseline for single statement
        assert "single statement" in result["evidence"][0].lower() or result["score"] == 70

    def test_empty_statements_returns_zero(self, engine):
        """No statements should return zero score."""
        result = engine.score_consistency([])
        assert result["score"] == 0

    def test_contradictory_negation_detected(self, engine):
        """Negation-based contradictions should be caught."""
        statements = [
            "I did receive the email on 5 January.",
            "I never received any email about this matter.",
        ]
        result = engine.score_consistency(statements)
        assert result["score"] <= 50

    def test_temporal_contradiction_detected(self, engine):
        """Different dates for same event should be caught."""
        statements = [
            "The disciplinary hearing was held on 10 April 2024.",
            "The disciplinary hearing took place on 15 May 2024.",
        ]
        result = engine.score_consistency(statements)
        assert result["score"] <= 60

    def test_many_consistent_statements_score_very_high(self, engine):
        """Multiple consistent statements reinforce credibility."""
        statements = [
            "The grievance was filed on 1 June 2024.",
            "I submitted my grievance on 1 June 2024.",
            "My formal grievance, dated 1 June 2024, was acknowledged.",
            "On 1 June 2024 I lodged the grievance with HR.",
        ]
        result = engine.score_consistency(statements)
        assert result["score"] >= 75


# =============================================================================
# CORROBORATION SCORING
# =============================================================================


class TestCorroborationScoring:
    """Test corroboration checking between testimony and documents."""

    def test_well_corroborated_scores_high(self, engine):
        """Claims supported by documents should score high."""
        statements = [
            "I sent the complaint email on 12 February 2024.",
            "The disciplinary hearing was on 20 March 2024.",
        ]
        documents = [
            {"title": "Complaint email", "text": "Email sent 12 February 2024 from claimant to HR."},
            {"title": "Hearing minutes", "text": "Disciplinary hearing held 20 March 2024."},
        ]
        result = engine.score_corroboration(statements, documents)
        assert result["score"] >= 60
        assert "evidence" in result

    def test_uncorroborated_scores_low(self, engine):
        """Claims with no document support should score low."""
        statements = [
            "I was promised a promotion in December 2023.",
            "My manager said I would be made permanent.",
        ]
        documents = [
            {"title": "Employment contract", "text": "Fixed-term contract from 1 Jan 2023 to 31 Dec 2023."},
        ]
        result = engine.score_corroboration(statements, documents)
        assert result["score"] <= 50

    def test_no_documents_returns_low(self, engine):
        """No documents at all should score very low."""
        statements = ["I was harassed repeatedly at work."]
        result = engine.score_corroboration(statements, [])
        assert result["score"] <= 30

    def test_no_statements_returns_zero(self, engine):
        """No statements should return zero."""
        result = engine.score_corroboration([], [{"title": "doc", "text": "text"}])
        assert result["score"] == 0

    def test_partial_corroboration(self, engine):
        """Some claims supported, others not, gives moderate score."""
        statements = [
            "The meeting was on 5 May 2024.",
            "I was denied sick leave on 10 June 2024.",
            "A verbal warning was given on 1 July 2024.",
        ]
        documents = [
            {"title": "Meeting minutes", "text": "Meeting held 5 May 2024 with all parties present."},
        ]
        result = engine.score_corroboration(statements, documents)
        assert 20 <= result["score"] <= 70


# =============================================================================
# SPECIFICITY SCORING
# =============================================================================


class TestSpecificityScoring:
    """Test specificity measurement of witness statements."""

    def test_highly_specific_scores_high(self, engine):
        """Statements with dates, names, and details should score high."""
        statements = [
            "On 14 March 2024 at 2:30pm, I met with Sarah Jones in Meeting Room 3 "
            "to discuss the grievance reference GR-2024-015.",
        ]
        result = engine.score_specificity(statements)
        assert result["score"] >= 70
        assert "evidence" in result

    def test_vague_statements_score_low(self, engine):
        """Vague statements without specifics should score low."""
        statements = [
            "I think it was sometime around then that something happened.",
            "Someone said something about it at some point.",
        ]
        result = engine.score_specificity(statements)
        assert result["score"] <= 40

    def test_empty_statements_returns_zero(self, engine):
        """No statements should return zero."""
        result = engine.score_specificity([])
        assert result["score"] == 0

    def test_date_patterns_boost_score(self, engine):
        """Specific date mentions should increase specificity."""
        statements = [
            "The incident occurred on 22 November 2023.",
            "I reported it on 23 November 2023.",
        ]
        result = engine.score_specificity(statements)
        assert result["score"] >= 50

    def test_hedging_language_reduces_score(self, engine):
        """Hedging words like 'perhaps', 'maybe' should reduce specificity."""
        statements = [
            "I think perhaps it was maybe around March or April, I'm not sure.",
            "It might have been discussed, possibly, I cannot really recall.",
        ]
        result = engine.score_specificity(statements)
        assert result["score"] <= 35

    def test_mixed_specificity(self, engine):
        """Mix of specific and vague should give moderate score."""
        statements = [
            "On 14 March 2024, I spoke to my manager John Smith.",
            "Something happened after that but I don't really remember when.",
        ]
        result = engine.score_specificity(statements)
        assert 30 <= result["score"] <= 70


# =============================================================================
# OVERALL SCORING
# =============================================================================


class TestOverallScoring:
    """Test the combined credibility scoring."""

    def test_score_witness_returns_all_factors(self, engine):
        """score_witness should return overall + per-factor breakdown."""
        statements = [
            "The meeting was on 14 March 2024 at 10am.",
            "I attended the meeting on 14 March 2024.",
        ]
        documents = [
            {"title": "Minutes", "text": "Meeting held 14 March 2024 at 10am."},
        ]
        result = engine.score_witness(statements, documents)

        assert "overall_score" in result
        assert 0 <= result["overall_score"] <= 100
        assert "factors" in result
        assert len(result["factors"]) == 3

        factor_names = {f["name"] for f in result["factors"]}
        assert "consistency" in factor_names
        assert "corroboration" in factor_names
        assert "specificity" in factor_names

        for factor in result["factors"]:
            assert "name" in factor
            assert "score" in factor
            assert "weight" in factor
            assert "evidence" in factor
            assert 0 <= factor["score"] <= 100
            assert 0.0 < factor["weight"] <= 1.0

    def test_weights_sum_to_one(self, engine):
        """Factor weights should sum to 1.0."""
        result = engine.score_witness(["test statement"], [])
        total_weight = sum(f["weight"] for f in result["factors"])
        assert abs(total_weight - 1.0) < 0.001

    def test_highly_credible_witness(self, engine):
        """A witness with consistent, corroborated, specific testimony should score high."""
        statements = [
            "On 14 March 2024 at 10:00am, I attended the disciplinary hearing in Room 4B.",
            "The disciplinary hearing on 14 March 2024 at 10am was chaired by Helen Clarke.",
            "I submitted my written response on 12 March 2024 via email to HR.",
        ]
        documents = [
            {"title": "Hearing notice", "text": "Disciplinary hearing scheduled 14 March 2024 10:00 Room 4B."},
            {"title": "Email record", "text": "Email from claimant to HR dated 12 March 2024 with written response."},
            {"title": "Hearing minutes", "text": "Hearing chaired by Helen Clarke on 14 March 2024."},
        ]
        result = engine.score_witness(statements, documents)
        assert result["overall_score"] >= 65

    def test_low_credibility_witness(self, engine):
        """A witness with contradictory, unsupported, vague testimony should score low."""
        statements = [
            "I think something happened sometime in March maybe.",
            "I wasn't there but I heard about it from someone.",
            "Actually I was there, or perhaps it was a different meeting.",
        ]
        documents = []
        result = engine.score_witness(statements, documents)
        assert result["overall_score"] <= 45

    def test_empty_everything_returns_zero(self, engine):
        """No statements and no documents should return zero."""
        result = engine.score_witness([], [])
        assert result["overall_score"] == 0

    def test_credibility_level_classification(self, engine):
        """Result should include a credibility level string."""
        result = engine.score_witness(
            ["On 14 March 2024 I attended the hearing."],
            [{"title": "Notice", "text": "Hearing on 14 March 2024."}],
        )
        assert "level" in result
        assert result["level"] in ("unreliable", "low", "medium", "high", "verified")


# =============================================================================
# TIMELINESS SCORING
# =============================================================================


class TestTimelinessScoring:
    """Test timeliness measurement of witness statements relative to events."""

    def test_recent_statements_score_high(self, engine):
        """Statements about events with dates close to event dates should score high."""
        statements = [
            "On 14 March 2024 I attended the hearing.",
            "I submitted the complaint on 12 March 2024.",
        ]
        events = [
            {"text": "Disciplinary hearing", "date": "2024-03-14"},
            {"text": "Complaint filed", "date": "2024-03-12"},
        ]
        result = engine.score_timeliness(statements, events)
        assert result["score"] >= 60
        assert "evidence" in result

    def test_old_statements_score_low(self, engine):
        """Statements about events far from event dates should score low."""
        statements = [
            "I remember something happening in early 2020.",
        ]
        events = [
            {"text": "Incident reported", "date": "2024-03-14"},
        ]
        result = engine.score_timeliness(statements, events)
        assert result["score"] <= 50

    def test_no_events_returns_neutral(self, engine):
        """No events should return neutral score."""
        statements = ["I attended the meeting on 14 March 2024."]
        result = engine.score_timeliness(statements, [])
        assert result["score"] == 50
        assert "evidence" in result

    def test_no_statements_returns_zero(self, engine):
        """No statements should return zero."""
        events = [{"text": "Hearing", "date": "2024-03-14"}]
        result = engine.score_timeliness([], events)
        assert result["score"] == 0

    def test_mixed_timeliness(self, engine):
        """Mix of recent and slightly older references gives moderate score."""
        statements = [
            "The meeting was held on 14 March 2024.",
            "The earlier incident was on 15 December 2023.",
        ]
        events = [
            {"text": "Meeting", "date": "2024-03-14"},
            {"text": "Earlier incident", "date": "2024-01-15"},
        ]
        result = engine.score_timeliness(statements, events)
        # One exact match, one ~2 months off -> moderate-to-high
        assert 40 <= result["score"] <= 90


# =============================================================================
# FOUR-FACTOR SCORING
# =============================================================================


class TestFourFactorScoring:
    """Test score_witness with events for four-factor scoring."""

    def test_with_events_returns_four_factors(self, engine):
        """When events are provided, score_witness should include timeliness."""
        statements = ["On 14 March 2024 I attended the hearing."]
        documents = [{"title": "Notice", "text": "Hearing on 14 March 2024."}]
        events = [{"text": "Hearing", "date": "2024-03-14"}]
        result = engine.score_witness(statements, documents, events=events)

        assert "factors" in result
        factor_names = {f["name"] for f in result["factors"]}
        assert "timeliness" in factor_names
        assert len(result["factors"]) == 4

    def test_four_factor_weights_sum_to_one(self, engine):
        """Four-factor weights should sum to 1.0."""
        statements = ["On 14 March 2024 I attended the hearing."]
        documents = [{"title": "Notice", "text": "Hearing on 14 March 2024."}]
        events = [{"text": "Hearing", "date": "2024-03-14"}]
        result = engine.score_witness(statements, documents, events=events)
        total_weight = sum(f["weight"] for f in result["factors"])
        assert abs(total_weight - 1.0) < 0.001

    def test_without_events_still_three_factors(self, engine):
        """Without events, should still use three-factor scoring."""
        statements = ["On 14 March 2024 I attended the hearing."]
        documents = [{"title": "Notice", "text": "Hearing on 14 March 2024."}]
        result = engine.score_witness(statements, documents)
        factor_names = {f["name"] for f in result["factors"]}
        assert "timeliness" not in factor_names
        assert len(result["factors"]) == 3

    def test_four_factor_uses_requested_weights(self, engine):
        """Four-factor scoring uses consistency=0.3, corroboration=0.3, specificity=0.2, timeliness=0.2."""
        statements = ["On 14 March 2024 I attended the hearing."]
        documents = [{"title": "Notice", "text": "Hearing on 14 March 2024."}]
        events = [{"text": "Hearing", "date": "2024-03-14"}]
        result = engine.score_witness(statements, documents, events=events)

        weight_map = {f["name"]: f["weight"] for f in result["factors"]}
        assert abs(weight_map["consistency"] - 0.3) < 0.001
        assert abs(weight_map["corroboration"] - 0.3) < 0.001
        assert abs(weight_map["specificity"] - 0.2) < 0.001
        assert abs(weight_map["timeliness"] - 0.2) < 0.001
