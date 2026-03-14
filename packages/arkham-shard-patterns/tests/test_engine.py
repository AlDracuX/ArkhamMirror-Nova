"""
Tests for PatternEngine - Pattern Detection Engine

TDD Red Phase: These tests define the expected behavior of the pattern
detection engine before implementation exists.
"""

from datetime import datetime, timedelta

import pytest
from arkham_shard_patterns.engine import PatternEngine


class TestPatternEngineInit:
    """Test engine instantiation."""

    def test_engine_creates(self):
        engine = PatternEngine()
        assert engine is not None

    def test_engine_has_detection_methods(self):
        engine = PatternEngine()
        assert hasattr(engine, "detect_ngram_patterns")
        assert hasattr(engine, "detect_temporal_clusters")
        assert hasattr(engine, "detect_behavioral_patterns")


class TestNgramDetection:
    """Test n-gram frequency analysis across documents."""

    def setup_method(self):
        self.engine = PatternEngine()

    def test_detects_repeated_bigram_across_docs(self):
        docs = [
            "The claimant raised a grievance about unfair treatment in the workplace.",
            "After the grievance about unfair treatment was filed, management ignored it.",
            "No action was taken on the grievance about unfair treatment despite policy.",
        ]
        results = self.engine.detect_ngram_patterns(docs)
        phrases = [r["phrase"] for r in results]
        assert any("unfair treatment" in p for p in phrases)

    def test_detects_repeated_trigram(self):
        docs = [
            "The respondent failed to follow the disciplinary procedure correctly.",
            "Again the respondent failed to follow proper protocol.",
            "Once more the respondent failed to follow established guidelines.",
        ]
        results = self.engine.detect_ngram_patterns(docs)
        phrases = [r["phrase"] for r in results]
        assert any("failed to follow" in p for p in phrases)

    def test_scores_by_frequency_and_spread(self):
        docs = [
            "The policy was ignored. The policy was ignored again.",
            "The policy was ignored by management.",
            "Different text with no overlap at all.",
        ]
        results = self.engine.detect_ngram_patterns(docs)
        if results:
            top = results[0]
            assert "frequency" in top
            assert "significance" in top
            assert top["frequency"] >= 2
            assert 0.0 < top["significance"] <= 1.0

    def test_returns_empty_for_no_overlap(self):
        docs = [
            "Alpha bravo charlie.",
            "Delta echo foxtrot.",
            "Golf hotel india.",
        ]
        results = self.engine.detect_ngram_patterns(docs)
        assert results == []

    def test_single_document_finds_internal_repeats(self):
        docs = [
            "The manager denied the request. Later the manager denied another request. "
            "The manager denied a third request."
        ]
        results = self.engine.detect_ngram_patterns(docs)
        phrases = [r["phrase"] for r in results]
        assert any("manager denied" in p for p in phrases)

    def test_filters_stopword_only_ngrams(self):
        docs = [
            "This is a test of the system for the purpose of testing.",
            "This is a test that should work for the purpose of validation.",
        ]
        results = self.engine.detect_ngram_patterns(docs)
        # Should not return pure stopword phrases like "this is a" or "of the"
        for r in results:
            words = r["phrase"].split()
            # At least one content word required
            stopwords = {"the", "a", "an", "is", "of", "for", "in", "to", "and", "this", "that"}
            content_words = [w for w in words if w.lower() not in stopwords]
            assert len(content_words) > 0

    def test_min_occurrences_parameter(self):
        docs = [
            "The breach of contract was clear.",
            "Another breach of contract occurred.",
        ]
        # With min_occurrences=3, two occurrences should not be enough
        results = self.engine.detect_ngram_patterns(docs, min_occurrences=3)
        assert results == []

        # With min_occurrences=2, should find it
        results = self.engine.detect_ngram_patterns(docs, min_occurrences=2)
        assert len(results) > 0


class TestTemporalClustering:
    """Test temporal cluster detection."""

    def setup_method(self):
        self.engine = PatternEngine()

    def test_detects_cluster_of_events(self):
        base = datetime(2025, 6, 1, 9, 0)
        events = [
            {"timestamp": base, "description": "Email sent"},
            {"timestamp": base + timedelta(hours=1), "description": "Meeting held"},
            {"timestamp": base + timedelta(hours=2), "description": "Document filed"},
            {"timestamp": base + timedelta(hours=3), "description": "Call made"},
            # Gap
            {"timestamp": base + timedelta(days=30), "description": "Review scheduled"},
        ]
        clusters = self.engine.detect_temporal_clusters(events)
        assert len(clusters) >= 1
        # The first cluster should contain the 4 close events
        assert clusters[0]["event_count"] >= 4

    def test_no_cluster_when_evenly_spaced(self):
        base = datetime(2025, 1, 1)
        events = [{"timestamp": base + timedelta(days=i * 30), "description": f"Event {i}"} for i in range(6)]
        clusters = self.engine.detect_temporal_clusters(events, window_hours=24)
        # Evenly spaced monthly events should not cluster
        assert all(c["event_count"] < 3 for c in clusters) if clusters else True

    def test_multiple_clusters(self):
        base = datetime(2025, 1, 1)
        events = [
            # Cluster 1
            {"timestamp": base, "description": "A1"},
            {"timestamp": base + timedelta(hours=1), "description": "A2"},
            {"timestamp": base + timedelta(hours=2), "description": "A3"},
            # Gap
            # Cluster 2
            {"timestamp": base + timedelta(days=60), "description": "B1"},
            {"timestamp": base + timedelta(days=60, hours=1), "description": "B2"},
            {"timestamp": base + timedelta(days=60, hours=2), "description": "B3"},
        ]
        clusters = self.engine.detect_temporal_clusters(events, window_hours=24)
        assert len(clusters) >= 2

    def test_cluster_includes_significance_score(self):
        base = datetime(2025, 3, 1)
        events = [{"timestamp": base + timedelta(hours=i), "description": f"Event {i}"} for i in range(10)]
        clusters = self.engine.detect_temporal_clusters(events)
        assert len(clusters) >= 1
        assert "significance" in clusters[0]
        assert 0.0 < clusters[0]["significance"] <= 1.0

    def test_empty_events_returns_empty(self):
        clusters = self.engine.detect_temporal_clusters([])
        assert clusters == []

    def test_configurable_window(self):
        base = datetime(2025, 6, 1)
        events = [
            {"timestamp": base, "description": "E1"},
            {"timestamp": base + timedelta(hours=6), "description": "E2"},
            {"timestamp": base + timedelta(hours=12), "description": "E3"},
        ]
        # With 4-hour window, these should NOT cluster together
        clusters_tight = self.engine.detect_temporal_clusters(events, window_hours=4)
        # With 24-hour window, they should
        clusters_wide = self.engine.detect_temporal_clusters(events, window_hours=24)

        tight_max = max((c["event_count"] for c in clusters_tight), default=0)
        wide_max = max((c["event_count"] for c in clusters_wide), default=0)
        assert wide_max >= tight_max


class TestBehavioralPatterns:
    """Test behavioral pattern detection (escalation, avoidance, coordination)."""

    def setup_method(self):
        self.engine = PatternEngine()

    def test_detects_escalation(self):
        base = datetime(2025, 1, 1)
        events = [
            {"timestamp": base, "description": "Verbal warning issued", "severity": 1},
            {"timestamp": base + timedelta(days=7), "description": "Written warning issued", "severity": 2},
            {"timestamp": base + timedelta(days=14), "description": "Final warning issued", "severity": 3},
            {"timestamp": base + timedelta(days=21), "description": "Dismissal", "severity": 4},
        ]
        patterns = self.engine.detect_behavioral_patterns(events)
        escalation = [p for p in patterns if p["pattern_subtype"] == "escalation"]
        assert len(escalation) >= 1
        assert escalation[0]["significance"] > 0.5

    def test_detects_avoidance(self):
        base = datetime(2025, 1, 1)
        events = [
            {"timestamp": base, "description": "Grievance filed", "entity": "claimant", "requires_response": True},
            # 30 days pass with no response
            {
                "timestamp": base + timedelta(days=30),
                "description": "Reminder sent",
                "entity": "claimant",
                "requires_response": True,
            },
            # Another 30 days pass with no response
            {
                "timestamp": base + timedelta(days=60),
                "description": "Escalation",
                "entity": "claimant",
                "requires_response": False,
            },
        ]
        patterns = self.engine.detect_behavioral_patterns(events)
        avoidance = [p for p in patterns if p["pattern_subtype"] == "avoidance"]
        assert len(avoidance) >= 1

    def test_detects_coordination(self):
        base = datetime(2025, 3, 1)
        events = [
            {"timestamp": base, "description": "Manager A action", "entity": "manager_a"},
            {"timestamp": base + timedelta(hours=1), "description": "Manager B action", "entity": "manager_b"},
            {"timestamp": base + timedelta(days=7), "description": "Manager A action", "entity": "manager_a"},
            {"timestamp": base + timedelta(days=7, hours=2), "description": "Manager B action", "entity": "manager_b"},
            {"timestamp": base + timedelta(days=14), "description": "Manager A action", "entity": "manager_a"},
            {"timestamp": base + timedelta(days=14, hours=1), "description": "Manager B action", "entity": "manager_b"},
        ]
        patterns = self.engine.detect_behavioral_patterns(events)
        coordination = [p for p in patterns if p["pattern_subtype"] == "coordination"]
        assert len(coordination) >= 1

    def test_no_patterns_from_random_events(self):
        import random

        random.seed(42)
        base = datetime(2025, 1, 1)
        events = [
            {
                "timestamp": base + timedelta(days=random.randint(0, 365)),
                "description": f"Random event {i}",
                "severity": random.randint(1, 5),
                "entity": f"entity_{random.randint(1, 10)}",
            }
            for i in range(5)
        ]
        patterns = self.engine.detect_behavioral_patterns(events)
        # Random events should produce few or no strong patterns
        strong = [p for p in patterns if p["significance"] > 0.7]
        assert len(strong) == 0

    def test_all_patterns_have_required_fields(self):
        base = datetime(2025, 1, 1)
        events = [
            {"timestamp": base, "description": "Warning 1", "severity": 1},
            {"timestamp": base + timedelta(days=7), "description": "Warning 2", "severity": 3},
            {"timestamp": base + timedelta(days=14), "description": "Warning 3", "severity": 5},
        ]
        patterns = self.engine.detect_behavioral_patterns(events)
        for p in patterns:
            assert "pattern_subtype" in p
            assert "description" in p
            assert "significance" in p
            assert "frequency" in p

    def test_empty_events_returns_empty(self):
        patterns = self.engine.detect_behavioral_patterns([])
        assert patterns == []


class TestScoring:
    """Test pattern scoring."""

    def setup_method(self):
        self.engine = PatternEngine()

    def test_score_increases_with_frequency(self):
        s1 = self.engine.score_pattern(frequency=2, doc_spread=2, total_docs=10)
        s2 = self.engine.score_pattern(frequency=8, doc_spread=2, total_docs=10)
        assert s2 > s1

    def test_score_increases_with_spread(self):
        s1 = self.engine.score_pattern(frequency=5, doc_spread=1, total_docs=10)
        s2 = self.engine.score_pattern(frequency=5, doc_spread=5, total_docs=10)
        assert s2 > s1

    def test_score_bounded_zero_to_one(self):
        s = self.engine.score_pattern(frequency=100, doc_spread=100, total_docs=100)
        assert 0.0 <= s <= 1.0
        s = self.engine.score_pattern(frequency=1, doc_spread=1, total_docs=1000)
        assert 0.0 <= s <= 1.0

    def test_score_zero_frequency_is_zero(self):
        s = self.engine.score_pattern(frequency=0, doc_spread=0, total_docs=10)
        assert s == 0.0
